"""
Example showcasing an agent that lets the LLM call a search tool.

The LLM determines whether to call `web_search` (powered by DuckDuckGo)
and loops until it can produce a final answer.

This example does not use Spark Agent, or Node/Graph, it only use Spark models and tools.
"""

from __future__ import annotations


from spark.tools.decorator import tool
from spark.tools.registry import ToolRegistry
from spark.models.types import Messages
from spark.models.openai import OpenAIModel
from spark.models.bedrock import BedrockModel
from spark.utils.common import arun, get_openai_client, search_web

MAX_TOOL_TURNS = 6

SYSTEM_PROMPT = """
You are an expert research assistant. You may call the `web_search` tool to look
up fresh information. When you have gathered enough context, provide a concise
and well sourced final answer. If the tool returns multiple snippets, extract
the key facts before responding.
""".strip()

@tool
def web_search(query: str) -> str:
    """Wrap spark.utils.common.search_web so it can be called as an LLM tool."""
    print(f"🌐 Running web search for: {query}")
    return search_web(query)


async def main(question: str):
    registry = ToolRegistry()
    registry.process_tools([web_search])
    specs = registry.get_all_tool_specs()
    # model = OpenAIModel(model_id='gpt-5-nano')
    model = BedrockModel(enable_cache=True)
    messages: Messages = [{"role": "user", "content": [{"text": question}]}]
    for turn in range(MAX_TOOL_TURNS):
        resp = await model.get_text(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            tool_specs=specs,
        )
        if 'tool_calls' not in resp or not resp['tool_calls']:
            # No tool calls, we have our final answer.
            break

        # Build assistant message content with tool_use blocks (Bedrock format)
        assistant_content = []

        # Add text content if present
        if resp.get('content'):
            assistant_content.append({'text': resp['content']})

        # Add tool use blocks
        for call in resp['tool_calls']:
            assistant_content.append({
                "toolUse": {
                    "toolUseId": call['id'],
                    "name": call['function'].get('name', ''),
                    "input": call['function'].get('arguments', {})
                }
            })

        messages.append({
            "role": "assistant",
            "content": assistant_content,
        })
        for call in resp['tool_calls']:
            if ('function' in call
                and 'name' in call['function']
                and call['function']['name'] in registry.registry
            ):
                current_tool = registry.registry[call['function']['name']]
                args = call['function'].get('arguments', {})
                tool_result = current_tool(**args)
                print(f"Tool call results for {args}: {tool_result}")
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": call['id'],
                                "content": [{"text": tool_result}]
                            }
                        }
                    ],
                })

    print("Final answer:", resp.get('content'))


if __name__ == "__main__":
    question = "Who won the Nobel Prize in Physics 2025?"
    arun(main(question))
