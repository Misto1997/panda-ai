# GCP setup (copy-paste, in order)

Target: Cloud Run (web, api, jobs) + AlloyDB (Postgres + pgvector) + BigQuery + Vertex Gemini + Firebase Auth. Run from a machine where `gcloud` and `bq` are logged in as a project owner (`gcloud auth login`). Nothing here contains secrets; the database password is typed at a prompt.

Placeholders used below: `YOUR_PROJECT_ID`, region `asia-southeast1`, service account `panda-api@YOUR_PROJECT_ID.iam.gserviceaccount.com`, AlloyDB cluster `panda-db` / instance `primary-instance`, BigQuery dataset `panda`, Cloud Run services `panda-api` and `panda-web`. Flags marked "verify" depend on your gcloud version; check `gcloud <command> --help` if one errors.

## 0. Prerequisites
```bash
git clone <repo> && cd panda
gcloud config set project YOUR_PROJECT_ID
cp deploy/env.example.sh deploy/env.sh      # gitignored; fill the REPLACE_* values as you go
```
`deploy/env.sh` holds project, region, models, limits, admin emails, budget and the Firebase web config. No secrets.

## 1. Database facts and Firebase web config
If the AlloyDB cluster does not exist yet, create it in the console (Enterprise, private services access on a VPC network) or with `gcloud alloydb clusters create` and `gcloud alloydb instances create` (verify flags). Then collect:
```bash
gcloud alloydb instances describe primary-instance --cluster=panda-db --region=asia-southeast1 --format='value(ipAddress)'
gcloud alloydb clusters describe panda-db --region=asia-southeast1 --format='value(networkConfig.network)'
gcloud compute networks subnets list --network=<network> --filter=region:asia-southeast1
```
Put the IP in `DB_HOST`, the network in `VPC_NETWORK`, and a subnet of that network in the same region (at least /26) in `VPC_SUBNET`.

Create the app user and database (once):
```bash
gcloud alloydb users create panda_app --cluster=panda-db --region=asia-southeast1 --password='<choose one; do not save it in the repo>'
```
In AlloyDB Studio (console, AlloyDB, cluster, AlloyDB Studio) as `postgres`:
```sql
CREATE DATABASE panda;
ALTER DATABASE panda OWNER TO panda_app;
```
Reconnect to database `panda`:
```sql
GRANT ALL ON SCHEMA public TO panda_app;   -- PostgreSQL 15+: ordinary users cannot create tables in public otherwise
CREATE EXTENSION IF NOT EXISTS vector;
```
Cloud SQL for PostgreSQL also works: create instance, user and database, then set `DB_HOST` to its private IP; no code change.

**Firebase web config** (public values): Firebase console, Project settings, General, Your apps, add a Web app, copy `apiKey`, `authDomain`, `projectId`, `appId` into `FIREBASE_*` in `deploy/env.sh`. Enable the Google sign-in provider under Authentication.

## 2. One-time setup
```bash
make gcp-setup
```
Enables the APIs, creates the Artifact Registry repo `panda`, the service account and its roles, the BigQuery dataset, and the secret `panda-db-password` (prompts for the password). Roles on the service account: `aiplatform.user`, `bigquery.jobUser`, `logging.logWriter`, `alloydb.client`, dataset-level write on `panda`, `secretAccessor` on the one secret. It also grants the Cloud Build account the roles it needs; builder-account defaults vary by project age (verify in Cloud Build settings if a build fails with a permission error).

## 3. Build and deploy
```bash
make gcp-build      # Cloud Build: api and web images to Artifact Registry
make gcp-deploy     # Cloud Run api (Direct VPC egress), then web; prints both URLs
```
Firebase config is inlined into the web image at build time (`REQUIRE_FIREBASE=true` fails the build if a value is empty). Cloud Run exposes two URL forms per service; add **both** hostnames (no `https://`) to Firebase console, Authentication, Settings, Authorized domains, or sign-in fails with `auth/unauthorized-domain` on the missing one:
```bash
gcloud run services describe panda-web --region=asia-southeast1 --format='value(status.url, status.address.url)'
```
If the second value is empty, read both URLs in the Cloud Run console (service, URLs).

## 4. Load data, build the index, warm the cache
The API starts even before the warehouse tables exist (`/ready` returns 503 and the UI shows "data not loaded"), so deploy and bootstrap can run in either order. Order within bootstrap: data, index, warm.
```bash
make gcp-bootstrap                 # STEP=all: data (BigQuery load), index (AlloyDB), warm (cache)
make gcp-bootstrap STEP=data       # or one step at a time; each is an idempotent Cloud Run Job
make gcp-bootstrap STEP=index
make gcp-bootstrap STEP=warm
gcloud run jobs executions list --job=panda-bootstrap-data --region=asia-southeast1
```
The data job prints per-table row counts. After editing anything under `semantic/`: `make gcp-build && make gcp-deploy && make gcp-bootstrap STEP=index`, then clear the cache (`POST /api/admin/cache/clear` as an admin).

