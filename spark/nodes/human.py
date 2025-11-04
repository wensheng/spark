"""
Built-in human-in-the-loop policy that drives interactive CLI prompts.
"""

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol, Sequence

from spark.nodes.base import BaseNode
from spark.nodes.types import ExecutionContext, NodeMessage

PromptKind = Literal['text', 'options', 'clipboard', 'custom']


class HumanInLoopPolicy(Protocol):
    """Protocol for human-in-the-loop policies."""

    async def apply(self, node: BaseNode, context: ExecutionContext, result: Any) -> Any:
        """Apply the policy to the given node result."""


@dataclass(slots=True)
class HumanPrompt:
    """Description of a human interaction."""

    message: str
    kind: PromptKind = 'text'
    options: Sequence[str] | None = None
    allow_freeform: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HumanResponse:
    """Captured user response from a human prompt."""

    kind: PromptKind
    raw_value: str
    selected_option: str | None = None
    selected_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a serialisable payload for logging or downstream use."""
        payload: dict[str, Any] = {
            'kind': self.kind,
            'raw_value': self.raw_value,
        }
        if self.selected_option is not None:
            payload['selected_option'] = self.selected_option
        if self.selected_index is not None:
            payload['selected_index'] = self.selected_index
        if self.metadata:
            payload['metadata'] = self.metadata
        return payload


InputProvider = Callable[[str], Awaitable[str]]
TriggerFn = Callable[[BaseNode, ExecutionContext, Any], bool | Awaitable[bool]]
PromptFactory = Callable[[BaseNode, ExecutionContext, Any], HumanPrompt | Awaitable[HumanPrompt]]
SubmitHandler = Callable[[BaseNode, ExecutionContext, Any, HumanResponse], Any | Awaitable[Any]]


async def _maybe_await(value: Any) -> Any:
    """Await value if it is awaitable."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_input(prompt: str) -> str:
    """Default synchronous input shim executed in a background thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


class InteractiveHumanPolicy:
    """
    Built-in human-in-the-loop policy that drives interactive CLI prompts.

    The policy supports simple option selection, free-form text, and multi-line
    clipboard-style pastes. Consumers can override the trigger, prompt factory,
    and submit handler to customise behaviour.
    """

    def __init__(
        self,
        *,
        trigger: TriggerFn | None = None,
        prompt: HumanPrompt | PromptFactory | None = None,
        on_submit: SubmitHandler | None = None,
        input_provider: InputProvider | None = None,
    ) -> None:
        self._trigger = trigger or (lambda node, ctx, result: True)
        self._prompt_factory = prompt
        self._on_submit = on_submit
        self._input: InputProvider = input_provider or _default_input

    async def apply(self, node: BaseNode, context: ExecutionContext, result: Any) -> Any:
        """Apply the policy, optionally gathering human input."""
        should_prompt = await _maybe_await(self._trigger(node, context, result))
        if not should_prompt:
            return result

        prompt = await self._resolve_prompt(node, context, result)
        response = await self._collect_input(prompt)

        if self._on_submit is not None:
            updated = await _maybe_await(self._on_submit(node, context, result, response))
        else:
            updated = self._default_on_submit(node, context, result, response)

        # Allow handlers to opt out of modifying the result by returning None.
        return result if updated is None else updated

    async def _resolve_prompt(
        self,
        node: BaseNode,
        context: ExecutionContext,
        result: Any,
    ) -> HumanPrompt:
        """Resolve the prompt descriptor from the provided factory."""
        if self._prompt_factory is None:
            return HumanPrompt(
                message='Review the node output and provide feedback (press Enter to skip).',
                kind='text',
                allow_freeform=True,
            )
        if isinstance(self._prompt_factory, HumanPrompt):
            return self._prompt_factory
        return await _maybe_await(self._prompt_factory(node, context, result))

    async def _collect_input(self, prompt: HumanPrompt) -> HumanResponse:
        """Collect user input based on the prompt kind."""
        if prompt.kind == 'options' and prompt.options:
            return await self._collect_option(prompt)
        if prompt.kind == 'clipboard':
            return await self._collect_clipboard(prompt)
        return await self._collect_text(prompt)

    async def _collect_option(self, prompt: HumanPrompt) -> HumanResponse:
        """Collect an option-based response."""
        if prompt.options is None or len(prompt.options) == 0:
            raise ValueError('options prompt requires at least one option')

        print(prompt.message)
        for idx, option in enumerate(prompt.options, 1):
            print(f'  [{idx}] {option}')
        if prompt.allow_freeform:
            print('  [custom] Type any other value for a custom response')

        while True:
            raw = (await self._input('Select option: ')).strip()
            if not raw:
                print('Please provide a selection.')
                continue
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(prompt.options):
                    value = prompt.options[index - 1]
                    return HumanResponse(
                        kind='options',
                        raw_value=value,
                        selected_option=value,
                        selected_index=index,
                        metadata=dict(prompt.metadata),
                    )
            if prompt.allow_freeform:
                return HumanResponse(
                    kind='options',
                    raw_value=raw,
                    selected_option=None,
                    selected_index=None,
                    metadata=dict(prompt.metadata),
                )
            print('Invalid selection, try again.')

    async def _collect_text(self, prompt: HumanPrompt) -> HumanResponse:
        """Collect a single-line text response."""
        if prompt.message:
            print(prompt.message)
        raw = await self._input('> ' if prompt.message else '')
        return HumanResponse(
            kind=prompt.kind,
            raw_value=raw,
            metadata=dict(prompt.metadata),
        )

    async def _collect_clipboard(self, prompt: HumanPrompt) -> HumanResponse:
        """Collect a multi-line clipboard-style response."""
        print(prompt.message)
        print('Paste content below. Submit an empty line to finish.')
        lines: list[str] = []
        while True:
            line = await self._input('')
            if line == '':
                break
            lines.append(line.rstrip('\n'))
        raw = '\n'.join(lines)
        return HumanResponse(
            kind='clipboard',
            raw_value=raw,
            metadata=dict(prompt.metadata),
        )

    def _default_on_submit(
        self,
        node: BaseNode,
        context: ExecutionContext,
        result: Any,
        response: HumanResponse,
    ) -> Any:
        """Default strategy attaches human feedback to the node result."""
        payload = response.to_payload()
        # Persist feedback on the node state for auditing.
        context.state['human_feedback'] = payload  # type: ignore[attr-defined]

        if isinstance(result, NodeMessage):
            extras = dict(result.extras)
            extras['human_feedback'] = payload
            return result.model_copy(update={'extras': extras})

        if isinstance(result, dict):
            merged = dict(result)
            merged['human_feedback'] = payload
            return merged

        return result
