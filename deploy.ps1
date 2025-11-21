# Configuration
$PROJECT_ID = "main-project-477501"
$REGION = "asia-northeast1"
$REPO_NAME = "amazon-rank-scraper"
$IMAGE_NAME = "scraper"
$JOB_NAME = "amazon-rank-scraper-job"
$BUCKET_NAME = "amazon-search-ranks"

Write-Host "Starting deployment to Project: $PROJECT_ID..."

# 1. Enable APIs
Write-Host "Enabling necessary APIs..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project $PROJECT_ID

# 2. Create Artifact Registry Repo (Ignore error if exists)
Write-Host "Creating Artifact Registry repository..."
try {
    gcloud artifacts repositories create $REPO_NAME --repository-format=docker --location=$REGION --description="Docker repository for Amazon Scraper" --project $PROJECT_ID
} catch {
    Write-Host "Repository might already exist, continuing..."
}

# 3. Build and Push Image
Write-Host "Building and pushing Docker image..."
gcloud builds submit --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME" . --project $PROJECT_ID

# 4. Create/Update Cloud Run Job
Write-Host "Creating/Updating Cloud Run Job..."
# Check if job exists to decide between create or update
$jobExists = gcloud run jobs describe $JOB_NAME --region $REGION --project $PROJECT_ID 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Updating existing job..."
    gcloud run jobs update $JOB_NAME `
      --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME" `
      --region $REGION `
      --memory 2Gi `
      --cpu 1 `
      --task-timeout 10m `
      --set-env-vars "BUCKET_NAME=$BUCKET_NAME,TAKE_SCREENSHOTS=true" `
      --project $PROJECT_ID
} else {
    Write-Host "Creating new job..."
    gcloud run jobs create $JOB_NAME `
      --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME" `
      --region $REGION `
      --tasks 1 `
      --memory 2Gi `
      --cpu 1 `
      --max-retries 0 `
      --task-timeout 10m `
      --set-env-vars "BUCKET_NAME=$BUCKET_NAME,TAKE_SCREENSHOTS=true" `
      --project $PROJECT_ID
}

Write-Host "Deployment complete!"
Write-Host "To run the job manually: gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT_ID"
