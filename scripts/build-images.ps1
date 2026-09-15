<#
.SYNOPSIS
    Build and release both images using ACR Tasks. No Docker required.

.DESCRIPTION
    A fallback for machines with no container runtime.

    `azd deploy` normally handles this via docker.remoteBuild, but azd
    falls back to a LOCAL docker/podman build if the remote build fails —
    which hard-fails when no runtime is installed. This script calls
    `az acr build` directly, so the build always happens server-side in
    Azure and never touches the local machine.

    Run `azd provision` first: the registry and container apps must exist.

.PARAMETER Tag
    Image tag. Defaults to a UTC timestamp.

.PARAMETER Service
    Limit to one service. Default: both.

.EXAMPLE
    ./scripts/build-images.ps1
    ./scripts/build-images.ps1 -Service backend
#>

[CmdletBinding()]
param(
    [string]$Tag = (Get-Date -Format 'yyyyMMdd-HHmmss'),

    [ValidateSet('all', 'backend', 'frontend')]
    [string]$Service = 'all'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

# --- resolve settings from the azd environment -------------------------------

function Get-AzdValue {
    param([string]$Name)
    $line = (azd env get-values 2>$null) | Select-String -Pattern "^$Name=" | Select-Object -First 1
    if (-not $line) { return '' }
    return ($line -split '=', 2)[1].Trim('"')
}

$registry     = Get-AzdValue 'AZURE_CONTAINER_REGISTRY_NAME'
$loginServer  = Get-AzdValue 'AZURE_CONTAINER_REGISTRY_ENDPOINT'
$resourceGroup = Get-AzdValue 'AZURE_LANDING_ZONE_RG'
$envName      = Get-AzdValue 'AZURE_ENV_NAME'

if (-not $registry) {
    throw "Container registry not found in the azd environment. Run 'azd provision' first."
}
if (-not $loginServer) { $loginServer = "$registry.azurecr.io" }
if (-not $envName) { $envName = 'dev' }

Write-Host "Registry      : $loginServer"
Write-Host "Resource group: $resourceGroup"
Write-Host "Tag           : $Tag"
Write-Host ''

# --- build server-side -------------------------------------------------------

function Invoke-AcrBuild {
    param(
        [string]$Name,
        [string]$Context,
        [string]$Dockerfile
    )

    Write-Host "Building $Name in ACR (no local Docker) ..." -ForegroundColor Cyan

    # --file is relative to the context directory.
    az acr build `
        --registry $registry `
        --image "$Name`:$Tag" `
        --image "$Name`:latest" `
        --file $Dockerfile `
        $Context
    if ($LASTEXITCODE -ne 0) {
        throw "$Name image build failed."
    }
    Write-Host "  pushed $loginServer/$Name`:$Tag" -ForegroundColor Green
}

if ($Service -in 'all', 'backend') {
    # Context is the repo root so artifacts/ is included alongside backend/.
    Invoke-AcrBuild -Name 'intake-backend' -Context $root -Dockerfile 'backend/Dockerfile'
}
if ($Service -in 'all', 'frontend') {
    Invoke-AcrBuild -Name 'intake-frontend' -Context (Join-Path $root 'frontend') -Dockerfile 'Dockerfile'
}

# --- point the container apps at the new images ------------------------------

if (-not $resourceGroup) {
    Write-Warning "AZURE_LANDING_ZONE_RG not set - images are built but not released."
    Write-Host "Release manually with: az containerapp update --name <app> --image <image>"
    exit 0
}

function Update-App {
    param([string]$AppName, [string]$Image)
    Write-Host "Releasing $AppName ..." -ForegroundColor Cyan
    az containerapp update `
        --resource-group $resourceGroup `
        --name $AppName `
        --image $Image `
        --output none
    if ($LASTEXITCODE -ne 0) { throw "Failed to update $AppName." }
}

if ($Service -in 'all', 'backend') {
    Update-App "ca-intake-$envName-backend" "$loginServer/intake-backend:$Tag"
}
if ($Service -in 'all', 'frontend') {
    Update-App "ca-intake-$envName-frontend" "$loginServer/intake-frontend:$Tag"
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
$fqdn = az containerapp show --resource-group $resourceGroup `
    --name "ca-intake-$envName-frontend" `
    --query 'properties.configuration.ingress.fqdn' -o tsv 2>$null
if ($fqdn) {
    Write-Host "Frontend: https://$fqdn"
    Write-Host 'The Container Apps environment is internal - reach it from inside the VNet.'
}
