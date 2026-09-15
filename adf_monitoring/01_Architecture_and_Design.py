# Databricks notebook source
# DBTITLE 1,Executive Summary
# MAGIC %md
# MAGIC # Track Azure Data Factory Jobs in Databricks
# MAGIC
# MAGIC ## Executive Summary
# MAGIC
# MAGIC This solution enables Databricks to **monitor ADF-native pipeline and activity executions** by polling the Azure Data Factory Management REST API on a recurring schedule. It captures pipeline runs, activity runs, statuses, durations, errors, and metadata into Delta tables, then exposes them through Databricks SQL dashboards and alerts.
# MAGIC
# MAGIC **What this tracks:** Copy activities, Mapping Data Flows, Stored Procedures, Execute Pipeline, Azure Functions, Web activities, and all other ADF-native activity types. This does **not** track Databricks jobs triggered by ADF — those are out of scope.
# MAGIC
# MAGIC **Key design decisions:**
# MAGIC * **Source of truth:** ADF Management REST API (`queryPipelineRuns`, `queryActivityRuns`)
# MAGIC * **Authentication:** Azure Managed Identity (preferred) or Service Principal with secrets in Databricks Secret Scope
# MAGIC * **Ingestion pattern:** Incremental polling every 1–5 minutes with lookback window; MERGE for idempotency
# MAGIC * **Data model:** Bronze (raw JSON) → Silver (normalized pipeline/activity runs) → Gold (dashboards/views)
# MAGIC * **Presentation:** Databricks SQL dashboard with alerts for failures, SLA breaches, and stuck runs
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Architecture Diagram
# MAGIC
# MAGIC ```
# MAGIC ┌─────────────────────────────────────────────────────────────────────────────────────────┐
# MAGIC │                              END-TO-END ARCHITECTURE                                    │
# MAGIC └─────────────────────────────────────────────────────────────────────────────────────────┘
# MAGIC
# MAGIC ┌──────────────┐     REST API (HTTPS)     ┌──────────────────────────────┐
# MAGIC │              │◄─────────────────────────│                              │
# MAGIC │  Azure Data  │  queryPipelineRuns       │   Databricks Notebook        │
# MAGIC │  Factory     │  queryActivityRuns       │   (Scheduled every 1-5 min)  │
# MAGIC │  (1..N       │─────────────────────────►│                              │
# MAGIC │   factories) │  JSON responses          │  ┌────────────────────────┐  │
# MAGIC │              │                          │  │ 1. Authenticate (MI/SP)│  │
# MAGIC └──────────────┘                          │  │ 2. Poll pipeline runs  │  │
# MAGIC        │                                  │  │ 3. Poll activity runs  │  │
# MAGIC        │                                  │  │ 4. Handle pagination   │  │
# MAGIC        │  Azure Resource Manager          │  │ 5. Retry on errors     │  │
# MAGIC        │  (/subscriptions/...)            │  │ 6. Write to Delta      │  │
# MAGIC        ▼                                  │  └────────────────────────┘  │
# MAGIC ┌──────────────┐                          └──────────────┬───────────────┘
# MAGIC │  Azure AD /  │                                         │
# MAGIC │  Entra ID    │  OAuth2 token                           │
# MAGIC │  (auth)      │─────────────────────────────────────────┘
# MAGIC └──────────────┘                                         │
# MAGIC                                                          │ Spark / Delta writes
# MAGIC                                                          ▼
# MAGIC ┌─────────────────────────────────────────────────────────────────────────────────────────┐
# MAGIC │                              Unity Catalog (Delta Tables)                                │
# MAGIC │                                                                                         │
# MAGIC │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
# MAGIC │  │  BRONZE              │  │  SILVER              │  │  GOLD                           │  │
# MAGIC │  │                     │  │                     │  │                                 │  │
# MAGIC │  │  raw_adf_api_       │  │  adf_pipeline_runs  │  │  v_current_running_pipelines    │  │
# MAGIC │  │  responses          │  │  adf_activity_runs  │  │  v_current_running_activities   │  │
# MAGIC │  │  (JSON payload,     │  │  (normalized,       │  │  v_failed_runs_24h              │  │
# MAGIC │  │   audit metadata)   │  │   typed columns,    │  │  v_pipeline_sla_status          │  │
# MAGIC │  │                     │  │   merge keys)       │  │  adf_pipeline_sla_config        │  │
# MAGIC │  └─────────────────────┘  └─────────────────────┘  └─────────────────────────────────┘  │
# MAGIC │                                                                                         │
# MAGIC └─────────────────────────────────────────────────────────────────────────────────────────┘
# MAGIC                                          │
# MAGIC                                          ▼
# MAGIC ┌─────────────────────────────────────────────────────────────────────────────────────────┐
# MAGIC │                              Presentation Layer                                         │
# MAGIC │                                                                                         │
# MAGIC │  ┌──────────────────────────┐   ┌──────────────────────────────────────────────────┐    │
# MAGIC │  │  Databricks SQL Dashboard │   │  Databricks SQL Alerts                          │    │
# MAGIC │  │                          │   │                                                  │    │
# MAGIC │  │  • Current running       │   │  • Pipeline failure alert                        │    │
# MAGIC │  │  • Failed pipelines      │   │  • Activity failure alert                        │    │
# MAGIC │  │  • Long-running          │   │  • SLA breach alert                              │    │
# MAGIC │  │  • Historical trends     │   │  • Stuck run alert (no update > N min)           │    │
# MAGIC │  │  • Failure rates         │   │  • Unusual failure rate alert                    │    │
# MAGIC │  │  • Duration analysis     │   │                                                  │    │
# MAGIC │  └──────────────────────────┘   └──────────────────────────────────────────────────┘    │
# MAGIC │                                                                                         │
# MAGIC └─────────────────────────────────────────────────────────────────────────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Design Decisions and Assumptions
# MAGIC
# MAGIC ### Design Decisions
# MAGIC
# MAGIC | Decision | Rationale |
# MAGIC | --- | --- |
# MAGIC | Poll ADF REST API (not Azure Monitor / Log Analytics) | Direct API gives real-time status; Log Analytics has 5-15 min ingestion delay |
# MAGIC | MERGE (upsert) instead of append | Runs change status (InProgress → Succeeded/Failed); must update in place |
# MAGIC | Lookback window (default 30 min) | ADF status updates can be delayed; lookback catches late updates |
# MAGIC | Store raw JSON in bronze | Full API response preserved for troubleshooting and schema evolution |
# MAGIC | Multi-factory support via widget parameters | Single notebook serves dev/staging/prod ADF factories |
# MAGIC | UTC internally, business TZ in views only | Avoids ambiguity; consistent merge keys |
# MAGIC | Managed Identity preferred over Service Principal | No secrets to rotate; better security posture |
# MAGIC | 1-5 minute polling interval | Balances freshness vs API quota (ADF allows ~200 calls/min) |
# MAGIC
# MAGIC ### Assumptions
# MAGIC
# MAGIC * ADF factories are in the same Azure tenant as the Databricks workspace (or cross-tenant auth is configured)
# MAGIC * The Databricks workspace has network connectivity to Azure management endpoints (`management.azure.com`)
# MAGIC * Unity Catalog is enabled on the target Databricks workspace
# MAGIC * The polling notebook runs on a job cluster or serverless compute
# MAGIC * ADF API version `2018-06-01` is current and stable (validate against [Microsoft docs](https://learn.microsoft.com/en-us/rest/api/datafactory/))
# MAGIC * ADF API rate limit is approximately 200 requests per minute per factory (validate for your subscription tier)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Authentication and Permissions
# MAGIC
# MAGIC ### Recommended: Azure Managed Identity (Production)
# MAGIC
# MAGIC **Configuration steps:**
# MAGIC 1. The Databricks workspace must be deployed with a system-assigned or user-assigned managed identity
# MAGIC 2. Grant the managed identity **Reader** role on each ADF factory resource (minimum required)
# MAGIC 3. For API access, the identity also needs **Data Factory Contributor** or a custom role with `Microsoft.DataFactory/factories/pipelineruns/read` and `Microsoft.DataFactory/factories/pipelineruns/activityruns/read`
# MAGIC
# MAGIC **Required RBAC permissions (minimum custom role):**
# MAGIC ```json
# MAGIC {
# MAGIC   "permissions": [
# MAGIC     {
# MAGIC       "actions": [
# MAGIC         "Microsoft.DataFactory/factories/pipelineruns/read",
# MAGIC         "Microsoft.DataFactory/factories/pipelineruns/queryPipelineRuns/action",
# MAGIC         "Microsoft.DataFactory/factories/pipelineruns/activityruns/read",
# MAGIC         "Microsoft.DataFactory/factories/pipelineruns/queryActivityruns/action",
# MAGIC         "Microsoft.DataFactory/factories/read"
# MAGIC       ],
# MAGIC       "notActions": [],
# MAGIC       "dataActions": [],
# MAGIC       "notDataActions": []
# MAGIC     }
# MAGIC   ]
# MAGIC }
# MAGIC ```
# MAGIC
# MAGIC ### Alternative: Service Principal (Development or Cross-Tenant)
# MAGIC
# MAGIC **Configuration steps:**
# MAGIC 1. Register an App in Azure AD / Entra ID
# MAGIC 2. Create a client secret (rotate every 90 days max)
# MAGIC 3. Grant the same RBAC roles as above on each ADF factory
# MAGIC 4. Store credentials in a Databricks Secret Scope:
# MAGIC    * `adf-monitor/tenant-id`
# MAGIC    * `adf-monitor/client-id`
# MAGIC    * `adf-monitor/client-secret`
# MAGIC 5. Never hard-code credentials in notebooks
# MAGIC
# MAGIC ### Network Requirements
# MAGIC
# MAGIC * Outbound HTTPS (443) to `management.azure.com` and `login.microsoftonline.com`
# MAGIC * If using Private Link, ensure the Databricks workspace can reach Azure management endpoints
# MAGIC * No inbound connectivity required
# MAGIC
# MAGIC ### Access Restriction
# MAGIC
# MAGIC * Scope RBAC assignments to specific ADF factory resources, not the entire subscription
# MAGIC * Use Azure Policy to prevent privilege escalation
# MAGIC * Audit access via Azure Activity Log
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Documentation Links
# MAGIC
# MAGIC | Resource | URL |
# MAGIC | --- | --- |
# MAGIC | ADF Pipeline Runs - Query | https://learn.microsoft.com/en-us/rest/api/datafactory/pipeline-runs/query-by-factory |
# MAGIC | ADF Activity Runs - Query | https://learn.microsoft.com/en-us/rest/api/datafactory/activity-runs/query-by-pipeline-run |
# MAGIC | ADF REST API Reference | https://learn.microsoft.com/en-us/rest/api/datafactory/ |
# MAGIC | Managed Identity for Databricks | https://learn.microsoft.com/en-us/azure/databricks/dev-tools/auth/ |
# MAGIC | Databricks Secret Scopes | https://docs.databricks.com/security/secrets/secret-scopes.html |
# MAGIC | Unity Catalog | https://docs.databricks.com/data-governance/unity-catalog/ |