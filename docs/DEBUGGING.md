# Debugging PANDA AI

Placeholders: project `YOUR_PROJECT_ID`, region `asia-southeast1`, services `panda-api` and `panda-web`, jobs `panda-bootstrap-data|index|warm|refresh|diagnose`. Run `gcloud` where you are logged in.

## Symptom to first check

| Symptom | First check |
|---|---|
| Deploy says "container failed to start" / `HealthCheckContainerError` on port 8080 | Not a port problem: the app crashed in startup. Read that revision's stderr (section 1); the last `ERROR` before `Application startup failed` is the cause |
| `/ready` is 503, UI shows "data not loaded" | BigQuery tables (section 3), then `make gcp-bootstrap STEP=data` |
| Answers wrong, search seems empty | Semantic index (section 2) |
| 401 in UI or API | Section 5 |
| 429 | Section 6 (quota / rate limit) or section 7 (model capacity) |
| "The language model is busy" or LLM errors in logs | Section 7 |
| First request after idle takes 10+ s | Cold start with `min-instances 0`; expected |

One command that checks most dependencies (config, BigQuery tables, database, extensions, tables, semantic index, one real Gemini call):
```bash
make gcp-diagnose      # Cloud Run Job inside the VPC, so it can reach the private database
gcloud run jobs executions list --job=panda-bootstrap-diagnose --region=asia-southeast1 --limit=1
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="panda-bootstrap-diagnose"' --project=YOUR_PROJECT_ID --limit=30 --format='value(textPayload)' --order=asc
```
Every line is `PASS` or `FAIL`; failures print a `hint:`. Locally: `make doctor` (`LLM=1` for a real model call).

## 1. Logs

Console: Cloud Run, the service, tab **Logs**; a failed deploy: tab **Revisions**, the failed revision, **Logs**.
```bash
gcloud run services logs read panda-api --region=asia-southeast1 --limit=100
gcloud beta run services logs tail panda-api --region=asia-southeast1          # live tail
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="panda-api" AND severity>=ERROR' --project=YOUR_PROJECT_ID --freshness=1h --limit=50 --format='value(timestamp,textPayload)'
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="<revision>"' --project=YOUR_PROJECT_ID --limit=100 --order=asc --format='value(textPayload)'
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="panda-bootstrap-index"' --project=YOUR_PROJECT_ID --limit=100 --order=asc --format='value(textPayload)'
```
Use `service_name="panda-web"` for the UI server.

**Reading a line:** `10:25:58 INFO  panda.query.service [3f9a1c2b7d10] message`. The bracket is the request id, also returned as `X-Request-Id` (DevTools, Network, the `chat` request, Response Headers). Follow one turn:
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="panda-api" AND textPayload:"3f9a1c2b7d10"' --project=YOUR_PROJECT_ID --freshness=1h --order=asc --format='value(textPayload)'
```
**Debug mode:** `LOG_LEVEL=DEBUG` and `TRACE_PAYLOADS=true` add SQL text and model output. The prod profile refuses to start with payload tracing on, so reproduce locally (section 9).

**Browser:** DevTools, Network, the `chat` request, **EventStream**: `RUN_STARTED`, `STEP_*`, `CUSTOM panda.step` (per-node timings), `ACTIVITY_SNAPSHOT` (answer surface), `CUSTOM panda.result` (full payload), `RUN_FINISHED` or `RUN_ERROR` (with a code). If the page is blank but `panda.result` arrived, the A2UI surface failed and the page falls back to the plain result view. Per-step timings are also under "N steps" in the UI; `cache: hit` means the model or engine was skipped.

## 2. Semantic index

The index is table `semantic_docs` (one row per metric, dimension, glossary term, example, runbook, check). The startup log line `catalog loaded: ... N docs` gives the expected count. In AlloyDB Studio (database `panda`, user `panda_app`):
```sql
SELECT count(*) FROM semantic_docs;                                    -- equals N from the startup log
SELECT kind, count(*) FROM semantic_docs GROUP BY 1 ORDER BY 2 DESC;
SELECT id, vector_dims(embedding) FROM semantic_docs LIMIT 5;          -- 768
SELECT extname FROM pg_extension;                                      -- includes vector
SELECT id FROM semantic_docs WHERE tsv @@ plainto_tsquery('english', 'net gmv') LIMIT 5;      -- lexical works
SELECT b.id FROM semantic_docs a, semantic_docs b WHERE a.id = 'net_gmv' ORDER BY a.embedding <=> b.embedding LIMIT 5;   -- vector works
```
Or as an admin: `curl -s -H "Authorization: Bearer $ID_TOKEN" "$API/api/admin/diagnostics"` (add `?llm=true` for one model call), with `API=$(gcloud run services describe panda-api --region=asia-southeast1 --format='value(status.url)')`.

After editing `semantic/`: `make gcp-build && make gcp-deploy && make gcp-bootstrap STEP=index`, then `curl -s -X POST -H "Authorization: Bearer $ID_TOKEN" "$API/api/admin/cache/clear"`.

## 3. Warehouse (BigQuery)

```bash
bq ls YOUR_PROJECT_ID:panda          # fact_sales, agg_sales_daily, agg_traffic_city_daily, agg_traffic_state_daily, agg_bu_traffic_daily
bq show --format=prettyjson YOUR_PROJECT_ID:panda | grep location      # must equal BQ_LOCATION
bq query --nouse_legacy_sql 'SELECT MAX(order_date) AS anchor, COUNT(*) AS days FROM `YOUR_PROJECT_ID.panda.agg_sales_daily`'
```
Bytes billed by PANDA queries (they carry the label `app=panda-ai`):
```sql
SELECT creation_time, total_bytes_billed/1e6 AS mb_billed, LEFT(query, 100) AS q
FROM `region-asia-southeast1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND (SELECT value FROM UNNEST(labels) WHERE key = 'app') = 'panda-ai'
ORDER BY creation_time DESC LIMIT 50;
```
A query over `BQ_MAX_BYTES_BILLED` (10 GiB) is rejected; the user sees a "too expensive" message. If answers say the data ends earlier than expected, check the nightly refresh (`make gcp-refresh CMD=status`); API instances re-read the data date every 60 s.

