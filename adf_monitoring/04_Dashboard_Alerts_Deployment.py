# Databricks notebook source
# DBTITLE 1,Dashboard Design Specification
# MAGIC %md
# MAGIC # Dashboard, Alerts, Deployment & Testing
# MAGIC
# MAGIC ## Dashboard Design: "ADF Operations Monitor"
# MAGIC
# MAGIC ### Page 1: Current Operations
# MAGIC
# MAGIC | Widget | Type | Data Source |
# MAGIC | --- | --- | --- |
# MAGIC | Active Pipeline Count | Counter | `v_current_running_pipelines WHERE status = 'InProgress'` |
# MAGIC | Queued Pipeline Count | Counter | `v_current_running_pipelines WHERE status = 'Queued'` |
# MAGIC | Failed (Last 1h) | Counter | `v_failed_runs_24h WHERE run_end >= now() - 1h` |
# MAGIC | SLA Breached | Counter | `v_current_running_pipelines WHERE sla_status = 'SLA_BREACHED'` |
# MAGIC | Currently Running Pipelines | Table | `v_current_running_pipelines` (factory, pipeline, status, elapsed_minutes, sla_status, trigger) |
# MAGIC | Currently Running Activities | Table | `v_current_running_activities` (factory, pipeline, activity, type, status, elapsed_minutes) |
# MAGIC | Stuck Runs | Table | `v_current_running_pipelines WHERE is_possibly_stuck = TRUE` |
# MAGIC
# MAGIC ### Page 2: Failures & Errors
# MAGIC
# MAGIC | Widget | Type | Data Source |
# MAGIC | --- | --- | --- |
# MAGIC | Failed Pipelines (24h) | Table | `v_failed_runs_24h WHERE run_type = 'Pipeline'` |
# MAGIC | Failed Activities (24h) | Table | `v_failed_runs_24h WHERE run_type = 'Activity'` |
# MAGIC | Failure Rate by Pipeline | Bar Chart | `adf_pipeline_runs` grouped by pipeline_name, % failed |
# MAGIC | Failure Rate by Activity Type | Bar Chart | `adf_activity_runs` grouped by activity_type, % failed |
# MAGIC | Error Message Distribution | Table | Top 20 error messages by frequency |
# MAGIC | Failures Over Time | Line Chart | Daily failure count, 30-day trend |
# MAGIC
# MAGIC ### Page 3: Performance & SLA
# MAGIC
# MAGIC | Widget | Type | Data Source |
# MAGIC | --- | --- | --- |
# MAGIC | SLA Status Summary | Table | `v_pipeline_sla_status` |
# MAGIC | Long-Running Pipelines | Table | Top 20 longest pipelines (current day) |
# MAGIC | Avg Duration by Pipeline | Bar Chart | `adf_pipeline_runs` avg duration_ms grouped by pipeline_name |
# MAGIC | P50/P95/P99 Duration | Table | Percentile durations per pipeline (7d window) |
# MAGIC | Duration Trend | Line Chart | Daily avg duration per top pipeline |
# MAGIC
# MAGIC ### Page 4: Historical Trends
# MAGIC
# MAGIC | Widget | Type | Data Source |
# MAGIC | --- | --- | --- |
# MAGIC | Daily Execution Volume | Bar Chart | Pipeline runs per day (30d) |
# MAGIC | Executions by Status | Stacked Bar | Daily runs split by status |
# MAGIC | Executions by Factory | Bar Chart | If multi-factory, runs per factory |
# MAGIC | Trigger Comparison | Bar Chart | Runs by trigger_type |
# MAGIC | Hourly Heatmap | Heatmap | Runs by hour-of-day and day-of-week |
# MAGIC
# MAGIC ### Filters (all pages)
# MAGIC * Factory name
# MAGIC * Pipeline name
# MAGIC * Status
# MAGIC * Date range
# MAGIC * Environment (if using SLA config)

# COMMAND ----------

