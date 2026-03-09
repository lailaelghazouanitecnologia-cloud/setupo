# Deploy Debian 12 on Vultr

Validated from the Vultr API on 2026-03-09:

- OS: `Debian 12 x64 (bookworm)` -> `2136`
- 4 vCPU plan: `vc2-4c-8gb`

Recommended flow for this branch:

1. Export the required secrets in your local shell.
2. Render the bootstrap script:

```powershell
$env:NSO_ADMIN_EMAIL="..."
$env:NSO_ADMIN_PASSWORD="..."
$env:AGENT_ADMIN_PASSWORD="..."
$env:VULTR_API_KEY="..."
$env:CF_API_TOKEN="..."
$env:CF_NSO_ZONE_ID="..."
$env:R2_ENDPOINT="..."
$env:R2_ACCESS_KEY_ID="..."
$env:R2_SECRET_ACCESS_KEY="..."

powershell -ExecutionPolicy Bypass -File .\deploy\render-cloud-init.ps1 -RepoBranch "claude/analyze-schemas-organization-EviP7" -NsoDomain "nso.dev"
```

3. Create the VPS in Vultr with:

- Type: `Cloud Compute`
- Region: pick the nearest region for your users
- Plan: `vc2-4c-8gb`
- OS: `Debian 12 x64 (bookworm)`
- User data: paste the contents of `deploy/out/cloud-init-rendered.sh`

4. After the server boots, verify:

```bash
systemctl status nso
systemctl status nso-agent
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8081/health
```

Notes:

- The script builds both Next.js frontends on the VPS and installs nginx, certbot, Python, and Node.
- It deploys the central API on `:8000`, the agent on `:8081`, dashboard on `/`, and admin on `sonfazt.<domain>`.
- Do not commit anything under `deploy/out/`; that output contains secrets.
