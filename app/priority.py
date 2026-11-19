"""Regra de prioridade EXPLICÁVEL dos chamados.

Cada ponto do score vem com um motivo em linguagem simples, para responder
"por que este ponto está em primeiro?" (IA responsável: critério transparente).
"""

from __future__ import annotations

from datetime import datetime, timezone

PESO_SEVERIDADE = {"inexistente": 50, "fraca": 30, "adequada": 0}
PESO_FLUXO = {"alto": 1.0, "medio": 0.7, "baixo": 0.4}


def calcular_prioridade(
    *,
    classificacao: str,
    qtd_relatos: int,
    dist_parada_m: float | None,
    fluxo_parada: str | None,
    ldr_veredito: str | None,
    criado_em: str,
    agora: datetime | None = None,
) -> tuple[float, list[str]]:
    agora = agora or datetime.now(timezone.utc)
    score = 0.0
    motivos: list[str] = []

    sev = PESO_SEVERIDADE.get(classificacao, 0)
    score += sev
    motivos.append(f"+{sev}: iluminação classificada como '{classificacao}'")

    extras = max(0, qtd_relatos - 1)
    if extras:
        pts = min(20, extras * 5)
        score += pts
        motivos.append(f"+{pts}: {qtd_relatos} relatos independentes do mesmo ponto")

    if dist_parada_m is not None and dist_parada_m <= 150:
        base = 20 if dist_parada_m <= 50 else 10
        pts = round(base * PESO_FLUXO.get(fluxo_parada or "medio", 0.7), 1)
        score += pts
        motivos.append(
            f"+{pts}: parada de ônibus a {round(dist_parada_m)} m (fluxo noturno {fluxo_parada})"
        )

    if ldr_veredito == "confirmado":
        score += 10
        motivos.append("+10: sensor LDR confirmou baixa luminosidade no local")
    elif ldr_veredito == "contestado":
        score -= 30
        motivos.append("-30: sensor LDR mediu luz adequada (relato contestado, revisão humana)")

    try:
        criado = datetime.fromisoformat(criado_em)
        dias = max(0, (agora - criado).days)
    except ValueError:
        dias = 0
    if dias:
        pts = min(10, dias)
        score += pts
        motivos.append(f"+{pts}: aberto há {dias} dia(s)")

    return round(max(0.0, min(100.0, score)), 1), motivos
