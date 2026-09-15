# Databricks notebook source
# DBTITLE 1,Widget Parameters and Configuration
# Databricks notebook: ADF Monitoring Collector
# Schedule this notebook every 1-5 minutes via a Lakeflow Job.
# It polls ADF Management API for pipeline and activity runs, then writes to Delta.

# ---------- Widget parameters ----------
dbutils.widgets.text("subscription_id",    "<SUBSCRIPTION_ID>",  "Azure Subscription ID")
dbutils.widgets.text("resource_group",     "<RESOURCE_GROUP>",   "Resource Group")
dbutils.widgets.text("factory_name",       "<ADF_FACTORY_NAME>", "ADF Factory Name")
dbutils.widgets.text("tenant_id",          "<TENANT_ID>",        "Azure Tenant ID")
dbutils.widgets.text("catalog",            "<CATALOG>",          "Databricks Catalog")
dbutils.widgets.text("schema",             "<SCHEMA>",           "Databricks Schema")
dbutils.widgets.text("auth_method",        "managed_identity",   "Auth Method (managed_identity|service_principal)")
dbutils.widgets.text("lookback_minutes",   "30",                 "Lookback Window (minutes)")
dbutils.widgets.text("backfill_start",     "",                   "Backfill Start (YYYY-MM-DD, leave empty for incremental)")
dbutils.widgets.text("backfill_end",       "",                   "Backfill End (YYYY-MM-DD, leave empty for incremental)")

# ---------- Read parameters ----------
SUBSCRIPTION_ID  = dbutils.widgets.get("subscription_id")
RESOURCE_GROUP   = dbutils.widgets.get("resource_group")
FACTORY_NAME     = dbutils.widgets.get("factory_name")
TENANT_ID        = dbutils.widgets.get("tenant_id")
CATALOG          = dbutils.widgets.get("catalog")
SCHEMA           = dbutils.widgets.get("schema")
AUTH_METHOD      = dbutils.widgets.get("auth_method")
LOOKBACK_MINUTES = int(dbutils.widgets.get("lookback_minutes"))
BACKFILL_START   = dbutils.widgets.get("backfill_start").strip()
BACKFILL_END     = dbutils.widgets.get("backfill_end").strip()

# ADF API version (validate against current Microsoft docs)
ADF_API_VERSION = "2018-06-01"

print(f"Factory: {FACTORY_NAME} | Auth: {AUTH_METHOD} | Lookback: {LOOKBACK_MINUTES} min")
print(f"Target: {CATALOG}.{SCHEMA}")
if BACKFILL_START:
    print(f"BACKFILL MODE: {BACKFILL_START} to {BACKFILL_END or 'now'}")

# COMMAND ----------

# DBTITLE 1,Authentication Module
import requests
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, LongType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("adf_collector")

# ---------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------

def get_access_token_managed_identity():
    """
    Acquire an Azure Management token using the Managed Identity
    attached to the Databricks workspace.
    Works on Azure Databricks clusters with system-assigned or
    user-assigned managed identity.
    """
    import azure.identity
    credential = azure.identity.ManagedIdentityCredential()
    token = credential.get_token("https://management.azure.com/.default")
    logger.info("Obtained token via Managed Identity (expires %s)", 
                datetime.fromtimestamp(token.expires_on, tz=timezone.utc).isoformat())
    return token.token


def get_access_token_service_principal(tenant_id: str):
    """
    Acquire an Azure Management token using a Service Principal
    whose credentials are stored in Databricks secrets.
    Secret scope: 'adf-monitor'
    Keys: 'client-id', 'client-secret'
    """
    client_id     = dbutils.secrets.get(scope="adf-monitor", key="client-id")
    client_secret = dbutils.secrets.get(scope="adf-monitor", key="client-secret")
    
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
        "scope":         "https://management.azure.com/.default"
    }
    
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    logger.info("Obtained token via Service Principal")
    return token


def get_access_token(auth_method: str, tenant_id: str) -> str:
    """Route to the correct authentication method."""
    if auth_method == "managed_identity":
        return get_access_token_managed_identity()
    elif auth_method == "service_principal":
        return get_access_token_service_principal(tenant_id)
    else:
        raise ValueError(f"Unknown auth_method: {auth_method}. Use 'managed_identity' or 'service_principal'.")


