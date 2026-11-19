# Evidências (prints)

Prints usados no PDF da entrega, na ordem dos critérios de avaliação.

## Container e IaC

| Print | O que mostra |
|---|---|
| [01-terraform-bloqueia-0000.jpg](01-terraform-bloqueia-0000.jpg) | `terraform plan` com `admin_cidr=0.0.0.0/0`: a validação recusa antes de criar qualquer recurso |
| [02-terraform-apply.jpg](02-terraform-apply.jpg) | `terraform apply`: 6 recursos criados, state com lock no Azure Storage |
| [03-recursos-azure.jpg](03-recursos-azure.jpg) | Recursos do grupo `rg-luz-segura-46grz`, todos em brazilsouth |
| [04-porta-admin-restrita.jpg](04-porta-admin-restrita.jpg) | SCM/Kudu (porta admin) com padrão Deny e só o IP do admin liberado |
| [05-state-remoto.jpg](05-state-remoto.jpg) | State remoto no Azure Storage e `git check-ignore` provando que tfvars e backend ficam fora do git |

## Pipeline DevSecOps

| Print | O que mostra |
|---|---|
| [06-pipeline-verde.jpg](06-pipeline-verde.jpg) | Execução #2: todos os controles verdes, push da imagem e deploy automático |
| [07-github-secrets.jpg](07-github-secrets.jpg) | Secrets do repositório: só IDs do Azure, nenhuma senha (login por OIDC) |
| [09a-pipeline-barrado-trivy.jpg](09a-pipeline-barrado-trivy.jpg) | Execução #1 barrada pelo Trivy (CVEs reais) — push e deploy não rodaram |
| [09-pipeline-barrado-gitleaks.jpg](09-pipeline-barrado-gitleaks.jpg) | Execução #3 barrada pelo Gitleaks (chave falsa colada no código) |
| [10-gitleaks-log.jpg](10-gitleaks-log.jpg) | Log do Gitleaks: regra, arquivo, linha e commit, com o valor mascarado |
| [11-barrada-e-corrigida.jpg](11-barrada-e-corrigida.jpg) | A branch de demonstração com a execução barrada e a corrigida lado a lado |
| [11a-pipeline-corrigido.jpg](11a-pipeline-corrigido.jpg) | Execução #4: a mesma mudança corrigida e aprovada |

## Observabilidade

| Print | O que mostra |
|---|---|
| [13-grafana-golden-signals.png](13-grafana-golden-signals.png) | Dashboard completo: latência, tráfego, erros, saturação e métricas de negócio |
| [13-grafana-top.png](13-grafana-top.png) | Topo do dashboard com o resumo das 4 métricas de ouro |
| [11b-prometheus-target-up.png](11b-prometheus-target-up.png) | Prometheus coletando o MVP publicado (alvo UP, HTTPS + token) |
| [12-alerta-disparado.png](12-alerta-disparado.png) | Alerta `LuzSeguraFilaDeManutencaoAlta` em FIRING |
| [08-mvp-no-ar.jpg](08-mvp-no-ar.jpg) | Página do MVP publicada no Azure |