# DBTITLE 1,Alert SQL Queries
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- ALERT 1: Pipeline Failure (trigger on any failed pipeline)
# MAGIC -- Schedule: every 2 minutes
# MAGIC -- Condition: failure_count > 0
# MAGIC -- ================================================================
# MAGIC SELECT 
# MAGIC     COUNT(*) AS failure_count,
# MAGIC     COLLECT_LIST(CONCAT(factory_name, '.', pipeline_name)) AS failed_pipelines
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs
# MAGIC WHERE status = 'Failed'
# MAGIC   AND run_end >= current_timestamp() - INTERVAL 5 MINUTES;
# MAGIC
# MAGIC -- ================================================================
# MAGIC -- ALERT 2: Activity Failure
# MAGIC -- Schedule: every 2 minutes  
# MAGIC -- Condition: failure_count > 0
# MAGIC -- ================================================================
# MAGIC -- SELECT 
# MAGIC --     COUNT(*) AS failure_count,
# MAGIC --     COLLECT_LIST(DISTINCT CONCAT(pipeline_name, '.', activity_name)) AS failed_activities
# MAGIC -- FROM <CATALOG>.<SCHEMA>.adf_activity_runs
# MAGIC -- WHERE status = 'Failed'
# MAGIC --   AND activity_run_end >= current_timestamp() - INTERVAL 5 MINUTES;
# MAGIC
# MAGIC -- ================================================================
# MAGIC -- ALERT 3: SLA Breach
# MAGIC -- Schedule: every 5 minutes
# MAGIC -- Condition: breach_count > 0
# MAGIC -- ================================================================
# MAGIC -- SELECT COUNT(*) AS breach_count
# MAGIC -- FROM <CATALOG>.<SCHEMA>.v_current_running_pipelines
# MAGIC -- WHERE sla_status = 'SLA_BREACHED';
# MAGIC
# MAGIC -- ================================================================
# MAGIC -- ALERT 4: Stuck Runs (no update for >30 min while InProgress)
# MAGIC -- Schedule: every 5 minutes
# MAGIC -- Condition: stuck_count > 0
# MAGIC -- ================================================================
# MAGIC -- SELECT COUNT(*) AS stuck_count
# MAGIC -- FROM <CATALOG>.<SCHEMA>.v_current_running_pipelines
# MAGIC -- WHERE is_possibly_stuck = TRUE;
# MAGIC
# MAGIC -- ================================================================
# MAGIC -- ALERT 5: Unusual Failure Rate (>20% failure in last hour)
# MAGIC -- Schedule: every 15 minutes
# MAGIC -- Condition: failure_rate > 0.20
# MAGIC -- ================================================================
# MAGIC -- SELECT 
# MAGIC --     ROUND(
# MAGIC --         SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) * 1.0 / 
# MAGIC --         NULLIF(COUNT(*), 0), 2
# MAGIC --     ) AS failure_rate
# MAGIC -- FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs
# MAGIC -- WHERE run_start >= current_timestamp() - INTERVAL 1 HOUR;

# COMMAND ----------

