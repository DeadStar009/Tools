import os
from typing import Dict, List, Any, Optional
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

class DatabaseConnector:
    """Handles database connections and operations for the Debales Tool Generator."""
    
    def __init__(self, cosmos_endpoint=None, cosmos_key=None, database_name=None):
        """Initialize the database connector.
        
        Args:
            cosmos_endpoint: Cosmos DB endpoint URL (optional, will use env var if not provided)
            cosmos_key: Cosmos DB key (optional, will use env var if not provided)
            database_name: Name of the database to use (optional, will use env var if not provided)
        """
        # Load configuration from environment if not provided
        self.cosmos_endpoint = cosmos_endpoint or os.environ.get("COSMOS_ENDPOINT") or os.environ.get("MONGODB_URI")
        self.cosmos_key = cosmos_key or os.environ.get("COSMOS_KEY")
        self.database_name = database_name or os.environ.get("DEBALES_DATABASE_NAME", "debales_tools")
        
        # Initialize the client and database
        self._init_client()
    
    def _init_client(self):
        """Initialize the Cosmos DB client and create the database if it doesn't exist."""
        try:
            if self.cosmos_key:
                self.client = CosmosClient(self.cosmos_endpoint, self.cosmos_key)
            else:
                # Use Azure identity if no key provided
                credential = DefaultAzureCredential()
                self.client = CosmosClient(self.cosmos_endpoint, credential=credential)
            
            # Create database if it doesn't exist
            self.database = self.client.create_database_if_not_exists(id=self.database_name)
            
            # Create containers if they don't exist
            self._create_containers()
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Cosmos DB client: {str(e)}")
    
    def _create_containers(self):
        """Create the required containers in Cosmos DB if they don't exist."""
        # Define the containers with their partition keys
        containers = [
            {"id": "specs", "partition_key": "/company_id"},
            {"id": "chunks", "partition_key": "/spec_id"},
            {"id": "code_artifacts", "partition_key": "/spec_id"},
            {"id": "constraints", "partition_key": "/spec_id"},
            {"id": "cache", "partition_key": "/id"}
        ]
        
        # Create each container if it doesn't exist
        for container_def in containers:
            self.database.create_container_if_not_exists(
                id=container_def["id"],
                partition_key=container_def["partition_key"]
            )
    
    def get_container(self, container_name):
        """Get a container client by name.
        
        Args:
            container_name: Name of the container
            
        Returns:
            Container client
        """
        return self.database.get_container_client(container_name)
    
    def create_item(self, container_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create an item in a container.
        
        Args:
            container_name: Name of the container
            item: Item to create
            
        Returns:
            Created item
        """
        container = self.get_container(container_name)
        return container.create_item(body=item)
    
    def upsert_item(self, container_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an item in a container.
        
        Args:
            container_name: Name of the container
            item: Item to upsert
            
        Returns:
            Upserted item
        """
        container = self.get_container(container_name)
        return container.upsert_item(body=item)
    
    def read_item(self, container_name: str, item_id: str, partition_key: str) -> Dict[str, Any]:
        """Read an item from a container.
        
        Args:
            container_name: Name of the container
            item_id: ID of the item to read
            partition_key: Partition key value
            
        Returns:
            Read item
        """
        container = self.get_container(container_name)
        return container.read_item(item=item_id, partition_key=partition_key)
    
    def delete_item(self, container_name: str, item_id: str, partition_key: str) -> None:
        """Delete an item from a container.
        
        Args:
            container_name: Name of the container
            item_id: ID of the item to delete
            partition_key: Partition key value
        """
        container = self.get_container(container_name)
        container.delete_item(item=item_id, partition_key=partition_key)
    
    def query_items(self, container_name: str, query: str, parameters: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Query items in a container.
        
        Args:
            container_name: Name of the container
            query: Query string
            parameters: Query parameters
            
        Returns:
            List of items matching the query
        """
        container = self.get_container(container_name)
        return list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        )) 