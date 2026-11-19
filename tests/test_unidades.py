from datetime import datetime, timedelta, timezone

import pytest

from app.classifier import ImagemInvalida, classificar_imagem, classificar_lux
from app.config import load_settings
from app.geo import arredondar_coord, haversine_m
from app.priority import calcular_prioridade

from .conftest import foto


def test_haversine_ordem_de_grandeza():
    # 0,001 grau de latitude ~ 111 m
    assert 105 < haversine_m(-23.53, -46.78, -23.531, -46.78) < 116


def test_arredondamento_lgpd():
    assert arredondar_coord(-23.532512345) == -23.5325


@pytest.mark.parametrize("brilho,esperado", [(3, "inexistente"), (40, "fraca"), (180, "adequada")])
def test_classificador(brilho, esperado):
    assert classificar_imagem(foto(brilho)).classificacao == esperado


def test_classificador_aceita_png():
    assert classificar_imagem(foto(3, fmt="PNG")).classificacao == "inexistente"


def test_classificador_rejeita_lixo():
    with pytest.raises(ImagemInvalida):
        classificar_imagem(b"nao sou imagem")


@pytest.mark.parametrize("lux,esperado", [(0, "inexistente"), (10, "fraca"), (30, "adequada")])
def test_classificar_lux(lux, esperado):
    assert classificar_lux(lux) == esperado


def test_prioridade_explicavel_e_limitada():
    criado = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    p, motivos = calcular_prioridade(
        classificacao="inexistente", qtd_relatos=10, dist_parada_m=10,
        fluxo_parada="alto", ldr_veredito="confirmado", criado_em=criado,
    )
    assert p == 100.0  # teto
    assert len(motivos) == 5


def test_prioridade_contestada_cai():
    agora = datetime.now(timezone.utc).isoformat()
    normal, _ = calcular_prioridade(classificacao="fraca", qtd_relatos=1, dist_parada_m=None,
                                    fluxo_parada=None, ldr_veredito=None, criado_em=agora)
    contest, _ = calcular_prioridade(classificacao="fraca", qtd_relatos=1, dist_parada_m=None,
                                     fluxo_parada=None, ldr_veredito="contestado", criado_em=agora)
    assert contest < normal


def test_producao_sem_segredo_nao_sobe(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        load_settings()


def test_ip_cliente_remove_porta_do_app_service():
    from types import SimpleNamespace

    from app.security import ip_cliente

    assert ip_cliente(SimpleNamespace(client=SimpleNamespace(host="177.10.20.30:51234"))) == "177.10.20.30"
    assert ip_cliente(SimpleNamespace(client=SimpleNamespace(host="2804:14c::1"))) == "2804:14c::1"
    assert ip_cliente(SimpleNamespace(client=None)) == "desconhecido"
