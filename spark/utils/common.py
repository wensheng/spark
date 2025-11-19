"""
Common Spark Utils
"""

import asyncio
import inspect
import os
from typing import Any

import openai
from pydantic import BaseModel

_OPENAI_CLIENT: dict[str, openai.OpenAI] = {}


def get_openai_client():
    """Get or create an OpenAI compatible client."""
    base_url = os.getenv('OPENAI_BASE_URL', 'openai')
    if base_url in _OPENAI_CLIENT:
        return _OPENAI_CLIENT[base_url]

    if base_url == 'openai':
        _OPENAI_CLIENT[base_url] = openai.OpenAI()
    else:
        _OPENAI_CLIENT[base_url] = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", 'null'),
            base_url=os.getenv("OPENAI_BASE_URL", base_url),
        )
    return _OPENAI_CLIENT[base_url]


class SparkUtilError(Exception):
    """Exception for Spark utility errors."""


def arun(fno):
    """Wrapper for asyncio.run."""
    if not inspect.iscoroutine(fno):
        raise SparkUtilError(f"{fno} must be a coroutine (use async def and call without await)")
    return asyncio.run(fno)


def ask_llm(
    messages: str | list[dict[str, str]],
    model='gpt-5-nano',
    instructions: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    response_format: Any = None,
) -> str:
    """
    Use new OpenAI responses.create API for openai.
    Use chat.completions.create for other models.
    """
    if response_format is not None and not issubclass(response_format, BaseModel):
        raise ValueError("response_format must be a Pydantic BaseModel or None")
    client = get_openai_client()

    if not os.getenv('OPENAI_BASE_URL') or os.environ['OPENAI_BASE_URL'] == 'openai':
        if response_format is not None:
            response = client.responses.parse(
                model=model,
                input=messages,
                instructions=instructions,
                tools=tools,
                text_format=response_format,
            )
            return response.output_parsed

        response = client.responses.create(
            model=model,
            input=messages,
            instructions=instructions,
            tools=tools,
        )
        return response.output_text

    if isinstance(messages, str):
        llm_messages = [{"role": "user", "content": messages}]
    else:
        llm_messages = list(messages)
    if instructions:
        llm_messages.insert(0, {"role": "system", "content": instructions})
    if response_format is not None:
        response = client.chat.completions.parse(
            model=model,
            messages=llm_messages,
            response_format=response_format,
            tools=tools,
        )
        return response.choices[0].message.output_parsed

    response = client.chat.completions.create(
        model=model,
        messages=llm_messages,
        tools=tools,
    )
    return response.choices[0].message.content


def search_web(query):
    """Search the web for a query."""
    try:
        import ddgs
    except ImportError:
        raise ImportError("ddgs package is required for search_web")
    results = ddgs.DDGS().text(query, max_results=5)
    # Convert results to a string
    results_str = "\n\n".join([f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}" for r in results])
    return results_str
