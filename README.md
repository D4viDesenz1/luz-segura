# Luz Segura

[![pipeline](https://github.com/D4viDesenz1/luz-segura/actions/workflows/devsecops.yml/badge.svg)](https://github.com/D4viDesenz1/luz-segura/actions)

O Luz Segura ajuda quem anda a pé ou usa transporte público à noite em Osasco (SP) a relatar pontos escuros e a cobrar o conserto da iluminação pública. Este repositório tem o **MVP em produção**: a API e a página de relatos em container, a nuvem criada por Terraform no Azure, o pipeline DevSecOps que barra segredo vazado e vulnerabilidade antes do deploy, e a observabilidade com dashboard e alerta.

O serviço também tem um assistente (modelo de linguagem local) que tira dúvidas do morador sobre iluminação pública em português simples, sempre em JSON, citando os trechos da base de conhecimento e dizendo "não consta" quando a base não cobre a pergunta. Por exemplo: quem conserta a lâmpada da rua, como pedir, o que é a CIP na conta de luz, o que fazer com um fio caído e como funciona o próprio Luz Segura.

**MVP no ar:** https://app-luz-segura-46grz.azurewebsites.net

FIAP · Global Solution 2026.2 · CitizenTech · Secure DevOps Tools & Cloud Computing (atividade *Deploy Blindado*)

## Equipe

| Nome | RM |
|---|---|
| Fabrício Gutierrez Saavedra | RM97631 |
| Márcio Gastaldi | RM98811 |
| Arthur Bessa Pian | RM99215 |
| Davi Desenzi | RM550849 |
| João Victor | RM551410 |

## A ideia

Ponto de ônibus escuro, rua com poste queimado, praça sem luz. Isso afeta a sensação de segurança, o risco de acidentes e a autonomia de idosos e pessoas com deficiência. A prefeitura só descobre o poste apagado quando alguém reclama, e a reclamação costuma ser mal localizada, duplicada ou nunca priorizada.

Com o Luz Segura:

1. O cidadão envia uma foto noturna do local, com a localização.
2. A visão computacional classifica a iluminação: adequada, fraca ou inexistente.
3. Relatos repetidos da mesma região viram um único chamado, priorizado e com o motivo explicado.
4. Um sensor LDR mede a luz real no local e confirma ou contesta o relato.
5. A manutenção recebe uma fila por prioridade e acompanha o tempo até o conserto.

## Ficha Técnica do MVP

| Campo | Conteúdo |
|---|---|
| **Nome do produto** | Luz Segura |
| **Cidadão e território** | Quem usa transporte público e anda a pé à noite (trabalhadores de turno, estudantes de cursos noturnos e idosos), no entorno da Estação Osasco e do centro de Osasco/SP |
| **Problema, em uma frase** | Pontos escuros em vias e paradas aumentam o risco e a insegurança, e o poder público demora a saber e a priorizar. |
| **Proposta de valor** | Relatos com foto, validados por IA e por sensor, viram chamados priorizados e explicáveis para a manutenção. |
| **Arquitetura** | Página web + API Python em container no Azure App Service (criado por Terraform), CI/CD DevSecOps no GitHub Actions, Prometheus + Grafana |
| **Fontes de dados** | Relatos e paradas simulados e documentados, leituras do LDR; previstos: Open-Meteo, paradas de ônibus (GTFS), IBGE |
| **Modelos de IA** | Classificador de imagens noturnas, classificador das leituras do LDR, LLM com RAG |
| **Indicadores de impacto** | Tempo médio entre relato e conserto, chamados resolvidos, relatos repetidos agrupados, pontos com validação física |
| **ODS** | 11 (principal), 9 e 10 |

## Como rodar

**Pré-requisitos:** Docker, Python 3.13, Azure CLI, Terraform ≥ 1.6.

**Local (API + Prometheus + Grafana):**
```bash
cp .env.example .env    # preencha ADMIN_TOKEN, DEVICE_TOKEN, METRICS_TOKEN e GRAFANA_ADMIN_PASSWORD
grep METRICS_TOKEN .env | cut -d= -f2- | tr -d '\n' > observability/secrets/metrics_token
docker compose up -d --build
# API http://localhost:8000 · Prometheus http://localhost:9090 · Grafana http://localhost:3000
```
Testes: `pip install -r requirements-dev.txt && python -m pytest -q`

**Nuvem (Azure):**
```bash
az login
./scripts/bootstrap-tfstate.sh                  # state remoto (fora do repositório)
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars    # preencha; fica fora do git
terraform init -backend-config=backend.hcl
terraform apply
```
Depois, `./scripts/azure-oidc.sh <usuario>/<repositorio>` configura o login do GitHub no Azure sem senha. A partir daí, todo push na `main` passa por testes, Gitleaks, Semgrep e Trivy e, se tudo passar, faz o deploy automático.

**Desligar:** `terraform -chdir=infra/terraform destroy`

## Estrutura do repositório

```
luz-segura/
├── app/                      API e página do cidadão (Python + Starlette)
│   ├── main.py               rotas da API e montagem da aplicação
│   ├── classifier.py         classifica a iluminação da foto
│   ├── priority.py           cálculo da prioridade explicável
│   ├── security.py           tokens, rate limit, cabeçalhos de segurança
│   ├── metrics.py            métricas do Prometheus (/metrics)
│   ├── db.py · geo.py        banco SQLite e cálculo de distância
│   ├── config.py             configurações lidas de variáveis de ambiente
│   ├── data/                 paradas de ônibus simuladas de Osasco
│   └── static/               página web (HTML, CSS e JS)
├── tests/                    38 testes automatizados (pytest)
├── Dockerfile                imagem enxuta e sem root
├── docker-compose.yml        stack local: API + Prometheus + Grafana
├── infra/terraform/          toda a nuvem do Azure em código
├── .github/workflows/        pipeline DevSecOps (devsecops.yml)
├── observability/            Prometheus (alertas) e Grafana (dashboard)
├── scripts/                  automações: state remoto, OIDC, demo do pipeline barrado, dados de demonstração
├── docs/
│   ├── ARQUITETURA.md        diagrama, responsabilidade compartilhada, LGPD e custo
│   └── evidencias/           prints da entrega, com a explicação de cada um
├── .gitleaks.toml            configuração do Gitleaks
├── .dockerignore · .gitignore
├── .env.example              modelo das variáveis (sem valores reais)
└── requirements*.txt         dependências da API e dos testes
```

Mais detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).
