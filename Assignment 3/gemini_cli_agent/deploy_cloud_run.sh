#!/usr/bin/env bash
# Deploy the Gemini CLI agent to Cloud Run (models via Vertex AI + the service account).
# Run from anywhere:  PROJECT_ID=my-proj REGION=us-central1 ./gemini_cli_agent/deploy_cloud_run.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"; SERVICE="${SERVICE:-gemini-cli-adk}"
cd "$(dirname "$0")/.."   # the 'Assignment 3' folder is the build context
gcloud builds submit --project "$PROJECT_ID" \
  --config gemini_cli_agent/cloudbuild.yaml --substitutions "_SERVICE=$SERVICE" .
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "gcr.io/$PROJECT_ID/$SERVICE" --memory 2Gi --cpu 2 --timeout 900 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global" \
  --no-allow-unauthenticated
