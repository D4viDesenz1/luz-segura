"""Métricas no formato texto do Prometheus, sem dependência externa.

As 4 métricas de ouro (Google SRE):
  - Latência   -> http_request_duration_seconds (histograma)
  - Tráfego    -> http_requests_total (contador)
  - Erros      -> http_requests_total{status=~"5.."}
  - Saturação  -> http_requests_in_progress, process_resident_memory_bytes,
                  process_cpu_seconds_total

Implementação própria = menos uma dependência na imagem (menor superfície
para o Trivy e para ataques de supply chain).
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_lock = threading.Lock()
_START = time.time()

_req_total: dict[tuple[str, str, str], int] = defaultdict(int)
_dur_buckets: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * len(BUCKETS))
_dur_sum: dict[tuple[str, str], float] = defaultdict(float)
_dur_count: dict[tuple[str, str], int] = defaultdict(int)
_in_progress = 0
_negocio: dict[tuple[str, str], int] = defaultdict(int)  # (nome_metrica, label) -> valor


def inicio_requisicao() -> None:
    global _in_progress
    with _lock:
        _in_progress += 1


def fim_requisicao(method: str, route: str, status: int, duracao: float) -> None:
    global _in_progress
    with _lock:
        _in_progress -= 1
        _req_total[(method, route, str(status))] += 1
        k = (method, route)
        for i, b in enumerate(BUCKETS):
            if duracao <= b:
                _dur_buckets[k][i] += 1
        _dur_sum[k] += duracao
        _dur_count[k] += 1


def contar(nome: str, label: str) -> None:
    with _lock:
        _negocio[(nome, label)] += 1


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _processo() -> tuple[float | None, float | None]:
    """CPU (s) e memória residente (bytes) lidas de /proc (Linux)."""
    try:
        with open("/proc/self/stat", encoding="ascii") as f:
            campos = f.read().rsplit(")", 1)[1].split()
        tick = os.sysconf("SC_CLK_TCK")
        cpu = (int(campos[11]) + int(campos[12])) / tick
        rss = int(campos[21]) * os.sysconf("SC_PAGE_SIZE")
        return cpu, float(rss)
    except (OSError, ValueError, IndexError):
        return None, None


def render(chamados_ativos: int | None = None) -> str:
    linhas: list[str] = []
    with _lock:
        linhas += [
            "# HELP http_requests_total Total de requisições HTTP.",
            "# TYPE http_requests_total counter",
        ]
        for (m, r, s), v in sorted(_req_total.items()):
            linhas.append(f'http_requests_total{{method="{_esc(m)}",route="{_esc(r)}",status="{s}"}} {v}')

        linhas += [
            "# HELP http_request_duration_seconds Latência das requisições HTTP.",
            "# TYPE http_request_duration_seconds histogram",
        ]
        for (m, r), bs in sorted(_dur_buckets.items()):
            lbl = f'method="{_esc(m)}",route="{_esc(r)}"'
            for b, v in zip(BUCKETS, bs):
                linhas.append(f'http_request_duration_seconds_bucket{{{lbl},le="{b}"}} {v}')
            linhas.append(f'http_request_duration_seconds_bucket{{{lbl},le="+Inf"}} {_dur_count[(m, r)]}')
            linhas.append(f"http_request_duration_seconds_sum{{{lbl}}} {_dur_sum[(m, r)]:.6f}")
            linhas.append(f"http_request_duration_seconds_count{{{lbl}}} {_dur_count[(m, r)]}")

        linhas += [
            "# HELP http_requests_in_progress Requisições em andamento (saturação).",
            "# TYPE http_requests_in_progress gauge",
            f"http_requests_in_progress {_in_progress}",
        ]

        metas = {
            "luzsegura_relatos_total": "Relatos recebidos por classificação da IA.",
            "luzsegura_relatos_rejeitados_total": "Relatos rejeitados por motivo.",
            "luzsegura_leituras_ldr_total": "Leituras do sensor LDR por veredito.",
        }
        for nome, ajuda in metas.items():
            linhas += [f"# HELP {nome} {ajuda}", f"# TYPE {nome} counter"]
            for (n, lbl), v in sorted(_negocio.items()):
                if n == nome:
                    chave = "motivo" if "rejeitados" in nome else (
                        "veredito" if "ldr" in nome else "classificacao")
                    linhas.append(f'{nome}{{{chave}="{_esc(lbl)}"}} {v}')

    if chamados_ativos is not None:
        linhas += [
            "# HELP luzsegura_chamados_ativos Chamados aguardando manutenção.",
            "# TYPE luzsegura_chamados_ativos gauge",
            f"luzsegura_chamados_ativos {chamados_ativos}",
        ]

    cpu, rss = _processo()
    if cpu is not None:
        linhas += [
            "# HELP process_cpu_seconds_total Tempo de CPU do processo.",
            "# TYPE process_cpu_seconds_total counter",
            f"process_cpu_seconds_total {cpu:.2f}",
            "# HELP process_resident_memory_bytes Memória residente do processo.",
            "# TYPE process_resident_memory_bytes gauge",
            f"process_resident_memory_bytes {rss:.0f}",
        ]
    linhas += [
        "# HELP process_start_time_seconds Início do processo (epoch).",
        "# TYPE process_start_time_seconds gauge",
        f"process_start_time_seconds {_START:.0f}",
    ]
    return "\n".join(linhas) + "\n"
