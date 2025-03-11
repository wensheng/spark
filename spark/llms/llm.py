"""
LLM class
"""
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential


@dataclass
class LLM:
    """LLM class"""
    model: str = field(default="gpt-4o-mini")
    model_config: dict[str, Any] = field(default_factory=dict)
    temperature: float = field(default=0.0)
    max_tokens: int = field(default=4096)
    client: AsyncOpenAI | None = field(default=None)

    def __post_init__(self):
        """Post-initialization setup"""
        if not self.client:
            self.client = AsyncOpenAI()

    @retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=2, max=10))
    async def chat(self, messages: list[dict[str, Any]]) -> str:
        """Chat with the LLM"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        bot_messages = []
        async for chunk in response:
            chunk_msg = chunk.choices[0].delta.content or ""
            bot_messages.append(chunk_msg)
            print(chunk_msg, end="", flush=True)

        print()  # Newline after streaming
        final_response = "".join(bot_messages).strip()
        if not final_response:
            raise ValueError("Empty response from streaming LLM")
        return final_response
