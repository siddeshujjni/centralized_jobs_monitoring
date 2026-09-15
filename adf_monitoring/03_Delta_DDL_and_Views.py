# Databricks notebook source
# DBTITLE 1,Schema Setup
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- ADF Monitoring: Delta Table DDL and SQL Views
# MAGIC -- Run this notebook once to create the schema and tables.
# MAGIC -- Replace <CATALOG> and <SCHEMA> with your actual values.
# MAGIC -- ================================================================
# MAGIC
# MAGIC -- Create schema if it doesn't exist
# MAGIC CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>
# MAGIC COMMENT 'ADF monitoring tables for pipeline and activity run tracking';

# COMMAND ----------

# DBTITLE 1,Bronze: Raw API Responses Table
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- BRONZE: Raw ADF API Responses (append-only audit trail)
# MAGIC -- ================================================================
# MAGIC CREATE TABLE IF NOT EXISTS <CATALOG>.<SCHEMA>.raw_adf_api_responses (
# MAGIC     factory_name          STRING     NOT NULL COMMENT 'ADF factory name',
# MAGIC     subscription_id       STRING     NOT NULL COMMENT 'Azure subscription ID',
# MAGIC     resource_group        STRING     NOT NULL COMMENT 'Azure resource group',
# MAGIC     api_endpoint          STRING     NOT NULL COMMENT 'API endpoint called (queryPipelineRuns or queryActivityRuns)',
# MAGIC     run_id                STRING     NOT NULL COMMENT 'Pipeline or activity run ID',
# MAGIC     raw_json              STRING     NOT NULL COMMENT 'Full JSON response from ADF API',
# MAGIC     collection_timestamp  TIMESTAMP  NOT NULL COMMENT 'UTC timestamp when this record was collected'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'Raw ADF API responses stored for auditability and troubleshooting'
# MAGIC PARTITIONED BY (factory_name)
# MAGIC TBLPROPERTIES (
# MAGIC     'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC     'delta.autoOptimize.autoCompact'   = 'true',
# MAGIC     'delta.logRetentionDuration'       = 'interval 30 days',
# MAGIC     'delta.deletedFileRetentionDuration' = 'interval 7 days'
# MAGIC );

# COMMAND ----------

# DBTITLE 1,Silver: ADF Pipeline Runs Table
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- SILVER: ADF Pipeline Runs (normalized, upserted via MERGE)
# MAGIC -- ================================================================
# MAGIC CREATE TABLE IF NOT EXISTS <CATALOG>.<SCHEMA>.adf_pipeline_runs (
# MAGIC     -- Identity
# MAGIC     factory_name          STRING     NOT NULL COMMENT 'ADF factory name',
# MAGIC     subscription_id       STRING     NOT NULL COMMENT 'Azure subscription ID',
# MAGIC     resource_group        STRING     NOT NULL COMMENT 'Azure resource group',
# MAGIC     pipeline_name         STRING     NOT NULL COMMENT 'Name of the ADF pipeline',
# MAGIC     pipeline_run_id       STRING     NOT NULL COMMENT 'Unique pipeline run identifier (merge key)',
# MAGIC     run_group_id          STRING              COMMENT 'Run group ID for correlated runs',
# MAGIC     
# MAGIC     -- Trigger / Invocation
# MAGIC     invoke_by             STRING              COMMENT 'Who/what invoked the pipeline',
# MAGIC     invoke_by_type        STRING              COMMENT 'Type of invoker (Manual, ScheduleTrigger, etc.)',
# MAGIC     trigger_name          STRING              COMMENT 'Trigger name if applicable',
# MAGIC     trigger_type          STRING              COMMENT 'Trigger type if applicable',
# MAGIC     
# MAGIC     -- Execution
# MAGIC     status                STRING     NOT NULL COMMENT 'Run status: InProgress, Succeeded, Failed, Cancelling, Cancelled, Queued',
# MAGIC     run_start             TIMESTAMP           COMMENT 'Pipeline run start time (UTC)',
# MAGIC     run_end               TIMESTAMP           COMMENT 'Pipeline run end time (UTC, NULL if still running)',
# MAGIC     duration_ms           BIGINT              COMMENT 'Duration in milliseconds',
# MAGIC     is_latest             BOOLEAN             COMMENT 'Whether this is the latest run attempt',
# MAGIC     
# MAGIC     -- Error / metadata
# MAGIC     message               STRING              COMMENT 'Status message or error details (truncated to 4000 chars)',
# MAGIC     parameters            STRING              COMMENT 'Pipeline parameters as JSON string',
# MAGIC     run_dimensions        STRING              COMMENT 'Run dimensions as JSON string',
# MAGIC     last_updated          TIMESTAMP           COMMENT 'Last update time from ADF API (UTC)',
# MAGIC     
# MAGIC     -- Audit
# MAGIC     _collection_ts        TIMESTAMP  NOT NULL COMMENT 'UTC timestamp of the collector run that wrote this record'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'Normalized ADF pipeline run records, upserted by the collector'
# MAGIC PARTITIONED BY (factory_name)
# MAGIC TBLPROPERTIES (
# MAGIC     'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC     'delta.autoOptimize.autoCompact'   = 'true'
# MAGIC );

