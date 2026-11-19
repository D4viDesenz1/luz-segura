from starlette.testclient import TestClient

from app.main import create_app

from .conftest import ADMIN, DEVICE, LAT, LON, METRICS, enviar, foto, settings


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_headers_de_seguranca(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "x-request-id" in r.headers


def test_pagina_inicial(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Luz Segura" in r.text


def test_relato_escuro_abre_chamado_com_explicacao(client):
    r = enviar(client, foto(5))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["chamado_novo"] is True
    assert j["analise_ia"]["classificacao"] == "inexistente"
    assert j["chamado"]["prioridade"] > 50  # severidade + parada próxima
    assert any("parada de ônibus" in m for m in j["chamado"]["explicacao_prioridade"])


def test_relato_iluminado_nao_abre_chamado(client):
    r = enviar(client, foto(200))
    assert r.status_code == 200
    assert "chamado" not in r.json()
    assert client.get("/api/v1/chamados").json()["total"] == 0


def test_deduplicacao_agrupa_relatos_proximos(client):
    r1 = enviar(client, foto(5, ruido=3))
    r2 = enviar(client, foto(40, ruido=17), lat=LAT + 0.0002)  # ~22 m de distância
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json()["chamado_novo"] is False
    c = client.get("/api/v1/chamados").json()
    assert c["total"] == 1
    assert c["chamados"][0]["qtd_relatos"] == 2
    assert c["chamados"][0]["classificacao"] == "inexistente"  # mantém a pior


def test_mesma_foto_duas_vezes_rejeitada(client):
    conteudo = foto(5)
    assert enviar(client, conteudo).status_code == 201
    assert enviar(client, conteudo).status_code == 409


def test_fora_do_territorio(client):
    r = enviar(client, foto(5), lat=-22.9, lon=-43.2)  # Rio de Janeiro
    assert r.status_code == 422


def test_arquivo_que_nao_e_imagem(client):
    r = enviar(client, b"<?php system($_GET['c']); ?>", nome="shell.jpg")
    assert r.status_code == 422


def test_coordenada_invalida(client):
    r = client.post("/api/v1/relatos", data={"lat": "abc", "lon": "1"},
                    files={"foto": ("f.jpg", foto(5), "image/jpeg")})
    assert r.status_code == 422


def test_upload_grande_rejeitado():
    with TestClient(create_app(settings(max_upload_bytes=1000))) as c:
        r = enviar(c, foto(5, tamanho=(800, 600)))
        assert r.status_code == 413


def test_rate_limit():
    with TestClient(create_app(settings(rate_limit_per_min=2))) as c:
        codes = [enviar(c, foto(5, ruido=i + 2), lon=-46.80 + i * 0.01).status_code for i in range(3)]
        assert codes[-1] == 429


def test_ldr_confirma_relato(client):
    cid = enviar(client, foto(30)).json()["chamado"]["id"]
    r = client.post("/api/v1/leituras-ldr", headers={"x-device-token": DEVICE},
                    json={"estacao_id": "est-01", "lat": LAT, "lon": LON, "lux": 2.0})
    assert r.status_code == 201
    assert r.json()["veredito"] == "confirmado"
    d = client.get(f"/api/v1/chamados/{cid}").json()
    assert d["validacao_ldr"]["veredito"] == "confirmado"
    assert any("LDR confirmou" in m for m in d["explicacao_prioridade"])


def test_ldr_contesta_relato(client):
    cid = enviar(client, foto(30)).json()["chamado"]["id"]
    r = client.post("/api/v1/leituras-ldr", headers={"x-device-token": DEVICE},
                    json={"estacao_id": "est-01", "lat": LAT, "lon": LON, "lux": 80})
    assert r.json()["veredito"] == "contestado"
    assert client.get(f"/api/v1/chamados/{cid}").json()["status"] == "contestado"


def test_ldr_sem_token(client):
    r = client.post("/api/v1/leituras-ldr", json={"estacao_id": "x", "lat": LAT, "lon": LON, "lux": 1})
    assert r.status_code == 401


def test_ldr_payload_invalido(client):
    r = client.post("/api/v1/leituras-ldr", headers={"x-device-token": DEVICE},
                    json={"estacao_id": "'; DROP TABLE chamados;--", "lat": LAT, "lon": LON, "lux": 1})
    assert r.status_code == 422


def test_manutencao_resolve_chamado(client):
    cid = enviar(client, foto(5)).json()["chamado"]["id"]
    r = client.patch(f"/api/v1/chamados/{cid}", json={"status": "resolvido"},
                     headers={"authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolvido"
    st = client.get("/api/v1/estatisticas").json()
    assert st["tempo_medio_relato_ate_conserto_h"] is not None


def test_patch_sem_token_e_token_errado(client):
    cid = enviar(client, foto(5)).json()["chamado"]["id"]
    assert client.patch(f"/api/v1/chamados/{cid}", json={"status": "resolvido"}).status_code == 401
    r = client.patch(f"/api/v1/chamados/{cid}", json={"status": "resolvido"},
                     headers={"authorization": "Bearer errado"})
    assert r.status_code == 401


def test_patch_status_invalido(client):
    cid = enviar(client, foto(5)).json()["chamado"]["id"]
    r = client.patch(f"/api/v1/chamados/{cid}", json={"status": "apagado"},
                     headers={"authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 422


def test_token_vazio_nunca_autoriza():
    with TestClient(create_app(settings(admin_token=""))) as c:
        r = c.patch("/api/v1/chamados/1", json={"status": "resolvido"},
                    headers={"authorization": "Bearer "})
        assert r.status_code == 401


def test_metrics_exige_token(client):
    assert client.get("/metrics").status_code == 401
    r = client.get("/metrics", headers={"authorization": f"Bearer {METRICS}"})
    assert r.status_code == 200
    assert "http_requests_total" in r.text
    assert "http_request_duration_seconds_bucket" in r.text
    assert "luzsegura_chamados_ativos" in r.text


def test_rota_inexistente_nao_vaza_detalhe(client):
    r = client.get("/admin/../../etc/passwd")
    assert r.status_code == 404
    assert "erro" in r.json()


def test_listagem_ordenada_por_prioridade(client):
    enviar(client, foto(45), lat=-23.5000, lon=-46.8300)   # fraca, longe de parada
    enviar(client, foto(3), lat=LAT, lon=LON)               # inexistente, perto de parada
    c = client.get("/api/v1/chamados").json()["chamados"]
    assert c[0]["prioridade"] >= c[1]["prioridade"]
    assert c[0]["classificacao"] == "inexistente"


def test_status_filtro_invalido(client):
    assert client.get("/api/v1/chamados?status=xpto").status_code == 422