## 4. Database state (AlloyDB Studio)

```sql
SELECT layer, count(*), min(created_at), max(created_at) FROM panda_cache GROUP BY 1;     -- plan and result cache
SELECT * FROM panda_usage ORDER BY day DESC, count DESC LIMIT 20;                         -- daily usage per user and 'global'
SELECT owner, count(*) FROM panda_threads GROUP BY 1 ORDER BY 2 DESC LIMIT 10;            -- chat history
SELECT rating, count(*) FROM panda_feedback GROUP BY 1;                                   -- thumbs
SELECT thread_id, count(*) FROM checkpoints GROUP BY 1 ORDER BY 2 DESC LIMIT 10;          -- LangGraph conversation memory
SELECT count(*) FROM pg_stat_activity WHERE datname = 'panda';                            -- open connections
```
Resets: `DELETE FROM panda_usage WHERE day = current_date;` lifts today's quota; `TRUNCATE panda_cache;` equals the admin cache-clear endpoint.

## 5. Sign-in and 401

1. Google button shows but sign-in fails with `auth/unauthorized-domain`: add the `panda-web` host (both Cloud Run URL forms, and any `web.app` host) to Firebase, Authentication, Settings, Authorized domains.
2. Sign-in works but chat returns 401 `unauthenticated`: check the request has `Authorization: Bearer ...`; API logs show `token verification failed`. Usual causes: `FIREBASE_PROJECT_ID` differs from the project the web app was registered in, or the four `NEXT_PUBLIC_FIREBASE_*` values were not build args (rebuild the web image).
3. Token for curl: signed-in UI, DevTools, Network, any `/api/chat` request, copy the value after `Bearer` (expires after about an hour):
```bash
curl -s -H "Authorization: Bearer $ID_TOKEN" $API/api/me      # {email, remaining_today, daily_limit}
```
4. `403 forbidden` on `/api/admin/*`: the email is not in `ADMIN_EMAILS` (set in `deploy/env.sh`, then `make gcp-deploy`).

## 6. Quota and rate limits (429)

`quota_exceeded`: per-user (30) or global (300) daily cap reached; resets 00:00 UTC (see `panda_usage`). Raise `DAILY_USER_QUERY_LIMIT` / `DAILY_GLOBAL_QUERY_LIMIT` in `deploy/env.sh` and redeploy, or delete today's rows. `rate_limited`: per-IP token bucket; behind the web proxy users share an IP, so a burst can trip it (`IP_RATE_PER_MINUTE`, `IP_RATE_BURST`).

## 7. Model (Gemini) problems

Run `make gcp-diagnose` and read the `llm` line.

| Log text | Fix |
|---|---|
| `404 ... model ... not found` | `GEMINI_MODEL` does not exist for your project or location. Check the model garden, then set `gemini_model` in `config/profiles/prod.yaml` or `GEMINI_MODEL` in `deploy/env.sh` |
| `403 ... aiplatform.endpoints.predict` | Service account lacks the role: `gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member=serviceAccount:panda-api@YOUR_PROJECT_ID.iam.gserviceaccount.com --role=roles/aiplatform.user` |
| `429 Resource exhausted` | Capacity or quota, see below |
| Embedding errors during `index` | Try `EMBEDDING_LOCATION=<region>` if the model is not served on `global` |

