import json
import hashlib
import anthropic
from typing import Dict, List, Any, Optional
from .constraint_manager import ConstraintManager

class SpecProcessor:
    """Processes OpenAPI specs using Claude 3 Opus."""
    
    def __init__(self, config):
        """Initialize the spec processor.
        
        Args:
            config: DebalesConfig instance with API keys and connections
        """
        self.client = anthropic.Anthropic(api_key=config.anthropic_key)
        self.model = config.claude_opus_model
        self.constraint_manager = ConstraintManager(config)
        self.specs_container = config.get_container("specs")
        self.chunks_container = config.get_container("chunks")
    
    def store_spec(self, spec_content: str, company_id: str) -> str:
        """Store an OpenAPI spec in the database.
        
        Args:
            spec_content: Raw OpenAPI spec content
            company_id: ID of the company owning the spec
            
        Returns:
            The ID of the stored spec
        """
        # Parse the spec to ensure it's valid JSON/YAML
        if isinstance(spec_content, str):
            try:
                # Try to parse as JSON
                spec_obj = json.loads(spec_content)
            except json.JSONDecodeError:
                # If not JSON, keep as string (might be YAML)
                spec_obj = spec_content
        else:
            spec_obj = spec_content
        
        # Generate a hash for the spec content
        if isinstance(spec_obj, dict):
            content_hash = hashlib.sha256(json.dumps(spec_obj, sort_keys=True).encode()).hexdigest()
        else:
            content_hash = hashlib.sha256(str(spec_obj).encode()).hexdigest()
        
        # Create the spec document
        spec_doc = {
            "id": content_hash,
            "company_id": company_id,
            "raw_spec": spec_obj,
            "version_hash": content_hash,
            "ingestion_date": anthropic.util.get_datetime_str()
        }
        
        # Store the spec in Cosmos DB
        self.specs_container.upsert_item(body=spec_doc)
        
        return content_hash
    
    def process_spec(self, spec_id: str, custom_prompt: str = "") -> Dict[str, Any]:
        """Process an OpenAPI spec to extract endpoints, constraints, and more.
        
        Args:
            spec_id: ID of the stored spec to process
            custom_prompt: Optional custom instructions for the LLM
            
        Returns:
            Dictionary with processed spec information
        """
        # Get the spec from the database
        try:
            spec_doc = self.specs_container.read_item(item=spec_id, partition_key=spec_doc["company_id"])
            spec_content = spec_doc["raw_spec"]
        except Exception as e:
            raise ValueError(f"Failed to retrieve spec {spec_id}: {str(e)}")
        
        # Build the prompt for Claude
        prompt = f"""
        Process this OpenAPI specification and extract the following:
        
        1. Chunk the spec into individual endpoints
        2. For each endpoint, extract:
           - Path and method
           - Parameters (path, query, body)
           - Response schemas
           - Required security
           - Business constraints and rules
        3. Identify dependencies between endpoints
        4. Detect potential rate limits, pagination, or other special handling
        
        {custom_prompt}
        
        Format your response as a JSON object with the following structure:
        {{
          "spec_id": "{spec_id}",
          "endpoints": [
            {{
              "path": "/example/path",
              "method": "GET",
              "parameters": [...],
              "responses": [...],
              "security": [...],
              "constraints": [
                {{
                  "type": "validation|business|security|rate_limit",
                  "condition": "description of the constraint",
                  "message": "error message if violated"
                }}
              ],
              "dependencies": [...]
            }}
          ]
        }}
        
        Here's the OpenAPI spec to process:
        
        {json.dumps(spec_content, indent=2) if isinstance(spec_content, dict) else spec_content}
        """
        
        # Call Claude to process the spec
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract and parse the JSON response
        try:
            response_text = response.content[0].text
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                processed_spec = json.loads(json_str)
            else:
                raise ValueError("No valid JSON found in the response")
        except Exception as e:
            raise ValueError(f"Failed to parse Claude's response: {str(e)}")
        
        # Store endpoint chunks and extract constraints
        self._store_endpoint_chunks(processed_spec)
        self._extract_constraints(processed_spec)
        
        return processed_spec
    
    def _store_endpoint_chunks(self, processed_spec: Dict[str, Any]) -> None:
        """Store endpoint chunks in the database.
        
        Args:
            processed_spec: Processed spec with endpoints
        """
        spec_id = processed_spec["spec_id"]
        
        for endpoint in processed_spec.get("endpoints", []):
            # Generate a unique ID for the endpoint chunk
            endpoint_id = hashlib.sha256(
                f"{spec_id}:{endpoint['path']}:{endpoint['method']}".encode()
            ).hexdigest()
            
            # Create the chunk document
            chunk_doc = {
                "id": endpoint_id,
                "chunk_id": endpoint_id,
                "spec_id": spec_id,
                "endpoint_data": endpoint,
                "last_accessed": anthropic.util.get_datetime_str()
            }
            
            # Store the chunk in Cosmos DB
            self.chunks_container.upsert_item(body=chunk_doc)
    
    def _extract_constraints(self, processed_spec: Dict[str, Any]) -> None:
        """Extract constraints from the processed spec and store them.
        
        Args:
            processed_spec: Processed spec with endpoints and constraints
        """
        spec_id = processed_spec["spec_id"]
        
        for endpoint in processed_spec.get("endpoints", []):
            endpoint_pattern = endpoint["path"]
            
            for constraint in endpoint.get("constraints", []):
                # Create the constraint document
                constraint_doc = {
                    "endpoint_pattern": endpoint_pattern,
                    "rule_type": constraint.get("type", "validation"),
                    "condition": constraint["condition"],
                    "error_message": constraint.get("message", "Constraint violation")
                }
                
                # Add the constraint to the database
                self.constraint_manager.add_constraint(spec_id, constraint_doc) 