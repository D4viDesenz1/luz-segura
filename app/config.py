"""Configuração lida exclusivamente de variáveis de ambiente.

Nenhum segredo tem valor padrão no código: se o token não for definido,
o endpoint protegido fica FECHADO (fail closed), nunca aberto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    env: str
    db_path: str
    admin_token: str
    device_token: str
    metrics_token: str
    max_upload_bytes: int
    rate_limit_per_min: int
    dedup_radius_m: float
    dedup_window_days: int
    # Território do MVP (bounding box). Padrão: município de Osasco/SP, com folga.
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def load_settings() -> Settings:
    s = Settings(
        env=os.getenv("APP_ENV", "development"),
        db_path=os.getenv("DB_PATH", "./data/luzsegura.db"),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        device_token=os.getenv("DEVICE_TOKEN", ""),
        metrics_token=os.getenv("METRICS_TOKEN", ""),
        max_upload_bytes=_int("MAX_UPLOAD_BYTES", 3 * 1024 * 1024),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 10),
        dedup_radius_m=_float("DEDUP_RADIUS_M", 50.0),
        dedup_window_days=_int("DEDUP_WINDOW_DAYS", 15),
        lat_min=_float("TERRITORIO_LAT_MIN", -23.60),
        lat_max=_float("TERRITORIO_LAT_MAX", -23.45),
        lon_min=_float("TERRITORIO_LON_MIN", -46.86),
        lon_max=_float("TERRITORIO_LON_MAX", -46.70),
    )
    if s.is_production:
        faltando = [
            n
            for n, v in (
                ("ADMIN_TOKEN", s.admin_token),
                ("DEVICE_TOKEN", s.device_token),
                ("METRICS_TOKEN", s.metrics_token),
            )
            if len(v) < 24
        ]
        if faltando:
            raise RuntimeError(
                "Em produção estes segredos são obrigatórios (mín. 24 caracteres): "
                + ", ".join(faltando)
            )
    return s
