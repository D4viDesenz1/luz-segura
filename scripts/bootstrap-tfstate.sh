#!/usr/bin/env bash
# Cria o armazenamento REMOTO do Terraform state (fora do repositório).
#  - Storage Account com TLS 1.2, sem acesso público a blobs, versionamento e soft delete
#  - acesso via Entra ID (use_azuread_auth), sem chave de acesso no backend.hcl
# Uso: ./scripts/bootstrap-tfstate.sh [regiao]
set -euo pipefail

REGIAO="${1:-brazilsouth}"
RG="rg-luzsegura-tfstate"
SA="stluzseguratf$(openssl rand -hex 3)"
CONTAINER="tfstate"

az group create -n "$RG" -l "$REGIAO" -o none
az storage account create -n "$SA" -g "$RG" -l "$REGIAO" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false \
  --https-only true -o none
az storage account blob-service-properties update --account-name "$SA" -g "$RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 7 -o none

# Permissão de dados para o usuário logado (necessária com use_azuread_auth)
EU=$(az ad signed-in-user show --query id -o tsv)
SA_ID=$(az storage account show -n "$SA" -g "$RG" --query id -o tsv)
az role assignment create --assignee "$EU" --role "Storage Blob Data Contributor" --scope "$SA_ID" -o none || true
echo "Aguardando a permissão propagar (30s)..."; sleep 30

az storage container create -n "$CONTAINER" --account-name "$SA" --auth-mode login -o none

cat > infra/terraform/backend.hcl <<HCL
resource_group_name  = "$RG"
storage_account_name = "$SA"
container_name       = "$CONTAINER"
key                  = "luz-segura.tfstate"
use_azuread_auth     = true
HCL
echo "OK: infra/terraform/backend.hcl criado (está no .gitignore)."
