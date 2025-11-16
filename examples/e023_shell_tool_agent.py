"""
A agent that can use shell tools to answer questions.
"""
import sys
from spark.utils import arun
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.models.openai import OpenAIModel
from spark.models.gemini import GeminiModel
from spark.models.bedrock import BedrockModel
from spark.tools.depot.shell_tools import ShellTool


grep_tool = ShellTool(
    name="grep_tool",
    description="A tool that searches for a pattern in files within a specified directory using grep.",
    command_template="cd {} && grep {} -R *",
    parameters={
        "directory": {
            "type": "string",
            "description": "The directory to search in",
            "required": True
        },
        "pattern": {
            "type": "string",
            "description": "The pattern to search for",
            "required": True
        }
    }
)

find_tool = ShellTool(
    name="find_tool",
    description="A tool that searches for files within a specified directory using find.",
    command_template="cd {} && find . -name '{}'",
    parameters={
        "directory": {
            "type": "string",
            "description": "The directory to search in",
            "required": True
        },
        "pattern": {
            "type": "string",
            "description": "The pattern to search for",
            "required": True
        }
    }
)


async def main(n=1):
    """Process a question using an agent with web search capability."""
    # question = "go to examples folder and search for 'BedrockModel'"
    question = "find all __init__.py files in current directory"
    
    if n == 1:
        model = OpenAIModel(model_id='gpt-5-nano')
    elif n == 2:
        model = GeminiModel(model_id='gemini-2.5-flash')
    elif n == 3:
        model = BedrockModel()
    system_prompt = "You are an assistant that can answer questions with access to different tools."
    config = AgentConfig(
        model=model, 
        tools=[grep_tool, find_tool], 
        system_prompt=system_prompt,
    )
    agent = Agent(config)
    
    print(f"🤔 Processing question: {question}\n")
    
    await agent.run({'messages': [{"role": "user", "content": question}]})
    
    print(f"\n✅ Final Answer:\n{agent.outputs and agent.outputs.content}")
    print(f"🔧 Tool traces:\n{agent.get_tool_traces()}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
            assert n in [1, 2, 3]
        except (ValueError, AssertionError):
            print("Invalid argument. Please provide a number between 1 and 3.")
            sys.exit(1)
    else:
        n = 1
    arun(main(n))
