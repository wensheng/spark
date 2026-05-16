# Spark

Spark is an async-first actor framework for Python. The core API is small:
start a `Syndicate`, create actors, and send messages with `tell(message,
target)` or `ask(message, target)`.

Workflow routing lives in the explicit `spark.workflow` package. Distributed
features such as TCP routes, WebSocket routes, relay traversal, federation, and
persistence are opt-in.

## Install

```bash
pip install spark
pip install "spark[cbor2]"                 # structured remote payloads
pip install "spark[websocket,cbor2]"       # websocket and NAT relay examples
```

For local development:

```bash
uv venv -p 3.13
uv pip install -e ".[dev,test,websocket,cbor2]"
uv run pytest
```

## Quick Start

```python
from spark import Actor, Syndicate
from spark.core.message import Message


class Echo(Actor):
    async def process(self, message: Message) -> str:
        return f"echo:{message.content}"


async with Syndicate("app") as system:
    echo = await system.create_actor(Echo)
    print(await system.ask("hello", echo, timeout=1.0))
```

`tell(message, target)` is fire-and-forget. `ask(message, target)` waits for
the first reply or raises `ActorTimeout`.

```python
await system.tell("event", echo)
reply = await system.ask("request", echo, timeout=5.0)
```

Inside an actor, omitting `target` sends to the owning syndicate inbox today;
that shape is reserved for future broadcast/parent behavior.

## Core Capabilities

- Actor lifecycle through explicit `Syndicate` instances.
- Parent/child actors, monitoring, linking, and restart/resume/escalate
  supervision.
- Bounded mailboxes, TTL/deadline delivery, dead letters, late replies, runtime
  events, and diagnostics snapshots.
- Stateless thread/process execution with `ActorSpec`.
- `Troupe` actor pools for parallel local work.
- Durable actors and durable timers through `SQLiteJournal`.
- TCP remote routes with shared-secret HMAC handshake and frame integrity.
- WebSocket direct routes and authenticated WebSocket relay registration for
  outbound-only NAT traversal.
- Authenticated federation membership and remote actor placement.

## Workflow Layer

Workflow support is intentionally separate from the actor root API:

```python
from spark import Syndicate
from spark.core.message import Message
from spark.workflow import Node, Workflow


class Normalize(Node):
    def process(self, message: Message) -> str:
        return str(message.content).strip().lower()


first = Normalize()
workflow = Workflow(start=first)

async with Syndicate("workflow-app") as system:
    print(await workflow.run("  Spark  ", system=system))
```

`Workflow` starts its nodes in an explicit `Syndicate`, validates edges,
initializes workflow state, and never uses the global actor system. Workflow
state is not a checkpoint/replay engine; use persistent actors when state must
survive restart.

## Networking

Direct TCP on a trusted route:

```python
left = Syndicate("left", remote=True, transport_secret="shared")
right = Syndicate("right", remote=True, transport_secret="shared")
```

WebSocket relay for two NATed networks:

```bash
export SPARK_RELAY_SECRET="change-me"
uv run --extra websocket --extra cbor2 spark-ws-relay \
  --host 0.0.0.0 --port 8765 --auth-secret-env SPARK_RELAY_SECRET
```

Both actor systems then call:

```python
await system.connect_relay("wss://relay.example.net/spark", secret=relay_secret)
```

Relay authentication prevents unauthenticated system registration. It does not
encrypt traffic by itself; use `wss://` or a TLS-terminating reverse proxy
outside local demos.

## Examples

Phase 9 adds runnable examples by feature area:

```bash
python examples/basic_actor_echo.py --message hello
python examples/workflow_router.py --score 95
python examples/tcp_two_hosts.py local --codec trusted-pickle
python examples/nat_relay_service.py local --codec trusted-pickle --secret shared
python examples/federation_placement.py local --codec trusted-pickle
```

See `docs/examples.md` for the complete index and `--help` output for each
script.

## Documentation

- `docs/actor_overview.md`: API walkthrough.
- `docs/actor_semantics.md`: delivery, ordering, failure, and shutdown
  semantics.
- `docs/security.md`: transport, codec, relay, federation, and artifact trust.
- `docs/networking.md`: TCP, WebSocket, relay/NAT, and federation recipes.
- `docs/workflow.md`: workflow layer guide.
- `docs/features.md`: stable, optional, experimental, and removed surfaces.
- `docs/spark_ug.md`: broader user guide.

## Development Checks

```bash
uv run pytest
uv run ruff check spark tests examples
uv run mypy spark
uv run black spark tests examples
```
