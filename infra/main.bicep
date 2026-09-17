// =============================================================================
// Intake Agent — azd entry point (subscription scope)
//
// azd requires a subscription-scoped template. This wrapper resolves the
// existing landing-zone resource group and delegates everything else to
// app.bicep.
//
// No resource group is created: the AI Landing Zone already owns one, and
// this solution deploys into it rather than alongside it.
// =============================================================================

targetScope = 'subscription'

@minLength(1)
@description('Environment name (azd: AZURE_ENV_NAME). Used as the resource suffix.')
param environmentName string

@minLength(1)
@description('Azure region (azd: AZURE_LOCATION). Must match the landing zone.')
param location string

@minLength(1)
@description('Existing landing-zone resource group to deploy into')
param resourceGroupName string

// --- Landing-zone resources referenced by the application --------------------

@description('Existing Container Apps Environment')
param containerAppsEnvironmentName string

@description('Existing Cosmos DB account')
param cosmosAccountName string

@description('Existing Key Vault')
param keyVaultName string

@description('Existing AI Search service')
param searchServiceName string

@description('Existing Application Insights')
param appInsightsName string

// --- Application settings -----------------------------------------------------

@description('Backend image (azd: SERVICE_BACKEND_IMAGE_NAME). Empty on first provision.')
param backendImage string = ''

@description('Frontend image (azd: SERVICE_FRONTEND_IMAGE_NAME). Empty on first provision.')
param frontendImage string = ''

@description('Compass / APIM AI Gateway base URL')
param compassBaseUrl string = 'https://api.core42.ai/v1'

@description('Allow public network access to the container registry. See app.bicep.')
param allowRegistryPublicAccess bool = true

@description('Key Vault secret name holding the Compass API key. Empty = stub mode.')
param compassSecretName string = ''

@description('Compass API key supplied directly when Key Vault is not reachable. See app.bicep.')
@secure()
param compassApiKey string = ''

@description('Compass chat model to call. Empty secret name means this is unused.')
param compassChatModel string = 'gpt-5.1'

// -----------------------------------------------------------------------------

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: resourceGroupName
}

module app 'app.bicep' = {
  name: 'intake-app'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    containerAppsEnvironmentName: containerAppsEnvironmentName
    cosmosAccountName: cosmosAccountName
    keyVaultName: keyVaultName
    searchServiceName: searchServiceName
    appInsightsName: appInsightsName
    backendImage: backendImage
    frontendImage: frontendImage
    compassBaseUrl: compassBaseUrl
    allowRegistryPublicAccess: allowRegistryPublicAccess
    compassSecretName: compassSecretName
    compassApiKey: compassApiKey
    compassChatModel: compassChatModel
  }
}

// -----------------------------------------------------------------------------
// Outputs
//
// azd writes these into .azure/<env>/.env. The AZURE_* names are the
// contract azd expects; the rest are for operators.
// -----------------------------------------------------------------------------

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_NAME string = app.outputs.acrName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = app.outputs.acrLoginServer
output AZURE_COSMOS_ENDPOINT string = app.outputs.cosmosEndpoint
output AZURE_SEARCH_ENDPOINT string = app.outputs.searchEndpoint
output AZURE_KEY_VAULT_NAME string = keyVaultName

output BACKEND_URL string = 'https://${app.outputs.backendFqdn}'
output FRONTEND_URL string = 'https://${app.outputs.frontendFqdn}'
output BACKEND_PRINCIPAL_ID string = app.outputs.backendPrincipalId
