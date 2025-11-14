"""
Client-facing helper node for invoking remote JSON-RPC 2.0 services.

RemoteRpcProxyNode lets a local Spark graph treat a remote RpcNode as if it
were another node in the pipeline. The node translates NodeMessage payloads
into JSON-RPC requests, forwards them over HTTP or WebSocket transports,
and optionally mirrors remote notifications onto the graph event bus.
"""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any, Dict, Literal, cast

from pydantic import Field

from spark.nodes.config import NodeConfig
from spark.nodes.exceptions import ContextValidationError, NodeExecutionError
from spark.nodes.nodes import Node
from spark.nodes.rpc_transport import (
    HttpJsonRpcTransport,
    JsonObject,
    JsonRpcConnectionError,
    JsonRpcPayload,
    JsonRpcTimeoutError,
    JsonRpcTransport,
    WebSocketJsonRpcTransport,
)
from spark.nodes.types import ExecutionContext, NodeMessage

RemoteTransportMode = Literal['http', 'websocket']


class RemoteRpcProxyConfig(NodeConfig):
    """Configuration for RemoteRpcProxyNode."""

    endpoint: str = Field(default="http://127.0.0.1:8000", description="JSON-RPC HTTP endpoint.")
    transport: RemoteTransportMode = Field(default='http', description="Transport used for RPC calls.")
    ws_endpoint: str | None = Field(
        default=None,
        description="Optional explicit ws:// endpoint when using WebSocket transport.",
    )
    headers: dict[str, str] = Field(default_factory=dict, description="Static headers sent with each request.")
    request_timeout: float | None = Field(default=30.0, description="Per-request timeout in seconds.")
    connect_timeout: float = Field(default=10.0, description="Connect timeout for WebSocket transport.")
    default_method: str | None = Field(
        default=None,
        description="Fallback method name if inputs don't specify a method explicitly.",
    )
    notification_topic_prefix: str = Field(
        default="remote.rpc",
        description="Default event bus topic prefix for remote notifications.",
    )
    notification_topic_key: str = Field(
        default="topic",
        description="Key name that carries the event topic inside remote params.",
    )
    notification_payload_key: str = Field(
        default="payload",
        description="Key name for the payload inside remote params.",
    )
    forward_notifications_to_event_bus: bool = Field(
        default=True,
        description="Publish remote notifications to the attached graph event bus.",
    )
    auto_connect_websocket: bool = Field(
        default=True,
        description="Whether to open the WebSocket connection eagerly.",
    )


