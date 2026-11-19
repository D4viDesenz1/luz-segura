"""Persistência em SQLite (arquivo único, sem servidor).

No App Service o arquivo fica em /home/data, que é armazenamento persistente
do plano. Todas as consultas usam parâmetros (?), nunca concatenação de texto.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .geo import haversine_m

SCHEMA = """
CREATE TABLE IF NOT EXISTS chamados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'aberto'
                    CHECK (status IN ('aberto','em_manutencao','resolvido','contestado')),
    classificacao   TEXT NOT NULL,
    qtd_relatos     INTEGER NOT NULL DEFAULT 1,
    prioridade      REAL NOT NULL DEFAULT 0,
    parada_id       TEXT,
    parada_nome     TEXT,
    parada_fluxo    TEXT,
    dist_parada_m   REAL,
    ldr_lux         REAL,
    ldr_veredito    TEXT,
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL,
    resolvido_em    TEXT
);
CREATE TABLE IF NOT EXISTS relatos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chamado_id      INTEGER REFERENCES chamados(id),
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    classificacao   TEXT NOT NULL,
    luminancia      REAL NOT NULL,
    confianca       REAL NOT NULL,
    modelo          TEXT NOT NULL,
    ahash           TEXT NOT NULL,
    criado_em       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leituras_ldr (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    estacao_id      TEXT NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    lux             REAL NOT NULL,
    classificacao   TEXT NOT NULL,
    chamado_id      INTEGER REFERENCES chamados(id),
    criado_em       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chamados_status ON chamados(status);
CREATE INDEX IF NOT EXISTS ix_relatos_criado ON relatos(criado_em);
"""

STATUS_ATIVOS = ("aberto", "em_manutencao", "contestado")
# Lista branca de colunas: só nomes definidos aqui podem entrar no SQL dinâmico.
COLUNAS_CHAMADO = frozenset({
    "lat", "lon", "status", "classificacao", "qtd_relatos", "prioridade", "parada_id",
    "parada_nome", "parada_fluxo", "dist_parada_m", "ldr_lux", "ldr_veredito",
    "criado_em", "atualizado_em", "resolvido_em",
})


def _validar_colunas(campos: dict) -> None:
    invalidas = set(campos) - COLUNAS_CHAMADO
    if invalidas:
        raise ValueError(f"colunas não permitidas: {sorted(invalidas)}")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Para testes com :memory: mantemos uma conexão única.
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) if path == ":memory:" else None
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        if self._mem is not None:
            self._mem.row_factory = sqlite3.Row
            yield self._mem
            self._mem.commit()
            return
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def ping(self) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1").fetchone()[0] == 1

    # ---------- consultas de apoio ----------
    def chamado_ativo_proximo(self, lat: float, lon: float, raio_m: float) -> dict | None:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM chamados WHERE status IN (?, ?, ?)", STATUS_ATIVOS
            ).fetchall()
        melhor, melhor_d = None, None
        for r in rows:
            d = haversine_m(lat, lon, r["lat"], r["lon"])
            if d <= raio_m and (melhor_d is None or d < melhor_d):
                melhor, melhor_d = dict(r), d
        return melhor

    def relato_duplicado(self, ahash: str, lat: float, lon: float, raio_m: float, dias: int) -> bool:
        limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
        with self.conn() as c:
            rows = c.execute(
                "SELECT lat, lon FROM relatos WHERE ahash = ? AND criado_em >= ?", (ahash, limite)
            ).fetchall()
        return any(haversine_m(lat, lon, r["lat"], r["lon"]) <= raio_m for r in rows)

    # ---------- escrita ----------
    def inserir_chamado(self, dados: dict) -> int:
        _validar_colunas(dados)
        cols = ", ".join(dados)
        ph = ", ".join("?" * len(dados))
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO chamados ({cols}) VALUES ({ph})", tuple(dados.values()))  # nosemgrep - colunas validadas por lista branca; valores parametrizados
            return int(cur.lastrowid)

    def atualizar_chamado(self, chamado_id: int, campos: dict) -> None:
        campos = {**campos, "atualizado_em": agora_iso()}
        _validar_colunas(campos)
        sets = ", ".join(f"{k} = ?" for k in campos)
        with self.conn() as c:
            c.execute(f"UPDATE chamados SET {sets} WHERE id = ?", (*campos.values(), chamado_id))  # nosemgrep - colunas validadas por lista branca; valores parametrizados

    def inserir_relato(self, dados: dict) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO relatos (chamado_id, lat, lon, classificacao, luminancia, confianca, modelo, ahash, criado_em)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    dados["chamado_id"], dados["lat"], dados["lon"], dados["classificacao"],
                    dados["luminancia"], dados["confianca"], dados["modelo"], dados["ahash"], dados["criado_em"],
                ),
            )
            return int(cur.lastrowid)

    def inserir_leitura(self, dados: dict) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO leituras_ldr (estacao_id, lat, lon, lux, classificacao, chamado_id, criado_em)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    dados["estacao_id"], dados["lat"], dados["lon"], dados["lux"],
                    dados["classificacao"], dados["chamado_id"], dados["criado_em"],
                ),
            )
            return int(cur.lastrowid)

    # ---------- leitura ----------
    def obter_chamado(self, chamado_id: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM chamados WHERE id = ?", (chamado_id,)).fetchone()
        return dict(r) if r else None

    def listar_chamados(self, status: str | None, limite: int) -> list[dict]:
        with self.conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM chamados WHERE status = ? ORDER BY prioridade DESC, criado_em ASC LIMIT ?",
                    (status, limite),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM chamados ORDER BY prioridade DESC, criado_em ASC LIMIT ?", (limite,)
                ).fetchall()
        return [dict(r) for r in rows]

    def estatisticas(self) -> dict:
        with self.conn() as c:
            por_status = {
                r["status"]: r["n"]
                for r in c.execute("SELECT status, COUNT(*) AS n FROM chamados GROUP BY status")
            }
            total_relatos = c.execute("SELECT COUNT(*) FROM relatos").fetchone()[0]
            relatos_agrupados = c.execute(
                "SELECT COALESCE(SUM(qtd_relatos - 1), 0) FROM chamados"
            ).fetchone()[0]
            horas = c.execute(
                "SELECT AVG((julianday(resolvido_em) - julianday(criado_em)) * 24) FROM chamados"
                " WHERE resolvido_em IS NOT NULL"
            ).fetchone()[0]
            leituras = c.execute("SELECT COUNT(*) FROM leituras_ldr").fetchone()[0]
            confirmados = c.execute(
                "SELECT COUNT(*) FROM chamados WHERE ldr_veredito IS NOT NULL"
            ).fetchone()[0]
            ativos = sum(por_status.get(s, 0) for s in STATUS_ATIVOS)
        return {
            "chamados_por_status": por_status,
            "chamados_ativos": ativos,
            "total_relatos": total_relatos,
            "relatos_agrupados_por_deduplicacao": relatos_agrupados,
            "tempo_medio_relato_ate_conserto_h": round(horas, 1) if horas is not None else None,
            "leituras_ldr": leituras,
            "chamados_com_validacao_fisica": confirmados,
        }
