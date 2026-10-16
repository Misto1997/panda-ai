# Copy to deploy/env.sh (gitignored) and fill the placeholders. NO secrets here: the DB password is prompted by 00-setup.sh.
export PROJECT_ID="ai-builder-hackathon"
export REGION="asia-southeast1"
export SERVICE_ACCOUNT_NAME="panda-api"
export SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

export AR_REPO="panda"
export API_SERVICE="panda-api"
export WEB_SERVICE="panda-web"
export IMAGE_TAG="${IMAGE_TAG:-latest}"

# BigQuery
export BQ_DATASET="panda"
export BQ_LOCATION="asia-southeast1"
export BQ_MAX_BYTES_BILLED="10737418240"   # 10 GiB per query

# AlloyDB (private IP) or Cloud SQL: only DATABASE_URL changes. Get the IP: see docs/GCP_SETUP.md
export ALLOYDB_CLUSTER="panda-db"
export ALLOYDB_INSTANCE="primary-instance"
export DB_HOST="REPLACE_WITH_ALLOYDB_PRIVATE_IP"
export DB_NAME="panda"
export DB_USER="panda_app"
export DB_PASSWORD_SECRET="panda-db-password"   # Secret Manager secret; exposed to Cloud Run as PGPASSWORD (libpq reads it)
export DATABASE_URL="postgresql://${DB_USER}@${DB_HOST}:5432/${DB_NAME}?sslmode=require"

# VPC used for Direct VPC egress (same network AlloyDB private services access is peered with)
export VPC_NETWORK="default"
export VPC_SUBNET="default"

# Models (Vertex, location global). Confirm the ids exist in your project.
export GEMINI_MODEL="gemini-3.8-flash"
export GEMINI_PRO_MODEL="gemini-3.8-flash"
export EMBEDDING_MODEL="gemini-embedding-001"
export EMBEDDING_LOCATION=""                    # empty = global; set e.g. asia-southeast1 if the embedding model is not served globally

# Firebase Auth (public web config: Firebase console > Project settings > Your apps)
export FIREBASE_PROJECT_ID="ai-builder-hackathon"
export FIREBASE_API_KEY="REPLACE"
export FIREBASE_AUTH_DOMAIN="ai-builder-hackathon.firebaseapp.com"
export FIREBASE_APP_ID="REPLACE"

# Limits
export DAILY_USER_QUERY_LIMIT="30"
export DAILY_GLOBAL_QUERY_LIMIT="300"
export LLM_MAX_CALLS_PER_TURN="8"

# Bootstrap job
export BOOTSTRAP_ROWS="20000000"
export JOB_MEMORY="8Gi"                          # Cloud Run's disk is memory-backed; 4Gi may be too small for 20M rows

# Budget
export BILLING_ACCOUNT_ID="REPLACE"              # gcloud billing accounts list
export BUDGET_AMOUNT="100"                       # in the billing account currency, no currency suffix
export BUDGET_TOPIC="panda-budget-alerts"
