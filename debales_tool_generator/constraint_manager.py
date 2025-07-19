import json
import hashlib
from typing import Dict, List, Any, Optional

class ConstraintManager:
    """Manages API constraints and rules for the Debales Tool Generator."""
    
    def __init__(self, config):
        """Initialize the constraint manager.
        
        Args:
            config: DebalesConfig instance with Cosmos DB connection
        """
        self.container = config.get_container("constraints")
    
    def add_constraint(self, spec_id: str, constraint: Dict[str, Any]) -> str:
        """Add a constraint to the database.
        
        Args:
            spec_id: ID of the API specification
            constraint: Dictionary containing constraint details
            
        Returns:
            The ID of the added constraint
        """
        # Generate a deterministic ID based on the constraint content
        if "id" not in constraint:
            constraint_json = json.dumps(constraint, sort_keys=True)
            constraint_id = hashlib.sha256(constraint_json.encode()).hexdigest()
            constraint["id"] = constraint_id
        
        # Add the spec ID to the constraint
        constraint["spec_id"] = spec_id
        
        # Store the constraint in Cosmos DB
        self.container.upsert_item(body=constraint)
        
        return constraint["id"]
    
    def add_constraints(self, spec_id: str, constraints: List[Dict[str, Any]]) -> List[str]:
        """Add multiple constraints to the database.
        
        Args:
            spec_id: ID of the API specification
            constraints: List of dictionaries containing constraint details
            
        Returns:
            List of IDs of the added constraints
        """
        constraint_ids = []
        for constraint in constraints:
            constraint_id = self.add_constraint(spec_id, constraint)
            constraint_ids.append(constraint_id)
        
        return constraint_ids
    
    def get_constraints(self, spec_id: str) -> List[Dict[str, Any]]:
        """Get all constraints for a specification.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            List of constraint dictionaries
        """
        query = "SELECT * FROM c WHERE c.spec_id = @spec_id"
        parameters = [{"name": "@spec_id", "value": spec_id}]
        
        # Query Cosmos DB for constraints
        constraints = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        return constraints
    
    def get_endpoint_constraints(self, spec_id: str, endpoint_pattern: str) -> List[Dict[str, Any]]:
        """Get constraints for a specific endpoint.
        
        Args:
            spec_id: ID of the API specification
            endpoint_pattern: Pattern matching the endpoint
            
        Returns:
            List of constraint dictionaries
        """
        query = """
        SELECT * FROM c 
        WHERE c.spec_id = @spec_id 
        AND c.endpoint_pattern = @endpoint_pattern
        """
        parameters = [
            {"name": "@spec_id", "value": spec_id},
            {"name": "@endpoint_pattern", "value": endpoint_pattern}
        ]
        
        # Query Cosmos DB for endpoint constraints
        constraints = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        return constraints
    
    def delete_constraint(self, constraint_id: str) -> None:
        """Delete a constraint from the database.
        
        Args:
            constraint_id: ID of the constraint to delete
        """
        try:
            # Get the constraint to find its partition key (spec_id)
            constraint = self.container.read_item(
                item=constraint_id,
                partition_key=constraint_id
            )
            
            # Delete the constraint
            self.container.delete_item(
                item=constraint_id,
                partition_key=constraint["spec_id"]
            )
        except Exception:
            # Constraint not found or other error, ignore
            pass
    
    def delete_spec_constraints(self, spec_id: str) -> int:
        """Delete all constraints for a specification.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            Number of constraints deleted
        """
        query = "SELECT c.id FROM c WHERE c.spec_id = @spec_id"
        parameters = [{"name": "@spec_id", "value": spec_id}]
        
        # Find all constraints for the spec
        constraints = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        # Delete each constraint
        count = 0
        for constraint in constraints:
            try:
                self.container.delete_item(
                    item=constraint["id"],
                    partition_key=spec_id
                )
                count += 1
            except Exception:
                # Constraint not found or other error, ignore
                pass
                
        return count 