"""
Example 18: Swarm of Agents (No Edges)

This example demonstrates a "swarm" architecture where agents operate independently
without explicit edges connecting them. Communication is handled entirely via
the Event Bus.

Key Concepts:
1.  **No Edges**: Graph is initialized with nodes but no connections.
2.  **Event-Driven**: Agents listen to and publish events.
3.  **Autonomous Loop**: Agents run their own loop (custom go() method) to bridge events to their processing logic.
4.  **Long Running**: The system runs continuously.

Scenario:
- **MissionControl**: Broadcasts a "MISSION_START" event.
- **Scout**: Listens for "MISSION_START", explores (simulated), and publishes "TargetFound".
- **Unit**: Listens for "TargetFound", engages, and publishes "TargetNeutralized".
- **HQ**: Listens for "TargetNeutralized" and aggregates results.
"""

import asyncio
import random
import time
from dataclasses import dataclass

from spark.graphs import Graph, Task, TaskType
from spark.nodes import Node
from spark.nodes.types import NodeMessage
from spark.nodes.channels import ChannelMessage
from spark.utils import arun


@dataclass
class SwarmEvent:
    topic: str
    payload: dict


class SwarmAgent(Node):
    """Base class for swarm agents that communicate via Event Bus."""

    def __init__(self, name: str, subscriptions: list[str]):
        super().__init__(name=name)
        self.subscriptions = subscriptions
        self._background_tasks = []

    async def go(self):
        """
        Override go() to setup event listeners.
        The default Node.go() loops on mailbox.receive().
        We need to feed the mailbox from the event bus.
        """
        print(f"[{self.name}] Coming online. Listening for: {self.subscriptions}")
        
        # Setup listeners for each topic
        for topic in self.subscriptions:
            self._background_tasks.append(
                asyncio.create_task(self._listen_and_forward(topic))
            )

        try:
            # Run the standard processing loop
            await super().go()
        finally:
            print(f"[{self.name}] Going offline.")
            for t in self._background_tasks:
                t.cancel()

    async def _listen_and_forward(self, topic: str):
        """Subscribe to event bus and forward messages to local mailbox."""
        if not self.event_bus:
            print(f"[{self.name}] Error: No event bus attached!")
            return

        subscription = await self.event_bus.subscribe(topic)
        try:
            async for event in subscription:
                # event is a ChannelMessage, extract payload
                real_payload = getattr(event, 'payload', event)
                
                # Wrap event in NodeMessage and send to self
                # We use metadata to indicate the source topic
                msg = NodeMessage(
                    content=real_payload,
                    metadata={'source_topic': topic, 'event_bus': True}
                )
                # Send to our own mailbox so process() picks it up
                # use send_nowait to avoid blocking the listener
                try:
                    self.mailbox.send_nowait(ChannelMessage(payload=msg))
                except Exception as e:
                    print(f"[{self.name}] Failed to forward event to mailbox: {e}")
        except asyncio.CancelledError:
            pass
        finally:
            await subscription.close()

    async def publish(self, topic: str, data: dict):
        """Helper to publish events."""
        print(f"[{self.name}] >>> Publishing to '{topic}': {data}")
        await self.publish_event(topic, data)


class MissionControl(SwarmAgent):
    """Initiates the mission."""
    
    def __init__(self):
        super().__init__(name="MissionControl", subscriptions=[])

    async def go(self):
        # Mission control doesn't just listen, it acts periodically or once
        # We can run a separate task for that
        asyncio.create_task(self._mission_logic())
        await super().go()

    async def _mission_logic(self):
        await asyncio.sleep(1.0) # Wait for everyone to be ready
        mission_id = f"OP-{random.randint(1000, 9999)}"
        print(f"[{self.name}] Initiating Mission: {mission_id}")
        await self.publish("MISSION_START", {"mission_id": mission_id, "region": "Sector 7"})

    async def process(self, context):
        # MC might receive direct commands, but here it mostly broadcasts
        pass


