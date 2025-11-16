"""Tests for approval-related CLI helpers."""

from __future__ import annotations

import json
from argparse import Namespace

from spark.kit import spec_cli


def _write_state(path, approvals):
    payload = {'approval_requests': approvals}
    path.write_text(json.dumps(payload), encoding='utf-8')


def _sample_subject():
    return {'identifier': 'agent', 'roles': [], 'attributes': {}, 'tags': {}}


def test_approval_list_table_output(tmp_path, capsys):
    state_path = tmp_path / 'state.json'
    approvals = [
        {
            'approval_id': 'ap-1',
            'created_at': 1_700_000_000.0,
            'action': 'agent:tool_execute',
            'resource': 'tool://demo',
            'subject': _sample_subject(),
            'status': 'pending',
            'reason': 'requires review',
            'metadata': {'rule': 'require_review'},
            'notes': None,
            'decided_at': None,
            'decided_by': None,
        }
    ]
    _write_state(state_path, approvals)
    args = Namespace(
        state=str(state_path),
        backend='file',
        table='graph_state',
        storage_key='approval_requests',
        status='pending',
        limit=None,
        format='table',
    )
    rc = spec_cli.cmd_approval_list(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert 'ap-1' in captured.out
    assert 'requires review' in captured.out


def test_approval_resolve_updates_state(tmp_path, capsys):
    state_path = tmp_path / 'state.json'
    approvals = [
        {
            'approval_id': 'ap-2',
            'created_at': 1_700_000_001.0,
            'action': 'graph:execute_task',
            'resource': 'graph://demo',
            'subject': _sample_subject(),
            'status': 'pending',
            'reason': 'needs operator review',
            'metadata': {},
            'notes': None,
            'decided_at': None,
            'decided_by': None,
        }
    ]
    _write_state(state_path, approvals)
    args = Namespace(
        approval_id='ap-2',
        state=str(state_path),
        backend='file',
        table='graph_state',
        storage_key='approval_requests',
        status='approved',
        reviewer='ops',
        notes='Looks good',
        format='text',
    )
    rc = spec_cli.cmd_approval_resolve(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert 'approved' in captured.out
    payload = json.loads(state_path.read_text(encoding='utf-8'))
    stored = payload['approval_requests'][0]
    assert stored['status'] == 'approved'
    assert stored['decided_by'] == 'ops'
    assert stored['notes'] == 'Looks good'
