# Simulation System

The Spark Simulation System enables testing of agentic workflows without external dependencies. By overriding tool implementations with static responses or custom handlers, you can test complex workflows in isolation, validate behavior, and iterate quickly without API costs or external service requirements.

## Overview

The simulation system (`spark/kit/simulation.py`) provides:

- **Tool Overrides**: Replace real tool implementations with simulated versions
- **Static Responses**: Return predefined responses for specific tools
- **Custom Handlers**: Implement custom simulation logic
- **Tool Call Recording**: Track all tool invocations during simulation
- **Policy Event Capture**: Record governance and approval events
- **Output Analysis**: Compare simulation runs to validate behavior
- **Cost-Free Testing**: Test without API calls or external services

**Use Cases**:
- Testing workflows before deployment
- Validating behavior without external dependencies
- Cost-free development and iteration
- Regression testing with deterministic outputs
- Training and demonstration environments
- CI/CD pipeline testing

## Simulation Configuration

### MissionSimulationSpec

Define simulation configuration in mission specifications.

```python
from spark.nodes.spec import MissionSimulationSpec, SimulationToolOverrideSpec

simulation = MissionSimulationSpec(
    enabled=True,
    latency_seconds=0.1,  # Simulated latency per tool call
    tools=[
        # Static response override
        SimulationToolOverrideSpec(
            name="external_api",
            description="Simulated external API",
            static_response={
                "status": "success",
                "data": {"result": "test data"}
            },
            parameters={"endpoint": {"type": "str"}},
            response_schema={"type": "object"}
        ),

        # Custom handler override
        SimulationToolOverrideSpec(
            name="database_query",
            description="Simulated database",
            handler="myapp.simulations:mock_database_query",
            parameters={
                "query": {"type": "str"},
                "table": {"type": "str"}
            }
        )
    ]
)
```

### SimulationToolOverrideSpec

Each tool override specifies:

**Required**:
- `name`: Tool name to override (must match agent tool name)

**Response Configuration** (choose one):
- `static_response`: Fixed response dict/value
- `handler`: Module:function reference to custom handler

**Optional**:
- `description`: Tool description
- `parameters`: Parameter schema
- `response_schema`: Response schema for validation

## Running Simulations

### Command Line

```bash
# Run simulation with mission
spark-spec simulation-run mission.json

# With custom inputs
spark-spec simulation-run mission.json --inputs inputs.json

# Override simulation config
spark-spec simulation-run mission.json --simulation-config sim_override.json

# Save outputs
spark-spec simulation-run mission.json -o simulation_output.json

# Verbose mode
spark-spec simulation-run mission.json -v
```

### Python API

```python
from spark.nodes.serde import load_mission_spec
from spark.kit.simulation import SimulationRunner

# Load mission
mission = load_mission_spec("mission.json")

# Create simulation runner
runner = SimulationRunner(mission)

# Run simulation
result = await runner.run(
    inputs={"user_query": "test query"},
    simulation_override=None  # Optional override
)

# Access results
print("Outputs:", result.outputs)
print("Tool records:", result.tool_records)
print("Policy events:", result.policy_events)
```

## Static Response Overrides

### Simple Static Responses

Return fixed values for tool calls.

```python
SimulationToolOverrideSpec(
    name="weather_api",
    static_response={
        "temperature": 72,
        "conditions": "sunny",
        "location": "San Francisco"
    }
)
```

**Use Cases**:
- Testing happy path scenarios
- Providing consistent test data
- Mocking external APIs with known responses

### Conditional Static Responses

Use handler for input-dependent responses.

```python
# myapp/simulations.py
def mock_weather(query: str) -> dict:
    """Return weather based on location in query."""
    if "London" in query:
        return {"temperature": 55, "conditions": "rainy"}
    elif "Miami" in query:
        return {"temperature": 85, "conditions": "sunny"}
    return {"temperature": 70, "conditions": "cloudy"}

# Simulation spec
SimulationToolOverrideSpec(
    name="weather_api",
    handler="myapp.simulations:mock_weather"
)
```