# DBTITLE 1,Dashboard Sample Queries
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- DASHBOARD QUERIES (sample SQL for dashboard widgets)
# MAGIC -- ================================================================
# MAGIC
# MAGIC -- Daily execution volume (30 days)
# MAGIC SELECT 
# MAGIC     DATE(run_start) AS run_date,
# MAGIC     COUNT(*) AS total_runs,
# MAGIC     SUM(CASE WHEN status = 'Succeeded' THEN 1 ELSE 0 END) AS succeeded,
# MAGIC     SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failed,
# MAGIC     SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs
# MAGIC WHERE run_start >= current_timestamp() - INTERVAL 30 DAYS
# MAGIC GROUP BY DATE(run_start)
# MAGIC ORDER BY run_date;
# MAGIC
# MAGIC -- -- Average and percentile duration by pipeline (7 days)
# MAGIC -- SELECT 
# MAGIC --     pipeline_name,
# MAGIC --     COUNT(*) AS run_count,
# MAGIC --     ROUND(AVG(duration_ms) / 60000.0, 1) AS avg_duration_min,
# MAGIC --     ROUND(PERCENTILE(duration_ms, 0.5) / 60000.0, 1) AS p50_min,
# MAGIC --     ROUND(PERCENTILE(duration_ms, 0.95) / 60000.0, 1) AS p95_min,
# MAGIC --     ROUND(PERCENTILE(duration_ms, 0.99) / 60000.0, 1) AS p99_min
# MAGIC -- FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs
# MAGIC -- WHERE status = 'Succeeded'
# MAGIC --   AND run_start >= current_timestamp() - INTERVAL 7 DAYS
# MAGIC -- GROUP BY pipeline_name
# MAGIC -- ORDER BY avg_duration_min DESC;
# MAGIC
# MAGIC -- -- Failure rate by pipeline (7 days)
# MAGIC -- SELECT
# MAGIC --     pipeline_name,
# MAGIC --     COUNT(*) AS total_runs,
# MAGIC --     SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failures,
# MAGIC --     ROUND(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS failure_pct
# MAGIC -- FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs
# MAGIC -- WHERE run_start >= current_timestamp() - INTERVAL 7 DAYS
# MAGIC -- GROUP BY pipeline_name
# MAGIC -- HAVING COUNT(*) >= 5
# MAGIC -- ORDER BY failure_pct DESC;
# MAGIC
# MAGIC -- -- Failure rate by activity type (7 days)
# MAGIC -- SELECT
# MAGIC --     activity_type,
# MAGIC --     COUNT(*) AS total_runs,
# MAGIC --     SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failures,
# MAGIC --     ROUND(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS failure_pct
# MAGIC -- FROM <CATALOG>.<SCHEMA>.adf_activity_runs
# MAGIC -- WHERE activity_run_start >= current_timestamp() - INTERVAL 7 DAYS
# MAGIC -- GROUP BY activity_type
# MAGIC -- ORDER BY failure_pct DESC;

# COMMAND ----------

