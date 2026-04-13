import os
import vertexai
from google.genai import types
from agent import a2a_agent

PROJECT_ID = os.environ.get("PROJECT_ID")
REGION_ID = os.environ.get("REGION_ID")
ALLOYDB_CLUSTER_NAME = os.environ.get("ALLOYDB_CLUSTER_NAME")
ALLOYDB_INSTANCE_NAME = os.environ.get("ALLOYDB_INSTANCE_NAME")
ALLOYDB_DATABASE_NAME = os.environ.get("ALLOYDB_DATABASE_NAME")

BUCKET_NAME = f"{PROJECT_ID}-a2a-bucket"  
BUCKET_URI = f"gs://{BUCKET_NAME}"

# Initialize Vertex AI session
vertexai.init(project=PROJECT_ID, location=REGION_ID, staging_bucket=BUCKET_URI)

client = vertexai.Client(
    project=PROJECT_ID,
    location=REGION_ID,
    http_options=types.HttpOptions(
        api_version="v1beta1", base_url=f"https://{REGION_ID}-aiplatform.googleapis.com/"
    ),
)

remote_env_vars = {
    "PROJECT_ID": PROJECT_ID,
    "REGION_ID": REGION_ID,
    "ALLOYDB_CLUSTER_NAME": ALLOYDB_CLUSTER_NAME,
    "ALLOYDB_INSTANCE_NAME": ALLOYDB_INSTANCE_NAME,
    "ALLOYDB_DATABASE_NAME": ALLOYDB_DATABASE_NAME,
}
# Deploy on Agent Engine

print("Starting deployment to Vertex AI Agent Engine. This may take a few minutes...")

remote_a2a_agent = client.agent_engines.create(
    agent=a2a_agent,
    config={
        "display_name": a2a_agent.agent_card.name,
        "description": a2a_agent.agent_card.description,
        "requirements": [
            "google-cloud-aiplatform[agent_engines,adk]>=1.141.0",
            "a2a-sdk >= 0.3.25",
            "cloudpickle", 
            "pydantic"
        ],
        "extra_packages": ["agent.py"],
        "env_vars": remote_env_vars,
        "http_options": {
            "base_url": f"https://{REGION_ID}-aiplatform.googleapis.com",
            "api_version": "v1beta1",
        },
        "staging_bucket": BUCKET_URI,
    },
)

print(f"\nDeployment successful. Resource Name: {remote_a2a_agent.api_resource.name}")