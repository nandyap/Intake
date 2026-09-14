<#
.SYNOPSIS
    Build, push and deploy the M42 Intake Agent.

.DESCRIPTION
    Phases:
      A  validate    what-if against the resource group (no changes)
      B  infra       deploy the Bicep (ACR, identities, Cosmos, apps)
      C  images      build and push backend + frontend via ACR Tasks
      D  release     point the container apps at the new images

    ACR Tasks builds server-side, so no local Docker daemon is needed.

    Run scripts/discover-resources.ps1 first to produce main.parameters.json.

.EXAMPLE
    ./scripts/deploy.ps1 -SubscriptionId <guid> -ResourceGroup <rg> -WhatIf
    ./scripts/deploy.ps1 -SubscriptionId <guid> -ResourceGroup <rg>
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [string]$ResourceGroup,

    [string]$Tag = (Get-Date -Format 'yyyyMMdd-HHmmss'),

    [ValidateSet('all', 'infra', 'images', 'release')]
    [string]$Phase = 'all'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$paramFile = Join-Path $root 'infra/main.parameters.json'

if (-not (Test-Path $paramFile)) {
    throw "Missing $paramFile. Run scripts/discover-resources.ps1 first."
}

az account set --subscription $SubscriptionId | Out-Null
Write-Host "Subscription : $SubscriptionId"
Write-Host "Resource group: $ResourceGroup"
Write-Host "Image tag     : $Tag"
Write-Host ''

# --- Phase A · validate ------------------------------------------------------

if ($WhatIfPreference) {
    Write-Host 'PHASE A - what-if (no changes)' -ForegroundColor Cyan
    az deployment group what-if `
        --resource-group $ResourceGroup `
        --template-file (Join-Path $root 'infra/main.bicep') `
        --parameters $paramFile
    return
}

# --- Phase B · infrastructure ------------------------------------------------

if ($Phase -in 'all', 'infra') {
    Write-Host 'PHASE B - infrastructure' -ForegroundColor Cyan
    az deployment group create `
        --resource-group $ResourceGroup `
        --name "intake-infra-$Tag" `
        --template-file (Join-Path $root 'infra/main.bicep') `
        --parameters $paramFile `
        --output none
    if ($LASTEXITCODE -ne 0) { throw 'Infrastructure deployment failed.' }
    Write-Host '  done' -ForegroundColor Green
}

$acrName = az deployment group show `
    --resource-group $ResourceGroup --name "intake-infra-$Tag" `
    --query 'properties.outputs.acrLoginServer.value' -o tsv 2>$null

if (-not $acrName) {
    $acrName = az acr list --resource-group $ResourceGroup `
        --query '[0].loginServer' -o tsv
}
if (-not $acrName) { throw 'Could not resolve the container registry.' }

$registry = $acrName.Split('.')[0]
Write-Host "Registry: $acrName"

# --- Phase C · images (built server-side by ACR Tasks) -----------------------

if ($Phase -in 'all', 'images') {
    Write-Host 'PHASE C - build and push images' -ForegroundColor Cyan

    Write-Host '  backend...'
    az acr build --registry $registry `
        --image "intake-backend:$Tag" --image 'intake-backend:latest' `
        --file 'backend/Dockerfile' $root `
        --output none
    if ($LASTEXITCODE -ne 0) { throw 'Backend image build failed.' }

    Write-Host '  frontend...'
    az acr build --registry $registry `
        --image "intake-frontend:$Tag" --image 'intake-frontend:latest' `
        --file 'Dockerfile' (Join-Path $root 'frontend') `
        --output none
    if ($LASTEXITCODE -ne 0) { throw 'Frontend image build failed.' }

    Write-Host '  done' -ForegroundColor Green
}

# --- Phase D · release -------------------------------------------------------

if ($Phase -in 'all', 'release') {
    Write-Host 'PHASE D - release' -ForegroundColor Cyan

    az containerapp update --resource-group $ResourceGroup `
        --name 'ca-intake-dev-backend' `
        --image "$acrName/intake-backend:$Tag" --output none

    az containerapp update --resource-group $ResourceGroup `
        --name 'ca-intake-dev-frontend' `
        --image "$acrName/intake-frontend:$Tag" --output none

    Write-Host '  done' -ForegroundColor Green
}

$fqdn = az containerapp show --resource-group $ResourceGroup `
    --name 'ca-intake-dev-frontend' `
    --query 'properties.configuration.ingress.fqdn' -o tsv

Write-Host ''
Write-Host "Frontend: https://$fqdn" -ForegroundColor Green
Write-Host 'Note: the Container Apps environment is internal — reachable from the VNet only.'
