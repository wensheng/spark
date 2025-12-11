---
title: Governance Classes
parent: API
nav_order: 5
---
# Governance Classes
---

This document provides comprehensive API reference for Spark's Governance system. These classes enable policy-based control of agent and graph behavior through declarative rules, approval workflows, and compliance enforcement.

## Table of Contents

- [Overview](#overview)
- [Policy Engine](#policy-engine)
  - [PolicyEngine](#policyengine)
  - [PolicySet](#policyset)
- [Policy Components](#policy-components)
  - [PolicyRule](#policyrule)
  - [PolicyConstraint](#policyconstraint)
  - [PolicyEffect](#policyeffect)
- [Request and Decision](#request-and-decision)
  - [PolicyRequest](#policyrequest)
  - [PolicySubject](#policysubject)
  - [PolicyDecision](#policydecision)
- [Approval System](#approval-system)
  - [ApprovalGateManager](#approvalgatemanager)
  - [ApprovalRequest](#approvalrequest)
  - [ApprovalStatus](#approvalstatus)
- [Exceptions](#exceptions)
- [Use Cases](#use-cases)
- [Examples](#examples)

---

## Overview

The Governance system provides policy-based control over agent and graph operations through:

- **Declarative Rules**: Define policies using conditions, effects, and constraints
- **Flexible Matching**: Use glob patterns for actions, resources, and subjects
- **Three Effects**: ALLOW, DENY, or REQUIRE_APPROVAL for fine-grained control
- **Approval Workflows**: Human-in-the-loop gates for critical operations
- **Audit Trail**: Track all policy decisions and approvals
- **Role-Based Access**: Support for role and tag-based subject matching

**Use Cases**:
- Cost control and budget enforcement
- Security policy enforcement
- Compliance requirements (SOC2, HIPAA, etc.)
- Approval workflows for critical actions
- Multi-tenant isolation
- Resource usage limits

---

## Policy Engine

### PolicyEngine

**Module**: `spark.governance.policy`

### Overview

`PolicyEngine` is the core evaluator that matches policy requests against registered rules and returns decisions. It supports priority-based rule evaluation and provides both evaluate (non-throwing) and enforce (throwing) modes.

### Class Signature

```python
class PolicyEngine:
    """Evaluate policy requests against an ordered set of rules."""
```

### Constructor

```python
def __init__(self, policy_set: Optional[PolicySet] = None) -> None
```

**Parameters**:
- `policy_set`: PolicySet with rules to evaluate (creates empty set if None)

### Key Properties

#### `policy_set: PolicySet`

Returns the wrapped policy set with all rules.

```python
@property
def policy_set(self) -> PolicySet
```

### Key Methods

#### `evaluate()`

Evaluate a policy request and return a decision without raising exceptions.

```python
def evaluate(self, request: PolicyRequest) -> PolicyDecision
```

**Parameters**:
- `request`: PolicyRequest describing the operation to evaluate

**Returns**: PolicyDecision with effect, matching rule, and reason

**Behavior**:
- Iterates through rules in priority order (lowest priority number first)
- Returns decision from first matching rule
- Returns default_effect if no rules match

#### `enforce()`

Evaluate a policy request and raise an exception if not ALLOW.

```python
def enforce(self, request: PolicyRequest) -> PolicyDecision
```

**Parameters**:
- `request`: PolicyRequest describing the operation to evaluate

**Returns**: PolicyDecision (only if effect is ALLOW)

**Raises**:
- `PolicyViolationError`: If effect is DENY
- `PolicyApprovalRequired`: If effect is REQUIRE_APPROVAL

### Example

```python
from spark.governance import PolicyEngine, PolicySet, PolicyRule, PolicyEffect

# Create policy set
policy_set = PolicySet(
    name="production_policies",
    default_effect=PolicyEffect.DENY,
    rules=[
        PolicyRule(
            name="allow_read_operations",
            effect=PolicyEffect.ALLOW,
            actions=["*.read", "*.list"],
            priority=100
        ),
        PolicyRule(
            name="require_approval_for_expensive_models",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["model.invoke"],
            resources=["gpt-4*", "claude-opus*"],
            priority=50
        ),
        PolicyRule(
            name="deny_dangerous_operations",
            effect=PolicyEffect.DENY,
            actions=["*.delete", "*.destroy"],
            priority=10
        )
    ]
)

# Create engine
engine = PolicyEngine(policy_set=policy_set)

# Evaluate request
from spark.governance import PolicyRequest, PolicySubject

request = PolicyRequest(
    subject=PolicySubject(
        identifier="user_123",
        roles=["developer"]
    ),
    action="model.invoke",
    resource="gpt-4",
    context={"estimated_cost": 2.5}
)

# Non-throwing evaluation
decision = engine.evaluate(request)
if decision.effect == PolicyEffect.ALLOW:
    # Proceed with operation
    pass
elif decision.requires_approval:
    # Initiate approval workflow
    pass

# Throwing enforcement
try:
    decision = engine.enforce(request)
    # Proceed with operation
except PolicyViolationError as e:
    print(f"Policy denied: {e}")
except PolicyApprovalRequired as e:
    print(f"Approval required: {e}")
```

---

### PolicySet

**Module**: `spark.governance.policy`

### Overview

`PolicySet` is a collection of rules evaluated in priority order with a default effect for unmatched requests.

### Class Signature

```python
class PolicySet(BaseModel):
    """Collection of rules evaluated in priority order."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | `'default'` | Name of the policy set |
| `description` | `Optional[str]` | `None` | Human-readable description |
| `default_effect` | `PolicyEffect` | `PolicyEffect.ALLOW` | Effect when no rules match |
| `rules` | `list[PolicyRule]` | `[]` | List of policy rules |

### Key Methods

#### `ordered_rules()`

Return rules sorted by priority (lowest number first).

```python
def ordered_rules(self) -> list[PolicyRule]
```

### Example

```python
from spark.governance import PolicySet, PolicyRule, PolicyEffect

policy_set = PolicySet(
    name="api_policies",
    description="Policies for API access control",
    default_effect=PolicyEffect.DENY,
    rules=[
        PolicyRule(name="rule1", priority=100, ...),
        PolicyRule(name="rule2", priority=50, ...),
        PolicyRule(name="rule3", priority=200, ...)
    ]
)

# Get ordered rules (50, 100, 200)
for rule in policy_set.ordered_rules():
    print(f"{rule.name}: priority {rule.priority}")
```

---

## Policy Components

### PolicyRule

**Module**: `spark.governance.policy`

**Inheritance**: `BaseModel`

### Overview

`PolicyRule` is a declarative rule that targets actions, resources, and subjects using glob patterns and optional constraints.

### Class Signature

```python
class PolicyRule(BaseModel):
    """Declarative rule that targets actions/resources/subjects via globs."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | - | Unique rule name (required) |
| `description` | `Optional[str]` | `None` | Human-readable description |
| `effect` | `PolicyEffect` | `PolicyEffect.ALLOW` | Effect when rule matches |
| `actions` | `list[str]` | `[]` | Glob patterns for actions |
| `resources` | `list[str]` | `[]` | Glob patterns for resources |
| `subjects` | `list[str]` | `[]` | Glob patterns, role:ROLE, or tag:KEY=VALUE |
| `constraints` | `list[PolicyConstraint]` | `[]` | Optional constraint predicates |
| `priority` | `int` | `100` | Lower numbers evaluate first |
| `metadata` | `dict[str, Any]` | `{}` | Additional rule metadata |

### Key Methods

#### `matches()`

Check if rule applies to a request.

```python
def matches(self, request: PolicyRequest) -> bool
```

**Parameters**:
- `request`: PolicyRequest to check

**Returns**: True if rule matches request

### Pattern Matching

**Actions, Resources**: Standard glob patterns
- `*`: Matches anything
- `?`: Matches single character
- `[seq]`: Matches any character in seq
- `[!seq]`: Matches any character not in seq

**Examples**:
- `model.*` matches `model.invoke`, `model.list`, etc.
- `gpt-4*` matches `gpt-4`, `gpt-4o`, `gpt-4-turbo`, etc.
- `*.read` matches `user.read`, `document.read`, etc.

**Subjects**: Special prefixes
- `role:ROLE` - Match subjects with specific role
- `tag:KEY=VALUE` - Match subjects with specific tag value
- `tag:KEY` - Match subjects with any value for tag
- Otherwise: Glob match against subject identifier

**Examples**:
- `role:admin` - Matches subjects with "admin" role
- `role:dev*` - Matches subjects with roles starting with "dev"
- `tag:env=prod` - Matches subjects tagged with env=prod
- `user_*` - Matches subject identifiers starting with "user_"

### Example

```python
from spark.governance import PolicyRule, PolicyEffect, PolicyConstraint

rule = PolicyRule(
    name="expensive_model_approval",
    description="Require approval for expensive model calls",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["model.invoke"],
    resources=["gpt-4*", "claude-opus*"],
    subjects=["role:developer", "role:analyst"],
    constraints=[
        PolicyConstraint(
            key="estimated_cost",
            any_of=[],  # No restriction
        )
    ],
    priority=50,
    metadata={"category": "cost_control"}
)

# Check if rule matches a request
from spark.governance import PolicyRequest, PolicySubject

request = PolicyRequest(
    subject=PolicySubject(identifier="user_123", roles=["developer"]),
    action="model.invoke",
    resource="gpt-4o",
    context={"estimated_cost": 3.0}
)

if rule.matches(request):
    print(f"Rule '{rule.name}' matches this request")
```

---

### PolicyConstraint

**Module**: `spark.governance.policy`

**Inheritance**: `BaseModel`

### Overview

`PolicyConstraint` is a predicate applied to the request context for fine-grained matching beyond glob patterns.

### Class Signature

```python
class PolicyConstraint(BaseModel):
    """Predicate applied to the request context."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `str` | - | Dot-notation key to inspect in context (required) |
| `equals` | `Any \| None` | `None` | Require attribute to equal this value |
| `any_of` | `list[Any]` | `[]` | Allow any of these values |
| `not_any_of` | `list[Any]` | `[]` | Disallow any of these values |
| `exists` | `bool \| None` | `None` | If True, attribute must exist; if False, must not exist |

### Key Methods

#### `matches()`

Check if constraint is satisfied for the provided attributes.

```python
def matches(self, attributes: Mapping[str, Any]) -> bool
```

**Parameters**:
- `attributes`: Dictionary of attributes to check

**Returns**: True if constraint matches

### Dot Notation

Access nested attributes using dot notation:
- `"user.role"` → `attributes["user"]["role"]`
- `"config.model.temperature"` → `attributes["config"]["model"]["temperature"]`

### Example

```python
from spark.governance import PolicyConstraint

# Simple equality
constraint = PolicyConstraint(key="model", equals="gpt-4")

# Value in set
constraint = PolicyConstraint(
    key="action_type",
    any_of=["read", "list", "view"]
)

# Value not in set
constraint = PolicyConstraint(
    key="environment",
    not_any_of=["production", "staging"]
)

# Check existence
constraint = PolicyConstraint(
    key="api_key",
    exists=True
)

# Complex nested
constraint = PolicyConstraint(
    key="config.model.temperature",
    any_of=[0.0, 0.1, 0.2, 0.3]
)

# Test constraint
attributes = {
    "model": "gpt-4",
    "config": {
        "model": {
            "temperature": 0.1
        }
    }
}

if constraint.matches(attributes):
    print("Constraint satisfied")
```

---

### PolicyEffect

**Module**: `spark.governance.policy`

**Type**: String Enum

### Overview

Enumeration of possible policy decision outcomes.

### Values

| Value | Description |
|-------|-------------|
| `ALLOW` | Allow the operation to proceed |
| `DENY` | Deny the operation outright |
| `REQUIRE_APPROVAL` | Require human approval before proceeding |

### Example

```python
from spark.governance import PolicyEffect

effect = PolicyEffect.ALLOW
effect = PolicyEffect.DENY
effect = PolicyEffect.REQUIRE_APPROVAL

# String comparison
if effect.value == "allow":
    pass
```

---

## Request and Decision

### PolicyRequest

**Module**: `spark.governance.policy`

**Inheritance**: `BaseModel`

### Overview

`PolicyRequest` is a structured request describing an operation to be evaluated against policy rules.

### Class Signature

```python
class PolicyRequest(BaseModel):
    """Structured request that will be evaluated against registered rules."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `subject` | `PolicySubject` | - | Actor requesting access (required) |
| `action` | `str` | - | Action being requested (required) |
| `resource` | `str` | - | Resource being accessed (required) |
| `context` | `dict[str, Any]` | `{}` | Arbitrary metadata for constraints |

### Key Methods

#### `context_map()`

Return a merged context dictionary for constraint evaluation.

```python
def context_map(self) -> dict[str, Any]
```

**Returns**: Dictionary with action, resource, subject, and context merged

### Example

```python
from spark.governance import PolicyRequest, PolicySubject

request = PolicyRequest(
    subject=PolicySubject(
        identifier="user_alice",
        roles=["developer", "team_lead"],
        tags={"department": "engineering", "level": "senior"}
    ),
    action="model.invoke",
    resource="gpt-4o",
    context={
        "estimated_cost": 2.5,
        "estimated_tokens": 5000,
        "model_config": {
            "temperature": 0.7,
            "max_tokens": 1000
        }
    }
)

# Get merged context for constraint evaluation
context_map = request.context_map()
# Contains: action, resource, subject, estimated_cost, estimated_tokens, model_config
```

---

### PolicySubject

**Module**: `spark.governance.policy`

**Inheritance**: `BaseModel`

### Overview

`PolicySubject` represents the actor requesting access to a resource or action.

### Class Signature

```python
class PolicySubject(BaseModel):
    """Actor requesting access to a resource/action."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `identifier` | `Optional[str]` | `None` | Stable identifier for the subject |
| `roles` | `list[str]` | `[]` | Roles assigned to the subject |
| `attributes` | `dict[str, Any]` | `{}` | Additional attributes about the subject |
| `tags` | `dict[str, str]` | `{}` | Labels for coarse-grained targeting |

### Example

```python
from spark.governance import PolicySubject

# User subject
subject = PolicySubject(
    identifier="user_alice_123",
    roles=["developer", "team_lead"],
    attributes={"email": "alice@example.com", "joined": "2023-01-15"},
    tags={"department": "engineering", "level": "senior", "clearance": "confidential"}
)

# Service account subject
subject = PolicySubject(
    identifier="service_account_api_worker",
    roles=["service", "worker"],
    tags={"environment": "production", "region": "us-west-2"}
)

# Anonymous subject
subject = PolicySubject(
    roles=["anonymous"],
    tags={"source": "public_api"}
)
```

---

### PolicyDecision

**Module**: `spark.governance.policy`

**Inheritance**: `BaseModel`

### Overview

`PolicyDecision` represents the outcome of a policy evaluation.

### Class Signature

```python
class PolicyDecision(BaseModel):
    """Outcome of a policy evaluation."""
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `effect` | `PolicyEffect` | - | Decision effect (required) |
| `rule` | `Optional[str]` | `None` | Name of matching rule (None if default) |
| `reason` | `Optional[str]` | `None` | Explanation for decision |
| `metadata` | `dict[str, Any]` | `{}` | Additional decision metadata |

### Key Properties

#### `is_allowed: bool`

Returns True if the decision allows the request.

```python
@property
def is_allowed(self) -> bool
```

#### `requires_approval: bool`

Returns True if a human approval gate must be satisfied.

```python
@property
def requires_approval(self) -> bool
```

### Example

```python
from spark.governance import PolicyEngine, PolicyRequest

engine = PolicyEngine(policy_set)
decision = engine.evaluate(request)

# Check decision
if decision.is_allowed:
    print("Operation allowed")
    print(f"Matched rule: {decision.rule}")
elif decision.requires_approval:
    print("Approval required")
    print(f"Reason: {decision.reason}")
else:
    print("Operation denied")
    print(f"Reason: {decision.reason}")
```

---

## Approval System

### ApprovalGateManager

**Module**: `spark.governance.approval`

### Overview

`ApprovalGateManager` manages approval requests with persistence, tracking, and resolution capabilities. Supports both in-memory and state-backed storage.

### Class Signature

```python
class ApprovalGateManager:
    """Persist approval requests and support resolve/update operations."""
```

### Constructor

```python
def __init__(
    self,
    state: Optional[Any] = None,
    *,
    storage_key: str = 'approval_requests'
) -> None
```

**Parameters**:
- `state`: Optional state backend (e.g., GraphState) for persistence
- `storage_key`: Key for storing approvals in state backend

### Key Methods

#### `submit_request()`

Create and persist a new approval request.

```python
async def submit_request(
    self,
    *,
    action: str,
    resource: str,
    subject: dict[str, Any],
    reason: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None
) -> ApprovalRequest
```

**Parameters**:
- `action`: Action requiring approval
- `resource`: Resource being accessed
- `subject`: Subject dictionary (from PolicySubject)
- `reason`: Optional reason for approval requirement
- `metadata`: Additional metadata

**Returns**: ApprovalRequest with PENDING status

#### `resolve_request()`

Mark an approval request as approved or rejected.

```python
async def resolve_request(
    self,
    approval_id: str,
    *,
    status: ApprovalStatus,
    reviewer: Optional[str] = None,
    notes: Optional[str] = None
) -> ApprovalRequest
```

**Parameters**:
- `approval_id`: Approval request identifier
- `status`: New status (APPROVED or REJECTED)
- `reviewer`: Optional reviewer identifier
- `notes`: Optional reviewer notes

**Returns**: Updated ApprovalRequest

**Raises**: `KeyError` if approval not found

#### `list_requests()`

Return all approval requests (pending or resolved).

```python
async def list_requests(self) -> list[ApprovalRequest]
```

#### `pending_requests()`

Return only pending approval requests.

```python
async def pending_requests(self) -> list[ApprovalRequest]
```

#### `get_request()`

Return a single approval request by identifier.

```python
async def get_request(self, approval_id: str) -> Optional[ApprovalRequest]
```

### Example

```python
from spark.governance import ApprovalGateManager, ApprovalStatus
from spark.graphs.graph_state import GraphState

# With graph state persistence
graph_state = GraphState()
manager = ApprovalGateManager(state=graph_state)

# Submit approval request
approval = await manager.submit_request(
    action="model.invoke",
    resource="gpt-4o",
    subject={"identifier": "user_123", "roles": ["developer"]},
    reason="High cost model invocation",
    metadata={"estimated_cost": 5.0}
)

print(f"Approval {approval.approval_id} is {approval.status.value}")

# List pending approvals
pending = await manager.pending_requests()
print(f"{len(pending)} pending approvals")

# Resolve approval
resolved = await manager.resolve_request(
    approval_id=approval.approval_id,
    status=ApprovalStatus.APPROVED,
    reviewer="manager_alice",
    notes="Approved for urgent analysis task"
)

print(f"Approval {resolved.approval_id} is now {resolved.status.value}")
```

---

### ApprovalRequest

**Module**: `spark.governance.approval`

**Inheritance**: `BaseModel`

### Overview

`ApprovalRequest` records an approval requirement surfaced by governance policies.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `approval_id` | `str` | `uuid4().hex` | Unique approval identifier |
| `created_at` | `float` | `time.time()` | Creation timestamp |
| `action` | `str` | - | Action requiring approval (required) |
| `resource` | `str` | - | Resource being accessed (required) |
| `subject` | `dict[str, Any]` | `{}` | Subject dictionary |
| `reason` | `Optional[str]` | `None` | Reason for approval requirement |
| `metadata` | `dict[str, Any]` | `{}` | Additional metadata |
| `status` | `ApprovalStatus` | `PENDING` | Current status |
| `decided_at` | `Optional[float]` | `None` | Decision timestamp |
| `decided_by` | `Optional[str]` | `None` | Reviewer identifier |
| `notes` | `Optional[str]` | `None` | Reviewer notes |

---

### ApprovalStatus

**Module**: `spark.governance.approval`

**Type**: String Enum

### Overview

Lifecycle state for an approval request.

### Values

| Value | Description |
|-------|-------------|
| `PENDING` | Awaiting decision |
| `APPROVED` | Approved by reviewer |
| `REJECTED` | Rejected by reviewer |

---

## Exceptions

### PolicyError

**Module**: `spark.governance.policy`

**Inheritance**: `RuntimeError`

Base exception for policy violations. Contains decision and request details.

**Attributes**:
- `decision`: PolicyDecision that caused the error
- `request`: PolicyRequest being evaluated

### PolicyViolationError

**Module**: `spark.governance.policy`

**Inheritance**: `PolicyError`

Raised when a policy denies execution outright (DENY effect).

### PolicyApprovalRequired

**Module**: `spark.governance.policy`

**Inheritance**: `PolicyError`

Raised when human approval is required before continuing (REQUIRE_APPROVAL effect).

### ApprovalPendingError

**Module**: `spark.governance.approval`

**Inheritance**: `RuntimeError`

Raised when execution must pause pending external approval.

**Attributes**:
- `approval`: ApprovalRequest requiring resolution

---

## Use Cases

### Cost Control

Enforce budget caps and require approval for expensive operations:

```python
PolicyRule(
    name="cost_cap",
    effect=PolicyEffect.DENY,
    actions=["model.invoke"],
    constraints=[
        PolicyConstraint(key="estimated_cost", exists=True),
        PolicyConstraint(key="estimated_cost", not_any_of=[])  # Custom logic
    ]
)
```

### Security Enforcement

Prevent dangerous operations from untrusted subjects:

```python
PolicyRule(
    name="prevent_data_deletion",
    effect=PolicyEffect.DENY,
    actions=["data.delete", "data.purge"],
    subjects=["role:external", "role:guest"]
)
```

### Compliance Requirements

Require approval for sensitive data access:

```python
PolicyRule(
    name="pii_access_approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["*.read", "*.access"],
    resources=["pii:*", "phi:*", "sensitive:*"]
)
```

### Multi-Tenant Isolation

Restrict access based on tenant tags:

```python
PolicyRule(
    name="tenant_isolation",
    effect=PolicyEffect.DENY,
    actions=["*"],
    resources=["tenant_a:*"],
    subjects=["tag:tenant=tenant_b"]
)
```

---

## Examples

### Complete Governance Setup

```python
from spark.governance import (
    PolicyEngine,
    PolicySet,
    PolicyRule,
    PolicyEffect,
    PolicyConstraint,
    PolicyRequest,
    PolicySubject,
    ApprovalGateManager
)

# Define policy set
policy_set = PolicySet(
    name="production_governance",
    description="Production environment governance policies",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Allow read operations for everyone
        PolicyRule(
            name="allow_reads",
            effect=PolicyEffect.ALLOW,
            actions=["*.read", "*.list", "*.view"],
            priority=100
        ),
        # Require approval for expensive models
        PolicyRule(
            name="expensive_model_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["model.invoke"],
            resources=["gpt-4*", "claude-opus*"],
            constraints=[
                PolicyConstraint(key="estimated_cost", exists=True)
            ],
            priority=50
        ),
        # Deny dangerous operations from non-admins
        PolicyRule(
            name="admin_only_dangerous_ops",
            effect=PolicyEffect.DENY,
            actions=["*.delete", "*.destroy", "*.purge"],
            subjects=["role:admin"],
            priority=10
        )
    ]
)

# Create engine
engine = PolicyEngine(policy_set=policy_set)

# Create approval manager
approval_manager = ApprovalGateManager()

# Evaluate request
request = PolicyRequest(
    subject=PolicySubject(
        identifier="user_alice",
        roles=["developer"],
        tags={"department": "engineering"}
    ),
    action="model.invoke",
    resource="gpt-4o",
    context={"estimated_cost": 3.5}
)

# Enforce policy
try:
    decision = engine.enforce(request)
    print("Operation allowed")
    # Proceed with model invocation
except PolicyApprovalRequired as e:
    # Submit approval request
    approval = await approval_manager.submit_request(
        action=request.action,
        resource=request.resource,
        subject=request.subject.model_dump(),
        reason=e.decision.reason,
        metadata=request.context
    )
    print(f"Approval {approval.approval_id} submitted")

    # Wait for approval (in real system, this would be async)
    # ... approval workflow ...

    # Check approval status
    resolved = await approval_manager.get_request(approval.approval_id)
    if resolved.status == ApprovalStatus.APPROVED:
        print("Approved - proceeding with operation")
    else:
        print(f"Rejected: {resolved.notes}")
except PolicyViolationError as e:
    print(f"Operation denied: {e.decision.reason}")
```

---

## Best Practices

1. **Start Permissive**: Begin with ALLOW default and add DENY rules incrementally
2. **Use Priorities**: Assign priorities carefully (10 = highest precedence, 100 = normal, 200 = lowest)
3. **Specific First**: Put specific rules at higher priority than broad rules
4. **Test Thoroughly**: Test policy rules with various subject/action/resource combinations
5. **Document Rules**: Use descriptive names and descriptions for all rules
6. **Audit Trail**: Log all policy decisions for compliance and debugging
7. **Version Policies**: Track policy set versions alongside code
8. **Review Regularly**: Periodically review and update policies
9. **Least Privilege**: Default to denying access and explicitly grant permissions
10. **Approval Workflows**: Use REQUIRE_APPROVAL for high-risk operations rather than blocking
