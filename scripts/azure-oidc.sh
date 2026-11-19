#!/usr/bin/env bash
# Cria a identidade que o GitHub Actions usa para fazer deploy, SEM senha:
#  - App Registration + Service Principal
#  - Credencial federada (OIDC) aceitando só o environment "producao" deste repositório
#  - Papel "Website Contributor" restrito ao resource group do MVP (menor privilégio)
# Uso: ./scripts/azure-oidc.sh <usuario-github>/<repositorio>   (rodar depois do terraform apply)
set -euo pipefail

REPO="${1:?informe usuario/repositorio do GitHub}"
RG=$(terraform -chdir=infra/terraform output -raw resource_group)
APP_NAME=$(terraform -chdir=infra/terraform output -raw webapp_nome)
SUB=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)

CLIENT_ID=$(az ad app create --display-name "gh-deploy-luz-segura" --query appId -o tsv)
az ad sp create --id "$CLIENT_ID" -o none 2>/dev/null || true

az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
  \"name\": \"github-producao\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:${REPO}:environment:producao\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}" -o none

# O GitHub passou a emitir o "subject" do token OIDC com os IDs numéricos do dono e do
# repositório (repo:dono@ID/repo@ID:environment:...). Cadastramos os dois formatos.
if command -v gh >/dev/null 2>&1; then
  OWNER_ID=$(gh api "users/${REPO%%/*}" -q .id 2>/dev/null || true)
  REPO_ID=$(gh api "repos/${REPO}" -q .id 2>/dev/null || true)
  if [ -n "$OWNER_ID" ] && [ -n "$REPO_ID" ]; then
    az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
      \"name\": \"github-producao-ids\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"repo:${REPO%%/*}@${OWNER_ID}/${REPO#*/}@${REPO_ID}:environment:producao\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" -o none
  fi
fi

sleep 20
az role assignment create --assignee "$CLIENT_ID" --role "Website Contributor" \
  --scope "/subscriptions/${SUB}/resourceGroups/${RG}" -o none

echo
echo "Crie estes secrets no GitHub (Settings > Secrets and variables > Actions)"
echo "ou rode os comandos abaixo com o GitHub CLI:"
echo
echo "gh secret set AZURE_CLIENT_ID       --repo $REPO --body $CLIENT_ID"
echo "gh secret set AZURE_TENANT_ID       --repo $REPO --body $TENANT"
echo "gh secret set AZURE_SUBSCRIPTION_ID --repo $REPO --body $SUB"
echo "gh secret set AZURE_RESOURCE_GROUP  --repo $REPO --body $RG"
echo "gh secret set AZURE_WEBAPP_NAME     --repo $REPO --body $APP_NAME"
echo
echo "E crie o environment 'producao' em Settings > Environments."
