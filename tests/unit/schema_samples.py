"""Test schemas for schema CLI."""

from spark.graphs.state_schema import MissionStateModel


class DemoState(MissionStateModel):
    schema_name = 'DemoState'
    schema_version = '1.0'

    counter: int
    owner: str


class DemoStateV2(MissionStateModel):
    schema_name = 'DemoState'
    schema_version = '2.0'

    counter: int
    owner: str
    status: str = 'pending'
    notes: str | None = None
