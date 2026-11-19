import io

import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN = "admin-token-de-teste-com-32-caracteres!"
DEVICE = "device-token-de-teste-com-32-caracteres"
METRICS = "metrics-token-de-teste-com-32-caracter"

# Centro de Osasco, perto da parada P003
LAT, LON = -23.5325, -46.7841


def settings(**over) -> Settings:
    base = dict(
        env="test", db_path=":memory:", admin_token=ADMIN, device_token=DEVICE,
        metrics_token=METRICS, max_upload_bytes=3 * 1024 * 1024, rate_limit_per_min=100,
        dedup_radius_m=50.0, dedup_window_days=15,
        lat_min=-23.60, lat_max=-23.45, lon_min=-46.86, lon_max=-46.70,
    )
    base.update(over)
    return Settings(**base)


def foto(brilho: int, ruido: int = 0, fmt: str = "JPEG", tamanho=(320, 240)) -> bytes:
    img = Image.new("RGB", tamanho, (brilho, brilho, brilho))
    if ruido:  # retângulo cinza em posição variável: muda o hash sem mudar a classe
        x = (ruido * 37) % (tamanho[0] - 60)
        y = (ruido * 23) % (tamanho[1] - 60)
        img.paste((min(255, brilho + 60),) * 3, (x, y, x + 60, y + 60))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def client():
    with TestClient(create_app(settings())) as c:
        yield c


def enviar(client, conteudo: bytes, lat=LAT, lon=LON, nome="foto.jpg"):
    return client.post(
        "/api/v1/relatos",
        data={"lat": str(lat), "lon": str(lon)},
        files={"foto": (nome, conteudo, "image/jpeg")},
    )
