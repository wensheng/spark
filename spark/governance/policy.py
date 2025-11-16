"""Policy models and evaluator for governance enforcement."""

from __future__ import annotations

from enum import Enum
from fnmatch import fnmatchcase
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, Field


class PolicyEffect(str, Enum):
    """Possible decision outcomes when evaluating a policy."""

    ALLOW = 'allow'
    DENY = 'deny'
    REQUIRE_APPROVAL = 'require_approval'


class PolicyConstraint(BaseModel):
    """Predicate applied to the request context."""

    key: str = Field(description="Dot-notation key to inspect in the policy context.")
    equals: Any | None = Field(default=None, description="Require the attribute to equal this value.")
    any_of: list[Any] = Field(default_factory=list, description="Allow any of the provided values.")
    not_any_of: list[Any] = Field(default_factory=list, description="Disallow any of the provided values.")
    exists: bool | None = Field(
        default=None,
        description="If True, attribute must exist. If False, attribute must be absent.",
    )

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Return True if the constraint is satisfied for the provided attributes."""

        value = _lookup_nested(attributes, self.key)

        if self.exists is True and value is None:
            return False
        if self.exists is False and value is not None:
            return False
        if self.equals is not None and value != self.equals:
            return False
        if self.any_of and value not in self.any_of:
            return False
        if self.not_any_of and value in self.not_any_of:
            return False
        return True


class PolicySubject(BaseModel):
    """Actor requesting access to a resource/action."""

    identifier: str | None = Field(default=None, description="Stable identifier for the subject.")
    roles: list[str] = Field(default_factory=list, description="Roles assigned to the subject.")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Additional attributes about the subject.")
    tags: dict[str, str] = Field(default_factory=dict, description="Labels for coarse-grained targeting.")


class PolicyRequest(BaseModel):
    """Structured request that will be evaluated against registered rules."""

    subject: PolicySubject
    action: str
    resource: str
    context: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata for constraints.")

    def context_map(self) -> dict[str, Any]:
        """Return a merged context dictionary for constraint evaluation."""

        merged = {
            'action': self.action,
            'resource': self.resource,
            'subject': self.subject.model_dump(),
        }
        merged.update(self.context)
        return merged


class PolicyDecision(BaseModel):
    """Outcome of a policy evaluation."""

    effect: PolicyEffect
    rule: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        """Return True if the decision allows the request."""

        return self.effect == PolicyEffect.ALLOW

    @property
    def requires_approval(self) -> bool:
        """Return True if a human approval gate must be satisfied."""

        return self.effect == PolicyEffect.REQUIRE_APPROVAL


class PolicyRule(BaseModel):
    """Declarative rule that targets actions/resources/subjects via globs."""

    name: str
    description: str | None = None
    effect: PolicyEffect = PolicyEffect.ALLOW
    actions: list[str] = Field(default_factory=list, description="Glob patterns for actions.")
    resources: list[str] = Field(default_factory=list, description="Glob patterns for resource identifiers.")
    subjects: list[str] = Field(default_factory=list, description="Glob patterns or role:ROLE entries.")
    constraints: list[PolicyConstraint] = Field(default_factory=list, description="Optional constraint predicates.")
    priority: int = Field(default=100, description="Lower numbers evaluate first.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    def matches(self, request: PolicyRequest) -> bool:
        """Return True if the rule applies to the request."""

        if self.actions and not _matches_any(request.action, self.actions):
            return False
        if self.resources and not _matches_any(request.resource, self.resources):
            return False
        if self.subjects and not self._matches_subject(request.subject):
            return False
        context = request.context_map()
        return all(constraint.matches(context) for constraint in self.constraints)

    def _matches_subject(self, subject: PolicySubject) -> bool:
        identifier = subject.identifier or ''
        for pattern in self.subjects:
            if pattern.startswith('role:'):
                role = pattern.split(':', 1)[1]
                if any(fnmatchcase(role_name, role) for role_name in subject.roles):
                    return True
                continue
            if pattern.startswith('tag:'):
                tag = pattern.split(':', 1)[1]
                key, _, expected = tag.partition('=')
                value = subject.tags.get(key)
                if expected:
                    if value is not None and fnmatchcase(value, expected):
                        return True
                    continue
                if key in subject.tags:
                    return True
                continue
            if identifier and fnmatchcase(identifier, pattern):
                return True
        return False


class PolicySet(BaseModel):
    """Collection of rules evaluated in priority order."""

    name: str = 'default'
    description: str | None = None
    default_effect: PolicyEffect = PolicyEffect.ALLOW
    rules: list[PolicyRule] = Field(default_factory=list)

    def ordered_rules(self) -> list[PolicyRule]:
        """Return rules sorted by priority."""

        return sorted(self.rules, key=lambda rule: rule.priority)


class PolicyError(RuntimeError):
    """Base exception for policy violations."""

    def __init__(self, message: str, *, decision: PolicyDecision, request: PolicyRequest) -> None:
        super().__init__(message)
        self.decision = decision
        self.request = request


class PolicyViolationError(PolicyError):
    """Raised when a policy denies execution outright."""


class PolicyApprovalRequired(PolicyError):
    """Raised when human approval is required before continuing."""


class PolicyEngine:
    """Evaluate policy requests against an ordered set of rules."""

    def __init__(self, policy_set: PolicySet | None = None) -> None:
        self._policy_set = policy_set or PolicySet()

    @property
    def policy_set(self) -> PolicySet:
        """Return the wrapped policy set."""

        return self._policy_set

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """Evaluate rules and return a decision without raising."""

        for rule in self._policy_set.ordered_rules():
            if rule.matches(request):
                return PolicyDecision(
                    effect=rule.effect,
                    rule=rule.name,
                    reason=rule.description,
                    metadata=dict(rule.metadata),
                )

        return PolicyDecision(
            effect=self._policy_set.default_effect,
            rule=None,
            reason='default_effect',
        )

    def enforce(self, request: PolicyRequest) -> PolicyDecision:
        """Evaluate and raise when the decision is not ALLOW."""

        decision = self.evaluate(request)
        if decision.effect == PolicyEffect.DENY:
            raise PolicyViolationError(
                f"Policy denied action '{request.action}' on resource '{request.resource}'",
                decision=decision,
                request=request,
            )
        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            raise PolicyApprovalRequired(
                f"Policy requires approval for action '{request.action}' on resource '{request.resource}'",
                decision=decision,
                request=request,
            )
        return decision


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    """Return True if the string matches any provided glob pattern."""

    return any(fnmatchcase(value, pattern) for pattern in patterns)


def _lookup_nested(mapping: Mapping[str, Any], dotted_key: str) -> Any:
    """Return nested attribute referenced via dot notation."""

    parts = dotted_key.split('.')
    current: Any = mapping
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        return None
    return current
