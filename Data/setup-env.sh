CONFIG_FILE="config.env"
# Ensure config.env exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.env file not found at $CONFIG_FILE"
    exit 1
fi

# Load Config variables for this script to use
export $(grep -v '^#' "$CONFIG_FILE" | xargs)
# Get the Project Number
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

# Construct the Default Compute Engine Service Account Email
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
REASONINGENGINE_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam"

echo "enabling required APIs"
gcloud services enable \
    servicenetworking.googleapis.com \
    vpcaccess.googleapis.com \
    aiplatform.googleapis.com \
    cloudresourcemanager.googleapis.com \
    alloydb.googleapis.com \
    iam.googleapis.com \
    compute.googleapis.com \
    --project=$PROJECT_ID

gcloud beta services identity create --service=alloydb.googleapis.com --project=$PROJECT_ID
gcloud beta services identity create --service=compute.googleapis.com --project=$PROJECT_ID


echo "Holding for 1 minute to make sure the default service accounts are created"
duration=60
interval=10
while [ $duration -gt 0 ]; do
    echo "$duration seconds remaining..."
    sleep $interval
    duration=$((duration - interval))
done

echo "Time's up!"

echo "Creating AlloyDB Cluster and Instance"

gcloud compute networks create $NETWORK_NAME \
    --subnet-mode=auto

gcloud compute addresses create google-managed-services-alloydb-network \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --description="peering range for AlloyDB" \
    --network=$NETWORK_NAME

gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-alloydb-network \
    --network=$NETWORK_NAME

gcloud alloydb clusters create $ALLOYDB_CLUSTER_NAME \
    --password=alloydb\
    --network=$NETWORK_NAME \
    --region=$REGION_ID \
    --database-version=POSTGRES_17

gcloud alloydb instances create $ALLOYDB_INSTANCE_NAME \
     --instance-type=PRIMARY \
     --cpu-count=2 \
     --region=$REGION_ID \
     --cluster=$ALLOYDB_CLUSTER_NAME \
     --availability-type=ZONAL \
     --ssl-mode=ALLOW_UNENCRYPTED_AND_ENCRYPTED

gcloud alloydb instances update $ALLOYDB_INSTANCE_NAME \
     --cluster=$ALLOYDB_CLUSTER_NAME \
     --region=$REGION_ID \
     --database-flags="alloydb.iam_authentication=on"

gcloud alloydb users create $REASONINGENGINE_SA \
     --cluster=$ALLOYDB_CLUSTER_NAME \
     --region=$REGION_ID \
     --type=IAM_BASED

echo "Granting roles to: $COMPUTE_SA"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/alloydb.admin"


gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-alloydb.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

echo "Holding for 2 minutes to make sure the IAM policy is activated"
duration=120
interval=10
while [ $duration -gt 0 ]; do
    echo "$duration seconds remaining..."
    sleep $interval
    duration=$((duration - interval))
done

echo "Time's up!"

pip install google-cloud-alloydb
python3 $BASE_DIR/mas/Data/setup-env.py
pip install GitPython
python3 $BASE_DIR/mas/Data/git_agent_setup.py