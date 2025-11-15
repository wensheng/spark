"""Test schemas for schema CLI."""

from spark.graphs.state_schema import MissionStateModel


class DemoState(MissionStateModel):
    schema_name = 'DemoState'
    schema_version = '1.0'

    counter: int
    owner: str
