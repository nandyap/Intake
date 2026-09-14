<#
.SYNOPSIS
    Discover landing-zone resource names and set them as azd environment
    variables.

.DESCRIPTION
    The application Bicep references existing landing-zone resources by
    name. Rather than typing those names, this script reads them from the
    resource group and runs `azd env set` for each.

    Read-only against Azure; it creates nothing. Values are written to
    .azure/<env>/.env, which is gitignored.

.EXAMPLE
    ./scripts/discover-resources.ps1 -SubscriptionId <guid> -ResourceGroup <rg>
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [string]$ResourceGroup
)

$ErrorActionPreference = 'Stop'

Write-Host "Subscription  : $SubscriptionId"
Write-Host "Resource group: $ResourceGroup"
Write-Host ''

az account set --subscription $SubscriptionId | Out-Null

$resources = az resource list --resource-group $ResourceGroup `
    --query "[].{name:name, type:type, location:location}" -o json | ConvertFrom-Json

if (-not $resources) {
    throw "No resources found in $ResourceGroup. Check the name and your access."
}

Write-Host "Found $($resources.Count) resources." -ForegroundColor Cyan

function Get-One {
    param([string]$Type, [string]$Label)
    $match = @($resources | Where-Object { $_.type -eq $Type })
    if ($match.Count -eq 0) {
        Write-Warning "$Label not found (type $Type)"
        return ''
    }
    if ($match.Count -gt 1) {
        Write-Warning "$Label is ambiguous ($($match.Count) matches) - using '$($match[0].name)'"
    }
    return $match[0].name
}

$discovered = [ordered]@{
    AZURE_LANDING_ZONE_RG         = $ResourceGroup
    AZURE_LOCATION                = ($resources | Select-Object -First 1).location
    AZURE_CONTAINER_APPS_ENV_NAME = Get-One 'Microsoft.App/managedEnvironments'     'Container Apps Environment'
    AZURE_COSMOSDB_ACCOUNT_NAME   = Get-One 'Microsoft.DocumentDB/databaseAccounts' 'Cosmos DB account'
    AZURE_KEY_VAULT_NAME          = Get-One 'Microsoft.KeyVault/vaults'             'Key Vault'
    AZURE_SEARCH_SERVICE_NAME     = Get-One 'Microsoft.Search/searchServices'       'AI Search'
    AZURE_APP_INSIGHTS_NAME       = Get-One 'Microsoft.Insights/components'         'Application Insights'
}

Write-Host ''
Write-Host 'Setting azd environment variables:' -ForegroundColor Green
foreach ($entry in $discovered.GetEnumerator()) {
    if (-not $entry.Value) {
        Write-Warning ("  {0,-30} <MISSING - set manually>" -f $entry.Key)
        continue
    }
    Write-Host ("  {0,-30} {1}" -f $entry.Key, $entry.Value)
    azd env set $entry.Key $entry.Value | Out-Null
}

Write-Host ''
Write-Host 'Done. Review with: azd env get-values' -ForegroundColor Green

$missing = @($discovered.GetEnumerator() | Where-Object { -not $_.Value })
if ($missing) {
    Write-Warning "$($missing.Count) value(s) unresolved. Set them with 'azd env set' before deploying."
    exit 1
}
