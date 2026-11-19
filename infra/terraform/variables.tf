variable "subscription_id" {
  description = "ID da assinatura Azure (az account show --query id -o tsv)."
  type        = string
}

variable "projeto" {
  description = "Prefixo dos recursos."
  type        = string
  default     = "luz-segura"
}

variable "localizacao" {
  description = "Região Azure. brazilsouth mantém os dados no Brasil (LGPD). Se a política do Azure for Students bloquear, use eastus."
  type        = string
  default     = "brazilsouth"
}

variable "sku_plano" {
  description = "SKU do App Service Plan. B1 = 1 vCPU / 1,75 GB, suporta Always On e health check."
  type        = string
  default     = "B1"
}

variable "imagem_container" {
  description = "Imagem inicial no GHCR, sem o host. Ex.: seu-usuario/luz-segura:latest. Depois o pipeline atualiza a tag a cada deploy."
  type        = string
}

variable "admin_cidr" {
  description = "Único IP/faixa que pode acessar a porta de administração (SCM/Kudu). Use o seu IP público com /32."
  type        = string

  validation {
    condition = (
      !contains(["0.0.0.0/0", "*", "Any", "Internet", "::/0"], var.admin_cidr)
      && can(cidrhost(var.admin_cidr, 0))
      && tonumber(split("/", var.admin_cidr)[1]) >= 24
    )

    error_message = "admin_cidr precisa ser um IP específico (ex.: 177.10.20.30/32). Abrir administração para 0.0.0.0/0 é proibido."
  }
}

variable "admin_token" {
  description = "Token da equipe de manutenção (PATCH de status). Mín. 24 caracteres."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.admin_token) >= 24
    error_message = "admin_token precisa de pelo menos 24 caracteres."
  }
}

variable "device_token" {
  description = "Token da estação com sensor LDR. Mín. 24 caracteres."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.device_token) >= 24
    error_message = "device_token precisa de pelo menos 24 caracteres."
  }
}

variable "metrics_token" {
  description = "Token que o Prometheus usa para ler /metrics. Mín. 24 caracteres."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.metrics_token) >= 24
    error_message = "metrics_token precisa de pelo menos 24 caracteres."
  }
}

variable "email_alerta_orcamento" {
  description = "E-mail para alerta de orçamento. Vazio = não cria o budget (algumas ofertas de estudante não suportam)."
  type        = string
  default     = ""
}

variable "orcamento_mensal_usd" {
  description = "Teto mensal para o alerta de custo."
  type        = number
  default     = 25
}

variable "tags" {
  type = map(string)
  default = {
    projeto    = "luz-segura"
    disciplina = "secure-devops-cloud"
    gs         = "fiap-2026.2-citizentech"
    gerenciado = "terraform"
  }
}
