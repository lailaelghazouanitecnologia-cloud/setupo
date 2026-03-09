param(
    [string]$TemplatePath = ".\deploy\cloud-init.sh",
    [string]$OutputPath = ".\deploy\out\cloud-init-rendered.sh",
    [string]$RepoBranch = "claude/analyze-schemas-organization-EviP7",
    [string]$NsoDomain = "nso.dev"
)

$ErrorActionPreference = "Stop"

$required = @(
    "NSO_ADMIN_EMAIL",
    "NSO_ADMIN_PASSWORD",
    "AGENT_ADMIN_PASSWORD",
    "VULTR_API_KEY",
    "CF_API_TOKEN",
    "CF_NSO_ZONE_ID",
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY"
)

$missing = $required | Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}

if (-not (Test-Path $TemplatePath)) {
    throw "Template not found: $TemplatePath"
}

$content = Get-Content $TemplatePath -Raw

$deployAgentApiKey = [Environment]::GetEnvironmentVariable("DEPLOY_AGENT_API_KEY")
if (-not $deployAgentApiKey) { $deployAgentApiKey = "" }

$replacements = @{
    "__NSO_ADMIN_EMAIL__" = $env:NSO_ADMIN_EMAIL
    "__NSO_ADMIN_PASSWORD__" = $env:NSO_ADMIN_PASSWORD
    "__AGENT_ADMIN_PASSWORD__" = $env:AGENT_ADMIN_PASSWORD
    "__VULTR_API_KEY__" = $env:VULTR_API_KEY
    "__CF_API_TOKEN__" = $env:CF_API_TOKEN
    "__CF_NSO_ZONE_ID__" = $env:CF_NSO_ZONE_ID
    "__R2_ENDPOINT__" = $env:R2_ENDPOINT
    "__R2_ACCESS_KEY_ID__" = $env:R2_ACCESS_KEY_ID
    "__R2_SECRET_ACCESS_KEY__" = $env:R2_SECRET_ACCESS_KEY
    "__DEPLOY_AGENT_API_KEY__" = $deployAgentApiKey
}

foreach ($pair in $replacements.GetEnumerator()) {
    $content = $content.Replace($pair.Key, $pair.Value)
}

$content = [regex]::Replace(
    $content,
    'REPO_BRANCH="\$\{REPO_BRANCH:-[^"]+\}"',
    ('REPO_BRANCH="${REPO_BRANCH:-' + $RepoBranch + '}"')
)

$content = [regex]::Replace(
    $content,
    'NSO_DOMAIN="\$\{NSO_DOMAIN:-[^"]+\}"',
    ('NSO_DOMAIN="${NSO_DOMAIN:-' + $NsoDomain + '}"')
)

$deployAgentApiUrl = [Environment]::GetEnvironmentVariable("DEPLOY_AGENT_API_URL")
if (-not $deployAgentApiUrl) { $deployAgentApiUrl = "https://api.groq.com/openai/v1" }
$content = [regex]::Replace(
    $content,
    'DEPLOY_AGENT_API_URL="\$\{DEPLOY_AGENT_API_URL:-[^"]+\}"',
    ('DEPLOY_AGENT_API_URL="${DEPLOY_AGENT_API_URL:-' + $deployAgentApiUrl + '}"')
)

$deployAgentModel = [Environment]::GetEnvironmentVariable("DEPLOY_AGENT_MODEL")
if (-not $deployAgentModel) { $deployAgentModel = "openai/gpt-oss-20b" }
$content = [regex]::Replace(
    $content,
    'DEPLOY_AGENT_MODEL="\$\{DEPLOY_AGENT_MODEL:-[^"]+\}"',
    ('DEPLOY_AGENT_MODEL="${DEPLOY_AGENT_MODEL:-' + $deployAgentModel + '}"')
)

$deployAgentProvider = [Environment]::GetEnvironmentVariable("DEPLOY_AGENT_PROVIDER")
if (-not $deployAgentProvider) { $deployAgentProvider = "groq" }
$content = [regex]::Replace(
    $content,
    'DEPLOY_AGENT_PROVIDER="\$\{DEPLOY_AGENT_PROVIDER:-[^"]+\}"',
    ('DEPLOY_AGENT_PROVIDER="${DEPLOY_AGENT_PROVIDER:-' + $deployAgentProvider + '}"')
)

$outDir = Split-Path -Parent $OutputPath
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

Set-Content -Path $OutputPath -Value $content -NoNewline

Write-Host "Rendered cloud-init to $OutputPath"
Write-Host "Branch: $RepoBranch"
Write-Host "Domain: $NsoDomain"
Write-Host "Vultr OS: Debian 12 x64 (2136)"
Write-Host "Suggested plan: vc2-4c-8gb"