# DBTITLE 1,Deployment Steps
# MAGIC %md
# MAGIC ## Deployment Steps
# MAGIC
# MAGIC ### Step 1: Azure Identity & Permissions
# MAGIC
# MAGIC 1. **Choose auth method**: Managed Identity (recommended for production) or Service Principal (for dev or cross-tenant)
# MAGIC 2. **If Managed Identity**: Ensure the Databricks workspace has a system-assigned managed identity enabled
# MAGIC 3. **If Service Principal**: Register app in Entra ID, create client secret, note `tenant_id`, `client_id`, `client_secret`
# MAGIC 4. **Assign RBAC**: Grant `Data Factory Contributor` (or custom role with pipeline/activity read actions) to the identity on each ADF factory resource
# MAGIC 5. **Verify**: Test from Azure CLI: `az rest --method POST --url "https://management.azure.com/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.DataFactory/factories/<FACTORY>/queryPipelineRuns?api-version=2018-06-01" --body '{"lastUpdatedAfter":"2024-01-01T00:00:00Z","lastUpdatedBefore":"2024-12-31T23:59:59Z"}'`
# MAGIC
# MAGIC ### Step 2: Databricks Secrets (Service Principal only)
# MAGIC
# MAGIC 1. Create a secret scope: `databricks secrets create-scope adf-monitor`
# MAGIC 2. Store secrets:
# MAGIC    * `databricks secrets put-secret adf-monitor tenant-id`
# MAGIC    * `databricks secrets put-secret adf-monitor client-id`
# MAGIC    * `databricks secrets put-secret adf-monitor client-secret`
# MAGIC 3. Grant access to the job service principal or running user
# MAGIC
# MAGIC ### Step 3: Create Delta Schema & Tables
# MAGIC
# MAGIC 1. Open `03_Delta_DDL_and_Views` notebook
# MAGIC 2. Replace `<CATALOG>` and `<SCHEMA>` with your actual catalog and schema
# MAGIC 3. Run all cells to create tables and views
# MAGIC 4. Optionally insert SLA configuration records
# MAGIC
# MAGIC ### Step 4: Deploy the Collector Notebook
# MAGIC
# MAGIC 1. Copy `02_ADF_API_Collector` to a stable workspace location (e.g., `/Repos/production/adf_monitoring/`)
# MAGIC 2. Test with widget parameters filled in
# MAGIC 3. Verify data appears in the Delta tables
# MAGIC
# MAGIC ### Step 5: Schedule the Collector Job
# MAGIC
# MAGIC 1. Create a Lakeflow Job with a single notebook task pointing to `02_ADF_API_Collector`
# MAGIC 2. Set widget parameter values as job parameters
# MAGIC 3. **Schedule**: Every 5 minutes (use cron: `0 */5 * * * ?`)
# MAGIC 4. **Cluster**: Use a small single-node job cluster or serverless compute
# MAGIC 5. **Retries**: Configure 2 retries with 60s delay
# MAGIC 6. **Timeout**: Set 10-minute task timeout
# MAGIC 7. **For multiple factories**: Create separate tasks in the same job, each with different `factory_name` parameters, or loop in the notebook
# MAGIC 8. **Concurrency**: Set max concurrent runs = 1 to avoid duplicate writes
# MAGIC
# MAGIC ### Step 6: Create Dashboard
# MAGIC
# MAGIC 1. Create a new Databricks SQL dashboard named "ADF Operations Monitor"
# MAGIC 2. Add widgets using the queries from this notebook and the SQL views from `03_Delta_DDL_and_Views`
# MAGIC 3. Add filters for factory_name, pipeline_name, status, and date range
# MAGIC 4. Set auto-refresh interval to 1 minute
# MAGIC
# MAGIC ### Step 7: Configure Alerts
# MAGIC
# MAGIC 1. Create Databricks SQL alerts using the alert queries above
# MAGIC 2. Set appropriate schedules (2-5 min for critical, 15 min for trend-based)
# MAGIC 3. Configure notification destinations (email, Slack, PagerDuty, Teams)
# MAGIC 4. Test each alert by simulating the condition
# MAGIC
# MAGIC ### Step 8: Monitor the Collector Itself
# MAGIC
# MAGIC 1. Create a "Collector Health" alert that checks `MAX(_collection_ts)` from the pipeline runs table
# MAGIC 2. If the most recent collection is older than 10 minutes, alert (the collector may have failed)
# MAGIC 3. Monitor the Lakeflow Job run history for collector failures
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Monitoring the Collector
# MAGIC
# MAGIC ```sql
# MAGIC -- Alert: Collector has not run in the last 10 minutes
# MAGIC SELECT 
# MAGIC     TIMESTAMPDIFF(MINUTE, MAX(_collection_ts), current_timestamp()) AS minutes_since_last_collection
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs;
# MAGIC -- Condition: minutes_since_last_collection > 10
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Testing Plan
# MAGIC %md
# MAGIC ## Testing Plan
# MAGIC
# MAGIC ### Functional Tests
# MAGIC
# MAGIC | # | Scenario | How to Test | Expected Outcome |
# MAGIC | --- | --- | --- | --- |
# MAGIC | 1 | Successful pipeline | Trigger a simple ADF pipeline, run collector | Record appears with status `Succeeded`, duration populated |
# MAGIC | 2 | Failed pipeline | Trigger a pipeline that will fail (bad source), run collector | Record appears with status `Failed`, message contains error |
# MAGIC | 3 | Failed activity | Pipeline with one failing activity among several | Activity record shows `Failed` with error_code and error_message |
# MAGIC | 4 | Long-running pipeline | Trigger a pipeline with a Wait activity (>SLA), run collector | `v_current_running_pipelines` shows `SLA_BREACHED` |
# MAGIC | 5 | Cancelled pipeline | Trigger a pipeline, cancel it mid-run, run collector | Record shows `Cancelled` status |
# MAGIC | 6 | Nested pipeline | Use Execute Pipeline activity, run collector | Parent and child pipeline runs both captured |
# MAGIC | 7 | Concurrent runs | Trigger same pipeline 5+ times simultaneously | All runs captured with distinct `pipeline_run_id` |
# MAGIC | 8 | API throttling | Run collector against a factory during high API load | Collector retries and completes with exponential backoff |
# MAGIC | 9 | Auth failure | Remove RBAC permissions, run collector | Collector logs auth error, does not crash, no data written |
# MAGIC | 10 | Collector restart | Kill collector mid-run, restart | MERGE produces no duplicates; status updates are captured |
# MAGIC | 11 | Duplicate polling | Run collector twice with overlapping time windows | No duplicate records in Delta tables (MERGE idempotency) |
# MAGIC | 12 | Late status update | Pipeline finishes after collector already captured InProgress | Next collector run updates status to Succeeded via MERGE |
# MAGIC | 13 | Historical backfill | Set `backfill_start=2024-01-01`, `backfill_end=2024-01-31` | 30 days of historical runs loaded, no overlap with incremental |
# MAGIC
# MAGIC ### Non-Functional Tests
# MAGIC
# MAGIC | # | Scenario | How to Test | Expected Outcome |
# MAGIC | --- | --- | --- | --- |
# MAGIC | 14 | Performance at scale | Backfill 90 days for a busy factory (10K+ runs) | Completes within cluster timeout, no OOM |
# MAGIC | 15 | Network disruption | Block `management.azure.com` temporarily | Collector retries, eventually fails gracefully |
# MAGIC | 16 | Secret rotation | Rotate SP secret, update Databricks secret | Next collector run authenticates successfully |
# MAGIC | 17 | Multi-factory | Configure 3 factories as separate job tasks | All 3 factories have data in tables with correct factory_name |

