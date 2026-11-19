output "url_publica" {
  description = "URL pública do MVP."
  value       = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "mvp_host" {
  description = "Host para o Prometheus local (MVP_HOST)."
  value       = azurerm_linux_web_app.api.default_hostname
}

output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "webapp_nome" {
  value = azurerm_linux_web_app.api.name
}
