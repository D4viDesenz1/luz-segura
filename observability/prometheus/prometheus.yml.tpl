global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    projeto: luz-segura

rule_files:
  - /etc/prometheus/alertas.yml

scrape_configs:
  - job_name: luz-segura
    scheme: __SCHEME__
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/metrics_token
    static_configs:
      - targets: ["__TARGET__"]
        labels:
          servico: api

  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