# COMMAND ----------

# DBTITLE 1,Production Readiness Checklist
# MAGIC %md
# MAGIC ## Production Readiness Checklist
# MAGIC
# MAGIC ### Security
# MAGIC - [ ] Authentication method configured (Managed Identity or Service Principal)
# MAGIC - [ ] RBAC permissions scoped to specific ADF factories (not subscription-wide)
# MAGIC - [ ] Secrets stored in Databricks Secret Scope (no hard-coded credentials)
# MAGIC - [ ] Secret rotation plan documented (90-day max for SP secrets)
# MAGIC - [ ] Network connectivity verified (`management.azure.com`, `login.microsoftonline.com`)
# MAGIC
# MAGIC ### Data Pipeline
# MAGIC - [ ] Schema and tables created (`03_Delta_DDL_and_Views` executed)
# MAGIC - [ ] SLA configuration populated for critical pipelines
# MAGIC - [ ] Collector notebook tested with real ADF factory
# MAGIC - [ ] MERGE idempotency verified (no duplicates after repeated runs)
# MAGIC - [ ] Backfill tested for historical date range
# MAGIC - [ ] Error handling validated (auth failure, API errors, null fields)
# MAGIC
# MAGIC ### Scheduling
# MAGIC - [ ] Lakeflow Job created with correct parameters
# MAGIC - [ ] Schedule configured (every 1-5 minutes based on freshness requirements)
# MAGIC - [ ] Job cluster sized appropriately (single node is usually sufficient)
# MAGIC - [ ] Max concurrent runs = 1
# MAGIC - [ ] Task retry configured (2 retries, 60s delay)
# MAGIC - [ ] Task timeout configured (10 minutes)
# MAGIC
# MAGIC ### Monitoring
# MAGIC - [ ] Dashboard created and published
# MAGIC - [ ] Dashboard auto-refresh enabled (1-minute interval)
# MAGIC - [ ] Dashboard shared with operations team
# MAGIC - [ ] Failure alert configured and tested
# MAGIC - [ ] SLA breach alert configured and tested
# MAGIC - [ ] Stuck run alert configured and tested
# MAGIC - [ ] Unusual failure rate alert configured
# MAGIC - [ ] Collector health alert configured (detect when collector stops running)
# MAGIC - [ ] Notification destinations configured (email/Slack/Teams/PagerDuty)
# MAGIC
# MAGIC ### Data Retention
# MAGIC - [ ] Bronze (raw JSON) retention policy set (e.g., 90 days)
# MAGIC - [ ] Silver table OPTIMIZE / VACUUM scheduled
# MAGIC - [ ] Old data archival or deletion strategy documented
# MAGIC
# MAGIC ### Documentation
# MAGIC - [ ] Runbook created for common scenarios (collector failure, auth renewal, backfill)
# MAGIC - [ ] On-call team knows how to interpret dashboard and alerts
# MAGIC - [ ] API version dependencies documented (`2018-06-01` — check for updates)
# MAGIC - [ ] Factory list and environments documented
# MAGIC
# MAGIC ### Multi-Factory / Multi-Environment
# MAGIC - [ ] All target ADF factories listed with subscription/RG/factory params
# MAGIC - [ ] Each factory has identity access configured
# MAGIC - [ ] Job parameterized for multiple factories (separate tasks or loop)
# MAGIC - [ ] Dashboard filters work across factories
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Official Documentation Links
# MAGIC
# MAGIC | Topic | URL |
# MAGIC | --- | --- |
# MAGIC | ADF REST API: Query Pipeline Runs | https://learn.microsoft.com/en-us/rest/api/datafactory/pipeline-runs/query-by-factory |
# MAGIC | ADF REST API: Query Activity Runs | https://learn.microsoft.com/en-us/rest/api/datafactory/activity-runs/query-by-pipeline-run |
# MAGIC | ADF REST API Overview | https://learn.microsoft.com/en-us/rest/api/datafactory/ |
# MAGIC | ADF Monitoring via API | https://learn.microsoft.com/en-us/azure/data-factory/monitor-programmatically |
# MAGIC | Azure Managed Identity | https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/ |
# MAGIC | Databricks on Azure: Auth | https://learn.microsoft.com/en-us/azure/databricks/dev-tools/auth/ |
# MAGIC | Databricks Secret Scopes | https://docs.databricks.com/security/secrets/secret-scopes.html |
# MAGIC | Unity Catalog | https://docs.databricks.com/data-governance/unity-catalog/ |
# MAGIC | Databricks SQL Alerts | https://docs.databricks.com/sql/user/alerts/ |
# MAGIC | Delta Lake MERGE | https://docs.databricks.com/delta/merge.html |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Important Caveats to Validate
# MAGIC
# MAGIC 1. **ADF API version**: This solution uses `api-version=2018-06-01`. Verify this is still the current stable version in Microsoft docs.
# MAGIC 2. **API rate limits**: ADF enforces rate limits (~200 req/min). If monitoring many factories, stagger collection. Validate limits for your subscription tier.
# MAGIC 3. **Managed Identity availability**: Managed Identity for Databricks on Azure depends on workspace configuration. Verify your workspace supports it.
# MAGIC 4. **azure-identity package**: The `azure.identity` Python package must be available on the cluster. It is pre-installed on Databricks Runtime 13.3+. For earlier runtimes, install via `%pip install azure-identity`.
# MAGIC 5. **ADF pipeline run retention**: ADF retains pipeline run data for 45 days by default. Plan your initial backfill accordingly.
# MAGIC 6. **Timestamp precision**: ADF API returns millisecond-precision ISO 8601 timestamps. The collector normalizes to UTC.
# MAGIC 7. **Cross-tenant access**: If ADF and Databricks are in different Azure tenants, additional Azure AD configuration (multi-tenant app registration) is required.