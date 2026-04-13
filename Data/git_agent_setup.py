import os
import random
import json
import subprocess
from datetime import datetime, timedelta

PROJECT_ID = os.environ.get("PROJECT_ID")
BUCKET_NAME = f"{PROJECT_ID}-mock-git-repo" 

FILES = [
    "UserService.java", "PaymentProcessor.py", "AuthGateway.go", 
    "DataIndexer.java", "ConfigManager.py", "ApiClient.js", 
    "LoggerService.go", "CacheValidator.java", "SchemaMigrator.py", "QueryBuilder.js"
]

AUTHORS = [
    ('Alice Smith', 'alice@corp.com'), 
    ('Bob Jones', 'bob@corp.com'), 
    ('Charlie Case', 'charlie@corp.com')
]

def generate_mock_history_gcs():
    history = {f: [] for f in FILES}
    
    # Generate 100 commits
    for i in range(100):
        f_name = random.choice(FILES)
        author_name, author_email = random.choice(AUTHORS)
        days_ago = random.randint(0, 30)
        commit_date = datetime.now() - timedelta(days=days_ago)
        
        commit = {
            "hash": f"{random.getrandbits(28):07x}", # Fake 7-char git hash
            "author": author_name,
            "date": commit_date.isoformat(),
            "message": f"Fix/Update related to ticket-{1000+i} in {f_name}"
        }
        history[f_name].append(commit)

    # Sort commits by date (newest first) for each file
    for f in history:
        history[f].sort(key=lambda x: x['date'], reverse=True)

    # Save locally first
    with open("git_history.json", "w") as f:
        json.dump(history, f, indent=2)

    print("Created mock git history locally.")

    # Upload to GCS using gcloud/gsutil
    print(f"Creating GCS bucket: gs://{BUCKET_NAME}...")
    subprocess.run(["gcloud", "storage", "buckets", "create", f"gs://{BUCKET_NAME}", f"--project={PROJECT_ID}"], check=False)
    
    print("Uploading to GCS...")
    subprocess.run(["gcloud", "storage", "cp", "git_history.json", f"gs://{BUCKET_NAME}/"], check=True)
    
    print(f"Success! Mock Git history is live at gs://{BUCKET_NAME}/git_history.json")

if __name__ == '__main__':
    generate_mock_history_gcs()