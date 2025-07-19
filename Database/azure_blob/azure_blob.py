from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import os
from dotenv import load_dotenv
load_dotenv()
import json
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Azure Blob Storage connection string
connection_string = os.environ['AZURE_BLOB_CONNECTION_STRING']
blob_service_client = BlobServiceClient.from_connection_string(connection_string)

# Extract account name and account key from connection string for SAS generation
def get_account_credentials():
    """Extract account name and key from connection string"""
    parts = connection_string.split(';')
    account_name = None
    account_key = None
    
    for part in parts:
        if part.startswith('AccountName='):
            account_name = part.split('=', 1)[1]
        elif part.startswith('AccountKey='):
            account_key = part.split('=', 1)[1]
    
    return account_name, account_key

def upload_or_update_blob(data, bot_id, file_type, file_name):
    try:
        # Create the container if it does not exist
        file_name=file_name.replace(".","_").replace("-","_")
        container_client = blob_service_client.get_container_client(bot_id)
        if not container_client.exists():
            container_client.create_container()
            print(f"Container '{bot_id}' created successfully")

    except Exception as e:
        print(f"Container already exists or could not be created: {e}")

    # Get a blob client for the specified blob
    blob_name = file_name + "." + file_type
    blob_client = container_client.get_blob_client(blob_name)
    
    # Convert data (dictionary) to JSON string
    if file_type == "json":
        data = json.dumps(data)
    elif file_type == "pdf":
        if isinstance(data, str):
            with open(data, 'rb') as pdf_file:
                data = pdf_file.read()

    
    try:
        # Upload the JSON data to the blob
        blob_client.upload_blob(data, overwrite=True)
        print(f"Blob {blob_name} in container {bot_id} has been uploaded/updated successfully.")
    except Exception as e:
        print(f"Error uploading blob: {e}")

def create_download_link(bot_id,file_type, file_name):
    """
    Create a download link for a blob with expiry on January 1st, 2030
    
    Args:
        bot_id (str): Container name
        file_name (str): Name of the file without extension
        file_type (str): File extension (json, csv, etc.)
    
    Returns:
        str: SAS URL for downloading the blob
    """
    try:
        file_name=file_name.replace(".","_").replace("-","_")
        # Get account credentials
        account_name, account_key = get_account_credentials()
        
        if not account_name or not account_key:
            raise ValueError("Could not extract account name or key from connection string")
        
        # Construct blob name
        blob_name = file_name + "." + file_type
        
        # Set expiry to January 1st, 2030
        expiry_time = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=account_name,
            account_key=account_key,
            container_name=bot_id,
            blob_name=blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time
        )
        
        # Construct the full URL
        blob_url = f"https://{account_name}.blob.core.windows.net/{bot_id}/{blob_name}?{sas_token}"
        
        print(f"Download link created for {blob_name} (expires: January 1st, 2030)")
        return blob_url
        
    except Exception as e:
        print(f"Error creating download link: {e}")
        return None

def getfromblob(session_id,namespace):

    try:
        session_id=session_id.replace(".","_").replace("-","_")
        product_json=session_id+".json"
        if not os.path.exists("blob_data"):
            os.makedirs("blob_data")
        if not os.path.exists("blob_data/"+namespace):
            os.makedirs("blob_data/"+namespace)
        download_file_path="blob_data/"+namespace+"/"+product_json

        # Get a client to interact with the specific blob
        blob_client = blob_service_client.get_blob_client(container=namespace, blob=product_json)

        # Check if the blob exists before trying to download
        if not blob_client.exists():
            print(f"Blob {product_json} does not exist in container {namespace}")
            return None

        # Download the blob (file) to a local file
        with open(download_file_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())

        print(f"Downloaded {product_json} to {download_file_path}")

        return download_file_path
    
    except Exception as e: 
        print(f"Error downloading blob {session_id} from namespace {namespace}: {str(e)}")
        return None