## Custom Handler Overrides

### Handler Function Format

Custom handlers receive tool parameters and return responses.

```python
# Sync handler
def mock_database_query(query: str, table: str) -> list[dict]:
    """Simulate database query."""
    if table == "users":
        return [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
    return []

# Async handler
async def mock_api_call(endpoint: str, method: str = "GET") -> dict:
    """Simulate async API call."""
    await asyncio.sleep(0.1)  # Simulate latency
    return {"status": "success", "endpoint": endpoint}
```

### Handler with Context

Access tool execution context.

```python
from spark.tools.simulation.types import SimulationContext

def mock_with_context(
    query: str,
    context: SimulationContext
) -> dict:
    """Handler with access to context."""
    # Access call count
    call_count = context.call_count

    # Access previous calls
    prev_calls = context.previous_calls

    # Return response based on context
    return {"result": f"Call #{call_count}: {query}"}
```

### Stateful Handlers

Maintain state across simulation runs.

```python
class MockDatabase:
    """Stateful database simulation."""

    def __init__(self):
        self.data = {}
        self.call_count = 0

    def query(self, table: str, filters: dict) -> list[dict]:
        """Query simulated database."""
        self.call_count += 1
        return self.data.get(table, [])

    def insert(self, table: str, record: dict) -> dict:
        """Insert into simulated database."""
        if table not in self.data:
            self.data[table] = []
        self.data[table].append(record)
        return {"status": "success", "id": len(self.data[table])}

# Create instance
mock_db = MockDatabase()

# Register handlers
SimulationToolOverrideSpec(
    name="db_query",
    handler="myapp.simulations:mock_db.query"
)
```

## Tool Call Recording

### Accessing Tool Records

```python
from spark.kit.simulation import SimulationRunner

runner = SimulationRunner(mission)
result = await runner.run()

# Access tool records by tool name
for tool_name, records in result.tool_records.items():
    print(f"\nTool: {tool_name}")
    for record in records:
        print(f"  Call {record.call_number}:")
        print(f"    Inputs: {record.inputs}")
        print(f"    Output: {record.output}")
        print(f"    Duration: {record.duration_ms}ms")
        if record.error:
            print(f"    Error: {record.error}")
```

### ToolExecutionRecord

Each tool call is recorded with:

```python
@dataclass
class ToolExecutionRecord:
    tool_name: str
    call_number: int
    inputs: dict[str, Any]
    output: Any
    error: str | None
    duration_ms: float
    timestamp: float
```

**Use Cases**:
- Verifying tool was called with expected inputs
- Checking call order and frequency
- Debugging tool execution flow
- Performance analysis

## Simulation Output Analysis

### SimulationRunResult

```python
@dataclass
class SimulationRunResult:
    outputs: Any                              # Final workflow outputs
    policy_events: list[dict[str, Any]]       # Governance events
    tool_records: dict[str, list[ToolExecutionRecord]]  # Tool call records
```

### Analyzing Outputs

```python
result = await runner.run()

# Check workflow output
assert result.outputs["status"] == "success"
assert "data" in result.outputs

# Verify tool was called
assert "external_api" in result.tool_records
api_calls = result.tool_records["external_api"]
assert len(api_calls) == 2

# Check first API call
first_call = api_calls[0]
assert first_call.inputs["endpoint"] == "/users"
assert first_call.output["status"] == "success"

# Check policy events
approval_events = [e for e in result.policy_events if e["type"] == "approval_requested"]
assert len(approval_events) == 1
```

## Comparing Simulation Runs

### CLI Comparison

```bash
# Compare two simulation runs
spark-spec simulation-diff run1.json run2.json

# HTML report
spark-spec simulation-diff run1.json run2.json --format html -o diff.html

# Focus on specific fields
spark-spec simulation-diff run1.json run2.json --fields outputs,tool_records
```

