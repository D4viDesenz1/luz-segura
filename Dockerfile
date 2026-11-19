# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Luz Segura - imagem de produção
#  - multi-stage: ferramentas de build não vão para a imagem final
#  - usuário não root (uid 10001), sem shell de login
#  - nenhum segredo na imagem: tokens chegam por variável de ambiente
#  - healthcheck sem curl (menos pacotes = menos CVE)
# ---------------------------------------------------------------------------
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="luz-segura" \
      org.opencontainers.image.description="API do Luz Segura - CitizenTech FIAP GS 2026.2" \
      org.opencontainers.image.licenses="MIT"

# Aplica correções de segurança do SO base e remove o cache do apt.
# nosemgrep - upgrade intencional: fecha CVEs com correção disponível na imagem base
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /home/data \
 && chown app:app /home/data

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DB_PATH=/home/data/luzsegura.db \
    PORT=8000

WORKDIR /srv
COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root app/ ./app/

# pip não é necessário em produção: removê-lo reduz superfície e alertas do Trivy.
RUN rm -rf /opt/venv/bin/pip* /opt/venv/lib/python3.*/site-packages/pip* /usr/local/bin/pip* /usr/local/lib/python3.*/site-packages/pip* /usr/local/lib/python3.*/ensurepip

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# --proxy-headers: o App Service termina o TLS e repassa o IP real do cliente.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--workers", "1"]