Behaviour on failure: narration failure keeps the correct data with the standard summary; two failed SQL generations fall back to the deterministic IR path (`meta.path = ir_fallback`); a stalled call shows "The language model is busy right now". Raw provider text is only in logs (search `llm structured ... failed after`).

**429 details.** "Resource exhausted, please try again later" is capacity (pay-as-you-go ramp, spikes); a message naming a quota or metric is a per-project limit. Check Console, APIs & Services, Vertex AI API, Metrics (429 counts), and IAM & Admin, Quotas & System Limits (filter `Service: Vertex AI API`, e.g. metrics containing `embed` or generate-content). In Metrics Explorer, `serviceruntime.googleapis.com/quota/exceeded` empty means capacity, not quota. Embeddings are retried with exponential backoff and paced; chat degrades to lexical-only search if embeddings keep failing. Exact error: `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="panda-bootstrap-index" AND severity>=ERROR' --project=YOUR_PROJECT_ID --limit=20 --format='value(textPayload)'`.

If the embedding model's quota is too low: use a model with more quota (`EMBEDDING_MODEL`), or run without embedding quota with `EMBEDDING_PROVIDER="hash"` in `deploy/env.sh` (`make gcp-deploy`, `make gcp-bootstrap STEP=index`; lexical search is unaffected, semantic recall is lower), then switch back to `auto` and re-index.

## 8. Performance

* Q&A: no model call for routing (rules), one model call for SQL, data shown, then insight text a few seconds later. RCA: no model call before the investigation; warehouse reads run 8 wide.
* Bounds: `llm_timeout_s` 25, `llm_max_retries` 1, `llm_max_concurrency` 6 per instance. Stalls of 40-90 s point at the model side: check Vertex metrics for 429s.
* A large `execute` step means a slow warehouse call: check `bytes_processed` in the chips and the BigQuery job list; the sidebar "Force raw table scan" option compares with the rollup.
* Cold start: Cloud Run, service, Metrics, "Container startup latency". `--cpu-boost` is set; set `min-instances 1` to avoid it.
* `make probe API=https://<panda-api-url> WEB=https://<panda-web-url> ID_TOKEN=... ARGS="--quick"` prints per-step latency; an `error` answer counts as a failure and its text is printed.

## 9. Local debugging

```bash
make config                                   # effective configuration of the active profile
make doctor                                   # dependency checks
make ask Q="why did visits drop?" DEBUG=1     # live step trace plus SQL and model payloads
make api-debug                                # server with DEBUG logs
make test && make bench                       # tests; golden questions through the full graph (LLM_PROVIDER=gemini for a real model)
```
Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` for full LangGraph tracing.

## 10. Cost and safety switches

```bash
deploy/alloydb.sh status | stop | start       # AlloyDB is the main cost; stopped instances still bill storage
gcloud billing budgets list --billing-account=<ID>
gcloud run services get-iam-policy panda-api --region=asia-southeast1      # allUsers invoker = public; the kill-switch removes it at 100% of budget
```
After a kill-switch trip, `make gcp-deploy` restores public access. Per-service breakdown: Console, Billing, Reports, group by SKU.

## 11. Common errors and fixes

| Error | Cause and fix |
|---|---|
| `Not found: Table ...agg_sales_daily` | Data job not run. `/ready` is 503 until `make gcp-bootstrap STEP=data` |
| `permission denied for schema public` | `GRANT ALL ON SCHEMA public TO panda_app;` as admin in database `panda` |
| `server closed the connection` after a quiet period | Idle pooled connection dropped by the VPC or database. Pools use keepalives, health checks and recycling; if it persists set `--no-cpu-throttling` on the API |
| `Division by zero` from BigQuery | Divisions are translated to `SAFE_DIVIDE`; rebuild and redeploy the API image if you see it |
| Period mismatch or "outside loaded data" replies | The period guard or data-range guard working as designed; ask "till when do you have data" to see the range |
| Build fails with missing `frontend/lib` files | `frontend/lib` must be committed (the Python `.gitignore` template ignores `lib/`; an exception exists) |

## 12. Roll back a bad deploy

```bash
gcloud run revisions list --service=panda-api --region=asia-southeast1
gcloud run services update-traffic panda-api --region=asia-southeast1 --to-revisions=<previous-revision>=100
```
Same for `panda-web`. Old images stay in Artifact Registry until the cleanup policy removes them (`deploy/90-cleanup.sh`).
