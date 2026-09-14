# Deployment

Deployed with the **Azure Developer CLI (`azd`)** onto an existing AI
Landing Zone. Landing-zone resources are referenced, never recreated.

No tenant values live in this repository. Every parameter in
`infra/main.parameters.json` is an `${ENV_VAR}` reference; the real values
go in `.azure/<env>/.env`, which is gitignored.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Azure CLI | `az login` |
| **azd 1.11+** | `winget upgrade Microsoft.Azd` |
| Contributor **and** User Access Administrator on the resource group | The template creates role assignments |
| An AI Landing Zone already deployed | Container Apps Environment, Cosmos, Key Vault, AI Search, App Insights |

**Docker is not required.** Images build server-side via ACR remote build.
If that fails, azd falls back to a local Docker/Podman build automatically.

---

## One-time setup

```powershell
az login
az account set --subscription <subscription-id>

azd auth login
azd env new intake-dev
```

Then point the environment at your landing zone:

```powershell
azd env set AZURE_LOCATION                 <region>
azd env set AZURE_LANDING_ZONE_RG          <resource-group>
azd env set AZURE_CONTAINER_APPS_ENV_NAME  <container-apps-environment>
azd env set AZURE_COSMOSDB_ACCOUNT_NAME    <cosmos-account>
azd env set AZURE_KEY_VAULT_NAME           <key-vault>
azd env set AZURE_SEARCH_SERVICE_NAME      <ai-search-service>
azd env set AZURE_APP_INSIGHTS_NAME        <application-insights>
```

Confirm before deploying:

```powershell
azd env get-values
```

`scripts/discover-resources.ps1` will resolve these names from a resource
group if you would rather not type them.

---

## Deploy

```powershell
azd up
```

That runs provision → package → deploy in one pass. Or step through it:

```powershell
azd provision            # infrastructure only
azd deploy backend       # one service
azd deploy frontend
azd deploy               # both
```

Day-to-day, after a code change, `azd deploy <service>` is all you need —
it rebuilds, pushes and updates the container app without touching
infrastructure.

To preview infrastructure changes without applying them:

```powershell
azd provision --preview
```

Review that output with the platform team before the first `azd up`.

---

## What gets created

Added to the existing resource group. Nothing existing is modified.

- Container Registry (Standard)
- Two user-assigned managed identities — **no shared account**, per v2.5
- Cosmos database `intake` with `design-packs` and `checkpoints`
- Two container apps: backend (internal ingress) and frontend
- Role assignments: AcrPull, Key Vault Secrets User, Search Index Data
  Reader, Cosmos Data Contributor

---

## Deploying without a model key

`compassSecretName` defaults to empty, so the backend starts in **stub
mode**:

- the full 3–22 graph executes
- all four human gates fire
- every deterministic service runs for real — feasibility, readiness,
  risk derivation, policy, composition, and the initial business case
- agentic steps return schema-valid placeholders marked `is_stub`

A deliberate first-deployment posture, not a degraded one: it proves
infrastructure, identity, networking and the whole orchestration
independently of model access.

When a key is available:

```powershell
az keyvault secret set --vault-name <kv> --name compass-api-key --value <key>
azd env set COMPASS_SECRET_NAME compass-api-key
azd provision
```

**No code change.**

---

## Registry network access

`allowRegistryPublicAccess` defaults to **true**, because a private-only
registry cannot be pushed to until Private DNS integration is complete.

Once it is, add a private endpoint and set the parameter to `false`.
Treat the default as a deliberate, temporary posture and record it as
such.

---

## Verifying

If the Container Apps environment is internal, reach it from a jumpbox
inside the VNet (Azure Bastion is the usual route). `azd` prints both
URLs after deployment.

```bash
curl https://<backend-fqdn>/api/health      # expect mode=stub
curl https://<backend-fqdn>/api/artifacts   # governed vs seed artifacts
```

Then open the frontend, submit a use case, and walk the four gates.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AuthorizationFailed` on role assignments | Missing User Access Administrator | Get the role, or have the platform team deploy |
| ACR name unavailable | Registry names are globally unique | Change `environmentName` |
| Container app stuck `Activating`, image pull fails | Container Apps subnet cannot reach the registry (NSG or UDR) | Check outbound rules; may need a private endpoint on ACR |
| `azd provision --preview` shows deletes | Something unexpected about the landing zone | **Stop** and investigate before applying |
| Remote build fails | ACR Tasks unavailable | azd falls back to local Docker automatically |

---

## Known limitations

Stated plainly so nothing is oversold:

- **Runs are held in memory.** A container restart loses in-flight runs.
  The Cosmos containers are created ahead of implementing the store so
  RBAC and connectivity are proven first; `PERSISTENCE_MODE` is `local`.
- **No authentication on the app.** Requirement 1 calls for Entra SSO
  with submitter / approver / admin roles. Not built. Acceptable only
  while ingress is internal.
- **Seven of eight governed artifacts are seeds.** Any derivation is
  provisional until the governed versions are delivered.
- **Stub mode until a model key is configured.** Agentic output is
  placeholder; deterministic output is real.