# COMMAND ----------

# DBTITLE 1,Silver: ADF Activity Runs Table
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- SILVER: ADF Activity Runs (normalized, upserted via MERGE)
# MAGIC -- ================================================================
# MAGIC CREATE TABLE IF NOT EXISTS <CATALOG>.<SCHEMA>.adf_activity_runs (
# MAGIC     -- Identity
# MAGIC     factory_name          STRING     NOT NULL COMMENT 'ADF factory name',
# MAGIC     subscription_id       STRING     NOT NULL COMMENT 'Azure subscription ID',
# MAGIC     resource_group        STRING     NOT NULL COMMENT 'Azure resource group',
# MAGIC     pipeline_name         STRING     NOT NULL COMMENT 'Parent pipeline name',
# MAGIC     pipeline_run_id       STRING     NOT NULL COMMENT 'Parent pipeline run ID',
# MAGIC     activity_name         STRING     NOT NULL COMMENT 'Activity name',
# MAGIC     activity_run_id       STRING     NOT NULL COMMENT 'Unique activity run identifier (merge key)',
# MAGIC     activity_type         STRING     NOT NULL COMMENT 'Activity type (Copy, DataFlow, SqlServerStoredProcedure, ExecutePipeline, AzureFunctionActivity, WebActivity, etc.)',
# MAGIC     linked_service        STRING              COMMENT 'Linked service name',
# MAGIC     
# MAGIC     -- Execution
# MAGIC     status                STRING     NOT NULL COMMENT 'Run status: InProgress, Succeeded, Failed, Cancelled, Queued',
# MAGIC     activity_run_start    TIMESTAMP           COMMENT 'Activity start time (UTC)',
# MAGIC     activity_run_end      TIMESTAMP           COMMENT 'Activity end time (UTC, NULL if still running)',
# MAGIC     duration_ms           BIGINT              COMMENT 'Duration in milliseconds',
# MAGIC     
# MAGIC     -- I/O metadata
# MAGIC     input_summary         STRING              COMMENT 'Truncated JSON of activity input',
# MAGIC     output_summary        STRING              COMMENT 'Truncated JSON of activity output',
# MAGIC     
# MAGIC     -- Error
# MAGIC     error_code            STRING              COMMENT 'Error code if failed',
# MAGIC     error_message         STRING              COMMENT 'Error details (truncated to 4000 chars)',
# MAGIC     
# MAGIC     -- Audit
# MAGIC     _collection_ts        TIMESTAMP  NOT NULL COMMENT 'UTC timestamp of the collector run'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'Normalized ADF activity run records, upserted by the collector'
# MAGIC PARTITIONED BY (factory_name)
# MAGIC TBLPROPERTIES (
# MAGIC     'delta.autoOptimize.optimizeWrite' = 'true',
# MAGIC     'delta.autoOptimize.autoCompact'   = 'true'
# MAGIC );

# COMMAND ----------

