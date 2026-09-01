# Centralized Jobs Monitoring

A real-time Databricks Jobs monitoring and anomaly detection dashboard that gives you a single pane of glass across all your workspaces. Deploy as a **Databricks App** — no infrastructure to manage, no VMs.

**Features:**
- Live job status, run history, and duration trends across one or many workspaces
- Statistical anomaly detection (duration spikes, failure rate, long-running jobs, missed schedules, consecutive failures)
- **Optional** AI-powered root-cause analysis and remediation steps (Claude via Databricks Foundation Models) — **disabled by default**, opt in with `ENABLE_AI_ANALYSIS=true`
- Email alerts for anomalies with severity filtering and auto-resolve notifications
- Multi-workspace view — monitor production, staging, and dev side-by-side

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Databricks workspace | Must support **Serverless** (for Databricks Apps) |
| Databricks CLI ≥ 0.229.0 | `databricks --version` |
| Python ≥ 3.11 + `uv` | `pip install uv` or see [uv docs](https://docs.astral.sh/uv/) |
| Node.js ≥ 18 | Only needed if you modify the frontend |

Install the Databricks CLI:
```bash
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

---

## Quick Start (5 minutes)

### 1. Clone the repository

```bash
git clone https://github.com/siddeshujjni/centralized_jobs_monitoring.git
cd centralized_jobs_monitoring
```

### 2. Authenticate the CLI

```bash
databricks auth login --host https://YOUR-WORKSPACE.cloud.databricks.com --profile myprofile
# Follow the OAuth browser flow
databricks auth env --profile myprofile  # verify it works
```

### 3. Configure `app.yaml`

Copy the example config and edit it (the real `app.yaml` is git-ignored so your
workspace URLs and tokens never get committed):

```bash
cp app.yaml.example app.yaml
```

Set at minimum:

```yaml
env:
  - name: APP_COMPANY_NAME
    value: "Your Company Name"     # shown in the sidebar and emails

  - name: WORKSPACE_URLS
    value: "https://YOUR-WORKSPACE.cloud.databricks.com"

  # AI analysis is optional and OFF by default. Leave "false" to run with
  # statistical anomaly detection only, or set "true" to enable Claude-powered
  # root-cause analysis (see "AI Analysis" below).
  - name: ENABLE_AI_ANALYSIS
    value: "false"
```

See [Configuration Reference](#configuration-reference) for all options.

### 4. Create the app

```bash
databricks apps create centralized-jobs-monitoring \
  --description "Real-time Jobs monitoring and anomaly detection" \
  --profile myprofile
```

### 5. Upload source code

```bash
# Upload everything except large local directories
databricks sync . /Workspace/Users/YOUR-EMAIL/centralized-jobs-monitoring \
  --exclude node_modules \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude .git \
  --exclude "frontend/src" \
  --exclude "frontend/public" \
  --profile myprofile
```

### 6. Deploy

```bash
databricks apps deploy centralized-jobs-monitoring \
  --source-code-path /Workspace/Users/YOUR-EMAIL/centralized-jobs-monitoring \
  --profile myprofile
```

Open the app URL printed in the output. Done.

---

## Multi-Workspace Setup

To monitor multiple workspaces simultaneously:

### 1. Update `app.yaml` workspace list

```yaml
- name: WORKSPACE_URLS
  value: "https://prod.cloud.databricks.com,https://dev.cloud.databricks.com"

# Optional display names (slug = hostname prefix, uppercased, dashes → underscores)
- name: WORKSPACE_NAME_PROD
  value: "Production"
- name: WORKSPACE_NAME_DEV
  value: "Development"
```

### 2. Create PAT tokens for each extra workspace

In each workspace you want to monitor (other than where the app is deployed):

1. Go to **Settings → Developer → Access Tokens**
2. Click **Generate new token** — give it a descriptive name, set expiry
3. Copy the token (`dapi...`)

### 3. Store PAT tokens securely (App Settings UI)

Do **not** put tokens in `app.yaml` (they would end up in source control).

After deployment, go to **Compute → Apps → centralized-jobs-monitoring → Edit** in the Databricks UI and add environment variables:

| Variable | Value |
|---|---|
| `WORKSPACE_TOKEN_PROD` | `dapi...` (token for prod workspace) |
| `WORKSPACE_TOKEN_DEV` | `dapi...` (token for dev workspace) |

The slug is the hostname prefix, uppercased with dashes replaced by underscores. For example:
- `https://my-production.cloud.databricks.com` → `WORKSPACE_TOKEN_MY_PRODUCTION`
- `https://e2-demo.cloud.databricks.com` → `WORKSPACE_TOKEN_E2_DEMO`

Redeploy after adding the tokens.

> **Note:** The workspace where the app is deployed does not need a PAT — it uses the app's service principal automatically.

---

## Email Alert Setup

Email alerts fire when anomalies are detected. They deduplicate (one email per anomaly until resolved) and send a follow-up when the issue clears.

### Configure via App Settings UI

After deployment, add these environment variables in **Compute → Apps → centralized-jobs-monitoring → Edit**:

| Variable | Description | Example |
|---|---|---|
| `ALERT_EMAIL_TO` | Comma-separated recipient addresses | `ops@yourcompany.com,oncall@yourcompany.com` |
| `ALERT_EMAIL_FROM` | Sender address | `databricks-monitor@yourcompany.com` |
| `SMTP_HOST` | SMTP server | `smtp.office365.com` |
| `SMTP_PORT` | SMTP port (usually 587) | `587` |
| `SMTP_USER` | SMTP login username | `databricks-monitor@yourcompany.com` |
| `SMTP_PASSWORD` | SMTP password or app password | `your-app-password` |
| `ALERT_MIN_SEVERITY` | Minimum severity to alert on | `medium` (low/medium/high/critical) |
| `ALERT_POLL_INTERVAL` | Seconds between checks | `300` (5 minutes) |
| `APP_URL` | Public URL of this app (for dashboard links in emails) | `https://your-app.databricksapps.com` |

### Gmail setup

1. Enable **2-Step Verification** on the Gmail account
2. Generate an **App Password**: Google Account → Security → App Passwords
3. Use `smtp.gmail.com`, port `587`, the app password as `SMTP_PASSWORD`

### Office 365 / Exchange setup

Use `smtp.office365.com`, port `587`, your O365 credentials.
Some tenants require SMTP AUTH to be explicitly enabled — check with your IT team.

### Test the configuration

After deployment, click **Send Test Alert** in the dashboard, or call the API:
```bash
curl -X POST https://YOUR-APP-URL.databricksapps.com/api/alerts/test
```

---

## AI Analysis (Optional — OFF by default)

> **Important:** Everything AI-related in this app is **optional and disabled by
> default.** No large language model is called unless an operator explicitly sets
> `ENABLE_AI_ANALYSIS=true`. With the flag unset or `false`, the app performs
> **zero** LLM calls and is fully functional — live job status, run history, all
> five statistical anomaly detectors, email alerts, and the multi-workspace view
> all work with no AI involved.

When enabled, AI adds a health score, root-cause explanation, remediation steps,
and predictive alerts on top of the statistical detectors, using Claude via the
Databricks Foundation Model API.

### How the feature is gated (single switch, enforced in three places)

`ENABLE_AI_ANALYSIS` is the one and only control. It is enforced at three layers,
so there is no path to an LLM call while it is off:

| Layer | File | Behavior when OFF |
|---|---|---|
| Config flag (source of truth) | `server/config.py` (`AI_ANALYSIS_ENABLED`) | Reads `ENABLE_AI_ANALYSIS`; default `False` |
| Backend guard | `server/routes/ai.py` (`_ensure_ai_enabled`) | `/api/ai/*` returns **404**; no prompt is built and `server/llm.py` is never reached |
| Frontend | `Dashboard.tsx`, `JobDetail.tsx` | AI panels are not rendered at all |

### Data handling when it IS enabled (for security review)

- **Stays inside your Databricks boundary.** The request goes to the Foundation
  Model endpoint in **your own Databricks workspace** (`server/llm.py` →
  `{host}/serving-endpoints`). It is **not** sent to any third-party or external
  API, and no API keys to outside providers are used.
- **What is sent:** job *metadata and run metrics only* — job name, schedule,
  status, creator, run durations, success rate, timestamps, detected-anomaly
  messages, and recent run states. See the exact prompt in
  `server/ai_analysis.py`.
- **What is NOT sent:** dataset contents, notebook/job source code, query
  results, or any row-level/PII data processed by the jobs.
- **Access control:** the model is only callable if the app's service principal
  is granted **Can Query** on the serving endpoint — a separate, explicit grant.
- **Kill switch:** set `ENABLE_AI_ANALYSIS=false` (or remove it) and redeploy;
  the AI endpoints immediately return 404 again.
- For your compliance sign-off, review Databricks' Foundation Model API data-use
  terms for the endpoint you choose.

### Enable it

1. Set `ENABLE_AI_ANALYSIS=true` in `app.yaml` (or the App Settings UI).
2. Make sure `SERVING_ENDPOINT` points to a Foundation Model endpoint enabled in
   your workspace (default: `databricks-claude-sonnet-4-5`).
3. Grant the app's service principal **Can Query** on that serving endpoint.
4. Redeploy.

When enabled, an **"AI Analysis"** panel appears on each job detail page and a
**"Workspace AI Health Check"** appears on the dashboard. When disabled, those
panels are hidden and the `/api/ai/*` endpoints return `404`.

### Available Foundation Model endpoints

| Model | Endpoint name | Notes |
|---|---|---|
| Claude Sonnet 4.5 | `databricks-claude-sonnet-4-5` | Recommended — best balance |
| Claude Opus 4.5 | `databricks-claude-opus-4-5` | Higher quality, more tokens |
| Llama 3.3 70B | `databricks-meta-llama-3-3-70b-instruct` | Cost-effective alternative |

---

## Configuration Reference

All configuration is done via environment variables in `app.yaml` or the Databricks App Settings UI.

| Variable | Default | Description |
|---|---|---|
| `APP_COMPANY_NAME` | `Databricks` | Company name shown in the sidebar and emails |
| `ENABLE_AI_ANALYSIS` | `false` | **Optional.** Set `true` to enable Claude-powered AI analysis. When `false`, AI endpoints are unavailable and AI panels are hidden — statistical anomaly detection still runs. |
| `SERVING_ENDPOINT` | `databricks-claude-sonnet-4-5` | Foundation Model endpoint for AI analysis (only used when `ENABLE_AI_ANALYSIS=true`) |
| `WORKSPACE_URLS` | _(required)_ | Comma-separated workspace URLs to monitor |
| `WORKSPACE_NAME_<SLUG>` | _(slug value)_ | Display name for a workspace |
| `WORKSPACE_TOKEN_<SLUG>` | _(none)_ | PAT for a specific workspace (set via UI) |
| `ALERT_EMAIL_TO` | _(none — alerts disabled)_ | Recipient email addresses |
| `ALERT_EMAIL_FROM` | SMTP_USER value | Sender address |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | _(none)_ | SMTP login username |
| `SMTP_PASSWORD` | _(none)_ | SMTP password (set via UI, not app.yaml) |
| `ALERT_MIN_SEVERITY` | `medium` | Minimum anomaly severity for email alerts |
| `ALERT_POLL_INTERVAL` | `300` | Seconds between alert checks |
| `APP_URL` | _(none)_ | App public URL (for links in alert emails) |

(Foundation Model endpoint options are listed under the **AI Analysis** section above.)

---

## Local Development

### 1. Install Python dependencies

```bash
uv sync
# or: pip install -r requirements.txt
```

### 2. Configure local credentials

```bash
# Option A: use your default Databricks CLI profile
export DATABRICKS_PROFILE=DEFAULT

# Option B: use a named profile
export DATABRICKS_PROFILE=myprofile

# Option C: use a PAT directly
export DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
export DATABRICKS_TOKEN=dapi...
```

For multi-workspace local testing, use the `DATABRICKS_PROFILES` variable:
```bash
export DATABRICKS_PROFILES=DEFAULT,prod-profile,dev-profile
```

### 3. Start the backend

```bash
export APP_COMPANY_NAME="Your Company"
uv run python app.py
# Backend runs on http://localhost:8000
```

### 4. Start the frontend (optional, for development)

```bash
cd frontend
npm install
npm run dev
# Frontend runs on http://localhost:5173 with proxy to backend
```

Or just open `http://localhost:8000` — the backend serves the pre-built frontend.

---

## Updating

After making code changes, re-sync and redeploy:

```bash
# 1. Re-sync source files
databricks sync . /Workspace/Users/YOUR-EMAIL/centralized-jobs-monitoring \
  --exclude node_modules --exclude .venv --exclude __pycache__ \
  --exclude .git --exclude "frontend/src" --exclude "frontend/public" \
  --profile myprofile

# 2. If you changed frontend source, rebuild first:
cd frontend && npm run build && cd ..

# 3. Redeploy
databricks apps deploy centralized-jobs-monitoring \
  --source-code-path /Workspace/Users/YOUR-EMAIL/centralized-jobs-monitoring \
  --profile myprofile
```

> **Important:** After each sync, re-upload `app.yaml` via the App Settings UI if it contains tokens, or use a separate `app_with_secrets.yaml` file that is **not** in source control.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Databricks App Container                       │
│                                                                      │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐   │
│  │  React SPA   │───▶│              FastAPI (Python)             │   │
│  │  (pre-built) │    │                                          │   │
│  └──────────────┘    │  /api/dashboard/summary  (cache-first)   │   │
│                      │  /api/jobs  /api/anomalies               │   │
│                      │  /api/multi/jobs         (cache-first)   │   │
│                      │  /api/ai/...             (optional)       │   │
│                      │  /api/alerts/...                         │   │
│                      │  /api/cache/status                       │   │
│                      └──────┬───────────────────────────────────┘   │
│                             │                                        │
│                    ┌────────┴────────┐                              │
│                    │                 │                              │
│          ┌─────────▼──────┐  ┌──────▼──────────────────────┐      │
│          │  Background     │  │  Live Databricks SDK calls  │      │
│          │  Poller (60s)   │  │  (fallback when cache miss) │      │
│          └─────────┬──────┘  └──────────────────────────────┘      │
│                    │  writes                                         │
│          ┌─────────▼──────────────┐                                 │
│          │  Lakebase (PostgreSQL) │  ← asyncpg, OAuth token auth   │
│          │  • jobs table          │                                 │
│          │  • job_runs table      │                                 │
│          │  • workspace_sync      │                                 │
│          └────────────────────────┘                                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                        │  Databricks SDK (PAT / SP OAuth)
         ┌──────────────┼──────────────────────────┐
         ▼              ▼                           ▼
  Workspace A     Workspace B              Foundation Model API
  (Jobs API)      (Jobs API)               (Claude — AI analysis, optional)
```

**Data flow:**
1. **Background poller** (`server/poller.py`) syncs all workspaces → Lakebase every 60 s
2. **API routes** read from Lakebase first (`data_source: "cache"`, <500 ms) and fall back to live Databricks API when cache is empty or stale
3. **OAuth token** for Lakebase is obtained from the app's service principal (SP has `CAN_CONNECT` on the database) and refreshed every 45 min

**Backend** (`server/`):
- `workspaces.py` — multi-workspace discovery and client management
- `jobs.py` — Databricks Jobs API data access
- `anomaly.py` — statistical anomaly detection (z-score, rolling averages)
- `ai_analysis.py` — Claude-powered health scores and remediation steps (optional; gated by `ENABLE_AI_ANALYSIS`)
- `alerts.py` — background email alert engine
- `llm.py` — Foundation Model API client
- `db.py` — Lakebase connection pool, schema, CRUD helpers
- `poller.py` — background async sync loop

**Frontend** (`frontend/src/`):
- `pages/Dashboard.tsx` — single-workspace view
- `pages/MultiWorkspace.tsx` — cross-workspace aggregated view
- `pages/JobDetail.tsx` — per-job run history and AI insights
- `pages/Anomalies.tsx` — anomaly explorer

---

## Anomaly Detection

Five detectors run on each job's last 20 runs:

| Detector | Triggers when | Severity |
|---|---|---|
| **Duration spike** | Current run > mean + 2× stddev | medium → high |
| **High failure rate** | >30% of recent runs failed | medium → critical |
| **Long running** | Job still running beyond P95 duration | medium → high |
| **Missed schedule** | Scheduled job hasn't run in 2× its interval | medium → high |
| **Consecutive failures** | 2+ runs failed in a row | high → critical |

---

## Troubleshooting

**App shows "Connection error" for a workspace**

Check that `WORKSPACE_TOKEN_<SLUG>` is set correctly in App Settings. The slug must exactly match the hostname prefix (uppercased, dashes→underscores).

**"More than one authorization method configured"**

This happens when Databricks auto-injects M2M credentials and you also provide a PAT. The app handles this automatically by temporarily suppressing the injected credentials. If you still see this, ensure you're on the latest version of this code.

**AI panels don't appear / `/api/ai/*` returns 404**

AI analysis is optional and off by default. Set `ENABLE_AI_ANALYSIS=true` and redeploy.

**AI analysis returns "Analysis unavailable"**

1. Confirm `ENABLE_AI_ANALYSIS=true` is set
2. Verify `SERVING_ENDPOINT` matches an endpoint enabled in your workspace
3. Check the app logs: `https://YOUR-APP-URL.databricksapps.com/logz`
4. Ensure the app's service principal has **Can Query** permission on the serving endpoint

**Emails not sending**

1. Use **Send Test Alert** in the dashboard to test SMTP connectivity
2. Check logs at `/logz` for SMTP error details
3. Gmail: use an App Password, not your account password
4. O365: confirm SMTP AUTH is enabled for the sender account

**Viewing application logs**

Append `/logz` to your app URL:
```
https://your-app-xxxx.databricksapps.com/logz
```
