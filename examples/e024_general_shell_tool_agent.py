"""
A agent that can use shell tools to answer user questions.
Warning:
    This agent is not safe to use, as it can execute any bash commands.
    Please use it with caution.
"""
import sys
from textwrap import dedent

from spark.utils import arun
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.models.openai import OpenAIModel
from spark.models.gemini import GeminiModel
from spark.tools.depot.shell_tools import ShellTool


# general shell tool that execute any shell commands
shell_tool = ShellTool()


async def main(question: str):
    """Process a question using an agent with web search capability."""
    model = OpenAIModel(model_id='gpt-5-mini')
    # model = GeminiModel(model_id='gemini-2.5-flash')
    config = AgentConfig(
        model=model, 
        tools=[shell_tool], 
        system_prompt=dedent("""
            You are a helpful assistant that can answer questions with access to a shell tool that can execute any bash commands.
            In addition to the normal bash commands such as ls, cd, cat, find, ex, wc, grep, sed, awk, date, time, xargs, etc.,
            these commands are also available:
            - python: use -c to execute python code, e.g. python -c "import math;print(math.sqrt(10))"
            - tree: display the directory structure in a tree-like format
            - ffmpeg: a powerful tool for processing audio and video files
            - curl: transfer data from or to a server
            - sqlite3: a command-line tool for SQLite databases
        """)
    )
    agent = Agent(config)
    
    print(f"🤔 Processing question: {question}\n")
    
    await agent.run({'messages': [{"role": "user", "content": question}]})
    
    print(f"\n✅ Final Answer:\n{agent.outputs and agent.outputs.content}")
    print(f"🔧 Tool traces:\n{agent.get_tool_traces()}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "how many markdown files in the current directory? list them all"
    arun(main(question))
