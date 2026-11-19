#!/usr/bin/env bash
# Roteiro da evidência "execução barrada e a corrigida" (critério Pipeline DevSecOps).
#
#   ./scripts/demo-pipeline-barrado.sh vazar     -> commita um segredo FICTÍCIO e faz push (pipeline FALHA no Gitleaks)
#   ./scripts/demo-pipeline-barrado.sh corrigir  -> troca por variável de ambiente, reescreve o commit e faz push (pipeline PASSA)
#
# O segredo é gerado na hora (aleatório e sem valor real), então este script não
# contém nenhum segredo e não dispara o próprio Gitleaks.
set -euo pipefail

BRANCH="demo/segredo-vazado"
ARQ="app/integracao_prefeitura.py"

case "${1:-}" in
  vazar)
    git checkout -B "$BRANCH"
    CHAVE=$(python3 -c "import secrets; print(secrets.token_urlsafe(30))")
    cat > "$ARQ" <<PY
"""Integração com a API de manutenção da prefeitura (DEMO de segredo vazado)."""

PREFEITURA_API_KEY = "${CHAVE}"


def cabecalhos() -> dict:
    return {"Authorization": f"Bearer {PREFEITURA_API_KEY}"}
PY
    git add "$ARQ"
    git commit -m "feat: integração com API da prefeitura"
    git push -u origin "$BRANCH" --force-with-lease
    echo
    echo ">> Abra a aba Actions: o job Gitleaks deve FALHAR; build, Semgrep e Trivy rodam, e push/deploy ficam bloqueados."
    echo ">> PRINT 1: lista de jobs com o X vermelho. PRINT 2: log do Gitleaks mostrando o achado (REDACTED)."
    ;;
  corrigir)
    git checkout "$BRANCH"
    cat > "$ARQ" <<'PY'
"""Integração com a API de manutenção da prefeitura."""

import os

# Segredo vem do ambiente (App Settings / GitHub Secrets), nunca do código.
PREFEITURA_API_KEY = os.environ.get("PREFEITURA_API_KEY", "")


def cabecalhos() -> dict:
    return {"Authorization": f"Bearer {PREFEITURA_API_KEY}"} if PREFEITURA_API_KEY else {}
PY
    git add "$ARQ"
    # Remediação correta: (1) revogar a chave no provedor e (2) tirar do histórico.
    git commit --amend -m "feat: integração com API da prefeitura (segredo via variável de ambiente)"
    git push --force-with-lease origin "$BRANCH"
    echo
    echo ">> Abra a aba Actions: agora todos os jobs passam. PRINT 3: execução verde."
    echo ">> Depois pode apagar a branch: git push origin --delete $BRANCH"
    ;;
  *)
    echo "uso: $0 vazar|corrigir"; exit 1 ;;
esac
