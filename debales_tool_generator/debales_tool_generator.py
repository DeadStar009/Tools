import json
import hashlib
from typing import Dict, List, Any, Optional
from langchain.tools import BaseTool

from .config import DebalesConfig
from .spec_processor import SpecProcessor
from .code_generator import CodeGenerator
from .tool_wrapper import ToolWrapper
from .master_orchestrator import MasterOrchestrator
from .constraint_manager import ConstraintManager
from .cache_manager import CacheManager

class DebalesToolGenerator:
    """Main entry point for the Debales Tool Generator."""
    
    def __init__(self, mongodb_uri=None, azure_openai_key=None, anthropic_key=None):
        """Initialize the Debales Tool Generator.
        
        Args:
            mongodb_uri: MongoDB connection URI (optional, will use env var if not provided)
            azure_openai_key: Azure OpenAI API key (optional, will use env var if not provided)
            anthropic_key: Anthropic API key (optional, will use env var if not provided)
        """
        # Initialize configuration
        self.config = DebalesConfig(
            mongodb_uri=mongodb_uri,
            azure_openai_key=azure_openai_key,
            anthropic_key=anthropic_key
        )
        
        # Initialize components
        self.spec_processor = SpecProcessor(self.config)
        self.code_generator = CodeGenerator(self.config)
        self.tool_wrapper = ToolWrapper(self.config)
        self.constraint_manager = ConstraintManager(self.config)
        self.cache_manager = CacheManager(self.config)
        self.master = MasterOrchestrator(
            self.config, 
            self.spec_processor,
            self.code_generator,
            self.tool_wrapper,
            self.constraint_manager,
            self.cache_manager
        )
    
    def generate_tools(self, spec_content: str, company_id: str, custom_prompt: str = "") -> List[BaseTool]:
        """Generate LangChain tools from an OpenAPI spec.
        
        Args:
            spec_content: Raw OpenAPI spec content (JSON or YAML)
            company_id: ID of the company owning the spec
            custom_prompt: Optional custom instructions for the LLMs
            
        Returns:
            List of instantiated LangChain tools
        """
        # Store the spec
        spec_id = self.spec_processor.store_spec(spec_content, company_id)
        
        # Orchestrate the tool generation process
        orchestration_result = self.master.orchestrate(spec_id, custom_prompt)
        
        # Check if orchestration was successful
        if not orchestration_result.get("complete", False) or orchestration_result.get("aborted", False):
            raise RuntimeError(f"Tool generation failed: {orchestration_result.get('errors', ['Unknown error'])}")
        
        # Load the generated tools
        tools = self.tool_wrapper.load_all_tools(spec_id)
        
        return tools
    
    def get_tools_by_spec_id(self, spec_id: str) -> List[BaseTool]:
        """Get previously generated tools by spec ID.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            List of instantiated LangChain tools
        """
        return self.tool_wrapper.load_all_tools(spec_id)
    
    def get_tool_code(self, spec_id: str) -> Dict[str, str]:
        """Get the code for all tools generated from a spec.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            Dictionary mapping tool names to their code
        """
        # Query all wrapped code artifacts for this spec
        code_artifacts = self.config.get_container("code_artifacts").find({
            "spec_id": spec_id,
            "is_wrapped": True
        })
        
        # Create a dictionary mapping tool names to their code
        tool_code = {}
        for artifact in code_artifacts:
            # Extract the tool name from the code
            code = artifact["tool_code"]
            
            # Look for class definition
            lines = code.split("\n")
            for line in lines:
                if "class" in line and "BaseTool" in line:
                    # Extract class name
                    class_name = line.split("class ")[1].split("(")[0].strip()
                    tool_code[class_name] = code
                    break
        
        return tool_code
    
    def get_constraints(self, spec_id: str) -> List[Dict[str, Any]]:
        """Get all constraints for a spec.
        
        Args:
            spec_id: ID of the API specification
            
        Returns:
            List of constraint dictionaries
        """
        return self.constraint_manager.get_constraints(spec_id)
    
    def add_constraint(self, spec_id: str, constraint: Dict[str, Any]) -> str:
        """Add a constraint to a spec.
        
        Args:
            spec_id: ID of the API specification
            constraint: Dictionary containing constraint details
            
        Returns:
            The ID of the added constraint
        """
        return self.constraint_manager.add_constraint(spec_id, constraint)
    
    def clear_cache(self) -> int:
        """Clear expired items from the cache.
        
        Returns:
            Number of items cleared
        """
        return self.cache_manager.clear_expired()
        
    def integrate_with_support_chatbot(self, spec_id: str, bot_id: str):
        """Integrate generated tools with the Support Chatbot system.
        
        Args:
            spec_id: ID of the API specification
            bot_id: ID of the chatbot to integrate with
            
        Returns:
            Dictionary with integration details
        """
        # Load the generated tools
        tools = self.tool_wrapper.load_all_tools(spec_id)
        
        # Create integration info
        integration_info = {
            "spec_id": spec_id,
            "bot_id": bot_id,
            "tools_count": len(tools),
            "tool_names": [tool.name for tool in tools],
            "integration_time": hashlib.sha256(f"{spec_id}:{bot_id}".encode()).hexdigest()
        }
        
        # Return integration details
        return integration_info 