"""Tests for structured logging utilities."""

import json
import logging

from spark.utils.logging_utils import get_structured_logger, structured_log_context, clear_log_context


def test_structured_logger_emits_context(caplog):
    caplog.set_level(logging.INFO, logger='spark.structured')
    logger = get_structured_logger()
    with structured_log_context(graph_id='graph1', task_id='taskA'):
        logger.info('test-event', status='ok')
    assert caplog.records
    record = caplog.records[0]
    payload = json.loads(record.getMessage())
    assert payload['graph_id'] == 'graph1'
    assert payload['task_id'] == 'taskA'
    assert payload['status'] == 'ok'
    clear_log_context()
