"""Tests for policy CLI helpers."""

from __future__ import annotations

import json
from argparse import Namespace

from spark.kit import spec_cli


def test_policy_generate_and_validate(tmp_path):
    output = tmp_path / 'policy.json'
    args = Namespace(
        name='test.policies',
        description='Example policies',
        default_effect='allow',
        rule_name='deny_sensitive',
        rule_description='Blocks sensitive tool use.',
        rule_effect='deny',
        rule_action='agent:tool_execute',
        rule_resource='tool://sensitive/*',
        empty=False,
        output=str(output),
    )
    rc = spec_cli.cmd_policy_generate(args)
    assert rc == 0
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['name'] == 'test.policies'
    assert payload['rules'][0]['name'] == 'deny_sensitive'

    validate_args = Namespace(file=str(output))
    rc = spec_cli.cmd_policy_validate(validate_args)
    assert rc == 0


def test_policy_diff_text_output(tmp_path, capsys):
    old_file = tmp_path / 'old.json'
    new_file = tmp_path / 'new.json'
    old_payload = {
        'name': 'policy',
        'default_effect': 'allow',
        'rules': [
            {
                'name': 'deny_sensitive',
                'effect': 'deny',
                'actions': ['agent:tool_execute'],
                'resources': ['tool://sensitive/*'],
                'constraints': [],
            }
        ],
    }
    new_payload = {
        'name': 'policy',
        'default_effect': 'allow',
        'rules': [
            {
                'name': 'deny_sensitive',
                'effect': 'require_approval',
                'actions': ['agent:tool_execute'],
                'resources': ['tool://sensitive/*'],
                'constraints': [],
            },
            {
                'name': 'deny_exports',
                'effect': 'deny',
                'actions': ['tool:*'],
                'resources': ['tool://export/*'],
                'constraints': [],
            },
        ],
    }
    old_file.write_text(json.dumps(old_payload), encoding='utf-8')
    new_file.write_text(json.dumps(new_payload), encoding='utf-8')
    args = Namespace(old=str(old_file), new=str(new_file), format='text')
    rc = spec_cli.cmd_policy_diff(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert 'deny_exports' in captured.out
    assert 'require_approval' in captured.out
