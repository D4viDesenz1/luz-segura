"""API do Luz Segura.

Fluxo: cidadão envia foto noturna + localização -> IA classifica a iluminação
-> deduplicação por raio -> chamado priorizado e explicável -> estação LDR
confirma ou contesta -> equipe de manutenção atualiza o status.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, metrics
from .classifier import ImagemInvalida, classificar_imagem, classificar_lux
from .config import Settings, load_settings
from .db import Database, agora_iso
from .geo import arredondar_coord, carregar_paradas, parada_mais_proxima
from .priority import calcular_prioridade
from .security import ObservabilityMiddleware, RateLimiter, bearer, ip_cliente, token_valido

STATIC_DIR = Path(__file__).parent / "static"
ORDEM_SEVERIDADE = {"adequada": 0, "fraca": 1, "inexistente": 2}
STATUS_VALIDOS = ("aberto", "em_manutencao", "resolvido", "contestado")
log = logging.getLogger("luzsegura")


# ---------------------------------------------------------------- modelos
class LeituraLDR(BaseModel):
    estacao_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    lux: float = Field(ge=0, le=200_000)


class AtualizacaoStatus(BaseModel):
    status: str = Field(pattern=r"^(aberto|em_manutencao|resolvido|contestado)$")


# ---------------------------------------------------------------- helpers
def _erro(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"erro": msg}, status_code=status)


def _no_territorio(s: Settings, lat: float, lon: float) -> bool:
    return s.lat_min <= lat <= s.lat_max and s.lon_min <= lon <= s.lon_max


def _recalcular(db: Database, chamado: dict) -> tuple[float, list[str]]:
    prioridade, motivos = calcular_prioridade(
        classificacao=chamado["classificacao"],
        qtd_relatos=chamado["qtd_relatos"],
        dist_parada_m=chamado["dist_parada_m"],
        fluxo_parada=chamado["parada_fluxo"],
        ldr_veredito=chamado["ldr_veredito"],
        criado_em=chamado["criado_em"],
    )
    db.atualizar_chamado(chamado["id"], {"prioridade": prioridade})
    return prioridade, motivos


def _publico(chamado: dict, motivos: list[str] | None = None) -> dict:
    out = {
        "id": chamado["id"],
        "status": chamado["status"],
        "classificacao": chamado["classificacao"],
        "prioridade": chamado["prioridade"],
        "qtd_relatos": chamado["qtd_relatos"],
        "localizacao": {"lat": chamado["lat"], "lon": chamado["lon"]},
        "parada_proxima": (
            {"nome": chamado["parada_nome"], "distancia_m": round(chamado["dist_parada_m"])}
            if chamado["parada_nome"] else None
        ),
        "validacao_ldr": (
            {"lux": chamado["ldr_lux"], "veredito": chamado["ldr_veredito"]}
            if chamado["ldr_veredito"] else None
        ),
        "criado_em": chamado["criado_em"],
        "atualizado_em": chamado["atualizado_em"],
    }
    if motivos is not None:
        out["explicacao_prioridade"] = motivos
    return out


# ---------------------------------------------------------------- app
def create_app(settings: Settings | None = None) -> Starlette:
    s = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Database(s.db_path)
    limiter = RateLimiter(s.rate_limit_per_min)

    async def index(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    async def health(request: Request) -> Response:
        try:
            ok = await run_in_threadpool(db.ping)
        except Exception:  # noqa: BLE001 - health nunca vaza detalhe
            ok = False
        body = {"status": "ok" if ok else "degradado", "versao": __version__}
        return JSONResponse(body, status_code=200 if ok else 503)

    async def metrics_endpoint(request: Request) -> Response:
        # Em produção /metrics exige token (Prometheus usa bearer_token).
        if s.is_production or s.metrics_token:
            if not token_valido(bearer(request), s.metrics_token):
                return _erro(401, "não autorizado")
        ativos = (await run_in_threadpool(db.estatisticas))["chamados_ativos"]
        return PlainTextResponse(metrics.render(ativos), media_type="text/plain; version=0.0.4")

    async def criar_relato(request: Request) -> Response:
        if not limiter.permitir(ip_cliente(request)):
            metrics.contar("luzsegura_relatos_rejeitados_total", "rate_limit")
            return _erro(429, "Muitos envios em sequência. Tente de novo em 1 minuto.")

        tamanho = request.headers.get("content-length")
        if tamanho and tamanho.isdigit() and int(tamanho) > s.max_upload_bytes + 64_000:
            return _erro(413, "Foto muito grande. Envie até 3 MB.")

        form = await request.form(max_files=1, max_fields=4, max_part_size=1024)
        try:
            lat = float(form.get("lat", ""))
            lon = float(form.get("lon", ""))
        except (TypeError, ValueError):
            return _erro(422, "Informe 'lat' e 'lon' numéricos.")
        if not _no_territorio(s, lat, lon):
            metrics.contar("luzsegura_relatos_rejeitados_total", "fora_territorio")
            return _erro(422, "Localização fora do território atendido pelo piloto (Osasco/SP).")

        foto = form.get("foto")
        if foto is None or isinstance(foto, str):
            return _erro(422, "Envie a foto no campo 'foto'.")
        conteudo = await foto.read(s.max_upload_bytes + 1)
        await form.close()
        if len(conteudo) > s.max_upload_bytes:
            return _erro(413, "Foto muito grande. Envie até 3 MB.")

        try:
            res = await run_in_threadpool(classificar_imagem, conteudo)
        except ImagemInvalida as exc:
            metrics.contar("luzsegura_relatos_rejeitados_total", "imagem_invalida")
            return _erro(422, str(exc))
        finally:
            del conteudo  # a foto não é guardada em lugar nenhum

        lat_r, lon_r = arredondar_coord(lat), arredondar_coord(lon)
        if db.relato_duplicado(res.ahash, lat_r, lon_r, s.dedup_radius_m, 1):
            metrics.contar("luzsegura_relatos_rejeitados_total", "foto_duplicada")
            return _erro(409, "Esta mesma foto já foi enviada para este local.")

        metrics.contar("luzsegura_relatos_total", res.classificacao)
        agora = agora_iso()
        relato = {
            "chamado_id": None, "lat": lat_r, "lon": lon_r,
            "classificacao": res.classificacao, "luminancia": res.luminancia_media,
            "confianca": res.confianca, "modelo": res.modelo, "ahash": res.ahash,
            "criado_em": agora,
        }
        analise = {
            "classificacao": res.classificacao,
            "confianca": res.confianca,
            "luminancia_media": res.luminancia_media,
            "modelo": res.modelo,
        }

        if res.classificacao == "adequada":
            db.inserir_relato(relato)
            return JSONResponse({
                "mensagem": "A foto indica iluminação adequada, então nenhum chamado foi aberto. "
                            "Se o local estiver escuro, tente outra foto sem flash.",
                "analise_ia": analise,
            }, status_code=200)

        existente = db.chamado_ativo_proximo(lat_r, lon_r, s.dedup_radius_m)
        if existente:
            pior = max(existente["classificacao"], res.classificacao, key=ORDEM_SEVERIDADE.get)
            db.atualizar_chamado(existente["id"], {
                "qtd_relatos": existente["qtd_relatos"] + 1, "classificacao": pior,
            })
            chamado_id, novo = existente["id"], False
        else:
            parada, dist = parada_mais_proxima(lat_r, lon_r)
            chamado_id = db.inserir_chamado({
                "lat": lat_r, "lon": lon_r, "status": "aberto",
                "classificacao": res.classificacao, "qtd_relatos": 1, "prioridade": 0,
                "parada_id": parada["id"] if parada else None,
                "parada_nome": parada["nome"] if parada else None,
                "parada_fluxo": parada["fluxo_noturno"] if parada else None,
                "dist_parada_m": round(dist, 1) if dist is not None else None,
                "criado_em": agora, "atualizado_em": agora,
            })
            novo = True

        relato["chamado_id"] = chamado_id
        db.inserir_relato(relato)
        chamado = db.obter_chamado(chamado_id)
        _, motivos = _recalcular(db, chamado)
        chamado = db.obter_chamado(chamado_id)
        return JSONResponse({
            "mensagem": "Chamado aberto." if novo else "Relato agrupado a um chamado já existente.",
            "chamado_novo": novo,
            "analise_ia": analise,
            "chamado": _publico(chamado, motivos),
        }, status_code=201 if novo else 200)

    async def listar_chamados(request: Request) -> Response:
        status = request.query_params.get("status")
        if status and status not in STATUS_VALIDOS:
            return _erro(422, f"status deve ser um de {list(STATUS_VALIDOS)}")
        try:
            limite = min(200, max(1, int(request.query_params.get("limite", "50"))))
        except ValueError:
            return _erro(422, "limite deve ser inteiro")
        rows = await run_in_threadpool(db.listar_chamados, status, limite)
        return JSONResponse({"total": len(rows), "chamados": [_publico(r) for r in rows]})

    async def detalhar_chamado(request: Request) -> Response:
        chamado = db.obter_chamado(request.path_params["chamado_id"])
        if not chamado:
            return _erro(404, "Chamado não encontrado.")
        _, motivos = calcular_prioridade(
            classificacao=chamado["classificacao"], qtd_relatos=chamado["qtd_relatos"],
            dist_parada_m=chamado["dist_parada_m"], fluxo_parada=chamado["parada_fluxo"],
            ldr_veredito=chamado["ldr_veredito"], criado_em=chamado["criado_em"],
        )
        return JSONResponse(_publico(chamado, motivos))

    async def atualizar_status(request: Request) -> Response:
        if not token_valido(bearer(request), s.admin_token):
            return _erro(401, "não autorizado")
        try:
            dados = AtualizacaoStatus.model_validate(await request.json())
        except (ValidationError, ValueError):
            return _erro(422, f"Envie {{\"status\": ...}} com um de {list(STATUS_VALIDOS)}")
        cid = request.path_params["chamado_id"]
        chamado = db.obter_chamado(cid)
        if not chamado:
            return _erro(404, "Chamado não encontrado.")
        campos: dict = {"status": dados.status}
        campos["resolvido_em"] = agora_iso() if dados.status == "resolvido" else None
        db.atualizar_chamado(cid, campos)
        log.info('{"evento": "status_alterado", "chamado_id": %d, "status": "%s"}', cid, dados.status)
        return JSONResponse(_publico(db.obter_chamado(cid)))

    async def receber_leitura(request: Request) -> Response:
        if not token_valido(request.headers.get("x-device-token"), s.device_token):
            return _erro(401, "dispositivo não autorizado")
        try:
            leitura = LeituraLDR.model_validate(await request.json())
        except (ValidationError, ValueError):
            return _erro(422, "Leitura inválida: estacao_id, lat, lon e lux são obrigatórios.")

        classe = classificar_lux(leitura.lux)
        lat_r, lon_r = arredondar_coord(leitura.lat), arredondar_coord(leitura.lon)
        chamado = db.chamado_ativo_proximo(lat_r, lon_r, s.dedup_radius_m)
        veredito = None
        if chamado:
            veredito = "contestado" if classe == "adequada" else "confirmado"
            campos = {"ldr_lux": leitura.lux, "ldr_veredito": veredito}
            if veredito == "contestado" and chamado["status"] == "aberto":
                campos["status"] = "contestado"
            elif veredito == "confirmado" and chamado["status"] == "contestado":
                campos["status"] = "aberto"
            db.atualizar_chamado(chamado["id"], campos)
            _recalcular(db, db.obter_chamado(chamado["id"]))
        metrics.contar("luzsegura_leituras_ldr_total", veredito or "sem_chamado")
        db.inserir_leitura({
            "estacao_id": leitura.estacao_id, "lat": lat_r, "lon": lon_r, "lux": leitura.lux,
            "classificacao": classe, "chamado_id": chamado["id"] if chamado else None,
            "criado_em": agora_iso(),
        })
        return JSONResponse({
            "classificacao_ldr": classe,
            "chamado_id": chamado["id"] if chamado else None,
            "veredito": veredito,
        }, status_code=201)

    async def paradas(request: Request) -> Response:
        return JSONResponse({"paradas": carregar_paradas()})

    async def estatisticas(request: Request) -> Response:
        return JSONResponse(await run_in_threadpool(db.estatisticas))

    async def http_error(request: Request, exc: HTTPException) -> Response:
        return _erro(exc.status_code, exc.detail if isinstance(exc.detail, str) else "erro")

    async def server_error(request: Request, exc: Exception) -> Response:
        log.exception("erro_nao_tratado")  # detalhe vai para o log, nunca para o cliente
        return _erro(500, "Erro interno. Tente novamente.")

    routes = [
        Route("/", index),
        Route("/health", health),
        Route("/metrics", metrics_endpoint),
        Route("/api/v1/relatos", criar_relato, methods=["POST"]),
        Route("/api/v1/chamados", listar_chamados),
        Route("/api/v1/chamados/{chamado_id:int}", detalhar_chamado),
        Route("/api/v1/chamados/{chamado_id:int}", atualizar_status, methods=["PATCH"]),
        Route("/api/v1/leituras-ldr", receber_leitura, methods=["POST"]),
        Route("/api/v1/paradas", paradas),
        Route("/api/v1/estatisticas", estatisticas),
        Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    app = Starlette(
        routes=routes,
        middleware=[Middleware(ObservabilityMiddleware)],
        exception_handlers={HTTPException: http_error, Exception: server_error},
        max_body_size=s.max_upload_bytes + 64_000,
    )
    app.state.db = db
    app.state.settings = s
    return app

