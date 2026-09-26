import os

# Load .env manually
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from backend.app.llm_provider import get_provider

def test_smoke():
    provider = get_provider()
    print("Provider:", type(provider).__name__)
    
    # Test simple completion
    response = provider.generate([{"role": "user", "content": "What is 2+2? Answer with a single digit."}])
    print("Simple response:", response.text)
    if not response.text:
        print("Raw response:", response.raw)

    # Test tool calling
    tools = [{
        "name": "calculate",
        "description": "Calculate a math expression",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"]
        }
    }]
    response_with_tool = provider.generate([{"role": "user", "content": "Calculate 15 * 7"}], tools=tools)
    print("Tool calls:", response_with_tool.tool_calls)

if __name__ == "__main__":
    test_smoke()