class RemoteRpcProxyNode(Node):
    """Node that proxies inputs to a remote JSON-RPC service."""

    def __init__(self, config: RemoteRpcProxyConfig | None = None, **kwargs: Any) -> None:
        initial_config = config or RemoteRpcProxyConfig()
        super().__init__(config=initial_config, **kwargs)
        self._config = cast(RemoteRpcProxyConfig, self.config)
        self._transport: JsonRpcTransport | None = None
        self._request_ids = count(1)
        self._transport_lock = asyncio.Lock()

    def _get_default_config(self) -> NodeConfig:
        return RemoteRpcProxyConfig()

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def process(self, context: ExecutionContext) -> NodeMessage:
        """Translate inputs into JSON-RPC request(s) and forward them."""

        payload, expect_response = self._normalize_payload(context)
        transport = await self._ensure_transport()

        timeout_override = self._extract_timeout_override(context)

        try:
            if expect_response:
                response = await transport.request(payload, timeout=timeout_override)
                return NodeMessage(
                    content=response,
                    metadata={'rpc_transport': self._config.transport, 'rpc_expect_response': True},
                )

            await transport.notify(payload)
            return NodeMessage(
                content={'status': 'sent', 'notification': True},
                metadata={'rpc_transport': self._config.transport, 'rpc_expect_response': False},
            )
        except (JsonRpcTimeoutError, JsonRpcConnectionError) as exc:
            raise NodeExecutionError(
                kind='rpc_transport',
                node=self,
                stage='process',
                original=exc,
                ctx_snapshot=context,
            ) from exc

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------

    async def _ensure_transport(self) -> JsonRpcTransport:
        async with self._transport_lock:
            if self._transport is None:
                self._transport = self._create_transport()

            if isinstance(self._transport, WebSocketJsonRpcTransport) and self._config.auto_connect_websocket:
                await self._transport.connect()
            return self._transport

    def _create_transport(self) -> JsonRpcTransport:
        if self._config.transport == 'websocket':
            ws_endpoint = self._resolve_ws_endpoint()
            transport = WebSocketJsonRpcTransport(
                ws_endpoint,
                headers=self._config.headers,
                connect_timeout=self._config.connect_timeout,
                request_timeout=self._config.request_timeout,
            )
            transport.register_notification_handler(self._handle_remote_notification)
            return transport

        return HttpJsonRpcTransport(
            self._config.endpoint,
            headers=self._config.headers,
            timeout=self._config.request_timeout,
        )

    def _resolve_ws_endpoint(self) -> str:
        if self._config.ws_endpoint:
            return self._config.ws_endpoint

        base = self._config.endpoint.rstrip('/')
        if base.startswith('https://'):
            base = 'wss://' + base[8:]
        elif base.startswith('http://'):
            base = 'ws://' + base[7:]
        elif not base.startswith('ws://') and not base.startswith('wss://'):
            base = f"ws://{base}"

        if not base.endswith('/ws'):
            base = f"{base}/ws"
        return base

    # ------------------------------------------------------------------

    def _extract_timeout_override(self, context: ExecutionContext) -> float | None:
        metadata = context.inputs.metadata or {}
        rpc_meta = metadata.get('rpc')
        if isinstance(rpc_meta, dict):
            override = rpc_meta.get('timeout')
            if isinstance(override, (int, float)):
                return float(override)
        return None

    def _normalize_payload(self, context: ExecutionContext) -> tuple[JsonRpcPayload, bool]:
        content = context.inputs.content
        metadata = context.inputs.metadata or {}
        rpc_meta = metadata.get('rpc') if isinstance(metadata, dict) else {}
        if not isinstance(rpc_meta, dict):
            rpc_meta = {}

        if isinstance(content, NodeMessage):
            content = content.content

        if isinstance(content, list):
            raise ContextValidationError(self, "Batch JSON-RPC payloads are not supported yet.")

        if isinstance(content, str):
            content = {'method': content}

        if content is None:
            content = {}

        if not isinstance(content, dict):
            raise ContextValidationError(self, f"Unsupported RPC payload type: {type(content).__name__}")

        if content.get('jsonrpc') == '2.0':
            merged = dict(content)
            if 'jsonrpc' not in merged:
                merged['jsonrpc'] = '2.0'
            expect_response = bool(merged.get('id')) and not bool(rpc_meta.get('notify'))
            if not expect_response:
                merged.pop('id', None)
            return merged, expect_response

        return self._build_payload_from_params(content, rpc_meta)

    def _build_payload_from_params(
        self,
        body: dict[str, Any],
        rpc_meta: Any,
    ) -> tuple[JsonObject, bool]:
        rpc_meta = rpc_meta if isinstance(rpc_meta, dict) else {}

        method = (
            body.get('method')
            or rpc_meta.get('method')
            or self._config.default_method
        )
        if not method:
            raise ContextValidationError(self, "RPC method name is required but missing.")

        notify_flag = bool(body.get('notify') or rpc_meta.get('notify'))
        params = self._extract_params(body, rpc_meta)

        payload: JsonObject = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
        }

        request_id = body.get('id') or rpc_meta.get('id')
        expect_response = not notify_flag

        if expect_response:
            payload['id'] = request_id if request_id is not None else next(self._request_ids)
        else:
            payload.pop('id', None)

        return payload, expect_response

    def _extract_params(self, body: dict[str, Any], rpc_meta: dict[str, Any]) -> Any:
        if 'params' in body:
            return body['params']
        if 'params' in rpc_meta:
            return rpc_meta['params']

        params = {k: v for k, v in body.items() if k not in {'method', 'notify', 'id'}}
        return params or {}

    # ------------------------------------------------------------------
    # Notification Handling
    # ------------------------------------------------------------------

    async def _handle_remote_notification(self, message: JsonObject) -> None:
        if not self._config.forward_notifications_to_event_bus or self.event_bus is None:
            return

        method = message.get('method', 'notification')
        params = message.get('params')
        topic = f"{self._config.notification_topic_prefix}.{method}"
        payload: Dict[str, Any]

        if isinstance(params, dict) and self._config.notification_topic_key in params:
            topic = params[self._config.notification_topic_key]
            payload = params.get(self._config.notification_payload_key, params)
        else:
            payload = message

        await self.publish_event(
            topic,
            payload,
            metadata={
                'rpc_transport': self._config.transport,
                'rpc_method': method,
            },
        )
