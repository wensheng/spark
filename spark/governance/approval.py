"""Approval gate utilities for governance workflows."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Lifecycle state for an approval request."""

    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class ApprovalRequest(BaseModel):
    """Record describing an approval requirement surfaced by governance policies."""

    approval_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: float = Field(default_factory=lambda: time.time())
    action: str
    resource: str
    subject: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: float | None = None
    decided_by: str | None = None
    notes: str | None = None


class ApprovalPendingError(RuntimeError):
    """Raised when execution must pause pending external approval."""

    def __init__(self, approval: ApprovalRequest) -> None:
        super().__init__(f"Approval required for action '{approval.action}' on '{approval.resource}'")
        self.approval = approval


class ApprovalGateManager:
    """Persist approval requests and support resolve/update operations."""

    def __init__(self, state: Any | None = None, *, storage_key: str = 'approval_requests') -> None:
        self._state = state
        self._storage_key = storage_key
        self._local_store: dict[str, ApprovalRequest] = {}

    async def submit_request(
        self,
        *,
        action: str,
        resource: str,
        subject: dict[str, Any],
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Create and persist a new approval request."""

        approval = ApprovalRequest(
            action=action,
            resource=resource,
            subject=subject,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        requests = await self._load_requests()
        requests.append(approval)
        await self._persist_requests(requests)
        return approval

    async def resolve_request(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> ApprovalRequest:
        """Mark an approval request as approved or rejected."""

        if status is ApprovalStatus.PENDING:
            raise ValueError("Cannot resolve an approval request back to pending.")
        requests = await self._load_requests()
        for index, request in enumerate(requests):
            if request.approval_id != approval_id:
                continue
            request.status = status
            request.decided_at = time.time()
            request.decided_by = reviewer
            request.notes = notes or request.notes
            requests[index] = request
            await self._persist_requests(requests)
            return request
        raise KeyError(f"Approval '{approval_id}' not found.")

    async def list_requests(self) -> list[ApprovalRequest]:
        """Return all approval requests (pending or resolved)."""

        return await self._load_requests()

    async def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Return a single approval request by identifier."""

        requests = await self._load_requests()
        for request in requests:
            if request.approval_id == approval_id:
                return request
        return None

    async def pending_requests(self) -> list[ApprovalRequest]:
        """Return pending approval requests."""

        requests = await self._load_requests()
        return [request for request in requests if request.status is ApprovalStatus.PENDING]

    async def _load_requests(self) -> list[ApprovalRequest]:
        if self._state is None:
            return list(self._local_store.values())
        raw = await self._state.get(self._storage_key, [])
        if not raw:
            return []
        return [ApprovalRequest.model_validate(item) for item in raw]

    async def _persist_requests(self, requests: Iterable[ApprovalRequest]) -> None:
        request_list = list(requests)
        if self._state is None:
            self._local_store = {req.approval_id: req for req in request_list}
            return
        await self._state.set(self._storage_key, [req.model_dump() for req in request_list])
