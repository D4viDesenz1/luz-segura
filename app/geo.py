"""Funções geográficas e base de paradas de ônibus do território."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

RAIO_TERRA_M = 6_371_000.0
_PARADAS_PATH = Path(__file__).parent / "data" / "paradas_osasco.json"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre dois pontos (lat/lon em graus)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(a))


def arredondar_coord(valor: float) -> float:
    """Minimização de dados (LGPD): 4 casas decimais ~ 11 m de precisão.

    Suficiente para a equipe de manutenção achar o poste, sem guardar a
    posição exata de quem enviou o relato.
    """
    return round(valor, 4)


@lru_cache(maxsize=1)
def carregar_paradas() -> list[dict]:
    with _PARADAS_PATH.open(encoding="utf-8") as f:
        return json.load(f)["paradas"]


def parada_mais_proxima(lat: float, lon: float) -> tuple[dict | None, float | None]:
    melhor, melhor_d = None, None
    for p in carregar_paradas():
        d = haversine_m(lat, lon, p["lat"], p["lon"])
        if melhor_d is None or d < melhor_d:
            melhor, melhor_d = p, d
    return melhor, melhor_d