# DBTITLE 1,Gold: Pipeline SLA Configuration Table
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- GOLD: Pipeline SLA Configuration (reference / lookup table)
# MAGIC -- ================================================================
# MAGIC CREATE TABLE IF NOT EXISTS <CATALOG>.<SCHEMA>.adf_pipeline_sla_config (
# MAGIC     factory_name          STRING     NOT NULL COMMENT 'ADF factory name',
# MAGIC     pipeline_name         STRING     NOT NULL COMMENT 'ADF pipeline name',
# MAGIC     sla_duration_minutes  INT        NOT NULL COMMENT 'Maximum expected duration in minutes',
# MAGIC     stale_threshold_min   INT        NOT NULL COMMENT 'Minutes without update before flagging as stuck (default: 30)',
# MAGIC     environment           STRING              COMMENT 'Environment label (dev/staging/prod)',
# MAGIC     owner                 STRING              COMMENT 'Pipeline owner or team',
# MAGIC     notes                 STRING              COMMENT 'Additional notes',
# MAGIC     _updated_ts           TIMESTAMP  NOT NULL COMMENT 'Last update time (set on insert/update)'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'SLA thresholds per ADF pipeline for monitoring and alerting';
# MAGIC
# MAGIC -- Example: Insert sample SLA records
# MAGIC -- INSERT INTO <CATALOG>.<SCHEMA>.adf_pipeline_sla_config 
# MAGIC --   (factory_name, pipeline_name, sla_duration_minutes, stale_threshold_min, environment, owner)
# MAGIC -- VALUES 
# MAGIC --   ('<ADF_FACTORY_NAME>', 'daily_customer_load', 60, 30, 'prod', 'data-engineering'),
# MAGIC --   ('<ADF_FACTORY_NAME>', 'hourly_transactions',  15, 10, 'prod', 'data-engineering');

# COMMAND ----------

# DBTITLE 1,Gold View: Currently Running Pipelines
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- GOLD VIEW: Currently Running Pipelines with SLA Indicator
# MAGIC -- ================================================================
# MAGIC CREATE OR REPLACE VIEW <CATALOG>.<SCHEMA>.v_current_running_pipelines AS
# MAGIC SELECT
# MAGIC     pr.factory_name,
# MAGIC     pr.subscription_id,
# MAGIC     pr.resource_group,
# MAGIC     pr.pipeline_name,
# MAGIC     pr.pipeline_run_id,
# MAGIC     pr.status,
# MAGIC     pr.trigger_name,
# MAGIC     pr.trigger_type,
# MAGIC     pr.invoke_by,
# MAGIC     pr.run_start,
# MAGIC     pr.run_end,
# MAGIC     pr.duration_ms,
# MAGIC     
# MAGIC     -- Elapsed duration for running pipelines
# MAGIC     CASE 
# MAGIC         WHEN pr.status IN ('InProgress', 'Queued') 
# MAGIC         THEN TIMESTAMPDIFF(MINUTE, pr.run_start, current_timestamp())
# MAGIC         ELSE CAST(pr.duration_ms / 60000 AS INT)
# MAGIC     END AS elapsed_minutes,
# MAGIC     
# MAGIC     -- SLA indicator
# MAGIC     sla.sla_duration_minutes,
# MAGIC     CASE
# MAGIC         WHEN sla.sla_duration_minutes IS NULL THEN 'NO_SLA_CONFIGURED'
# MAGIC         WHEN pr.status IN ('InProgress', 'Queued') 
# MAGIC              AND TIMESTAMPDIFF(MINUTE, pr.run_start, current_timestamp()) > sla.sla_duration_minutes
# MAGIC         THEN 'SLA_BREACHED'
# MAGIC         WHEN pr.status IN ('InProgress', 'Queued') 
# MAGIC              AND TIMESTAMPDIFF(MINUTE, pr.run_start, current_timestamp()) > (sla.sla_duration_minutes * 0.8)
# MAGIC         THEN 'SLA_WARNING'
# MAGIC         WHEN pr.status IN ('Succeeded') 
# MAGIC              AND pr.duration_ms > (sla.sla_duration_minutes * 60000)
# MAGIC         THEN 'SLA_BREACHED'
# MAGIC         ELSE 'OK'
# MAGIC     END AS sla_status,
# MAGIC     
# MAGIC     -- Stale run detection (no update for N minutes)
# MAGIC     TIMESTAMPDIFF(MINUTE, pr.last_updated, current_timestamp()) AS minutes_since_last_update,
# MAGIC     CASE
# MAGIC         WHEN pr.status IN ('InProgress', 'Queued')
# MAGIC              AND TIMESTAMPDIFF(MINUTE, pr.last_updated, current_timestamp()) 
# MAGIC                  > COALESCE(sla.stale_threshold_min, 30)
# MAGIC         THEN TRUE
# MAGIC         ELSE FALSE
# MAGIC     END AS is_possibly_stuck,
# MAGIC     
# MAGIC     pr.message,
# MAGIC     pr.parameters,
# MAGIC     pr.last_updated,
# MAGIC     pr._collection_ts
# MAGIC
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs pr
# MAGIC LEFT JOIN <CATALOG>.<SCHEMA>.adf_pipeline_sla_config sla
# MAGIC     ON pr.factory_name  = sla.factory_name
# MAGIC     AND pr.pipeline_name = sla.pipeline_name
# MAGIC WHERE pr.status IN ('InProgress', 'Queued', 'Cancelling')
# MAGIC    OR (pr.status IN ('Succeeded', 'Failed', 'Cancelled') 
# MAGIC        AND pr.run_end >= current_timestamp() - INTERVAL 1 HOUR)
# MAGIC ORDER BY 
# MAGIC     CASE pr.status
# MAGIC         WHEN 'InProgress' THEN 1
# MAGIC         WHEN 'Queued'     THEN 2
# MAGIC         WHEN 'Cancelling' THEN 3
# MAGIC         WHEN 'Failed'     THEN 4
# MAGIC         ELSE 5
# MAGIC     END,
# MAGIC     pr.run_start DESC;

