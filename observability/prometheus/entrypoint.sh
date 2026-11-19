#!/bin/sh
# Gera a config final a partir do template, trocando o alvo (local ou Azure).
# O token NÃO entra na config: o Prometheus lê de /run/secrets/metrics_token.
set -eu
sed -e "s|__SCHEME__|${ALVO_SCHEME}|g" -e "s|__TARGET__|${ALVO_HOST}|g" \
    /etc/prometheus/prometheus.yml.tpl > /tmp/prometheus.yml
exec /bin/prometheus \
  --config.file=/tmp/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=7d \
  --web.enable-lifecycle
