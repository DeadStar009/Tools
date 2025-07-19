import os
import sys
from pathlib import Path

# Create specs directory if it doesn't exist
specs_dir = Path(__file__).parent / "specs"
os.makedirs(specs_dir, exist_ok=True)

# Check if the Depossco API spec file exists
spec_path = specs_dir / "depossco_api.yml"
if not spec_path.exists():
    print(f"Error: Spec file not found at {spec_path}")
    print("Please create a file named 'depossco_api.yml' in the 'specs' directory with your OpenAPI spec.")
    sys.exit(1)

# Import the DebalesToolGenerator class
try:
    from debales_tool_generator.debales_tool_generator import DebalesToolGenerator
except ImportError as e:
    print(f"Error importing DebalesToolGenerator: {e}")
    print("Make sure all required files are present in the debales_tool_generator directory.")
    print("Required files: __init__.py, config.py, cache_manager.py, database_connector.py, etc.")
    sys.exit(1)

def test_depossco_api():
    # Initialize the tool generator
    try:
    generator = DebalesToolGenerator()
    except Exception as e:
        print(f"Error initializing DebalesToolGenerator: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Load the Depossco OpenAPI spec
    try:
    with open(spec_path, "r") as f:
        spec_content = f.read()
    except Exception as e:
        print(f"Error reading spec file: {e}")
        return False
    
    # Generate LangChain tools
    try:
        print("Generating tools from Depossco API spec...")
        tools = generator.generate_tools(
            spec_content=spec_content,
            company_id="depossco",
            custom_prompt="Generate tools with detailed error handling and validation."
        )
        
        print(f"Successfully generated {len(tools)} tools:")
        for tool in tools:
            print(f"- {tool.name}: {tool.description}")
        
        # Get tool code for inspection
        spec_id = getattr(tools[0], "spec_id", None)
        if not spec_id:
            print("Warning: Could not determine spec_id from tools.")
            return True
            
        tool_code = generator.get_tool_code(spec_id)
        
        # Save the generated code for inspection
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        
        for tool_name, code in tool_code.items():
            with open(output_dir / f"{tool_name}.py", "w") as f:
                f.write(code)
                
        print(f"Tool code saved to {output_dir}")
        return True
        
    except Exception as e:
        print(f"Error generating tools: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_depossco_api()
    if not success:
        sys.exit(1)