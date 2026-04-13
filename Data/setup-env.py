import os
import csv
from google.cloud import alloydb_v1

# --- Configuration Loading ---
PROJECT_ID = os.environ.get("PROJECT_ID")
REGION_ID = os.environ.get("REGION_ID")
CLUSTER_ID = os.environ.get("ALLOYDB_CLUSTER_NAME")
INSTANCE_ID = os.environ.get("ALLOYDB_INSTANCE_NAME")
DATABASE_ID = os.environ.get("ALLOYDB_DATABASE_NAME")
BASE_DIR = os.environ.get("BASE_DIR")
DB_USER = "postgres"
DB_PASSWORD = "alloydb"
SCHEMA_FILE = f"{BASE_DIR}/Building-Multi-Agent-Systems/Data/schema.sql"
PROJECT_NUMBER=os.environ.get("PROJECT_NUMBER")


GENERATE_EMBEDDINGS_SQL = """
UPDATE troubleshooting_kb 
SET stack_trace_embedding = embedding(
    'text-embedding-005', 
    stack_trace)
;
"""
GRANT_IAM_USER_SQL = f"""GRANT SELECT ON public.troubleshooting_kb TO "service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam";"""

def execute_alloydb_sql(client, instance_path, db_name, sql_statement):
    """Helper function to execute SQL via the AlloyDB Admin API."""
    request = alloydb_v1.ExecuteSqlRequest(
        instance=instance_path,
        database=db_name,
        user=DB_USER,
        password=DB_PASSWORD,
        sql_statement=sql_statement
    )
    
    response = client.execute_sql(request=request)
    return response

def escape_sql_value(val):
    """Escapes single quotes and formats empty strings as NULL for SQL."""
    if val is None or val.strip() == "":
        return "NULL"
    # Escape single quotes by doubling them (standard SQL)
    escaped_val = val.replace("'", "''")
    # Wrap in single quotes. PostgreSQL automatically casts strings to the correct column type
    return f"'{escaped_val}'"

def main():
    # Initialize the AlloyDB Admin Client
    client = alloydb_v1.AlloyDBAdminClient()
    
    # Construct the fully qualified instance path
    instance_path = client.instance_path(PROJECT_ID, REGION_ID, CLUSTER_ID, INSTANCE_ID)

    # Create Database
    print(f"Connected to AlloyDB Admin API. Creating database '{DATABASE_ID}'...")
    try:
        execute_alloydb_sql(client, instance_path, "postgres", f"DROP DATABASE IF EXISTS {DATABASE_ID};")
        execute_alloydb_sql(client, instance_path, "postgres", f"CREATE DATABASE {DATABASE_ID};")
        print("Database created successfully.")
    except Exception as e:
        print(f"Warning during DB creation : {e}")

    # create schema
    if not os.path.exists(SCHEMA_FILE):
        print(f" Error: Could not find {SCHEMA_FILE}.")
        return

    print(f"Reading schema from {SCHEMA_FILE} and executing...")
    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        schema_sql = f.read()
        try:
            execute_alloydb_sql(client, instance_path, DATABASE_ID, schema_sql)
            print("Schema executed successfully.")
        except Exception as e:
            print(f"Error executing schema: {e}")
            return

    # Load CSV Data via Bulk INSERT

    files_to_load = [
        ("troubleshooting_kb", f"{BASE_DIR}/Building-Multi-Agent-Systems/Data/troubleshooting_kb.csv")
    ]

    for table_name, file_name in files_to_load:
        if not os.path.exists(file_name):
            print(f"Could not find {file_name}. Skipping...")
            continue
            
        print(f"Importing data into {table_name} from {file_name}...")
        
        with open(file_name, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            columns = next(reader) # Read headers
            
            # Construct base INSERT statement
            col_names = ", ".join(columns)
            
            # Read all rows and format them for bulk insert
            values_list = []
            for row in reader:
                formatted_values = ", ".join([escape_sql_value(val) for val in row])
                values_list.append(f"({formatted_values})")
            
            # If we have data, execute the bulk INSERT
            if values_list:
                bulk_insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES \n" + ",\n".join(values_list) + ";"
                try:
                    execute_alloydb_sql(client, instance_path, DATABASE_ID, bulk_insert_sql)
                    print(f"Successfully loaded {len(values_list)} rows into {table_name}.")
                except Exception as e:
                    print(f"Error loading data into {table_name}: {e}")

    # Generate Embeddings 
    print("Generating vector embeddings")
    try:
        execute_alloydb_sql(client, instance_path, DATABASE_ID, GENERATE_EMBEDDINGS_SQL)
        print("Embeddings generated and updated successfully.")
    except Exception as e:
        print(f"Failed to generate embeddings. Error: {e}")

    # Grant SELECT TO IAM User
    print("Granting select privilege to IAM user")
    try:
        execute_alloydb_sql(client, instance_path, DATABASE_ID, GRANT_IAM_USER_SQL)
        print("Privilege granted successfully.")
    except Exception as e:
        print(f"Failed to grant select privilege. Error: {e}")
    print("\nAll Data tasks completed successfully!")

if __name__ == "__main__":
    main()