class Scout(SwarmAgent):
    """Finds targets."""
    
    def __init__(self, scout_id: int):
        super().__init__(
            name=f"Scout-{scout_id}", 
            subscriptions=["MISSION_START"]
        )

    async def process(self, context):
        topic = context.inputs.metadata.get('source_topic')
        data = context.inputs.content

        if topic == "MISSION_START":
            mission_id = data.get('mission_id')
            print(f"[{self.name}] Received mission {mission_id}. Deploying...")
            
            # Simulate search time
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Found a target
            target_loc = f"Grid-{random.randint(1, 100)}"
            print(f"[{self.name}] Target spotted at {target_loc}!")
            
            await self.publish("TARGET_FOUND", {
                "mission_id": mission_id,
                "location": target_loc,
                "type": "Hostile"
            })


class Unit(SwarmAgent):
    """Engages targets."""
    
    def __init__(self, unit_id: int):
        super().__init__(
            name=f"Unit-{unit_id}", 
            subscriptions=["TARGET_FOUND"]
        )

    async def process(self, context):
        topic = context.inputs.metadata.get('source_topic')
        data = context.inputs.content

        if topic == "TARGET_FOUND":
            loc = data.get('location')
            print(f"[{self.name}] Moving to intercept at {loc}.")
            
            # Simulate engagement
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            print(f"[{self.name}] Target at {loc} neutralized.")
            await self.publish("TARGET_NEUTRALIZED", {
                "mission_id": data.get('mission_id'),
                "location": loc,
                "unit": self.name
            })


class HQ(SwarmAgent):
    """Aggregates results."""
    
    def __init__(self):
        super().__init__(
            name="HQ", 
            subscriptions=["TARGET_NEUTRALIZED"]
        )
        self.neutralized_count = 0
        self.max_targets = 2 # End simulation after this many

    async def process(self, context):
        topic = context.inputs.metadata.get('source_topic')
        data = context.inputs.content

        if topic == "TARGET_NEUTRALIZED":
            self.neutralized_count += 1
            print(f"[{self.name}] Confirmed kill by {data.get('unit')}. Total: {self.neutralized_count}")
            
            if self.neutralized_count >= self.max_targets:
                print(f"[{self.name}] Mission objectives met. Shutting down swarm.")
                # This is a hacky way to stop the graph from inside a node in this example
                # In a real app, you might publish a SHUTDOWN event that all agents listen to
                await self.publish("SWARM_SHUTDOWN", {})


class SwarmShutdownListener(SwarmAgent):
    """Global shutdown handler."""
    def __init__(self, graph_ref):
        super().__init__(name="ShutdownListener", subscriptions=["SWARM_SHUTDOWN"])
        self.graph_ref = graph_ref

    async def process(self, context):
        if context.inputs.metadata.get('source_topic') == "SWARM_SHUTDOWN":
            print(f"[{self.name}] Shutdown signal received.")
            self.graph_ref.stop_all_nodes()


async def main():
    print("=== Swarm Agent Example (No Edges) ===")
    
    # 1. Initialize Graph
    graph = Graph()
    
    # 2. Create Agents
    mc = MissionControl()
    scout1 = Scout(1)
    scout2 = Scout(2)
    unit1 = Unit(1)
    unit2 = Unit(2)
    hq = HQ()
    shutdown = SwarmShutdownListener(graph)
    
    # 3. Add agents to graph (No edges!)
    # The add_node method we recently added is crucial here
    for agent in [mc, scout1, scout2, unit1, unit2, hq, shutdown]:
        graph.add_node(agent)
        
    # 4. Define Task
    # Note: No initial input is needed as MC kicks things off autonomously
    task = Task(
        type=TaskType.LONG_RUNNING,
        budget={'max_seconds': 10} # Safety timeout
    )
    
    print("Starting Swarm...")
    try:
        await graph.run(task)
    except Exception as e:
        print(f"Graph execution finished: {e}")
        
    print("Swarm operation complete.")

if __name__ == "__main__":
    arun(main())
