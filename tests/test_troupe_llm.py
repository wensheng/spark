"""Integration coverage for running LLM provider work through a Troupe."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import pytest

from spark import Syndicate
from spark.agent import ChatMessage, LLMRequest, LLMResponse, LLMStreamChunk, Tool, ToolResult
from spark.contrib.troupe import Troupe
from spark.core.message import Message


@dataclass(frozen=True, slots=True)
class TranslationJob:
    language: str
    text: str


class ParallelProbeProvider:
    """Provider-compatible fake that only completes once all requests have started."""

    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.started: list[str] = []
        self._lock = asyncio.Lock()
        self._all_started = asyncio.Event()

    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        language = str(request.metadata["language"])
        async with self._lock:
            self.started.append(language)
            if len(self.started) >= self.expected:
                self._all_started.set()

        await asyncio.wait_for(self._all_started.wait(), timeout=1.0)
        content = f"{language}: {request.prompt}"
        return LLMResponse(
            request_id=request.request_id,
            content=content,
            history=(*history, ChatMessage("assistant", content)),
            metadata={"provider": "parallel-probe", "language": language},
        )

    async def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        if False:
            yield LLMStreamChunk(request_id=request.request_id)
        raise NotImplementedError


class TranslationTroupe(Troupe):
    troupe_max_count = 5
    troupe_idle_count = 5

    provider: ParallelProbeProvider | None = None

    async def process(self, message: Message) -> None:
        job = message.content
        if not isinstance(job, TranslationJob) or message.sender is None:
            return
        if self.provider is None:
            raise RuntimeError("TranslationTroupe.provider must be configured")

        request = LLMRequest(
            prompt=job.text,
            instructions=f"Translate the paragraph into {job.language}.",
            metadata={"language": job.language},
        )
        response = await self.provider.complete(request, [ChatMessage("user", request.prompt)])
        await self.tell((job.language, response.content), message.sender)


@pytest.mark.asyncio
async def test_troupe_runs_llm_provider_requests_in_parallel() -> None:
    languages = ["Spanish", "French", "German", "Japanese", "Chinese"]
    TranslationTroupe.provider = ParallelProbeProvider(expected=len(languages))
    try:
        async with Syndicate("troupe-llm-parallel-test") as system:
            translator = await system.create_actor(TranslationTroupe)
            for language in languages:
                await system.tell(translator, TranslationJob(language, "Actor pools can run independent LLM work."))

            replies = [await system.receive(timeout=2.0) for _ in languages]
    finally:
        provider = TranslationTroupe.provider
        TranslationTroupe.provider = None

    assert sorted(language for language, _content in replies) == sorted(languages)
    assert provider is not None
    assert sorted(provider.started) == sorted(languages)