### Programmatic Comparison

```python
from spark.kit.simulation import compare_simulation_results

# Run simulations
result1 = await runner.run(inputs=inputs1)
result2 = await runner.run(inputs=inputs2)

# Compare
diff = compare_simulation_results(result1, result2)

print("Output differences:")
for key, (val1, val2) in diff["outputs"].items():
    print(f"  {key}: {val1} -> {val2}")

print("\nTool call differences:")
for tool_name in diff["tool_records"]:
    print(f"  {tool_name}: {diff['tool_records'][tool_name]}")
```

## Integration with Missions

### Mission with Simulation

```python
from spark.nodes.spec import MissionSpec, MissionSimulationSpec

mission = MissionSpec(
    mission_id="com.example.test-workflow",
    version="1.0.0",
    graph=graph_spec,

    simulation=MissionSimulationSpec(
        enabled=True,
        latency_seconds=0.05,
        tools=[
            SimulationToolOverrideSpec(
                name="expensive_api",
                static_response={"result": "test data"}
            )
        ]
    )
)
```

### Conditional Simulation

Enable simulation based on environment.

```python
import os

simulation_enabled = os.getenv("SIMULATION_MODE", "false") == "true"

mission = MissionSpec(
    ...,
    simulation=MissionSimulationSpec(
        enabled=simulation_enabled,
        tools=[...]
    )
)
```

## Testing Patterns

### Unit Testing with Simulation

```python
import pytest
from spark.kit.simulation import SimulationRunner

@pytest.mark.asyncio
async def test_workflow_happy_path():
    """Test workflow with simulated tools."""
    mission = load_mission_spec("workflow.json")
    runner = SimulationRunner(mission)

    result = await runner.run(inputs={"query": "test"})

    # Verify outputs
    assert result.outputs["status"] == "success"

    # Verify tool calls
    assert "search" in result.tool_records
    search_calls = result.tool_records["search"]
    assert len(search_calls) == 1
    assert search_calls[0].inputs["query"] == "test"

@pytest.mark.asyncio
async def test_workflow_error_handling():
    """Test workflow error handling with simulation."""
    mission = load_mission_spec("workflow.json")

    # Override to return error
    error_sim = MissionSimulationSpec(
        enabled=True,
        tools=[
            SimulationToolOverrideSpec(
                name="external_api",
                handler="tests.mocks:error_handler"
            )
        ]
    )

    runner = SimulationRunner(mission)
    result = await runner.run(simulation_override=error_sim)

    # Verify error handling
    assert result.outputs["status"] == "error"
    assert "error_message" in result.outputs
```

### Regression Testing

```python
@pytest.mark.asyncio
async def test_workflow_regression():
    """Regression test: verify outputs match baseline."""
    mission = load_mission_spec("workflow.json")
    runner = SimulationRunner(mission)

    # Load baseline
    with open("baseline_output.json") as f:
        baseline = json.load(f)

    # Run simulation
    result = await runner.run(inputs=baseline["inputs"])

    # Compare outputs
    assert result.outputs == baseline["outputs"]

    # Compare tool calls
    for tool_name in baseline["tool_calls"]:
        assert tool_name in result.tool_records
        assert len(result.tool_records[tool_name]) == baseline["tool_calls"][tool_name]
```

### Performance Testing

```python
@pytest.mark.asyncio
async def test_workflow_performance():
    """Test workflow performance with simulation."""
    import time

    mission = load_mission_spec("workflow.json")
    runner = SimulationRunner(mission)

    start = time.time()
    result = await runner.run()
    duration = time.time() - start

    # Verify performance
    assert duration < 5.0, f"Workflow took {duration:.2f}s (expected < 5s)"

    # Check tool call durations
    for tool_name, records in result.tool_records.items():
        for record in records:
            assert record.duration_ms < 1000, f"{tool_name} call took {record.duration_ms}ms"
```

