# mypy: disable-error-code="attr-defined, typeddict-item"
"""
An agent is a node, but more intelligent.
It can:
- call LLMs (with or without tools)
- keep history of messages
- call other agents/nodes
"""

import asyncio
import inspect
import json
import logging
import time
from typing import Any, Callable, Optional, TypeVar, cast

import jinja2

from spark.nodes.base import ExecutionContext, SparkError
from spark.nodes.nodes import Node
from spark.models.types import (
    ContentBlock,
    Messages as LlmMessages,
    Message as LlmMessage,
)
from spark.models.utils import get_model_from_id
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import DecoratedFunctionTool
from spark.models.echo import EchoModel
from spark.nodes.types import NodeMessage
from spark.agents.config import AgentConfig, HookFn
from spark.agents.memory import MemoryPolicyType, MemoryManager
from spark.agents.policies import (
    AgentBudgetManager,
    AgentBudgetExceededError,
    HumanPolicyManager,
    HumanApprovalRequired,
    AgentStoppedError,
)
from spark.agents.types import AgentState, ToolTrace, default_agent_state
from spark.tools.types import BaseTool, ToolChoice, ToolUse
from spark.governance.approval import ApprovalGateManager, ApprovalPendingError
from spark.governance.policy import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    PolicySubject,
    PolicyViolationError,
)

SelfAgent = TypeVar('SelfAgent', bound='Agent')
logger = logging.getLogger(__name__)


class AgentError(SparkError):
    """Base exception for all agent-related errors."""


class ToolExecutionError(AgentError):
    """Raised when a tool execution fails."""


class TemplateRenderError(AgentError):
    """Raised when template rendering fails."""


class ModelError(AgentError):
    """Raised when LLM model call fails."""


class ConfigurationError(AgentError):
    """Raised when agent configuration is invalid."""


