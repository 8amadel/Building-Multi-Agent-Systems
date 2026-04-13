CONFIG_FILE="config.env"

# Ensure config.env exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env file not found at $CONFIG_FILE"
    exit 1
fi

# Load Config variables for this script to use
export $(grep -v '^#' "$CONFIG_FILE" | xargs)

echo "Granting IAM roles"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
REASONINGENGINE_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/alloydb.databaseUser" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/alloydb.client" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/mcp.toolUser" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/serviceusage.serviceUsageConsumer" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/storage.objectUser" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/aiplatform.reasoningEngineServiceAgent" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$REASONINGENGINE_SA" \
  --role="roles/aiplatform.user" \
  --condition=None

echo "enabling required APIs"
gcloud services enable \
  telemetry.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  clouderrorreporting.googleapis.com \
  cloudasset.googleapis.com \
  --project=$PROJECT_ID

echo "installing packages"
pip install -r $BASE_DIR/mas/mas_agent/requirements.txt

echo "setting Gemini Model in agent definition"
sed -i "s|PHGM|$GEMINI_MODEL|g" "$BASE_DIR/mas/mas_agent/agent.py"

echo "Creating deployment bucket"
gcloud storage buckets create gs://$PROJECT_ID-a2a-bucket --location=$REGION_ID --project=$PROJECT_ID

(
cd $BASE_DIR/mas/mas_agent
python deploy.py
)

echo "Holding for 1 minute to make sure the reasoning engine's resource ID is refreshed"
duration=60
interval=10
while [ $duration -gt 0 ]; do
    echo "$duration seconds remaining..."
    sleep $interval
    duration=$((duration - interval))
done
echo "Time's up!"

echo "Constructing agent card and setting in .md file"
AGENT_RESOURCE=$(gcloud asset search-all-resources \
  --scope=projects/$PROJECT_ID \
  --asset-types='aiplatform.googleapis.com/ReasoningEngine' \
  --format="value(name)" | head -n 1)

AGENT_ID=$(basename "$AGENT_RESOURCE")
AGENT_URL="https://$REGION_ID-aiplatform.googleapis.com/v1beta1/projects/$PROJECT_NUMBER/locations/$REGION_ID/reasoningEngines/$AGENT_ID/a2a/v1/card"
sed -i "s|PHAR|$AGENT_URL|g" "$BASE_DIR/mas/mas_agent/mas_agent.md"

mkdir -p ~/.gemini/agents
cp ~/.gemini/settings.json ~/.gemini/setting.json.bk
cp $BASE_DIR/mas/mas_agent/settings.json ~/.gemini
cp $BASE_DIR/mas/mas_agent/mas_agent.md ~/.gemini/agents

echo "Deployment Completed!"