# Acquire the token for this run
access_token = get_access_token(AUTH_METHOD, TENANT_ID)
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type":  "application/json"
}
logger.info("Authentication successful for factory: %s", FACTORY_NAME)

# COMMAND ----------

# DBTITLE 1,ADF API Client with Retry and Pagination
# ---------------------------------------------------------------
# ADF API Client with retry, pagination, and throttle handling
# ---------------------------------------------------------------

MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2  # exponential backoff base in seconds
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _api_call_with_retry(method: str, url: str, headers: dict, 
                          json_body: dict = None, params: dict = None) -> dict:
    """
    Make an HTTP request with exponential backoff retry for transient errors.
    Handles:
      - 429 Too Many Requests (respects Retry-After header)
      - 5xx server errors
      - Connection/timeout errors
    Logs failures WITHOUT exposing credentials.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if method.upper() == "POST":
                resp = requests.post(url, headers=headers, json=json_body, 
                                     params=params, timeout=60)
            else:
                resp = requests.get(url, headers=headers, params=params, timeout=60)
            
            if resp.status_code == 200:
                return resp.json()
            
            if resp.status_code in RETRY_STATUS_CODES:
                # Respect Retry-After header for 429
                retry_after = int(resp.headers.get("Retry-After", 
                                  RETRY_BACKOFF_BASE ** attempt))
                logger.warning(
                    "API returned %d on attempt %d/%d. Retrying in %ds. URL: %s",
                    resp.status_code, attempt, MAX_RETRIES, retry_after,
                    url.split("?")[0]  # Log URL without query params
                )
                time.sleep(retry_after)
                continue
            
            # Non-retryable error
            logger.error(
                "API returned %d (non-retryable). URL: %s | Body: %s",
                resp.status_code, url.split("?")[0], resp.text[:500]
            )
            resp.raise_for_status()
            
        except requests.exceptions.ConnectionError as e:
            logger.warning("Connection error on attempt %d/%d: %s", 
                          attempt, MAX_RETRIES, str(e)[:200])
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_BACKOFF_BASE ** attempt)
            
        except requests.exceptions.Timeout as e:
            logger.warning("Timeout on attempt %d/%d: %s", 
                          attempt, MAX_RETRIES, str(e)[:200])
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_BACKOFF_BASE ** attempt)
    
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url.split('?')[0]}")


def query_pipeline_runs(subscription_id: str, resource_group: str, 
                        factory_name: str, start_time: datetime, 
                        end_time: datetime, headers: dict) -> list:
    """
    Call ADF queryPipelineRuns API with pagination.
    Returns a list of all pipeline run dicts in the time window.
    
    API: POST /subscriptions/{sub}/resourceGroups/{rg}/providers/
         Microsoft.DataFactory/factories/{factory}/queryPipelineRuns
    """
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}/providers/Microsoft.DataFactory"
        f"/factories/{factory_name}/queryPipelineRuns"
    )
    params = {"api-version": ADF_API_VERSION}
    
    body = {
        "lastUpdatedAfter":  start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "lastUpdatedBefore": end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    }
    
    all_runs = []
    continuation_token = None
    page = 0
    
    while True:
        page += 1
        if continuation_token:
            body["continuationToken"] = continuation_token
        
        result = _api_call_with_retry("POST", url, headers, 
                                       json_body=body, params=params)
        
        runs = result.get("value", [])
        all_runs.extend(runs)
        logger.info("Pipeline runs page %d: fetched %d runs (total: %d)", 
                    page, len(runs), len(all_runs))
        
        continuation_token = result.get("continuationToken")
        if not continuation_token:
            break
    
    return all_runs


def query_activity_runs(subscription_id: str, resource_group: str,
                        factory_name: str, pipeline_run_id: str,
                        start_time: datetime, end_time: datetime,
                        headers: dict) -> list:
    """
    Call ADF queryActivityRuns API for a specific pipeline run.
    Returns a list of all activity run dicts.
    
    API: POST /subscriptions/{sub}/resourceGroups/{rg}/providers/
         Microsoft.DataFactory/factories/{factory}/pipelineruns/
         {runId}/queryActivityruns
    """
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}/providers/Microsoft.DataFactory"
        f"/factories/{factory_name}/pipelineruns/{pipeline_run_id}"
        f"/queryActivityruns"
    )
    params = {"api-version": ADF_API_VERSION}
    
    body = {
        "lastUpdatedAfter":  start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "lastUpdatedBefore": end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    }
    
    all_activities = []
    continuation_token = None
    page = 0
    
    while True:
        page += 1
        if continuation_token:
            body["continuationToken"] = continuation_token
        
        result = _api_call_with_retry("POST", url, headers,
                                       json_body=body, params=params)
        
        activities = result.get("value", [])
        all_activities.extend(activities)
        
        continuation_token = result.get("continuationToken")
        if not continuation_token:
            break
    
    return all_activities


logger.info("API client functions loaded.")

# COMMAND ----------

# DBTITLE 1,Determine Time Window (Incremental or Backfill)
# ---------------------------------------------------------------
# Determine the polling time window
# ---------------------------------------------------------------

now_utc = datetime.now(timezone.utc)

if BACKFILL_START:
    # Backfill mode: use explicit date range
    window_start = datetime.strptime(BACKFILL_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if BACKFILL_END:
        window_end = datetime.strptime(BACKFILL_END, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    else:
        window_end = now_utc
    logger.info("BACKFILL mode: %s to %s", window_start.isoformat(), window_end.isoformat())
else:
    # Incremental mode: lookback from now
    window_start = now_utc - timedelta(minutes=LOOKBACK_MINUTES)
    window_end = now_utc
    logger.info("INCREMENTAL mode: %s to %s (lookback %d min)", 
                window_start.isoformat(), window_end.isoformat(), LOOKBACK_MINUTES)

collection_timestamp = now_utc.isoformat()

# COMMAND ----------

# DBTITLE 1,Collect Pipeline Runs
# ---------------------------------------------------------------
# Collect Pipeline Runs
# ---------------------------------------------------------------

logger.info("Fetching pipeline runs from %s...", FACTORY_NAME)
raw_pipeline_runs = query_pipeline_runs(
    SUBSCRIPTION_ID, RESOURCE_GROUP, FACTORY_NAME,
    window_start, window_end, headers
)
logger.info("Total pipeline runs fetched: %d", len(raw_pipeline_runs))

# Store raw JSON for auditability (bronze layer)
raw_pipeline_records = []
for run in raw_pipeline_runs:
    raw_pipeline_records.append({
        "factory_name":         FACTORY_NAME,
        "subscription_id":      SUBSCRIPTION_ID,
        "resource_group":       RESOURCE_GROUP,
        "api_endpoint":         "queryPipelineRuns",
        "run_id":               run.get("runId", ""),
        "raw_json":             json.dumps(run),
        "collection_timestamp": collection_timestamp
    })

# Normalize pipeline run records (silver layer)
def parse_adf_timestamp(ts_str):
    """Parse ADF timestamp to ISO format string, handling None/empty."""
    if not ts_str:
        return None
    # ADF returns ISO 8601 strings; normalize to UTC
    return ts_str.replace("+00:00", "Z") if "+00:00" in ts_str else ts_str

def safe_duration_ms(run):
    """Calculate duration in milliseconds from durationInMs field or run start/end."""
    dur = run.get("durationInMs")
    if dur is not None:
        return int(dur)
    return None

pipeline_records = []
for run in raw_pipeline_runs:
    pipeline_records.append({
        "factory_name":       FACTORY_NAME,
        "subscription_id":    SUBSCRIPTION_ID,
        "resource_group":     RESOURCE_GROUP,
        "pipeline_name":      run.get("pipelineName", ""),
        "pipeline_run_id":    run.get("runId", ""),
        "run_group_id":       run.get("runGroupId", ""),
        "invoke_by":          run.get("invokedBy", {}).get("name", "") if run.get("invokedBy") else "",
        "invoke_by_type":     run.get("invokedBy", {}).get("invokedByType", "") if run.get("invokedBy") else "",
        "trigger_name":       run.get("invokedBy", {}).get("name", "") if run.get("invokedBy") else "",
        "trigger_type":       run.get("invokedBy", {}).get("invokedByType", "") if run.get("invokedBy") else "",
        "status":             run.get("status", "Unknown"),
        "run_start":          parse_adf_timestamp(run.get("runStart")),
        "run_end":            parse_adf_timestamp(run.get("runEnd")),
        "duration_ms":        safe_duration_ms(run),
        "is_latest":          run.get("isLatest", True),
        "message":            (run.get("message") or "")[:4000],  # Truncate long error messages
        "parameters":         json.dumps(run.get("parameters", {})),
        "run_dimensions":     json.dumps(run.get("runDimensions", {})),
        "last_updated":       parse_adf_timestamp(run.get("lastUpdated")),
        "_collection_ts":     collection_timestamp
    })

logger.info("Parsed %d pipeline run records", len(pipeline_records))

# COMMAND ----------

# DBTITLE 1,Collect Activity Runs for Each Pipeline
# ---------------------------------------------------------------
# Collect Activity Runs for each pipeline run
# ---------------------------------------------------------------

logger.info("Fetching activity runs for %d pipeline runs...", len(raw_pipeline_runs))

raw_activity_records = []
activity_records = []

for i, run in enumerate(raw_pipeline_runs):
    pipeline_run_id = run.get("runId", "")
    pipeline_name   = run.get("pipelineName", "")
    
    try:
        raw_activities = query_activity_runs(
            SUBSCRIPTION_ID, RESOURCE_GROUP, FACTORY_NAME,
            pipeline_run_id, window_start, window_end, headers
        )
    except Exception as e:
        logger.error("Failed to fetch activities for pipeline run %s: %s", 
                     pipeline_run_id, str(e)[:300])
        continue
    
    for act in raw_activities:
        # Raw record (bronze)
        raw_activity_records.append({
            "factory_name":         FACTORY_NAME,
            "subscription_id":      SUBSCRIPTION_ID,
            "resource_group":       RESOURCE_GROUP,
            "api_endpoint":         "queryActivityRuns",
            "run_id":               act.get("activityRunId", ""),
            "raw_json":             json.dumps(act),
            "collection_timestamp": collection_timestamp
        })
        
        # Normalized record (silver)
        activity_records.append({
            "factory_name":       FACTORY_NAME,
            "subscription_id":    SUBSCRIPTION_ID,
            "resource_group":     RESOURCE_GROUP,
            "pipeline_name":      pipeline_name,
            "pipeline_run_id":    pipeline_run_id,
            "activity_name":      act.get("activityName", ""),
            "activity_run_id":    act.get("activityRunId", ""),
            "activity_type":      act.get("activityType", ""),
            "linked_service":     act.get("linkedServiceName", ""),
            "status":             act.get("status", "Unknown"),
            "activity_run_start": parse_adf_timestamp(act.get("activityRunStart")),
            "activity_run_end":   parse_adf_timestamp(act.get("activityRunEnd")),
            "duration_ms":        act.get("durationInMs"),
            "input_summary":      json.dumps(act.get("input", {}))[:4000] if act.get("input") else "",
            "output_summary":     json.dumps(act.get("output", {}))[:4000] if act.get("output") else "",
            "error_code":         (act.get("error", {}) or {}).get("errorCode", ""),
            "error_message":      (json.dumps(act.get("error", {})) if act.get("error") else "")[:4000],
            "_collection_ts":     collection_timestamp
        })
    
    if (i + 1) % 50 == 0:
        logger.info("Processed activities for %d / %d pipeline runs", i + 1, len(raw_pipeline_runs))

logger.info("Total activity run records: %d", len(activity_records))

# COMMAND ----------

# DBTITLE 1,Write Raw JSON to Bronze Table
# ---------------------------------------------------------------
# Write raw API responses to bronze table (append-only for audit)
# ---------------------------------------------------------------

RAW_TABLE = f"{CATALOG}.{SCHEMA}.raw_adf_api_responses"

all_raw_records = raw_pipeline_records + raw_activity_records

if all_raw_records:
    df_raw = spark.createDataFrame(all_raw_records)
    df_raw = df_raw.withColumn("collection_timestamp", 
                                F.to_timestamp(F.col("collection_timestamp")))
    df_raw.write.mode("append").saveAsTable(RAW_TABLE)
    logger.info("Appended %d raw records to %s", len(all_raw_records), RAW_TABLE)
else:
    logger.info("No raw records to write.")

# COMMAND ----------

# DBTITLE 1,MERGE Pipeline Runs into Silver Table
# ---------------------------------------------------------------
# MERGE pipeline runs into silver table (idempotent upsert)
# ---------------------------------------------------------------

PIPELINE_TABLE = f"{CATALOG}.{SCHEMA}.adf_pipeline_runs"

if pipeline_records:
    df_pipelines = spark.createDataFrame(pipeline_records)
    
    # Cast timestamp columns
    for col_name in ["run_start", "run_end", "last_updated", "_collection_ts"]:
        df_pipelines = df_pipelines.withColumn(
            col_name, F.to_timestamp(F.col(col_name))
        )
    
    # Create temp view for MERGE
    df_pipelines.createOrReplaceTempView("_stg_pipeline_runs")
    
    # MERGE on natural key: factory_name + pipeline_run_id
    # This handles both new runs and status updates to existing runs
    merge_sql = f"""
    MERGE INTO {PIPELINE_TABLE} AS target
    USING _stg_pipeline_runs AS source
    ON  target.factory_name    = source.factory_name
    AND target.pipeline_run_id = source.pipeline_run_id
    WHEN MATCHED AND (
        target.status       != source.status
        OR target.run_end   != source.run_end
        OR target.duration_ms != source.duration_ms
        OR target.message   != source.message
        OR target.last_updated < source.last_updated
    ) THEN UPDATE SET
        target.status          = source.status,
        target.run_end         = source.run_end,
        target.duration_ms     = source.duration_ms,
        target.message         = source.message,
        target.is_latest       = source.is_latest,
        target.last_updated    = source.last_updated,
        target.parameters      = source.parameters,
        target.run_dimensions  = source.run_dimensions,
        target._collection_ts  = source._collection_ts
    WHEN NOT MATCHED THEN INSERT *
    """
    
    result = spark.sql(merge_sql)
    logger.info("MERGE completed for pipeline runs into %s", PIPELINE_TABLE)
    
    # Show merge metrics
    display(result)
else:
    logger.info("No pipeline records to merge.")

# COMMAND ----------

# DBTITLE 1,MERGE Activity Runs into Silver Table
# ---------------------------------------------------------------
# MERGE activity runs into silver table (idempotent upsert)
# ---------------------------------------------------------------

ACTIVITY_TABLE = f"{CATALOG}.{SCHEMA}.adf_activity_runs"

if activity_records:
    df_activities = spark.createDataFrame(activity_records)
    
    # Cast timestamp columns
    for col_name in ["activity_run_start", "activity_run_end", "_collection_ts"]:
        df_activities = df_activities.withColumn(
            col_name, F.to_timestamp(F.col(col_name))
        )
    
    # Create temp view for MERGE
    df_activities.createOrReplaceTempView("_stg_activity_runs")
    
    # MERGE on natural key: factory_name + activity_run_id
    merge_sql = f"""
    MERGE INTO {ACTIVITY_TABLE} AS target
    USING _stg_activity_runs AS source
    ON  target.factory_name     = source.factory_name
    AND target.activity_run_id  = source.activity_run_id
    WHEN MATCHED AND (
        target.status             != source.status
        OR target.activity_run_end != source.activity_run_end
        OR target.duration_ms     != source.duration_ms
        OR target.error_message   != source.error_message
    ) THEN UPDATE SET
        target.status             = source.status,
        target.activity_run_end   = source.activity_run_end,
        target.duration_ms        = source.duration_ms,
        target.input_summary      = source.input_summary,
        target.output_summary     = source.output_summary,
        target.error_code         = source.error_code,
        target.error_message      = source.error_message,
        target._collection_ts     = source._collection_ts
    WHEN NOT MATCHED THEN INSERT *
    """
    
    result = spark.sql(merge_sql)
    logger.info("MERGE completed for activity runs into %s", ACTIVITY_TABLE)
    display(result)
else:
    logger.info("No activity records to merge.")

# COMMAND ----------

# DBTITLE 1,Collection Summary
# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------

print("="*60)
print("ADF MONITORING COLLECTION COMPLETE")
print("="*60)
print(f"Factory:            {FACTORY_NAME}")
print(f"Time window:        {window_start.isoformat()} to {window_end.isoformat()}")
print(f"Pipeline runs:      {len(pipeline_records)}")
print(f"Activity runs:      {len(activity_records)}")
print(f"Raw records stored: {len(all_raw_records) if all_raw_records else 0}")
print(f"Collection time:    {collection_timestamp}")
print(f"Target tables:      {PIPELINE_TABLE}, {ACTIVITY_TABLE}, {RAW_TABLE}")
print("="*60)