# COMMAND ----------

# DBTITLE 1,Gold View: Currently Running Activities
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- GOLD VIEW: Currently Running Activities with Elapsed Duration
# MAGIC -- ================================================================
# MAGIC CREATE OR REPLACE VIEW <CATALOG>.<SCHEMA>.v_current_running_activities AS
# MAGIC SELECT
# MAGIC     ar.factory_name,
# MAGIC     ar.pipeline_name,
# MAGIC     ar.pipeline_run_id,
# MAGIC     ar.activity_name,
# MAGIC     ar.activity_run_id,
# MAGIC     ar.activity_type,
# MAGIC     ar.linked_service,
# MAGIC     ar.status,
# MAGIC     ar.activity_run_start,
# MAGIC     ar.activity_run_end,
# MAGIC     ar.duration_ms,
# MAGIC     
# MAGIC     -- Elapsed time for running activities
# MAGIC     CASE
# MAGIC         WHEN ar.status = 'InProgress'
# MAGIC         THEN TIMESTAMPDIFF(MINUTE, ar.activity_run_start, current_timestamp())
# MAGIC         ELSE CAST(ar.duration_ms / 60000 AS INT)
# MAGIC     END AS elapsed_minutes,
# MAGIC     
# MAGIC     -- Parent pipeline status
# MAGIC     pr.status AS pipeline_status,
# MAGIC     pr.trigger_name,
# MAGIC     
# MAGIC     ar.error_code,
# MAGIC     ar.error_message,
# MAGIC     ar._collection_ts
# MAGIC
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_activity_runs ar
# MAGIC INNER JOIN <CATALOG>.<SCHEMA>.adf_pipeline_runs pr
# MAGIC     ON ar.factory_name    = pr.factory_name
# MAGIC     AND ar.pipeline_run_id = pr.pipeline_run_id
# MAGIC WHERE ar.status IN ('InProgress', 'Queued')
# MAGIC    OR (ar.status IN ('Succeeded', 'Failed', 'Cancelled') 
# MAGIC        AND ar.activity_run_end >= current_timestamp() - INTERVAL 1 HOUR)
# MAGIC ORDER BY
# MAGIC     CASE ar.status
# MAGIC         WHEN 'InProgress' THEN 1
# MAGIC         WHEN 'Queued'     THEN 2
# MAGIC         WHEN 'Failed'     THEN 3
# MAGIC         ELSE 4
# MAGIC     END,
# MAGIC     ar.activity_run_start DESC;

# COMMAND ----------

