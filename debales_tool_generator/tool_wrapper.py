import json
import hashlib
import openai
from typing import Dict, List, Any, Optional
from langchain.tools import BaseTool

class ToolWrapper:
    """Wraps client code into LangChain tools using GPT-4-Turbo."""
    
    def __init__(self, config):
        """Initialize the tool wrapper.
        
        Args:
            config: DebalesConfig instance with API keys and connections
        """
        self.client = openai.AzureOpenAI(
            api_key=config.azure_openai_key,
            api_version=config.azure_openai_api_version,
            azure_endpoint=config.azure_openai_endpoint
        )
        self.model = config.gpt_model
        self.deployment = config.azure_gpt_deployment
        self.code_artifacts_container = config.get_container("code_artifacts")
        self.chunks_container = config.get_container("chunks")
    
    def wrap_as_tool(self, artifact_id: str, custom_prompt: str = "") -> Dict[str, Any]:
        """Wrap client code as a LangChain tool.
        
        Args:
            artifact_id: ID of the code artifact to wrap
            custom_prompt: Optional custom instructions for the LLM
            
        Returns:
            Dictionary with the wrapped tool code and metadata
        """
        # Get the code artifact
        try:
            artifact_doc = self.code_artifacts_container.read_item(
                item=artifact_id, 
                partition_key=artifact_doc["spec_id"]
            )
            code = artifact_doc["tool_code"]
            endpoint_id = artifact_doc["endpoint_id"]
        except Exception as e:
            raise ValueError(f"Failed to retrieve code artifact {artifact_id}: {str(e)}")
        
        # Get the endpoint data
        try:
            endpoint_doc = self.chunks_container.read_item(
                item=endpoint_id, 
                partition_key=artifact_doc["spec_id"]
            )
            endpoint_data = endpoint_doc["endpoint_data"]
        except Exception as e:
            raise ValueError(f"Failed to retrieve endpoint {endpoint_id}: {str(e)}")
        
        # Build the prompt for GPT-4
        prompt = f"""
        Create a LangChain BaseTool class that wraps this API client code:
        
        ```python
        {code}
        ```
        
        Endpoint details:
        - Path: {endpoint_data['path']}
        - Method: {endpoint_data['method']}
        - Description: {endpoint_data.get('description', 'No description available')}
        
        Requirements:
        1. Extend langchain.tools.BaseTool
        2. Implement name, description, and _run methods
        3. Handle all parameters as tool arguments
        4. Include proper error handling
        5. Return structured data
        6. Make the tool compatible with LangChain agents
        7. Use proper type hints
        
        {custom_prompt}
        
        Return ONLY the Python code for the LangChain tool class without any explanation or markdown formatting.
        """
        
        # Call GPT-4 to generate the tool wrapper
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": "You are an expert Python developer specializing in LangChain tool creation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        # Extract the code from the response
        response_text = response.choices[0].message.content
        
        # Try to extract code block if present
        tool_code = self._extract_code_block(response_text)
        
        # Update the code artifact with the tool code
        artifact_doc["tool_code"] = tool_code
        artifact_doc["is_wrapped"] = True
        self.code_artifacts_container.replace_item(
            item=artifact_id,
            body=artifact_doc
        )
        
        return artifact_doc
    
    def wrap_batch_tools(self, spec_id: str, custom_prompt: str = "") -> List[Dict[str, Any]]:
        """Wrap all code artifacts for a spec as LangChain tools.
        
        Args:
            spec_id: ID of the API specification
            custom_prompt: Optional custom instructions for the LLM
            
        Returns:
            List of dictionaries with wrapped tool code and metadata
        """
        # Query all code artifacts for this spec
        query = "SELECT * FROM c WHERE c.spec_id = @spec_id"
        parameters = [{"name": "@spec_id", "value": spec_id}]
        
        artifacts = list(self.code_artifacts_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        # Wrap each artifact as a tool
        wrapped_artifacts = []
        for artifact in artifacts:
            try:
                wrapped = self.wrap_as_tool(
                    artifact["artifact_id"], custom_prompt
                )
                wrapped_artifacts.append(wrapped)
            except Exception as e:
                # Log error and continue with next artifact
                print(f"Error wrapping artifact {artifact['artifact_id']}: {str(e)}")
        
        return wrapped_artifacts
    
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
    
    def load_tool(self, artifact_id: str) -> BaseTool:
        """Load a wrapped tool from the database and instantiate it.
        
        Args:
            artifact_id: ID of the code artifact
            
        Returns:
            Instantiated LangChain tool
        """
        # Get the code artifact
        try:
            artifact_doc = self.code_artifacts_container.read_item(
                item=artifact_id, 
                partition_key=artifact_doc["spec_id"]
            )
            tool_code = artifact_doc["tool_code"]
        except Exception as e:
            raise ValueError(f"Failed to retrieve code artifact {artifact_id}: {str(e)}")
        
        # Compile and instantiate the tool
        try:
            # Create a namespace for the code execution
            namespace = {}
            
            # Execute the code in the namespace
            exec(tool_code, namespace)
            
            # Find the tool class (subclass of BaseTool)
            tool_class = None
            for name, obj in namespace.items():
                if isinstance(obj, type) and issubclass(obj, BaseTool) and obj != BaseTool:
                    tool_class = obj
                    break
            
            if tool_class is None:
                raise ValueError("No BaseTool subclass found in the code")
            
            # Instantiate the tool
            tool_instance = tool_class()
            return tool_instance
        except Exception as e:
            raise ValueError(f"Failed to instantiate tool: {str(e)}")
    
    def load_all_tools(self, spec_id: str) -> List[BaseTool]:
        """Load all wrapped tools for a spec.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            List of instantiated LangChain tools
        """
        # Query all wrapped code artifacts for this spec
        query = "SELECT * FROM c WHERE c.spec_id = @spec_id AND c.is_wrapped = true"
        parameters = [{"name": "@spec_id", "value": spec_id}]
        
        artifacts = list(self.code_artifacts_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        # Load each tool
        tools = []
        for artifact in artifacts:
            try:
                tool = self.load_tool(artifact["artifact_id"])
                tools.append(tool)
            except Exception as e:
                # Log error and continue with next tool
                print(f"Error loading tool {artifact['artifact_id']}: {str(e)}")
        
        return tools 