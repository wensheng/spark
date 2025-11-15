"""Tests for TaskScheduler dependency and budget management."""

from __future__ import annotations

import pytest

from spark.graphs.tasks import (
    Budget,
    CampaignBudgetError,
    CampaignInfo,
    Task,
    TaskScheduler,
)


def make_task(task_id: str, *, depends_on=None, priority: int = 0, campaign: CampaignInfo | None = None) -> Task:
    return Task(task_id=task_id, depends_on=depends_on or [], priority=priority, campaign=campaign)


def test_scheduler_respects_dependencies():
    collect = make_task('collect')
    build = make_task('build', depends_on=['collect'])
    scheduler = TaskScheduler([collect, build])

    first = scheduler.acquire_next_task()
    assert first.task_id == 'collect'
    scheduler.mark_completed(first.task_id)

    second = scheduler.acquire_next_task()
    assert second.task_id == 'build'


def test_scheduler_enforces_concurrency_limit():
    scheduler = TaskScheduler([make_task('a'), make_task('b')], concurrency_limit=1)

    task1 = scheduler.acquire_next_task()
    assert task1 is not None
    assert scheduler.acquire_next_task() is None  # Cannot exceed concurrency limit

    scheduler.mark_completed(task1.task_id)
    task2 = scheduler.acquire_next_task()
    assert task2 is not None
    assert {task1.task_id, task2.task_id} == {'a', 'b'}


def test_priority_orders_ready_tasks():
    low = make_task('low', priority=0)
    high = make_task('high', priority=10)
    scheduler = TaskScheduler([low, high])

    assert scheduler.acquire_next_task().task_id == 'high'


def test_campaign_budget_enforcement():
    campaign = CampaignInfo(campaign_id='c1', budget=Budget(max_cost=100))
    task = make_task('task', campaign=campaign)
    scheduler = TaskScheduler([task])

    scheduler.record_campaign_usage(task, cost=50)
    with pytest.raises(CampaignBudgetError):
        scheduler.record_campaign_usage(task, cost=60)
