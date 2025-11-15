"""Tests for schema CLI helpers."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from spark.kit import spec_cli


def test_schema_render_writes_json(tmp_path):
    output = tmp_path / 'schema.json'
    args = Namespace(target='tests.unit.schema_samples:DemoState', output=str(output))
    rc = spec_cli.cmd_schema_render(args)
    assert rc == 0
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['metadata']['name'] == 'DemoState'
    assert 'properties' in payload['json_schema']


def test_schema_validate_success(tmp_path):
    fixture = tmp_path / 'state.json'
    fixture.write_text(json.dumps({'counter': 1, 'owner': 'ops'}), encoding='utf-8')
    args = Namespace(schema='tests.unit.schema_samples:DemoState', fixture=str(fixture))
    rc = spec_cli.cmd_schema_validate(args)
    assert rc == 0


def test_schema_validate_failure(tmp_path, capsys):
    fixture = tmp_path / 'bad.json'
    fixture.write_text(json.dumps({'counter': 'oops'}), encoding='utf-8')
    args = Namespace(schema='tests.unit.schema_samples:DemoState', fixture=str(fixture))
    rc = spec_cli.cmd_schema_validate(args)
    captured = capsys.readouterr()
    assert rc == 2
    assert 'Invalid fixture' in captured.err


def test_schema_migrate(tmp_path):
    input_path = tmp_path / 'legacy.json'
    input_path.write_text(json.dumps({'counter': 1, 'owner': 'ops', '__schema_version__': '1.0'}), encoding='utf-8')
    output_path = tmp_path / 'migrated.json'
    args = Namespace(schema='tests.unit.schema_samples:DemoState', input=str(input_path), output=str(output_path))
    rc = spec_cli.cmd_schema_migrate(args)
    assert rc == 0
    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert payload['__schema_version__'] == '1.0'