## Advanced Simulation

### Dynamic Response Generation

```python
def dynamic_search(query: str, context: SimulationContext) -> list[dict]:
    """Generate search results based on query."""
    import hashlib

    # Deterministic but query-dependent results
    hash_val = int(hashlib.md5(query.encode()).hexdigest()[:8], 16)
    num_results = (hash_val % 5) + 1

    return [
        {"title": f"Result {i}", "url": f"http://example.com/{i}"}
        for i in range(num_results)
    ]
```

### Error Injection

```python
def error_injector(input: str, context: SimulationContext) -> dict:
    """Inject errors for specific inputs."""
    if "error" in input.lower():
        raise ValueError("Simulated error")

    if context.call_count > 3:
        raise RuntimeError("Too many calls")

    return {"status": "success"}
```

### Latency Simulation

```python
import asyncio
import random

async def latency_simulator(query: str) -> dict:
    """Simulate variable latency."""
    # Random latency between 100-500ms
    await asyncio.sleep(random.uniform(0.1, 0.5))

    return {"result": f"Results for {query}"}
```

## Best Practices

**Use Simulation for All Tests**: Test workflows with simulation before real tool testing.

**Provide Realistic Responses**: Static responses should match real API structure.

**Test Error Paths**: Simulate errors to verify error handling.

**Record Baselines**: Save simulation outputs as baselines for regression testing.

**Version Simulation Configs**: Track simulation configurations alongside code.

**Document Overrides**: Document what each override simulates and why.

**Test Edge Cases**: Use simulation to test boundary conditions.

**Validate Tool Calls**: Verify tools are called with expected inputs.

**Compare Runs**: Use diff to track behavior changes across versions.

**Iterate Quickly**: Use simulation for rapid development iteration.

## Limitations

**Not Perfect Fidelity**: Simulations approximate real behavior but aren't identical.

**Timing Differences**: Simulated latencies may not match real-world timing.

**State Management**: Stateful handlers require careful design to avoid test coupling.

**Complex Interactions**: Cannot simulate all complex external system behaviors.

**No Network Issues**: Cannot simulate network failures, timeouts comprehensively.

## Troubleshooting

**Tool Not Overridden**: Verify tool name matches exactly (case-sensitive).

**Handler Not Found**: Check module:function reference is correct and importable.

**Simulation Disabled**: Verify `simulation.enabled = True` in spec.

**Unexpected Outputs**: Review tool call records to debug tool behavior.

## Examples

```python
# Complete example: test data pipeline with simulation
from spark.nodes.serde import load_mission_spec
from spark.kit.simulation import SimulationRunner

async def test_data_pipeline():
    # Load mission
    mission = load_mission_spec("data_pipeline.json")

    # Override external dependencies
    simulation = MissionSimulationSpec(
        enabled=True,
        tools=[
            SimulationToolOverrideSpec(
                name="fetch_data",
                static_response={"records": [{"id": 1}, {"id": 2}]}
            ),
            SimulationToolOverrideSpec(
                name="send_email",
                handler="tests.mocks:mock_email_sender"
            )
        ]
    )

    # Run simulation
    runner = SimulationRunner(mission)
    result = await runner.run(
        inputs={"source": "test_source"},
        simulation_override=simulation
    )

    # Verify
    assert result.outputs["records_processed"] == 2
    assert "fetch_data" in result.tool_records
    assert "send_email" in result.tool_records
```

## Next Steps

- **[Mission System](./missions.md)**: Creating complete mission packages
- **[Spec CLI Tool](./cli.md)**: Simulation CLI commands
- **[Best Practices: Testing](../best-practices/testing.md)**: Testing strategies
- **[API Reference: Simulation](../api/simulation.md)

## Related Documentation

- [Tools System: Development](../tools/development.md)
- [Integration: Testing Workflows](../integration/testing.md)
- [Examples: Simulation Testing](../examples/simulation.md)