## 5. Nightly refresh (keeps "yesterday" true; stops by itself)
A Cloud Scheduler job runs the Cloud Run Job `panda-bootstrap-refresh` after midnight UTC: regenerate the synthetic data to end yesterday (UTC), reload BigQuery, clear the cache, prune idle conversation state, re-warm the cache. Running API instances re-read the data date within 60 s; no restart. A failed night leaves the previous data in place. Table-by-table reload means a question during the few minutes of the reload may see mixed days.
```bash
gcloud services enable cloudscheduler.googleapis.com     # once
make gcp-refresh CMD=create DAYS=30      # schedule for 30 days; the job also refuses to run after its stop date
make gcp-refresh CMD=run                 # run once now
make gcp-refresh CMD=status              # schedule, stop date, recent executions
make gcp-refresh CMD=pause               # stop the schedule (CMD=resume restarts it)
make gcp-refresh CMD=extend DAYS=14      # move the stop date to today + 14 days
make gcp-refresh CMD=delete              # remove schedule and job; data stays as of the last run
```
Default time is 00:30 UTC; change with `REFRESH_CRON` and re-run `create`. Scheduler flags: verify.

## 6. Free address with Firebase Hosting (optional)
```bash
npm i -g firebase-tools && firebase login
HOSTING_SITE=<site> make gcp-hosting      # creates the site if the id is free, rewrites everything to Cloud Run panda-web
```
Add `<site>.web.app` and `<site>.firebaseapp.com` to Authorized domains. Hosting proxies to Cloud Run with a request time limit (verify the current value) and may buffer responses, so test streaming before sharing the link (section 10). If an RCA turn is cut off, use the `run.app` URL.

## 7. Budget and kill-switch
Set `BILLING_ACCOUNT_ID` (`gcloud billing accounts list`) and `BUDGET_AMOUNT` in `deploy/env.sh`.
```bash
make gcp-budget     # alerts at 50/90/100% to Pub/Sub; deploys function panda-killswitch
```
At 100% the function removes `allUsers` from `roles/run.invoker` on both services, so the site goes dark. It does not stop AlloyDB. Restore with `make gcp-deploy`. Budgets lag usage by hours and do not cap spend by themselves.

Stop or start AlloyDB when idle (stopped instances still bill storage; verify the flag in current docs):
```bash
deploy/alloydb.sh stop | start | status
```

## 8. Smoke test
```bash
make gcp-smoke                                       # health, ready, meta, web; anonymous chat must be 401
SMOKE_ID_TOKEN=<firebase id token> make gcp-smoke    # adds a real chat turn
```

## 9. Diagnose
```bash
make gcp-diagnose      # Cloud Run Job inside the VPC: config, BigQuery tables, database, extensions, semantic index, one real Gemini call
gcloud run jobs executions list --job=panda-bootstrap-diagnose --region=asia-southeast1 --limit=1
```
Locally: `make doctor` (`LLM=1` for a real model call). More in `docs/DEBUGGING.md`.

## 10. Probe (latency and UX)
```bash
pip3 install httpx
make probe API=https://<panda-api-url> WEB=https://<panda-web-url> ID_TOKEN=<firebase id token> ARGS="--quick"
make probe API=https://<panda-api-url> WEB=https://<site>.web.app ID_TOKEN=<token> ARGS="--quick --via-web"   # through Hosting
```

## What each Cloud Run service and job needs

| | Image | Service account | VPC egress | Secrets | Key environment |
|---|---|---|---|---|---|
| `panda-api` | api | `panda-api` | Direct VPC, private ranges | `PGPASSWORD` | `PANDA_PROFILE=prod`, project, models, BigQuery, `DATABASE_URL`, Firebase project, limits, `ADMIN_EMAILS` (all from `deploy/api_env.sh`) |
| `panda-web` | web | default | none | none | `GATEWAY_URL` (the api URL); Firebase values baked in at build |
| `panda-bootstrap-data`, `-index`, `-warm`, `-diagnose` | api | `panda-api` | Direct VPC | `PGPASSWORD` | same as api; 16 GiB memory for `data` (`JOB_MEMORY`) |
| `panda-bootstrap-refresh` | api | `panda-api` (also invoker for Scheduler) | Direct VPC | `PGPASSWORD` | same plus `--until <stop date>` |
| `panda-killswitch` (function) | function | its own | none | none | triggered by the budget Pub/Sub topic |

## Feedback table
Ratings go to `panda_feedback` (created on first use; recorded only, never read back into the model). In AlloyDB Studio on database `panda`:
```sql
SELECT rating, count(*) FROM panda_feedback GROUP BY 1;
SELECT created_at, question, reasons, comment, route, path, sql
FROM panda_feedback WHERE rating = 'down' ORDER BY created_at DESC LIMIT 50;
```
History lives in `panda_threads` and `panda_turns` (per user, 30 days, 50 chats).

## Rollback and emergency off
```bash
gcloud run revisions list --service=panda-api --region=asia-southeast1
gcloud run services update-traffic panda-api --region=asia-southeast1 --to-revisions=<previous-revision>=100
gcloud run services remove-iam-policy-binding panda-api --region=asia-southeast1 --member=allUsers --role=roles/run.invoker   # emergency off (repeat for panda-web)
deploy/90-cleanup.sh            # dry run of the Artifact Registry cleanup policy; --apply to enforce
```
Same rollback for `panda-web`.
