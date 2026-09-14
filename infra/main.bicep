// =============================================================================
// Intake Agent — application infrastructure
//
// Deploys ON TOP of an already-provisioned AI Landing Zone. Existing
// resources are referenced, never recreated. This module adds only what the
// application needs: a container registry, managed identities, Cosmos
// containers and the two container apps.
// =============================================================================

targetScope = 'resourceGroup'

@description('Environment suffix, e.g. dev')
param environmentName string = 'dev'

@description('Azure region — must match the landing zone')
param location string = resourceGroup().location

// The landing-zone resource names are deployment inputs, not defaults.
// Supply them via a parameters file — see infra/main.parameters.example.json
// and scripts/discover-resources.ps1.

@description('Existing Container Apps Environment from the AILZ deployment')
param containerAppsEnvironmentName string

@description('Existing Cosmos DB account from the AILZ deployment')
param cosmosAccountName string

@description('Existing Key Vault from the AILZ deployment')
param keyVaultName string

@description('Existing AI Search service from the AILZ deployment')
param searchServiceName string

@description('Existing Application Insights from the AILZ deployment')
param appInsightsName string

@description('Container image for the backend')
param backendImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Container image for the frontend')
param frontendImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Compass / APIM AI Gateway base URL for model access')
param compassBaseUrl string = 'https://api.core42.ai/v1'

@description('''
Allow public network access to the container registry.

The landing zone\'s Private DNS Zone integration is a manual customer step
that is NOT yet complete (AILZ handover section 5.1). Until it is, a
private-only registry cannot be pushed to from a build agent. Leave this
true for the first deployment, then set it to false once a private
endpoint and DNS resolution are in place.
''')
param allowRegistryPublicAccess bool = true

@description('''
Name of the Key Vault secret holding the Compass API key.

Leave EMPTY to deploy without model access. The backend then runs in stub
mode: the full 3-22 graph, all four human gates and every deterministic
service execute, with agentic steps returning schema-valid placeholders.

Set this to the secret name once Compass credentials are issued, create
the secret in Key Vault, and redeploy. No code change is required.
''')
param compassSecretName string = ''

// Deploying without the secret is a supported first-deployment posture,
// not a degraded one — it proves infrastructure, identity and networking
// independently of model access.
var useCompassSecret = !empty(compassSecretName)

var prefix = 'intake-${environmentName}'
var tags = {
  workload: 'm42-intake-agent'
  phase: 'phase-1'
  environment: environmentName
}

// -----------------------------------------------------------------------------
// Existing landing-zone resources
// -----------------------------------------------------------------------------

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource search 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: searchServiceName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// -----------------------------------------------------------------------------
// Container registry
// -----------------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: replace('acr${prefix}m42', '-', '')
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    // Managed identity only — no admin credentials to leak.
    adminUserEnabled: false
    publicNetworkAccess: allowRegistryPublicAccess ? 'Enabled' : 'Disabled'
  }
}

// -----------------------------------------------------------------------------
// Per-service workload identities
//
// v2.5 requires per-service workload identity with no shared account, so
// the backend and the frontend get separate identities even though they
// are co-deployed.
// -----------------------------------------------------------------------------

resource backendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-backend'
  location: location
  tags: tags
}

resource frontendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-frontend'
  location: location
  tags: tags
}

// -----------------------------------------------------------------------------
// Cosmos containers — design pack and MAF checkpoints
// -----------------------------------------------------------------------------

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'intake'
  properties: {
    resource: { id: 'intake' }
  }
}

resource designPacks 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'design-packs'
  properties: {
    resource: {
      id: 'design-packs'
      partitionKey: {
        paths: ['/tracking_reference']
        kind: 'Hash'
      }
    }
  }
}

resource checkpoints 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'checkpoints'
  properties: {
    resource: {
      id: 'checkpoints'
      partitionKey: {
        paths: ['/workflow_id']
        kind: 'Hash'
      }
      // Checkpoints exist to resume interrupted runs; they are not the
      // audit record, so they expire after 30 days.
      defaultTtl: 2592000
    }
  }
}

// -----------------------------------------------------------------------------
// Role assignments
// -----------------------------------------------------------------------------

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var cosmosContributorRoleId = '00000000-0000-0000-0000-000000000002'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'

resource backendAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, backendIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource frontendAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, frontendIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: frontendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendKeyVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendIdentity.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, backendIdentity.id, searchIndexDataReaderRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, backendIdentity.id, cosmosContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosContributorRoleId}'
    principalId: backendIdentity.properties.principalId
    scope: cosmos.id
  }
}

// -----------------------------------------------------------------------------
// Container apps
// -----------------------------------------------------------------------------

resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${prefix}-backend'
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${backendIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Internal only — the frontend proxies to it.
        external: false
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: backendIdentity.id
        }
      ]
      secrets: useCompassSecret ? [
        {
          // Resolved from Key Vault at runtime via the workload identity —
          // the key is never an environment variable in the template.
          name: 'compass-api-key'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/${compassSecretName}'
          identity: backendIdentity.id
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: concat([
            { name: 'AZURE_CLIENT_ID', value: backendIdentity.properties.clientId }
            { name: 'COMPASS_API_BASE_URL', value: compassBaseUrl }
            // 'local' until the Cosmos-backed design-pack store is
            // implemented. The containers below are created now so RBAC
            // and connectivity are proven ahead of that work; runs are
            // currently held in memory and do not survive a restart.
            { name: 'PERSISTENCE_MODE', value: 'local' }
            { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
            { name: 'COSMOS_DATABASE', value: 'intake' }
            { name: 'AZURE_SEARCH_ENDPOINT', value: 'https://${searchServiceName}.search.windows.net' }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            // Reproducibility is the product, not a tuning preference.
            { name: 'MODEL_TEMPERATURE', value: '0' }
            // Fail-closed retrieval is mandatory in every environment.
            { name: 'FAIL_CLOSED', value: 'true' }
            // Seeds remain permitted until M42 delivers the governed
            // artifacts. Flip to false to enforce governed-only.
            { name: 'ALLOW_SEED_ARTIFACTS', value: 'true' }
          ], useCompassSecret ? [
            { name: 'COMPASS_API_KEY', secretRef: 'compass-api-key' }
          ] : [])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [backendAcrPull, backendKeyVault, designPacks, checkpoints]
}

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${prefix}-frontend'
  location: location
  tags: union(tags, { 'azd-service-name': 'frontend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${frontendIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // The environment itself is internal, so this is reachable only
        // from the VNet.
        external: true
        targetPort: 3000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: frontendIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            {
              name: 'BACKEND_URL'
              value: 'https://${backend.properties.configuration.ingress.fqdn}'
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [frontendAcrPull]
}

// -----------------------------------------------------------------------------
// Outputs
// -----------------------------------------------------------------------------

output acrLoginServer string = acr.properties.loginServer
output backendFqdn string = backend.properties.configuration.ingress.fqdn
output frontendFqdn string = frontend.properties.configuration.ingress.fqdn
output backendPrincipalId string = backendIdentity.properties.principalId
