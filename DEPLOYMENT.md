# Deployment

Deploys onto an existing **AI Landing Zone**. Landing-zone resources are
referenced, never recreated.

Tenant-specific values live in `infra/main.parameters.json` and
`DEPLOYMENT.local.md`, both gitignored.

---

## Prerequisites

| Requirement | Why |
|---|---|
| Azure CLI + Bicep | Templates and deployment |
| **Contributor _and_ User Access Administrator** on the resource group | The template creates role assignments |
| An AI Landing Zone already deployed | Container Apps Environment, Cosmos, Key Vault, AI Search, App Insights |
| Private DNS Zones for the landing zone's private endpoints | Without them, private endpoint names do not resolve |

No local Docker daemon is needed — images build server-side via **ACR
Tasks**.

---

## Sequence

```powershell
# 1 · Resolve landing-zone resource names (read-only; writes main.parameters.json)
./scripts/discover-resources.ps1 -SubscriptionId <guid> -ResourceGroup <rg>

# 2 · Preview. Changes nothing.
./scripts/deploy.ps1 -SubscriptionId <guid> -ResourceGroup <rg> -WhatIf

# 3 · Deploy
./scripts/deploy.ps1 -SubscriptionId <guid> -ResourceGroup <rg>
```

Review the what-if output before step 3.

---

## What gets created

- Container Registry (Standard)
- Two user-assigned managed identities — **no shared account**, per v2.5
- Cosmos database `intake` with `design-packs` and `checkpoints`
- Two container apps: backend (internal ingress) and frontend
- Role assignments: AcrPull, Key Vault Secrets User, Search Index Data
  Reader, Cosmos Data Contributor

---

## Deploying without a model key

`compassSecretName` defaults to empty. The backend then runs in **stub
mode**:

- the full 3–22 graph executes
- all four human gates fire
- every deterministic service runs for real — feasibility, readiness,
  risk derivation, policy, composition, and the initial business case
- agentic steps return schema-valid placeholders marked `is_stub`

This is a deliberate first-deployment posture, not a degraded one: it
proves infrastructure, identity, networking and the whole orchestration
independently of model access.

When a key is available:

```powershell
az keyvault secret set --vault-name <kv> --name compass-api-key --value <key>
```

Set `compassSecretName` to `compass-api-key` in
`infra/main.parameters.json` and redeploy. **No code change.**

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
inside the VNet (Azure Bastion is the usual route):

```bash
curl https://<backend-fqdn>/api/health      # expect mode=stub
curl https://<backend-fqdn>/api/artifacts   # lists governed vs seed artifacts
```

Then open the frontend, submit a use case, and walk the four gates.

---

## Known limitations

Stated plainly so nothing is oversold:

- **Runs are held in memory.** A container restart loses in-flight runs.
  The Cosmos containers are created ahead of implementing the store so
  RBAC and connectivity are proven first. `PERSISTENCE_MODE` is therefore
  `local`.
- **No authentication on the app.** Requirement 1 calls for Entra SSO
  with submitter / approver / admin roles. Not built. Acceptable only
  while ingress is internal.
- **Seven of eight governed artifacts are seeds.** Any derivation is
  provisional until the governed versions are delivered.
- **Stub mode until a model key is configured.** Agentic output is
  placeholder; deterministic output is real.
