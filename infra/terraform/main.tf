resource "random_string" "sufixo" {
  length  = 5
  special = false
  upper   = false
}

locals {
  nome = "${var.projeto}-${random_string.sufixo.result}"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.nome}"
  location = var.localizacao
  tags     = var.tags
}

# ---------------------------------------------------------------- logs
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "log-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # trava de custo
  tags                = var.tags
}

# ---------------------------------------------------------------- compute
resource "azurerm_service_plan" "plano" {
  name                = "asp-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = var.sku_plano
  tags                = var.tags
}

resource "azurerm_linux_web_app" "api" {
  name                = "app-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plano.id

  https_only                                     = true
  public_network_access_enabled                  = true # o app é público; a ADMINISTRAÇÃO não
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  client_affinity_enabled                        = false

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                         = true
    http2_enabled                     = true
    minimum_tls_version               = "1.2"
    scm_minimum_tls_version           = "1.2"
    ftps_state                        = "Disabled"
    remote_debugging_enabled          = false
    health_check_path                 = "/health"
    health_check_eviction_time_in_min = 5

    application_stack {
      docker_image_name   = var.imagem_container
      docker_registry_url = "https://ghcr.io"
    }

    # Site público: aceita qualquer origem (é um serviço ao cidadão).
    ip_restriction_default_action = "Allow"

    # Porta de ADMINISTRAÇÃO (SCM/Kudu): negada por padrão, liberada só para o IP do admin.
    scm_use_main_ip_restriction       = false
    scm_ip_restriction_default_action = "Deny"
    scm_ip_restriction {
      name       = "somente-admin"
      ip_address = var.admin_cidr
      action     = "Allow"
      priority   = 100
    }
  }

  app_settings = {
    WEBSITES_PORT                       = "8000"
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = "false"
    APP_ENV                             = "production"
    DB_PATH                             = "/tmp/luzsegura.db"
    ADMIN_TOKEN                         = var.admin_token
    DEVICE_TOKEN                        = var.device_token
    METRICS_TOKEN                       = var.metrics_token
  }

  logs {
    detailed_error_messages = false
    failed_request_tracing  = false
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  tags = var.tags

  lifecycle {
    # A tag da imagem é atualizada pelo pipeline a cada deploy; o Terraform não reverte.
    ignore_changes = [site_config[0].application_stack[0].docker_image_name]
  }
}

resource "azurerm_monitor_diagnostic_setting" "api" {
  name                       = "diag-${local.nome}"
  target_resource_id         = azurerm_linux_web_app.api.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id

  enabled_log {
    category = "AppServiceHTTPLogs"
  }
  enabled_log {
    category = "AppServiceConsoleLogs"
  }
  enabled_log {
    category = "AppServicePlatformLogs"
  }
  enabled_metric {
    category = "AllMetrics"
  }
}

# ---------------------------------------------------------------- custo
resource "azurerm_consumption_budget_resource_group" "orcamento" {
  count             = var.email_alerta_orcamento == "" ? 0 : 1
  name              = "budget-${local.nome}"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = var.orcamento_mensal_usd
  time_grain        = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.email_alerta_orcamento]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