class Agent(Node):
    """Base class for all Spark agents with LLM orchestration helpers."""

    def __init__(self, config: Optional[AgentConfig] = None, **kwargs) -> None:
        """Initialize the agent with configuration and optional parameters."""
        if config is None:
            if 'model_id' in kwargs:
                self.config = AgentConfig(model=get_model_from_id(**kwargs))
            else:
                self.config = self._get_default_config()
        else:
            self.config = config
        super().__init__(config=self.config, **kwargs)

        self.jinja2_template: Optional[jinja2.Template] = None
        if self.config.prompt_template:
            self.jinja2_template = jinja2.Template(self.config.prompt_template)

        # TODO: remove
        self.after_llm_hooks.append(self.post_llm_hook)
        # self.record_direct_tool_call: bool = True,
        self.tool_registry = ToolRegistry()
        self.tool_registry.process_tools(self.config.tools)
        self.tool_specs = self.tool_registry.get_all_tool_specs()

        # # Initialize tools and configuration
        # self.tool_registry.initialize_tools(self.load_tools_from_directory)

        # Initialize agent state management
        self._state: AgentState = default_agent_state()
        if self.config.initial_state:
            self._state.update(self.config.initial_state)  # type: ignore[typeddict-item]

        # Initialize memory manager and preload messages if any
        self.memory_manager = MemoryManager(self.config.memory_config)
        if self.config.preload_messages:
            for m in self.config.preload_messages:
                self.memory_manager.add_message(cast(dict[str, Any], m))
        # Note: memory_manager.memory is the source of truth for messages
        # state['messages'] is kept for backward compatibility but should not be used directly

        # Initialize reasoning strategy
        if self.config.reasoning_strategy is None:
            from spark.agents.strategies import NoOpStrategy
            self.reasoning_strategy = NoOpStrategy()
        else:
            self.reasoning_strategy = self.config.reasoning_strategy

        # Initialize strategy-specific state
        self.reasoning_strategy.initialize_state(self._state)

        # Initialize cost tracking
        from spark.agents.cost_tracker import CostTracker
        self.cost_tracker = CostTracker()

        self.budget_manager: AgentBudgetManager | None = None
        if self.config.budget:
            self.budget_manager = AgentBudgetManager(self.config.budget)
            self.cost_tracker.add_listener(self._handle_cost_update)

        self.human_policy_manager = HumanPolicyManager(self.config.human_policy)
        existing_policy_engine = getattr(self, 'policy_engine', None)
        if existing_policy_engine is None and self.config.policy_set:
            existing_policy_engine = PolicyEngine(self.config.policy_set)
        self.policy_engine = existing_policy_engine

    @property
    def state(self) -> AgentState:
        """Get the current state of the agent.

        Note: The 'messages' field in state is synchronized from memory_manager
        on access for backward compatibility. Use agent.messages property for
        direct access to conversation history.
        """
        # Sync messages from memory_manager (source of truth)
        self._state['messages'] = list(self.memory_manager.memory)
        return self._state

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Get conversation messages from memory manager.

        This is the preferred way to access conversation history.
        Returns a reference to the memory manager's message list.
        """
        return self.memory_manager.memory

    def _get_default_config(self) -> AgentConfig:
        """Get the default config instance for this agent type."""
        return AgentConfig(model=EchoModel())

    def _record_tool_trace(
        self,
        tool_name: str,
        tool_use_id: str,
        input_params: dict[str, Any],
        output: Any,
        start_time: float,
        end_time: float,
        error: Optional[str] = None,
    ) -> None:
        """Record a tool execution trace in the agent state.

        Args:
            tool_name: Name of the tool that was executed
            tool_use_id: Unique identifier for this tool invocation
            input_params: Input parameters passed to the tool
            output: Result returned by the tool
            start_time: Unix timestamp when execution started
            end_time: Unix timestamp when execution completed
            error: Error message if execution failed, None otherwise
        """
        duration_ms = (end_time - start_time) * 1000
        trace: ToolTrace = {
            'tool_name': tool_name,
            'tool_use_id': tool_use_id,
            'input_params': input_params,
            'output': output,
            'start_time': start_time,
            'end_time': end_time,
            'duration_ms': duration_ms,
            'error': error,
        }
        self._state['tool_traces'].append(trace)
        logger.debug(f"Tool trace recorded: {tool_name} (ID: {tool_use_id}) completed in {duration_ms:.2f}ms")

    def _handle_cost_update(self, call_cost, namespace: str) -> None:
        if self.budget_manager:
            self.budget_manager.handle_cost_event(call_cost, namespace)

    def _register_llm_call(self) -> None:
        if self.budget_manager:
            self.budget_manager.register_llm_call()

    def _check_runtime_budget(self) -> None:
        if self.budget_manager:
            self.budget_manager.check_runtime()

    async def _ensure_strategy_plan(self, context: ExecutionContext[AgentState] | None) -> None:
        if not getattr(self.reasoning_strategy, 'supports_planning', lambda: False)():
            return
        if self.reasoning_strategy.has_plan(self._state):
            return
        plan = await self.reasoning_strategy.generate_plan(context)
        if plan:
            self.reasoning_strategy.save_plan_to_state(plan, self._state)

    def _prepare_context(self, inputs: NodeMessage) -> ExecutionContext[AgentState]:
        """Prepare the execution context from inputs."""
        if not isinstance(inputs, NodeMessage):
            raise TypeError("inputs must be a Message")
        return ExecutionContext(inputs=inputs, state=self._state)

    def _extract_tool_call_metadata(self, tool_call: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
        """Normalize tool call payloads across providers."""

        tool_func = tool_call.get('function', {})
        func_name = tool_func.get('name')
        tool_use_id = tool_call.get('id') or func_name

        raw_args = tool_func.get('arguments') or {}
        if isinstance(raw_args, str):
            try:
                func_args = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.error("Failed to parse tool arguments for toolUse: %s", raw_args)
                func_args = {}
        else:
            func_args = raw_args

        return func_name, tool_use_id, func_args

    async def _execute_single_tool(
        self,
        tool_call: dict[str, Any],
        context: ExecutionContext[AgentState]
    ) -> tuple[Any, Optional[ContentBlock]]:
        """Execute a single tool call and return result + ContentBlock.

        Args:
            tool_call: Tool call dict with 'function' and 'id'
            context: Execution context

        Returns:
            Tuple of (tool_result, content_block for toolResult)
        """
        func_name, tool_use_id, func_args = self._extract_tool_call_metadata(tool_call)

        if not func_name:
            return None, None

        func = self.tool_registry.registry.get(func_name)
        if not func or not isinstance(func, BaseTool):
            return None, None

        # Capture timing for tool trace
        start_time = time.time()
        tool_error: Optional[str] = None
        result = None

        try:
            # Handle DecoratedFunctionTool with context injection
            if isinstance(func, DecoratedFunctionTool):
                # Validate inputs
                try:
                    validated_input = func._metadata.validate_input(func_args)
                except Exception as e:
                    raise ToolExecutionError(
                        f"Tool '{func_name}' input validation failed: {str(e)}"
                    ) from e

                # Create ToolUse object for context
                tool_use: ToolUse = {
                    'toolUseId': tool_use_id,
                    'name': func_name,
                    'input': func_args,
                }

                # Inject special parameters (like ToolContext)
                invocation_state = {'agent': self}
                func._metadata.inject_special_parameters(
                    validated_input, tool_use, invocation_state
                )

                # Call with validated and injected parameters
                result = func(**validated_input)
            else:
                # Call directly for non-decorated tools
                result = func(**func_args)

            logger.info('Tool "%s" executed successfully: %s', func_name, result)
        except ToolExecutionError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            tool_error = str(e)
            result = NodeMessage(content=f"Error: {tool_error}")
            logger.error(
                'Tool "%s" execution failed: %s',
                func_name,
                tool_error,
                exc_info=True,
                extra={'tool_use_id': tool_use_id, 'tool_args': func_args}
            )
        finally:
            end_time = time.time()
            # Record the tool trace
            self._record_tool_trace(
                tool_name=func_name,
                tool_use_id=tool_use_id,
                input_params=func_args,
                output=result,
                start_time=start_time,
                end_time=end_time,
                error=tool_error,
            )

        # Create toolResult ContentBlock
        tool_result_block = cast(
            ContentBlock,
            {
                'toolResult': {
                    'toolUseId': tool_use_id,
                    'content': [{'text': str(result)}],
                    'status': 'success' if tool_error is None else 'error',
                }
            },
        )

        return result, tool_result_block

    async def _create_tool_use_blocks(self, tool_calls: list[dict]) -> list[ContentBlock]:
        """Convert tool_calls to ContentBlock format with toolUse.

        Args:
            tool_calls: List of tool call dicts

        Returns:
            List of ContentBlocks with toolUse entries
        """
        assistant_content_blocks: list[ContentBlock] = []

        for tool_call in tool_calls:
            tool_func = tool_call.get('function', {})
            func_name = tool_func.get('name')
            tool_use_id = tool_call.get('id') or func_name

            # Parse arguments if it's a JSON string
            func_args_raw = tool_func.get('arguments')
            if isinstance(func_args_raw, str):
                try:
                    func_args = json.loads(func_args_raw)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse tool arguments for toolUse: {func_args_raw}")
                    func_args = {}
            elif func_args_raw is None:
                func_args = {}
            else:
                func_args = func_args_raw

            assistant_content_blocks.append(
                cast(
                    ContentBlock,
                    {
                        'toolUse': {
                            'toolUseId': tool_use_id,
                            'name': func_name,
                            'input': func_args,
                        }
                    },
                )
            )

        return assistant_content_blocks

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict],
        context: ExecutionContext[AgentState]
    ) -> list[ContentBlock]:
        """Execute multiple tool calls and return toolResult blocks.

        Args:
            tool_calls: List of tool call dicts
            context: Execution context

        Returns:
            List of ContentBlocks with toolResult entries
        """
        tool_result_blocks: list[ContentBlock] = []
        normalized_calls: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            func_name, tool_use_id, func_args = self._extract_tool_call_metadata(tool_call)
            normalized_calls.append(
                {
                    'tool_call': tool_call,
                    'tool_name': func_name,
                    'tool_use_id': tool_use_id,
                    'tool_args': func_args,
                }
            )

        if self.human_policy_manager:
            for call in normalized_calls:
                tool_name = call.get('tool_name')
                if tool_name:
                    self.human_policy_manager.ensure_tool_allowed(tool_name)

        if self.policy_engine:
            await self._enforce_tool_policies(normalized_calls, context)

        if self.config.parallel_tool_execution and len(tool_calls) > 1:
            # Execute tools in parallel for better performance
            logger.debug(f"Executing {len(tool_calls)} tools in parallel")
            results = await asyncio.gather(
                *[self._execute_single_tool(tc, context) for tc in tool_calls],
                return_exceptions=True
            )

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle exceptions from parallel execution
                    logger.error(
                        f"Tool execution failed in parallel mode: {result}",
                        exc_info=result
                    )
                    # Create error result block
                    tool_call = tool_calls[i]
                    tool_func = tool_call.get('function', {})
                    func_name = tool_func.get('name', 'unknown')
                    tool_use_id = tool_call.get('id') or func_name

                    error_block: ContentBlock = {
                        'toolResult': {
                            'toolUseId': tool_use_id,
                            'content': [{'text': f"Error: {str(result)}"}],
                            'status': 'error'
                        }
                    }
                    tool_result_blocks.append(error_block)
                else:
                    _, tool_result_block = result
                    if tool_result_block:
                        tool_result_blocks.append(tool_result_block)
        else:
            # Execute tools sequentially (default)
            for tool_call in tool_calls:
                result, tool_result_block = await self._execute_single_tool(tool_call, context)
                if tool_result_block:
                    tool_result_blocks.append(tool_result_block)

        return tool_result_blocks

    async def _enforce_tool_policies(
        self,
        normalized_calls: list[dict[str, Any]],
        context: ExecutionContext[AgentState],
    ) -> None:
        """Evaluate governance policies before tool execution."""

        if not self.policy_engine:
            return

        for call in normalized_calls:
            tool_name = call.get('tool_name')
            if not tool_name:
                continue
            request = self._build_tool_policy_request(
                tool_name=tool_name,
                tool_args=call.get('tool_args') or {},
                tool_use_id=call.get('tool_use_id'),
                context=context,
            )
            decision = self.policy_engine.evaluate(request)
            await self._handle_tool_policy_decision(decision, request, context)

    def _build_tool_policy_request(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_use_id: str | None,
        context: ExecutionContext[AgentState],
    ) -> PolicyRequest:
        """Construct a policy request describing the pending tool call."""

        subject = PolicySubject(
            identifier=self.config.name or self.id,
            roles=['agent'],
            attributes={
                'agent_id': self.id,
                'agent_type': self.__class__.__name__,
            },
            tags={'agent': self.config.name or self.__class__.__name__},
        )
        policy_context = {
            'agent': {
                'id': self.id,
                'name': self.config.name,
                'type': self.__class__.__name__,
            },
            'tool': {
                'name': tool_name,
                'arguments': tool_args,
                'tool_use_id': tool_use_id,
            },
            'graph': {
                'has_state': context.graph_state is not None,
            },
            'execution': context.metadata.as_dict(),
        }
        if context.inputs.metadata:
            policy_context['inputs'] = dict(context.inputs.metadata)

        return PolicyRequest(
            subject=subject,
            action='agent:tool_execute',
            resource=f"tool://{tool_name}",
            context=policy_context,
        )

    async def _handle_tool_policy_decision(
        self,
        decision: PolicyDecision,
        request: PolicyRequest,
        context: ExecutionContext[AgentState],
    ) -> None:
        """Record decision and raise if policy blocked or requires approval."""

        await self._record_policy_decision(decision, request, context)
        if decision.effect == PolicyEffect.ALLOW:
            return
        if decision.effect == PolicyEffect.DENY:
            raise PolicyViolationError(
                f"Tool '{request.resource}' blocked by policy",
                decision=decision,
                request=request,
            )
        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            approval = await self._create_tool_approval_request(decision, request, context)
            raise ApprovalPendingError(approval)

    async def _create_tool_approval_request(
        self,
        decision: PolicyDecision,
        request: PolicyRequest,
        context: ExecutionContext[AgentState],
    ):
        """Persist an approval request tied to the current execution context."""

        manager = ApprovalGateManager(getattr(context, 'graph_state', None))
        approval = await manager.submit_request(
            action=request.action,
            resource=request.resource,
            subject=request.subject.model_dump(),
            reason=decision.reason or 'Tool execution requires approval',
            metadata={
                'rule': decision.rule,
                'policy_metadata': dict(decision.metadata),
                'context': dict(request.context),
            },
        )
        return approval

    async def _record_policy_decision(
        self,
        decision: PolicyDecision,
        request: PolicyRequest,
        context: ExecutionContext[AgentState] | None = None,
    ) -> None:
        """Append a policy decision to graph state for auditing."""

        graph_state = getattr(context, 'graph_state', None) if context else None
        if graph_state is None:
            return
        events = await graph_state.get('policy_events', [])
        event_list = list(events) if isinstance(events, list) else []
        event_list.append(
            {
                'timestamp': time.time(),
                'decision': decision.effect.value,
                'rule': decision.rule,
                'reason': decision.reason,
                'action': request.action,
                'resource': request.resource,
                'subject': request.subject.model_dump(),
                'metadata': dict(decision.metadata),
            }
        )
        await graph_state.set('policy_events', event_list)

    def _get_tool_choice(self) -> ToolChoice | None:
        """Convert the configured tool_choice to the proper ToolChoice format.

        Returns:
            ToolChoice dict in Bedrock format, or None if tools are disabled.

        The config.tool_choice can be:
        - 'auto': LLM decides whether to use tools
        - 'any': LLM must use at least one tool
        - 'none': Disable tools
        - '<tool_name>': Force a specific tool
        - None: Same as 'auto' if tools available
        """
        # If no tools available, return None
        if not self.tool_specs:
            return None

        tool_choice_config = self.config.tool_choice

        # Handle 'none' - disable tools by returning None
        if tool_choice_config == 'none':
            return None

        # Handle 'auto' - let model decide
        if tool_choice_config == 'auto':
            return {'auto': {}}

        # Handle 'any' - model must use a tool
        if tool_choice_config == 'any':
            return {'any': {}}

        # Handle specific tool name - force that tool
        # Validate the tool exists
        available_tool_names = {spec['name'] for spec in self.tool_specs}
        if tool_choice_config in available_tool_names:
            return {'tool': {'name': tool_choice_config}}
        else:
            logger.warning(
                f"tool_choice '{tool_choice_config}' does not match any available tool. "
                f"Available tools: {available_tool_names}. Falling back to 'auto'."
            )
            return {'auto': {}}

    async def process(self, context: ExecutionContext[AgentState] | None = None) -> NodeMessage:
        """
        Process the execution context and return an agent result.
        This method is called by either do() or go() method.
        do(self, inputs) take inputs of type `Message` as argument, package into ExecutionContext
        with self._prepare_context(inputs) then pass the context to this method.
        go() method take inputs from queue, and do the same.
        """
        if context is None:
            context = ExecutionContext()
        if self.human_policy_manager:
            self.human_policy_manager.ensure_not_stopped()
        if self.budget_manager:
            self.budget_manager.start_run()
        await self._ensure_strategy_plan(context)
        self._check_runtime_budget()
        payload = self.build_prompt(context)
        for hook in self.before_llm_hooks:
            await self._run_before_llm_hook(hook, payload, context)

        raw: list[Any] = []
        result: NodeMessage | None = None
        try:
            # Get tool choice from configuration
            tool_choice: ToolChoice | None = self._get_tool_choice()

            if self.output_mode == 'json':
                # When using JSON mode with tools, we need to loop like text mode
                # but request structured output on each iteration
                iteration_count = 0

                # Keep native tool calling available even when requesting structured JSON output
                json_mode_tool_specs = self.tool_specs
                json_mode_tool_choice = tool_choice

                self._register_llm_call()
                self._check_runtime_budget()
                completion_message = await self.model.get_json(
                    output_model=self.output_schema,
                    messages=payload,
                    system_prompt=self.system_prompt,
                    tool_specs=json_mode_tool_specs,
                    tool_choice=json_mode_tool_choice,
                )

                # Initialize history list in state if not present
                if 'history' not in self._state:
                    self._state['history'] = []

                # Store the parsed structured output in state for template access
                # This allows templates to maintain custom history (e.g., ReAct steps)
                parsed_output = None
                if self.output_schema and completion_message.get('content'):
                    content = completion_message.get('content')
                    if isinstance(content, str):
                        try:
                            parsed_output = json.loads(content)
                        except json.JSONDecodeError:
                            parsed_output = content
                    else:
                        parsed_output = content
                    # Store in state so templates can access it via {{ last_output }}
                    self._state['last_output'] = parsed_output

                # Loop through tool calls until we get a final response
                # In JSON mode, check both native tool_use AND embedded actions in structured output
                # Use reasoning strategy to determine if we should continue
                while completion_message.get('stop_reason') == 'tool_use' or (
                    parsed_output and self.reasoning_strategy.should_continue(parsed_output)
                ):
                    self._check_runtime_budget()
                    iteration_count += 1
                    if self.config.max_steps and iteration_count >= self.config.max_steps:
                        logger.warning(f"Max steps ({self.config.max_steps}) reached, stopping tool execution")
                        break

                    # Get tool calls - either native or from structured output
                    tool_calls = completion_message.get('tool_calls')

                    # If no native tool calls but we have embedded action in JSON, construct tool_calls manually
                    if not tool_calls and parsed_output and has_tool_action(parsed_output):
                        action = parsed_output.get('action')
                        action_input = parsed_output.get('action_input', '')
                        # Convert to tool_calls format
                        tool_calls = [{
                            'id': f'call_{iteration_count}',
                            'type': 'function',
                            'function': {
                                'name': action,
                                'arguments': (
                                    json.dumps({'query': action_input})
                                    if isinstance(action_input, str)
                                    else action_input
                                ),
                            },
                        }]
                        logger.debug(f"Constructed tool call from JSON output: {action}")

                    if not tool_calls:
                        break

                    # Allow JSON output mode to reuse the standard tool call flow so tools stay synchronized
                    skip_tool_blocks_in_history = False

                    # Use extracted helper methods for tool execution
                    if not skip_tool_blocks_in_history:
                        assistant_content_blocks = await self._create_tool_use_blocks(tool_calls)
                        # Add assistant message with toolUse blocks
                        assistant_message = LlmMessage(role='assistant', content=assistant_content_blocks)
                        payload.append(assistant_message)

                    # Execute all tools and collect results
                    tool_result_blocks = await self._execute_tool_calls(tool_calls, context)

                    # Add user message with toolResult blocks (only if not skipping)
                    if not skip_tool_blocks_in_history and tool_result_blocks:
                        user_message = LlmMessage(role='user', content=tool_result_blocks)
                        payload.append(user_message)

                    # Process reasoning step using strategy (e.g., build ReAct history)
                    if self._state.get('last_output'):
                        await self.reasoning_strategy.process_step(
                            parsed_output=self._state['last_output'],
                            tool_result_blocks=tool_result_blocks if not skip_tool_blocks_in_history else [],
                            state=self._state,
                            context=context
                        )
                        await self.reasoning_strategy.update_plan(
                            self._state.get('last_output'),
                            self._state,
                        )

                    # Re-render template with updated context
                    # If a template is configured, re-render it with current state to include
                    # any structured history maintained by the reasoning strategy
                    if self.jinja2_template and context and context.inputs:
                        inputs = context.inputs.content if isinstance(context.inputs, NodeMessage) else context.inputs
                        # Re-render the template with updated state (includes history, last_output, etc.)
                        re_rendered_txt = self._render_template(inputs, context)
                        # Append the re-rendered prompt as an additional user message
                        # This ensures the LLM sees the structured history in the expected format
                        re_rendered_msg = LlmMessage(role='user', content=[{'text': re_rendered_txt}])
                        payload.append(re_rendered_msg)
                        logger.debug(f"Re-rendered template with {len(self._state.get('history', []))} history steps")

                    # Get the next response while continuing to request structured output
                    self._register_llm_call()
                    self._check_runtime_budget()
                    completion_message = await self.model.get_json(
                        output_model=self.output_schema,
                        messages=payload,
                        system_prompt=self.system_prompt,
                        tool_specs=json_mode_tool_specs,
                        tool_choice=json_mode_tool_choice,
                    )

                    # Store the parsed structured output in state for next iteration
                    if self.output_schema and completion_message.get('content'):
                        content = completion_message.get('content')
                        if isinstance(content, str):
                            try:
                                parsed_output = json.loads(content)
                            except json.JSONDecodeError:
                                parsed_output = content
                        else:
                            parsed_output = content
                        self._state['last_output'] = parsed_output

                # Parse final JSON response
                content = completion_message.get('content')
                if isinstance(content, str):
                    content = json.loads(content)
                else:
                    logger.info('Expected JSON content, but got %s', type(content))
                result = NodeMessage(content=content, raw=completion_message)
                return result

            self._register_llm_call()
            self._check_runtime_budget()
            completion_message = await self.model.get_text(
                payload, system_prompt=self.system_prompt, tool_specs=self.tool_specs, tool_choice=tool_choice
            )
            # print('completion_message:', completion_message)

            # Keep executing tools until the model returns a final assistant message
            iteration_count = 0
            while completion_message.get('stop_reason') == 'tool_use':
                self._check_runtime_budget()
                iteration_count += 1
                if self.config.max_steps and iteration_count >= self.config.max_steps:
                    logger.warning(f"Max steps ({self.config.max_steps}) reached, stopping tool execution")
                    break
                tool_calls = completion_message.get('tool_calls')
                if not tool_calls:
                    break

                # Use extracted helper methods for tool execution
                assistant_content_blocks = await self._create_tool_use_blocks(tool_calls)

                # Add assistant message with toolUse blocks
                assistant_message = LlmMessage(role='assistant', content=assistant_content_blocks)
                payload.append(assistant_message)

                # Execute all tools and collect results
                tool_result_blocks = await self._execute_tool_calls(tool_calls, context)

                # Add user message with toolResult blocks
                tool_result_message = LlmMessage(role='user', content=tool_result_blocks)
                payload.append(tool_result_message)

                # Make the next API call
                # print('payload:', payload)
                self._register_llm_call()
                self._check_runtime_budget()
                completion_message = await self.model.get_text(
                    payload, system_prompt=self.system_prompt, tool_specs=self.tool_specs, tool_choice=tool_choice
                )
                await self.reasoning_strategy.update_plan(None, self._state)

            content = completion_message.get('content')
            result = NodeMessage(content=content, raw=raw)
            self._state['last_result'] = result
            return result

        except AgentBudgetExceededError as exc:
            logger.warning('Agent budget exceeded: %s', exc)
            result = self.handle_model_error(exc)
            self._state['last_result'] = result
            return result
        except (HumanApprovalRequired, AgentStoppedError, ApprovalPendingError) as exc:
            logger.warning('Agent paused awaiting approval: %s', exc)
            result = self.handle_model_error(exc)
            self._state['last_result'] = result
            return result
        except ToolExecutionError as exc:
            # Tool execution errors are already logged, just handle gracefully
            logger.warning('Agent process interrupted by tool execution error: %s', str(exc))
            result = self.handle_model_error(exc)
            self._state['last_result'] = result
            return result
        except Exception as exc:  # pragma: no cover - error path kept for completeness
            logger.error(
                'Agent process failed with unexpected error: %s',
                str(exc),
                exc_info=True,
                extra={
                    'agent_config': self.config.name or 'unnamed',
                    'output_mode': self.output_mode,
                    'tool_count': len(self.tool_specs)
                }
            )
            result = self.handle_model_error(exc)
            self._state['last_result'] = result
            return result
        finally:
            for hook in self.after_llm_hooks:
                if result:
                    await self._run_after_llm_hook(hook, result, context)

    def _render_template(self, inputs: Any, context: Optional[ExecutionContext] = None) -> str:
        """Render the Jinja2 template with full context including inputs and state.

        Args:
            inputs: The input data to pass to the template
            context: Optional execution context with state and other metadata

        Returns:
            Rendered template string
        """
        if not self.jinja2_template:
            return str(inputs)

        # Build template context with inputs, state, and other useful variables
        template_context = {}

        # Add inputs (flatten if it's a dict)
        if isinstance(inputs, dict):
            template_context.update(inputs)
        else:
            template_context['inputs'] = inputs

        # Add state if available (makes state accessible to templates)
        if context and context.state:
            template_context['state'] = context.state

        # Add any custom fields from state directly to context for convenience
        # This allows templates to use {{ history }} instead of {{ state.history }}
        if context and context.state and isinstance(context.state, dict):
            for key, value in context.state.items():
                if key not in template_context:  # Don't override inputs
                    template_context[key] = value

        try:
            return self.jinja2_template.render(**template_context)
        except Exception as e:
            logger.warning(
                'Template rendering failed with full context: %s, attempting fallback',
                str(e),
                exc_info=True,
                extra={'template_context_keys': list(template_context.keys())}
            )
            # Fallback: try with just inputs
            try:
                if isinstance(inputs, dict):
                    return self.jinja2_template.render(**inputs)
                else:
                    return self.jinja2_template.render() + str(inputs)
            except Exception as fallback_error:
                logger.error(
                    'Template rendering fallback failed: %s, using string representation',
                    str(fallback_error),
                    exc_info=True
                )
                return str(inputs)

    def build_prompt(self, context: ExecutionContext) -> LlmMessages:
        """Build the prompt payload for LLM call from the execution context."""
        if not isinstance(context.inputs, NodeMessage):
            context.inputs = NodeMessage(content=context.inputs, metadata={})
        inputs = context.inputs.content
        messages: LlmMessages

        if self.memory_config.policy == MemoryPolicyType.NULL:
            messages = []
        else:
            # Use MemoryManager as the source of truth
            messages = cast(LlmMessages, list(self.memory_manager.memory))

        if isinstance(inputs, dict) and inputs.get('messages'):
            # already have messages, use them directly
            raw_messages = list(inputs.get('messages', []))
            # Normalize any legacy/simple formats into the internal Messages format
            normalized: LlmMessages = []
            for m in raw_messages:
                # Defensive: skip falsy entries
                if not m:
                    continue
                if isinstance(m, dict) and m.get('role') in {'user', 'assistant', 'system'}:
                    role = m['role']
                else:
                    role = 'user'
                content = m.get('content') if isinstance(m, dict) else m

                # Cases:
                # 1. content is a plain string -> wrap as single text block
                # 2. content is list[str] -> each becomes its own text block
                # 3. content is list[dict] (assumed already ContentBlock) -> keep
                # 4. content is dict -> if has known content block keys, wrap; else coerce to text
                # 5. anything else -> str() and wrap
                blocks: list[ContentBlock]
                if isinstance(content, str):
                    blocks = [cast(ContentBlock, {'text': content})]
                elif isinstance(content, list):
                    if all(isinstance(item, str) for item in content):
                        blocks = [cast(ContentBlock, {'text': item}) for item in content]
                    else:
                        # assume already list of ContentBlock dicts
                        blocks = cast(list[ContentBlock], content)  # type: ignore[assignment]
                elif isinstance(content, dict):
                    if any(
                        k in content
                        for k in [
                            'text',
                            'image',
                            'document',
                            'toolUse',
                            'toolResult',
                            'guardContent',
                            'reasoningContent',
                        ]
                    ):
                        blocks = [cast(ContentBlock, content)]
                    else:
                        blocks = [cast(ContentBlock, {'text': str(content)})]
                else:
                    blocks = [cast(ContentBlock, {'text': str(content)})]

                normalized.append({'role': role, 'content': cast(list[ContentBlock], blocks)})
            # Extend prompt and persist into memory
            messages.extend(normalized)
            for nm in normalized:
                self.memory_manager.add_message(cast(dict[str, Any], nm))
        else:
            # inputs is not a dict, or has not 'messages' key
            # Use the new template rendering method that includes state
            txt = self._render_template(inputs, context)
            user_msg: dict[str, Any] = {'role': 'user', 'content': [{'text': txt}]}
            messages.append(LlmMessage(role='user', content=[{'text': txt}]))
            self.memory_manager.add_message(user_msg)

        return messages

    async def post_llm_hook(self, result: NodeMessage, context: ExecutionContext[AgentState]) -> None:
        """Post process hook for the agent."""

        if result.content:
            # Persist assistant output into memory and sync state view
            # Normalize content to structured format: [{'text': '...'}]
            content = result.content
            if isinstance(content, str):
                content = [{'text': content}]
            elif isinstance(content, dict):
                # If it's already a dict but not a list, wrap it
                content = (
                    [content]
                    if 'text' in content or 'image' in content or 'document' in content
                    else [{'text': str(content)}]
                )
            elif not isinstance(content, list):
                # Convert other types to string and wrap
                content = [{'text': str(content)}]

            assistant_msg: dict[str, Any] = {'role': 'assistant', 'content': content}
            self.add_message_to_history(assistant_msg)
        self._state['last_result'] = result

    @property
    def result(self) -> Optional[dict[str, Any]]:
        """Get the last agent result."""
        return self._state['last_result']

    def handle_model_error(self, exc: Exception) -> NodeMessage:
        """Handle model errors and return an error result with detailed information.

        Args:
            exc: The exception that was raised

        Returns:
            NodeMessage containing error details
        """
        error_type = type(exc).__name__
        error_message = str(exc)

        self._state['last_error'] = error_message

        # Build detailed error response
        error_content = {
            'error': error_message,
            'error_type': error_type,
            'timestamp': time.time()
        }

        # Add specific context for different error types
        if isinstance(exc, ToolExecutionError):
            error_content['category'] = 'tool_execution'
        elif isinstance(exc, TemplateRenderError):
            error_content['category'] = 'template_rendering'
        elif isinstance(exc, ModelError):
            error_content['category'] = 'model_call'
        elif isinstance(exc, ConfigurationError):
            error_content['category'] = 'configuration'
        elif isinstance(exc, AgentBudgetExceededError):
            error_content['category'] = 'budget'
        elif isinstance(exc, (HumanApprovalRequired, AgentStoppedError)):
            error_content['category'] = 'human_policy'
        elif isinstance(exc, ApprovalPendingError):
            error_content['category'] = 'governance'
            error_content['approval_id'] = exc.approval.approval_id
        else:
            error_content['category'] = 'unknown'

        logger.debug('Agent error handled: %s (%s)', error_message, error_type)

        return NodeMessage(content=error_content, raw=exc)

    def set_memory_policy(
        self,
        policy: MemoryPolicyType | Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
        memory_window: int | None = None,
    ) -> None:
        """Set the memory policy for the agent."""
        if callable(policy):
            self.memory_config.callable = policy
            self.memory_config.policy = MemoryPolicyType.CUSTOM
            return
        self.memory_config.policy = policy
        if memory_window is not None:
            self.memory_config.window = memory_window

    def add_message_to_history(self, message: dict[str, Any] | str) -> None:
        """Add a message to the agent's conversation history.

        Note: Messages are stored in memory_manager, which is the source of truth.
        The state['messages'] field is synchronized lazily when state is accessed.
        """
        if isinstance(message, str):
            message = {'role': 'user', 'content': message}
        # Delegate to MemoryManager for policy enforcement
        self.memory_manager.add_message(message)

    def get_history(self) -> list[dict[str, Any]]:
        """Get the conversation history."""
        return list(self.memory_manager.memory)

    def clear_history(self) -> None:
        """Clear the conversation history.

        Note: Clears memory_manager.memory, which is the source of truth.
        The state['messages'] field will be synchronized on next access.
        """
        self.memory_manager.memory.clear()

    def get_tool_traces(self) -> list[ToolTrace]:
        """Get the history of all tool executions.

        Returns:
            List of ToolTrace records containing timing, inputs, outputs, and errors
            for all tool executions in this agent's session.
        """
        return self._state['tool_traces']

    def get_last_tool_trace(self) -> Optional[ToolTrace]:
        """Get the most recent tool execution trace.

        Returns:
            The last ToolTrace record, or None if no tools have been executed.
        """
        traces = self._state['tool_traces']
        return traces[-1] if traces else None

    def get_tool_traces_by_name(self, tool_name: str) -> list[ToolTrace]:
        """Get all traces for a specific tool.

        Args:
            tool_name: Name of the tool to filter by

        Returns:
            List of ToolTrace records for the specified tool.
        """
        return [trace for trace in self._state['tool_traces'] if trace['tool_name'] == tool_name]

    def get_failed_tool_traces(self) -> list[ToolTrace]:
        """Get all tool traces that resulted in errors.

        Returns:
            List of ToolTrace records where execution failed.
        """
        return [trace for trace in self._state['tool_traces'] if trace['error'] is not None]

    def clear_tool_traces(self) -> None:
        """Clear all tool execution traces."""
        self._state['tool_traces'] = []

    def get_cost_stats(self, namespace: str | None = None):
        """Get cost tracking statistics for this agent."""
        return self.cost_tracker.get_stats(namespace)

    def reset_cost_tracking(self) -> None:
        """Reset cost tracking data."""
        self.cost_tracker.reset()

    def get_cost_summary(self, namespace: str | None = None) -> str:
        """Get formatted cost summary."""
        return self.cost_tracker.format_summary(namespace)

    def pause(self, reason: str | None = None) -> None:
        """Trigger the configured stop token so operators can resume later."""
        policy = self.config.human_policy
        if not policy or not policy.stop_token:
            raise ConfigurationError("No stop_token configured for this agent.")
        HumanPolicyManager.issue_stop_signal(policy.stop_token, reason)

    def resume(self) -> None:
        """Clear the stop token to resume execution."""
        policy = self.config.human_policy
        if policy and policy.stop_token:
            HumanPolicyManager.clear_stop_signal(policy.stop_token)

    def checkpoint(self) -> dict[str, Any]:
        """Create a checkpoint of the agent's current state.

        This saves all stateful information needed to restore the agent later,
        including conversation history, tool traces, cost tracking, and state.

        Returns:
            Dict containing the checkpoint data

        Example:
            checkpoint = agent.checkpoint()
            # ... later ...
            agent = Agent.restore(checkpoint, config)
        """
        from spark.agents.cost_tracker import CostStats

        checkpoint_data = {
            'version': '1.0',
            'timestamp': time.time(),
            'config': {
                'name': self.config.name,
                'description': self.config.description,
                'system_prompt': self.config.system_prompt,
                'prompt_template': self.config.prompt_template,
                'output_mode': self.config.output_mode,
                'max_steps': self.config.max_steps,
                'parallel_tool_execution': self.config.parallel_tool_execution,
            },
            'memory': {
                'messages': list(self.memory_manager.memory),
                'policy': self.config.memory_config.policy.value,
                'window': self.config.memory_config.window,
            },
            'state': {
                'tool_traces': list(self._state['tool_traces']),
                'last_result': self._state['last_result'],
                'last_error': self._state['last_error'],
                'last_output': self._state['last_output'],
                'history': self._state.get('history', []),
            },
            'cost_tracking': {
                'stats': self.cost_tracker.get_stats().__dict__,
                'calls': [
                    {
                        'model_id': call.model_id,
                        'input_tokens': call.input_tokens,
                        'output_tokens': call.output_tokens,
                        'cost': call.total_cost,
                        'timestamp': call.timestamp,
                        'namespace': getattr(call, 'namespace', 'default'),
                    }
                    for call in self.cost_tracker.calls
                ],
            },
        }

        logger.debug(f"Created checkpoint with {len(checkpoint_data['memory']['messages'])} messages")
        return checkpoint_data

    @classmethod
    def restore(cls, checkpoint: dict[str, Any], config: Optional[AgentConfig] = None) -> 'Agent':
        """Restore an agent from a checkpoint.

        Args:
            checkpoint: Checkpoint data from agent.checkpoint()
            config: Optional AgentConfig to use. If None, creates config from checkpoint.
                   Note: model, tools, and hooks cannot be serialized, so must be provided.

        Returns:
            Restored Agent instance

        Example:
            checkpoint = agent.checkpoint()
            # ... later, with same config ...
            agent = Agent.restore(checkpoint, config)
        """
        from spark.agents.memory import MemoryConfig, MemoryPolicyType

        # Use provided config or create minimal one
        if config is None:
            # Create minimal config from checkpoint
            ckpt_config = checkpoint['config']
            from spark.models.echo import EchoModel

            config = AgentConfig(
                model=EchoModel(),  # Placeholder - user should provide real model
                name=ckpt_config.get('name'),
                description=ckpt_config.get('description'),
                system_prompt=ckpt_config.get('system_prompt'),
                prompt_template=ckpt_config.get('prompt_template'),
                output_mode=ckpt_config.get('output_mode', 'text'),
                max_steps=ckpt_config.get('max_steps', 100),
                parallel_tool_execution=ckpt_config.get('parallel_tool_execution', False),
            )
            logger.warning(
                "No config provided to restore(), using EchoModel. "
                "Provide original config for full restoration."
            )

        # Create agent with config
        agent = cls(config=config)

        # Restore memory
        memory_data = checkpoint['memory']
        for msg in memory_data['messages']:
            agent.memory_manager.add_message(msg)

        # Restore state
        state_data = checkpoint['state']
        agent._state['tool_traces'] = state_data.get('tool_traces', [])
        agent._state['last_result'] = state_data.get('last_result')
        agent._state['last_error'] = state_data.get('last_error')
        agent._state['last_output'] = state_data.get('last_output')
        if 'history' in state_data:
            agent._state['history'] = state_data['history']

        # Restore cost tracking
        cost_data = checkpoint.get('cost_tracking', {})
        if 'calls' in cost_data:
            for call in cost_data['calls']:
                agent.cost_tracker.record_call(
                    model_id=call['model_id'],
                    input_tokens=call['input_tokens'],
                    output_tokens=call['output_tokens'],
                    timestamp=call['timestamp'],
                    namespace=call.get('namespace'),
                )

        logger.info(
            f"Restored agent from checkpoint: "
            f"{len(memory_data['messages'])} messages, "
            f"{len(state_data.get('tool_traces', []))} tool traces"
        )

        return agent

    def save_checkpoint(self, filepath: str) -> None:
        """Save checkpoint to a JSON file.

        Args:
            filepath: Path to save the checkpoint file

        Example:
            agent.save_checkpoint('agent_state.json')
        """
        checkpoint = self.checkpoint()

        import json
        with open(filepath, 'w') as f:
            json.dump(checkpoint, f, indent=2, default=str)

        logger.info(f"Saved checkpoint to {filepath}")

    @classmethod
    def load_checkpoint(cls, filepath: str, config: Optional[AgentConfig] = None) -> 'Agent':
        """Load agent from a checkpoint file.

        Args:
            filepath: Path to the checkpoint file
            config: Optional AgentConfig (required for model, tools, hooks)

        Returns:
            Restored Agent instance

        Example:
            agent = Agent.load_checkpoint('agent_state.json', config)
        """
        import json
        with open(filepath, 'r') as f:
            checkpoint = json.load(f)

        logger.info(f"Loaded checkpoint from {filepath}")
        return cls.restore(checkpoint, config)

    def _truncate_history(self, history: list[dict[str, Any]]) -> None:
        """Truncate the history based on the memory policy."""
        # Historical no-op: Memory trimming is handled by MemoryManager.add_message
        # Retained for backward compatibility if called elsewhere.
        return

    async def _run_before_llm_hook(
        self, hook: HookFn, msgs: LlmMessages, context: ExecutionContext[AgentState]
    ) -> None:
        """Run a hook function if it exists."""
        result = hook(msgs, context)
        if inspect.isawaitable(result):
            await result

    async def _run_after_llm_hook(
        self, hook: HookFn, result_msg: NodeMessage, context: ExecutionContext[AgentState]
    ) -> None:
        """Run a hook function if it exists."""
        result = hook(result_msg, context)
        if inspect.isawaitable(result):
            await result
