<#
.SYNOPSIS
    Diagnose, and optionally fix, private DNS for an internal Container
    Apps environment.

.DESCRIPTION
    An internal Container Apps environment publishes its apps on a
    generated domain, for example:

        ca-intake-dev-frontend.<name>.<region>.azurecontainerapps.io

    That name only resolves inside the VNet if a Private DNS Zone exists
    for the environment's default domain, linked to the VNet, with a
    wildcard A record pointing at the environment's static IP.

    Without it, a jumpbox inside the VNet still cannot reach the app: the
    hostname does not resolve at all.

    Run with -CheckOnly first. It reads state and changes nothing.

.PARAMETER CheckOnly
    Report what is present and what is missing. Makes no changes.

.EXAMPLE
    ./scripts/setup-private-dns.ps1 -ResourceGroup <rg> -CheckOnly
    ./scripts/setup-private-dns.ps1 -ResourceGroup <rg>
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$ResourceGroup,

    [string]$ContainerAppsEnvironment,

    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

function Write-Step { param([string]$Text) Write-Host "`n$Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "  [ok]   $Text" -ForegroundColor Green }
function Write-Miss { param([string]$Text) Write-Host "  [--]   $Text" -ForegroundColor Yellow }

# --- locate the environment ---------------------------------------------------

if (-not $ContainerAppsEnvironment) {
    $ContainerAppsEnvironment = az containerapp env list `
        --resource-group $ResourceGroup --query '[0].name' -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $ContainerAppsEnvironment) {
        throw "Could not list Container Apps environments in $ResourceGroup. Check the resource group name and that you have Microsoft.App/managedEnvironments/read."
    }
}

Write-Step "Container Apps environment: $ContainerAppsEnvironment"

# Capture stderr so an authorization failure is reported here rather than
# leaving $envJson null further down.
$envRaw = az containerapp env show `
    --name $ContainerAppsEnvironment --resource-group $ResourceGroup `
    --query "{staticIp:properties.staticIp, defaultDomain:properties.defaultDomain, internal:properties.vnetConfiguration.internal, subnet:properties.vnetConfiguration.infrastructureSubnetId}" `
    -o json 2>&1
$envQueryFailed = $LASTEXITCODE -ne 0

$envJson = $null
if (-not $envQueryFailed) {
    try { $envJson = $envRaw | ConvertFrom-Json } catch { $envQueryFailed = $true }
}

# FAIL LOUDLY. A failed lookup must never be mistaken for "this environment
# is external, so no private DNS is required" — that is a false all-clear,
# and it is the single most misleading thing this script could report.
if ($envQueryFailed -or $null -eq $envJson -or $null -eq $envJson.defaultDomain) {
    Write-Host ''
    Write-Host 'CANNOT DETERMINE ENVIRONMENT STATE' -ForegroundColor Red
    Write-Host ($envRaw | Out-String).Trim()
    Write-Host ''
    Write-Host 'This is NOT a clean result. The environment may still be internal'
    Write-Host 'and may still require a Private DNS Zone.'
    Write-Host ''
    Write-Host 'Most likely cause: the signed-in principal lacks'
    Write-Host '  Microsoft.App/managedEnvironments/read'
    Write-Host 'on the resource group. Reader on the resource group is enough.'
    Write-Host ''
    Write-Host 'If access was granted in the last few minutes, run'
    Write-Host '  az account clear; az login'
    Write-Host 'and retry - RBAC changes take time to reach the token.'
    exit 2
}

$staticIp      = $envJson.staticIp
$defaultDomain = $envJson.defaultDomain
$isInternal    = [bool]$envJson.internal
$subnetId      = $envJson.subnet

Write-Host "  default domain : $defaultDomain"
Write-Host "  static IP      : $staticIp"
Write-Host "  internal       : $isInternal"

if (-not $isInternal) {
    Write-Ok 'Environment is external — apps are reachable publicly. No private DNS needed.'
    exit 0
}

if (-not $subnetId) {
    throw 'Environment is internal but exposes no infrastructure subnet. Cannot determine the VNet.'
}

# The VNet id is the subnet id minus the trailing /subnets/<name>.
$vnetId   = $subnetId -replace '/subnets/.*$', ''
$vnetName = $vnetId.Split('/')[-1]
Write-Host "  VNet           : $vnetName"

# --- current DNS state --------------------------------------------------------

Write-Step 'Private DNS state'

$zoneExists = $false
$null = az network private-dns zone show `
    --resource-group $ResourceGroup --name $defaultDomain 2>$null
if ($LASTEXITCODE -eq 0) { $zoneExists = $true }

if ($zoneExists) { Write-Ok "Zone '$defaultDomain' exists" }
else { Write-Miss "Zone '$defaultDomain' does not exist" }

$linkExists = $false
if ($zoneExists) {
    $links = az network private-dns link vnet list `
        --resource-group $ResourceGroup --zone-name $defaultDomain `
        --query "[?virtualNetwork.id=='$vnetId'].name" -o tsv 2>$null
    if ($links) { $linkExists = $true; Write-Ok "Zone is linked to $vnetName" }
    else { Write-Miss "Zone is NOT linked to $vnetName" }
}

$recordOk = $false
if ($zoneExists) {
    $recorded = az network private-dns record-set a show `
        --resource-group $ResourceGroup --zone-name $defaultDomain --name '*' `
        --query 'aRecords[].ipv4Address' -o tsv 2>$null
    if ($recorded -contains $staticIp) {
        $recordOk = $true
        Write-Ok "Wildcard A record points at $staticIp"
    }
    elseif ($recorded) { Write-Miss "Wildcard A record exists but points at: $recorded" }
    else { Write-Miss 'Wildcard A record is missing' }
}

if ($zoneExists -and $linkExists -and $recordOk) {
    Write-Host "`nPrivate DNS is correctly configured." -ForegroundColor Green
    Write-Host 'Apps should resolve from any machine inside the VNet.'
    exit 0
}

if ($CheckOnly) {
    Write-Host "`nPrivate DNS is INCOMPLETE." -ForegroundColor Yellow
    Write-Host 'Re-run without -CheckOnly to create the missing pieces.'
    Write-Host 'This is a change to shared networking — get it approved first.'
    exit 1
}

# --- apply --------------------------------------------------------------------

Write-Step 'Applying'
Write-Host '  This modifies shared landing-zone networking.' -ForegroundColor Yellow

if (-not $PSCmdlet.ShouldProcess($defaultDomain, 'Create and link Private DNS Zone')) {
    exit 0
}

if (-not $zoneExists) {
    Write-Host '  creating zone ...'
    az network private-dns zone create `
        --resource-group $ResourceGroup --name $defaultDomain --output none
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the private DNS zone.' }
    Write-Ok 'zone created'
}

if (-not $linkExists) {
    Write-Host '  linking to VNet ...'
    az network private-dns link vnet create `
        --resource-group $ResourceGroup `
        --zone-name $defaultDomain `
        --name "link-$vnetName" `
        --virtual-network $vnetId `
        --registration-enabled false `
        --output none
    if ($LASTEXITCODE -ne 0) { throw 'Failed to link the zone to the VNet.' }
    Write-Ok 'linked'
}

if (-not $recordOk) {
    Write-Host '  adding wildcard A record ...'
    # add-record creates the record set when it does not exist.
    az network private-dns record-set a add-record `
        --resource-group $ResourceGroup `
        --zone-name $defaultDomain `
        --record-set-name '*' `
        --ipv4-address $staticIp `
        --output none
    if ($LASTEXITCODE -ne 0) { throw 'Failed to add the wildcard A record.' }
    Write-Ok "wildcard -> $staticIp"
}

Write-Host "`nDone." -ForegroundColor Green
Write-Host 'From a VM inside the VNet, verify with:'
Write-Host "  nslookup <app>.$defaultDomain"
