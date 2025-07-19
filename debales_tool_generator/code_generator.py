import json
import hashlib
import anthropic
from typing import Dict, List, Any, Optional
from .constraint_manager import ConstraintManager

class CodeGenerator:
    """Generates client code using Claude 3.5 Sonnet."""
    
    def __init__(self, config):
        """Initialize the code generator.
        
        Args:
            config: DebalesConfig instance with API keys and connections
        """
        self.client = anthropic.Anthropic(api_key=config.anthropic_key)
        self.model = config.claude_sonnet_model
        self.constraint_manager = ConstraintManager(config)
        self.chunks_container = config.get_container("chunks")
        self.code_artifacts_container = config.get_container("code_artifacts")
    
    def generate_client_code(self, spec_id: str, endpoint_id: str, custom_prompt: str = "") -> Dict[str, Any]:
        """Generate client code for an endpoint.
        
        Args:
            spec_id: ID of the API specification
            endpoint_id: ID of the endpoint to generate code for
            custom_prompt: Optional custom instructions for the LLM
            
        Returns:
            Dictionary with generated code and metadata
        """
        # Get the endpoint data
        try:
            endpoint_doc = self.chunks_container.read_item(item=endpoint_id, partition_key=spec_id)
            endpoint_data = endpoint_doc["endpoint_data"]
        except Exception as e:
            raise ValueError(f"Failed to retrieve endpoint {endpoint_id}: {str(e)}")
        
        # Get constraints for this endpoint
        constraints = self.constraint_manager.get_endpoint_constraints(
            spec_id, endpoint_data["path"]
        )
        
        # Format constraints for the prompt
        constraint_block = "\n".join([
            f"- {c['condition']} # {c['error_message']}"
            for c in constraints
        ])
        
        # Build the prompt for Claude
        prompt = f"""
        Generate Python client code for this API endpoint:
        
        {endpoint_data['method']} {endpoint_data['path']}
        
        Endpoint details:
        {json.dumps(endpoint_data, indent=2)}
        
        CONSTRAINTS TO ENFORCE:
        {constraint_block}
        
        Requirements:
        1. Use modern Python best practices (type hints, docstrings, error handling)
        2. Handle all parameters correctly (path, query, body)
        3. Implement proper error handling with specific error messages
        4. Enforce all constraints listed above
        5. Include retry logic for transient errors
        6. Return structured response data
        7. Include detailed documentation
        
        {custom_prompt}
        
        Return ONLY the Python code without any explanation or markdown formatting.
        """
        
        # Call Claude to generate the code
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract the code from the response
        response_text = response.content[0].text
        
        # Try to extract code block if present
        code = self._extract_code_block(response_text)
        
        # Generate a unique ID for the code artifact
        artifact_id = hashlib.sha256(
            f"{spec_id}:{endpoint_id}:{code}".encode()
        ).hexdigest()
        
        # Create the code artifact document
        artifact_doc = {
            "id": artifact_id,
            "artifact_id": artifact_id,
            "spec_id": spec_id,
            "endpoint_id": endpoint_id,
            "tool_code": code,
            "validation_status": "pending",
            "created_at": anthropic.util.get_datetime_str()
        }
        
        # Store the code artifact in Cosmos DB
        self.code_artifacts_container.upsert_item(body=artifact_doc)
        
        return artifact_doc
    
    def generate_batch_client_code(self, spec_id: str, custom_prompt: str = "") -> List[Dict[str, Any]]:
        """Generate client code for all endpoints in a spec.
        
        Args:
            spec_id: ID of the API specification
            custom_prompt: Optional custom instructions for the LLM
            
        Returns:
            List of dictionaries with generated code and metadata
        """
        # Query all endpoint chunks for this spec
        query = "SELECT * FROM c WHERE c.spec_id = @spec_id"
        parameters = [{"name": "@spec_id", "value": spec_id}]
        
        endpoint_chunks = list(self.chunks_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        # Generate code for each endpoint
        artifacts = []
        for chunk in endpoint_chunks:
            try:
                artifact = self.generate_client_code(
                    spec_id, chunk["chunk_id"], custom_prompt
                )
                artifacts.append(artifact)
            except Exception as e:
                # Log error and continue with next endpoint
                print(f"Error generating code for endpoint {chunk['chunk_id']}: {str(e)}")
        
        return artifacts
    
    def _extract_code_block(self, text: str) -> str:
        """Extract code block from text if present.
        
        Args:
            text: Text that may contain a code block
            
        Returns:
            Extracted code or the original text
        """
        # Look for Python code block
        python_start = text.find("```python")
        if python_start >= 0:
            code_start = text.find("\n", python_start) + 1
            code_end = text.find("```", code_start)
            if code_end >= 0:
                return text[code_start:code_end].strip()
        
        # Look for generic code block
        code_start = text.find("```")
        if code_start >= 0:
            code_start = text.find("\n", code_start) + 1
            code_end = text.find("```", code_start)
            if code_end >= 0:
                return text[code_start:code_end].strip()
        
        # No code block found, return the text as is
        return text.strip() 