# DBTITLE 1,Gold View: Failed Runs (Last 24 Hours)
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- GOLD VIEW: Failed Pipeline and Activity Runs (Last 24 Hours)
# MAGIC -- ================================================================
# MAGIC CREATE OR REPLACE VIEW <CATALOG>.<SCHEMA>.v_failed_runs_24h AS
# MAGIC SELECT
# MAGIC     'Pipeline' AS run_type,
# MAGIC     pr.factory_name,
# MAGIC     pr.pipeline_name,
# MAGIC     pr.pipeline_run_id,
# MAGIC     NULL AS activity_name,
# MAGIC     NULL AS activity_run_id,
# MAGIC     NULL AS activity_type,
# MAGIC     pr.status,
# MAGIC     pr.run_start,
# MAGIC     pr.run_end,
# MAGIC     pr.duration_ms,
# MAGIC     pr.message AS error_details,
# MAGIC     pr.trigger_name,
# MAGIC     pr.invoke_by
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs pr
# MAGIC WHERE pr.status = 'Failed'
# MAGIC   AND pr.run_end >= current_timestamp() - INTERVAL 24 HOURS
# MAGIC
# MAGIC UNION ALL
# MAGIC
# MAGIC SELECT
# MAGIC     'Activity' AS run_type,
# MAGIC     ar.factory_name,
# MAGIC     ar.pipeline_name,
# MAGIC     ar.pipeline_run_id,
# MAGIC     ar.activity_name,
# MAGIC     ar.activity_run_id,
# MAGIC     ar.activity_type,
# MAGIC     ar.status,
# MAGIC     ar.activity_run_start AS run_start,
# MAGIC     ar.activity_run_end AS run_end,
# MAGIC     ar.duration_ms,
# MAGIC     ar.error_message AS error_details,
# MAGIC     pr.trigger_name,
# MAGIC     pr.invoke_by
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_activity_runs ar
# MAGIC INNER JOIN <CATALOG>.<SCHEMA>.adf_pipeline_runs pr
# MAGIC     ON ar.factory_name = pr.factory_name
# MAGIC     AND ar.pipeline_run_id = pr.pipeline_run_id
# MAGIC WHERE ar.status = 'Failed'
# MAGIC   AND ar.activity_run_end >= current_timestamp() - INTERVAL 24 HOURS
# MAGIC ORDER BY run_end DESC;

# COMMAND ----------

# DBTITLE 1,Gold View: Pipeline SLA Status
# MAGIC %sql
# MAGIC -- ================================================================
# MAGIC -- GOLD VIEW: Pipeline SLA Status (all recent runs with SLA eval)
# MAGIC -- ================================================================
# MAGIC CREATE OR REPLACE VIEW <CATALOG>.<SCHEMA>.v_pipeline_sla_status AS
# MAGIC SELECT
# MAGIC     pr.factory_name,
# MAGIC     pr.pipeline_name,
# MAGIC     pr.pipeline_run_id,
# MAGIC     pr.status,
# MAGIC     pr.run_start,
# MAGIC     pr.run_end,
# MAGIC     ROUND(pr.duration_ms / 60000.0, 1) AS duration_minutes,
# MAGIC     sla.sla_duration_minutes,
# MAGIC     sla.environment,
# MAGIC     sla.owner,
# MAGIC     CASE
# MAGIC         WHEN sla.sla_duration_minutes IS NULL THEN 'NO_SLA'
# MAGIC         WHEN pr.status IN ('InProgress', 'Queued') 
# MAGIC              AND TIMESTAMPDIFF(MINUTE, pr.run_start, current_timestamp()) > sla.sla_duration_minutes
# MAGIC         THEN 'BREACHED'
# MAGIC         WHEN pr.status IN ('Succeeded', 'Failed', 'Cancelled')
# MAGIC              AND pr.duration_ms > (sla.sla_duration_minutes * 60000)
# MAGIC         THEN 'BREACHED'
# MAGIC         ELSE 'MET'
# MAGIC     END AS sla_result,
# MAGIC     pr.trigger_name,
# MAGIC     pr.message
# MAGIC FROM <CATALOG>.<SCHEMA>.adf_pipeline_runs pr
# MAGIC LEFT JOIN <CATALOG>.<SCHEMA>.adf_pipeline_sla_config sla
# MAGIC     ON pr.factory_name = sla.factory_name
# MAGIC     AND pr.pipeline_name = sla.pipeline_name
# MAGIC WHERE pr.run_start >= current_timestamp() - INTERVAL 7 DAYS
# MAGIC ORDER BY pr.run_start DESC;