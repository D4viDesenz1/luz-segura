"""Controles de segurança da API (camada de aplicação)."""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from starlette.requests import Request
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import metrics

log = logging.getLogger("luzsegura")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "geolocation=(self), camera=(self), microphone=()",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
    "cache-control": "no-store",
}


def token_valido(recebido: str | None, esperado: str) -> bool:
    """Comparação em tempo constante. Token esperado vazio = sempre nega."""
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(recebido.encode(), esperado.encode())


def bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def ip_cliente(request: Request) -> str:
    """IP real do cliente. O uvicorn roda com --proxy-headers atrás do App Service.

    O front-end do App Service manda o X-Forwarded-For no formato "ip:porta". Removemos
    a porta para o rate limit não tratar cada conexão como um cliente diferente.
    """
    host = request.client.host if request.client else "desconhecido"
    if host.count(":") == 1:  # IPv4 com porta. IPv6 tem vários ":" e fica como está.
        host = host.split(":", 1)[0]
    return host


class RateLimiter:
    """Janela deslizante em memória por IP. O IP NÃO é logado nem persistido (LGPD)."""

    def __init__(self, limite_por_min: int) -> None:
        self.limite = limite_por_min
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def permitir(self, chave: str) -> bool:
        agora = time.monotonic()
        with self._lock:
            fila = self._hits[chave]
            while fila and agora - fila[0] > 60:
                fila.popleft()
            if len(fila) >= self.limite:
                return False
            fila.append(agora)
            if len(self._hits) > 10_000:  # evita crescer sem limite
                self._hits.clear()
            return True


class ObservabilityMiddleware:
    """ASGI puro: request-id, headers de segurança, métricas e log JSON."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _rota(self, scope: Scope) -> str:
        app = scope.get("app")
        for route in getattr(app, "routes", []):
            match, _ = route.matches(scope)
            if match in (Match.FULL, Match.PARTIAL):  # PARTIAL = rota certa, método errado (405)
                return getattr(route, "path", "outro")
        return "nao_encontrada"  # evita explosão de cardinalidade com URLs aleatórias

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        req_id = uuid.uuid4().hex[:16]
        rota = self._rota(scope)  # antes de chamar o app: o roteador altera o scope
        inicio = time.perf_counter()
        status = {"code": 500}
        metrics.inicio_requisicao()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", []))
                existentes = {k.decode().lower() for k, _ in headers}
                for k, v in SECURITY_HEADERS.items():
                    if k not in existentes:
                        headers.append((k.encode(), v.encode()))
                headers.append((b"x-request-id", req_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dur = time.perf_counter() - inicio
            metrics.fim_requisicao(scope["method"], rota, status["code"], dur)
            if rota not in ("/health", "/metrics"):
                log.info(json.dumps({
                    "evento": "http",
                    "request_id": req_id,
                    "metodo": scope["method"],
                    "rota": rota,
                    "status": status["code"],
                    "duracao_ms": round(dur * 1000, 1),
                }))
