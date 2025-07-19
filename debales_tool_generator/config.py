import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Build the path to the .env file in the current directory
env_path = Path(".env")
load_dotenv(dotenv_path=env_path)

class DebalesConfig:
    """Central configuration for the Debales Tool Generator."""
    
    def __init__(self, mongodb_uri=None, azure_openai_key=None, anthropic_key=None):
        # Load from environment if not provided
        self.mongodb_uri = mongodb_uri or os.environ.get("MONGODB_URI")
        self.azure_openai_key = azure_openai_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.azure_openai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        
        # Database configuration
        self.database_name = os.environ.get("DEBALES_DATABASE_NAME", "debales_tools")
        
        # Model configuration
        self.embeddings_model = os.environ.get("EMBEDDINGS_MODEL", "text-embedding-ada-002")
        self.gpt_model = os.environ.get("GPT_MODEL", "gpt-4-turbo")
        self.claude_opus_model = os.environ.get("CLAUDE_OPUS_MODEL", "claude-3-opus-20240229")
        self.claude_sonnet_model = os.environ.get("CLAUDE_SONNET_MODEL", "claude-3-5-sonnet-20240620")
        
        # Azure OpenAI deployments
        self.azure_embeddings_deployment = os.environ.get("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT") or os.environ.get("AZURE_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-ada-002")
        self.azure_gpt_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        
        # Initialize clients
        self._init_mongodb_client()
    
    def _init_mongodb_client(self):
        """Initialize the MongoDB client."""
        try:
            # Connect to MongoDB
            self.client = MongoClient(self.mongodb_uri)
            
            # Get or create database
            self.database = self.client[self.database_name]
            
            # Create collections if they don't exist
            self._create_collections()
        except Exception as e:
            raise ConnectionError(f"Failed to initialize MongoDB client: {str(e)}")
    
    def _create_collections(self):
        """Create the required collections if they don't exist."""
        # Define the collections
        collections = [
            "specs",
            "chunks",
            "code_artifacts",
            "constraints",
            "cache"
        ]
        
        # Create each collection if it doesn't exist
        for collection_name in collections:
            if collection_name not in self.database.list_collection_names():
                self.database.create_collection(collection_name)
    
    def get_container(self, collection_name):
        """Get a collection by name."""
        return self.database[collection_name] 