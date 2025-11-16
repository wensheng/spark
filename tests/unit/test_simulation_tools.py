"""Tests for simulation tool adapters and registries."""

from __future__ import annotations

from argparse import Namespace

from spark.tools.registry import ToolRegistry
from spark.tools.simulation.adapters import SimulationToolAdapter, SimulationToolBundle
from spark.tools.simulation.registry import MockResourceRegistry


def test_simulation_tool_adapter_records_invocations():
    bundle = SimulationToolBundle(
        tool_name='mock_lookup',
        description='Return a canned value.',
        handler=lambda inputs: {'value': inputs.get('key', 'default')},
    )
    adapter = SimulationToolAdapter(bundle=bundle, latency_seconds=0.0)
    result = adapter()
    assert result['status'] == 'success'
    assert adapter.executions()[0].outputs == {'value': 'default'}


def test_mock_resource_registry_installs_tools():
    registry = MockResourceRegistry()
    registry.register_static_response(
        tool_name='mock_search',
        description='Returns a static payload.',
        response={'documents': []},
    )
    tool_registry = ToolRegistry()
    registry.install(tool_registry)
    tool = tool_registry.get_tool('mock_search')
    result = tool()
    assert 'documents' in result['content'][0]['text']
    records = registry.get_records('mock_search')
    assert len(records) == 1
