<#
.SYNOPSIS
    Discover the deployed AILZ resources and write infra/main.parameters.json.

.DESCRIPTION
    The application Bicep references existing landing-zone resources by name.
    Rather than guessing those names, this script reads them from the
    resource group and writes a parameters file.

    Run this BEFORE any deployment. It is read-only — it creates nothing.

.EXAMPLE
    ./scripts/discover-resources.ps1 -SubscriptionId <guid> -ResourceGroup <rg>
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [string]$ResourceGroup,

    [string]$OutFile = "$PSScriptRoot/../infra/main.parameters.json"
)

$ErrorActionPreference = 'Stop'

Write-Host "Subscription : $SubscriptionId"
Write-Host "Resource group: $ResourceGroup"
Write-Host ''

az account set --subscription $SubscriptionId | Out-Null

$resources = az resource list --resource-group $ResourceGroup `
    --query "[].{name:name, type:type, location:location}" -o json | ConvertFrom-Json

if (-not $resources) {
    throw "No resources found in $ResourceGroup. Check the name and your access."
}

Write-Host "Found $($resources.Count) resources:" -ForegroundColor Cyan
$resources | Sort-Object type | Format-Table -AutoSize

function Get-One {
    param([string]$Type, [string]$Label)
    $match = @($resources | Where-Object { $_.type -eq $Type })
    if ($match.Count -eq 0) {
        Write-Warning "$Label not found (type $Type) - parameter left blank"
        return ''
    }
    if ($match.Count -gt 1) {
        Write-Warning "$Label is ambiguous ($($match.Count) matches) - using '$($match[0].name)'"
    }
    return $match[0].name
}

$discovered = [ordered]@{
    containerAppsEnvironmentName = Get-One 'Microsoft.App/managedEnvironments'          'Container Apps Environment'
    cosmosAccountName            = Get-One 'Microsoft.DocumentDB/databaseAccounts'      'Cosmos DB account'
    keyVaultName                 = Get-One 'Microsoft.KeyVault/vaults'                  'Key Vault'
    searchServiceName            = Get-One 'Microsoft.Search/searchServices'            'AI Search'
}

$location = ($resources | Select-Object -First 1).location

Write-Host ''
Write-Host 'Resolved parameters:' -ForegroundColor Green
$discovered.GetEnumerator() | ForEach-Object {
    $value = if ($_.Value) { $_.Value } else { '<MISSING>' }
    Write-Host ("  {0,-30} {1}" -f $_.Key, $value)
}
Write-Host ("  {0,-30} {1}" -f 'location', $location)

$parameters = [ordered]@{
    '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
    contentVersion = '1.0.0.0'
    parameters     = [ordered]@{
        environmentName = @{ value = 'dev' }
        location        = @{ value = $location }
    }
}
foreach ($entry in $discovered.GetEnumerator()) {
    $parameters.parameters[$entry.Key] = @{ value = $entry.Value }
}

$parameters | ConvertTo-Json -Depth 6 | Set-Content -Path $OutFile -Encoding utf8

Write-Host ''
Write-Host "Written to $OutFile" -ForegroundColor Green

$missing = @($discovered.GetEnumerator() | Where-Object { -not $_.Value })
if ($missing) {
    Write-Host ''
    Write-Warning "$($missing.Count) parameter(s) could not be resolved. Fill them in manually before deploying."
    exit 1
}
