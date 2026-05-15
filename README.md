# Spark Framework

Spark is an async-first, zero-dependency, actor model framework for Python.

## Install
```bash
pip install spark
```

mailboxes are async queues, wakeups are event-loop timers, fd watching uses the
event loop, and remote TCP messaging uses asyncio streams.

## Quick Start

```python
import asyncio

from spark import Actor, Syndicate
from spark.core.message import Message


class HelloActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(f"Hello {message.content}", message.sender)


async def main() -> None:
    async with Syndicate("hello") as syn:
        hello = await syn.create_actor(HelloActor)
        await syn.tell(hello, "World")
        print(await syn.receive(timeout=1.0))


asyncio.run(main())
```

For synchronous application entrypoints, use the built-in runner:

```python
Syndicate.run(main())
```

## API Shape

```python
async with Syndicate("app") as syn:
    worker = await syn.create_actor(Worker)
    await syn.tell(worker, "fire-and-forget")
    reply = await syn.ask(worker, "request", timeout=5.0)

    async for message in syn.listen():
        ...
```

Actors use async helpers:

```python
await self.tell(payload, target)
reply = await self.ask(payload, target, timeout=1.0)
child = await self.create_actor(ChildActor)
self.schedule_after(0.5, "timer-payload")
await self.watch(read=(fd,))
```

## Backends

The async in-process backend is the reference runtime. Hybrid local executor
backends are also available for explicit stateless actors:

```python
from spark import ActorSpec, Syndicate


async with Syndicate("workers", backend="threaded") as system:
    worker = await system.create_actor_from_spec(
        ActorSpec(actor_class=Worker, execution="system", stateless=True)
    )
```

`backend="threaded"` resolves `execution="system"` to a dedicated worker
thread. `backend="process"` resolves it to a dedicated worker process. Normal
actors still run in the async coordinator unless an `ActorSpec` explicitly asks
for `execution="thread"`, `execution="process"`, or `execution="system"`.

Thread/process executor actors are for stateless jobs. They can reply with
`tell`, but full actor APIs such as child actor creation, `ask`, wakeups, fd
watching, and system shutdown are intentionally limited to in-process actors.

## Remote Systems

```python
async with Syndicate("left", remote=True) as left, Syndicate("right", remote=True) as right:
    assert left.remote_address is not None
    assert right.remote_address is not None
    await left.connect(right.system_id, *right.remote_address)
    await right.connect(left.system_id, *left.remote_address)
```

Remote transport is system-level TCP routing by `SystemId`. The current codec
uses pickle and should only be used with trusted peers.

For structured CBOR-native payloads, install `spark-actor[cbor2]` and opt in
on every peer:

```python
async with Syndicate("left", remote=True, transport_codec="cbor2") as left:
    ...
```

Both sides must use the same codec. The default remains `transport_codec="pickle"`
for compatibility with arbitrary Python message payloads.

WebSocket transport is available as an optional extra for direct `ws://` /
`wss://` routes or relay-backed routes:

```python
async with Syndicate("left", remote=True, remote_transport="websocket") as left:
    await left.connect_uri(right_system_id, "wss://right.example.net/spark")
```

For networks where neither side can accept inbound connections, run a relay
with `spark-ws-relay --host 0.0.0.0 --port 8765` and connect each system with
`await system.connect_relay("wss://relay.example.net")`. The websocket
transport uses the same trusted-peer pickle codec as TCP.

See `examples/websocket_two_networks.py` for a runnable relay example where
one machine hosts a responder actor and another machine asks it through a
shared websocket relay.

## LLM Actors

```python
from spark.agent import LLMAgent, LLMRequest, OpenAIResponsesProvider


async with Syndicate("llm") as system:
    provider = OpenAIResponsesProvider()
    agent = await system.create_actor(LLMAgent, provider, instructions="Answer briefly.")
    response = await system.ask(agent, LLMRequest("Explain actors in one sentence."), timeout=120)
    print(response.content)
```

Provider interfaces are async-native. Streaming providers return async
iterators of `LLMStreamChunk`.

## Troupe Worker Execution

`spark.contrib.troupe.Troupe` can run workers in-process, in threads, or in
processes while keeping the manager in the async coordinator:

```python
class Translate(Troupe):
    troupe_max_count = 5
    troupe_idle_count = 5
    troupe_worker_execution = "thread"
```

Use thread workers for parallel external I/O such as LLM calls, and process
workers for picklable CPU-style jobs. See `examples/llm_troupe_translation.py`
and `examples/process_troupe_cpu.py`.

## Development

```bash
uv venv -p 3.13
uv pip install -e ".[dev,test]"
uv run pytest
uv run ruff check spark/actor/base.py spark/runtime/async_backend.py spark/runtime/backend.py spark/system.py spark/transport/async_tcp.py spark/contrib/llm spark/contrib/troupe.py tests/async
uv run mypy spark/actor/base.py spark/runtime/async_backend.py spark/runtime/backend.py spark/system.py spark/transport/async_tcp.py spark/contrib/llm spark/contrib/troupe.py
```
