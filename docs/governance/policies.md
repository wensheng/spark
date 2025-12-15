---
title: Policy Rules & Effects
parent: Governance
nav_order: 1
---
# Policy Rules & Effects
---

This guide covers the detailed structure of PolicyRule, how to define conditions and constraints, the three policy effects, and how rules are evaluated by the PolicyEngine.

## Table of Contents

- [PolicyRule Structure](#policyrule-structure)
- [Rule Matching](#rule-matching)
- [Policy Effects](#policy-effects)
- [Constraints](#constraints)
- [Policy Sets](#policy-sets)
- [Rule Evaluation Order](#rule-evaluation-order)
- [Advanced Patterns](#advanced-patterns)

## PolicyRule Structure

A `PolicyRule` is a declarative specification that defines:
- **What** operations to target (actions, resources, subjects)
- **How** to decide (effect: ALLOW, DENY, or REQUIRE_APPROVAL)
- **When** to apply (constraints on context)
- **Priority** for evaluation order

### Complete Example

```python
from spark.governance import PolicyRule, PolicyEffect, PolicyConstraint

rule = PolicyRule(
    name="high_cost_approval",
    description="Require approval for operations estimated to cost over $1",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["agent:tool_execute", "agent:model_invoke"],
    resources=["model://gpt-4*", "model://claude-opus*"],
    subjects=["role:developer", "role:analyst"],
    constraints=[
        PolicyConstraint(key="estimated_cost", any_of=[]),  # Will need custom logic
        PolicyConstraint(key="environment", equals="production")
    ],
    priority=10,
    metadata={
        "cost_threshold": 1.0,
        "approval_sla_hours": 24,
        "compliance_tag": "cost_control"
    }
)
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | Yes | Unique identifier for the rule |
| `description` | str | No | Human-readable explanation of the rule's purpose |
| `effect` | PolicyEffect | Yes | ALLOW, DENY, or REQUIRE_APPROVAL |
| `actions` | list[str] | No | Glob patterns for action identifiers |
| `resources` | list[str] | No | Glob patterns for resource identifiers |
| `subjects` | list[str] | No | Patterns for subject identifiers or roles |
| `constraints` | list[PolicyConstraint] | No | Additional conditions on request context |
| `priority` | int | No | Evaluation order (default: 100, lower = earlier) |
| `metadata` | dict[str, Any] | No | Custom data attached to decisions |

## Rule Matching

A rule **matches** a request if ALL of the following are true:

1. **Action matches** (if actions specified): Request action matches at least one action pattern
2. **Resource matches** (if resources specified): Request resource matches at least one resource pattern
3. **Subject matches** (if subjects specified): Request subject matches at least one subject pattern
4. **All constraints pass**: Every constraint evaluates to True

If any list (actions, resources, subjects) is empty, that dimension is not checked (implicitly matches all).

### Pattern Matching

Spark uses **glob patterns** (via `fnmatch`) for flexible matching:

#### Action Patterns

```python
# Exact match
actions=["agent:tool_execute"]

# Wildcard suffix
actions=["agent:*"]  # Matches agent:tool_execute, agent:model_invoke, etc.

# Wildcard prefix
actions=["*:execute"]  # Matches agent:execute, node:execute, etc.

# Multiple patterns (OR logic)
actions=["agent:tool_execute", "agent:model_invoke"]
```

#### Resource Patterns

```python
# Exact resource
resources=["tool://web_search"]

# Glob patterns
resources=["model://gpt-4*"]  # Matches gpt-4, gpt-4-turbo, gpt-5-mini
resources=["dataset://production/*"]  # Matches any production dataset
resources=["graph://*/nodes/Sensitive*"]  # Any graph, nodes starting with Sensitive

# Multiple resources
resources=["tool://shell_execute", "tool://eval_code"]
```

#### Subject Patterns

Subjects support three matching modes:

**1. Identifier Pattern Matching**

```python
# Match by identifier
subjects=["user-alice"]
subjects=["user-*"]  # All users with IDs starting with "user-"
subjects=["bot-*", "service-*"]  # Bots or services
```

**2. Role Matching**

```python
# Match by role (prefix with "role:")
subjects=["role:admin"]
subjects=["role:developer"]
subjects=["role:*"]  # Any role

# Subject must have at least one matching role
request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        roles=["developer", "analyst"]  # Matches role:developer
    ),
    # ...
)
```

**3. Tag Matching**

```python
# Match by tag existence (prefix with "tag:")
subjects=["tag:environment"]  # Has any value for "environment" tag

# Match by tag value
subjects=["tag:environment=production"]  # environment tag equals "production"

# Subject tags
request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        tags={"environment": "production", "team": "platform"}
    ),
    # ...
)
```

### Empty Lists Match All

If a selector list is empty, it matches **all** values:

```python
# Matches all actions and all resources
rule = PolicyRule(
    name="deny_interns",
    effect=PolicyEffect.DENY,
    actions=[],  # Empty = matches all actions
    resources=[],  # Empty = matches all resources
    subjects=["role:intern"]
)

# Matches all subjects on specific action
rule = PolicyRule(
    name="sensitive_operation",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["data:delete"],
    resources=["dataset://production/*"],
    subjects=[]  # Empty = matches all subjects
)
```

## Policy Effects

The three policy effects determine what happens when a rule matches:

### ALLOW

**Effect**: Permit the operation to proceed without restrictions.

**Use Cases**:
- Explicitly allow safe operations
- Override more restrictive default policies
- Grant permissions to specific roles or users

```python
from spark.governance import PolicyEffect

allow_rule = PolicyRule(
    name="allow_read_operations",
    effect=PolicyEffect.ALLOW,
    actions=["data:read", "data:list"],
    resources=["dataset://*"],
    subjects=["role:analyst", "role:developer"]
)
```

**Behavior**:
- `engine.evaluate(request)` returns `PolicyDecision(effect=ALLOW, ...)`
- `engine.enforce(request)` returns decision and does NOT raise exception
- `decision.is_allowed` returns `True`

### DENY

**Effect**: Block the operation immediately. Raises `PolicyViolationError` when enforced.

**Use Cases**:
- Security restrictions (block dangerous operations)
- Access control (prevent unauthorized access)
- Compliance enforcement (prevent policy violations)

```python
deny_rule = PolicyRule(
    name="deny_dangerous_tools",
    effect=PolicyEffect.DENY,
    actions=["agent:tool_execute"],
    resources=["tool://shell_execute", "tool://eval_code"],
    subjects=["role:untrusted_user"]
)
```

**Behavior**:
- `engine.evaluate(request)` returns `PolicyDecision(effect=DENY, ...)`
- `engine.enforce(request)` raises `PolicyViolationError`
- `decision.is_allowed` returns `False`

**Exception Structure**:
```python
from spark.governance import PolicyViolationError

try:
    engine.enforce(request)
except PolicyViolationError as e:
    print(f"Message: {e}")  # "Policy denied action 'X' on resource 'Y'"
    print(f"Decision: {e.decision}")  # PolicyDecision object
    print(f"Request: {e.request}")  # Original PolicyRequest
    print(f"Rule: {e.decision.rule}")  # Name of rule that denied
```

### REQUIRE_APPROVAL

**Effect**: Pause execution and require human approval before proceeding. Raises `PolicyApprovalRequired` when enforced.

**Use Cases**:
- High-risk operations (deletions, production changes)
- Cost control (expensive operations)
- Compliance (operations requiring audit trail)
- Governance (human oversight for critical decisions)

```python
approval_rule = PolicyRule(
    name="approval_for_production_changes",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["data:write", "data:delete"],
    resources=["dataset://production/*"],
    subjects=[]  # All subjects require approval
)
```

**Behavior**:
- `engine.evaluate(request)` returns `PolicyDecision(effect=REQUIRE_APPROVAL, ...)`
- `engine.enforce(request)` raises `PolicyApprovalRequired`
- `decision.requires_approval` returns `True`

**Exception Structure**:
```python
from spark.governance import PolicyApprovalRequired

try:
    engine.enforce(request)
except PolicyApprovalRequired as e:
    print(f"Message: {e}")  # "Policy requires approval for action 'X' on resource 'Y'"
    print(f"Decision: {e.decision}")  # PolicyDecision object
    print(f"Request: {e.request}")  # Original PolicyRequest

    # Access approval request if integrated with ApprovalGateManager
    # (See approvals.md for details)
```

## Constraints

Constraints are fine-grained conditions evaluated against the request's context map. All constraints must pass for a rule to match.

### PolicyConstraint Structure

```python
from spark.governance import PolicyConstraint

constraint = PolicyConstraint(
    key="tool.arguments.region",  # Dot-notation path in context
    equals="us-east-1",  # Must equal this value
    any_of=["us-east-1", "us-west-2"],  # Must be one of these values
    not_any_of=["eu-west-1"],  # Must NOT be one of these values
    exists=True  # Must exist (or False for must NOT exist)
)
```

### Constraint Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `key` | str | Dot-notation path in context | `"tool.arguments.region"` |
| `equals` | Any | Value must exactly equal this | `equals="production"` |
| `any_of` | list[Any] | Value must be in this list | `any_of=["dev", "staging"]` |
| `not_any_of` | list[Any] | Value must NOT be in this list | `not_any_of=["admin", "root"]` |
| `exists` | bool | Whether key must exist | `exists=True` (must exist) |

### Constraint Evaluation Logic

Constraints are evaluated in this order (all must pass):

1. **Existence check** (if `exists` is set)
   - If `exists=True` and value is `None`: constraint fails
   - If `exists=False` and value is not `None`: constraint fails

2. **Equality check** (if `equals` is set)
   - If value != equals: constraint fails

3. **Inclusion check** (if `any_of` is set)
   - If value not in any_of: constraint fails

4. **Exclusion check** (if `not_any_of` is set)
   - If value in not_any_of: constraint fails

5. If all checks pass: constraint succeeds

### Constraint Examples

#### Check Value Equality

```python
PolicyConstraint(
    key="environment",
    equals="production"
)

# Matches context: {"environment": "production"}
# Fails context: {"environment": "development"}
```

#### Check Value in Set

```python
PolicyConstraint(
    key="tool.arguments.region",
    any_of=["us-east-1", "us-west-2", "us-central-1"]
)

# Matches context: {"tool": {"arguments": {"region": "us-east-1"}}}
# Fails context: {"tool": {"arguments": {"region": "eu-west-1"}}}
```

#### Check Value NOT in Set

```python
PolicyConstraint(
    key="subject.username",
    not_any_of=["admin", "root", "system"]
)

# Matches context: {"subject": {"username": "alice"}}
# Fails context: {"subject": {"username": "admin"}}
```

#### Check Key Existence

```python
# Require presence of approval_ticket
PolicyConstraint(
    key="approval_ticket",
    exists=True
)

# Ensure no dev_mode flag
PolicyConstraint(
    key="dev_mode",
    exists=False
)
```

#### Nested Context Paths

```python
PolicyConstraint(
    key="tool.arguments.query.contains_pii",
    equals=False
)

# Matches context:
# {
#     "tool": {
#         "arguments": {
#             "query": {
#                 "contains_pii": False
#             }
#         }
#     }
# }
```

### Context Map Construction

The `PolicyRequest.context_map()` method builds a merged dictionary for constraint evaluation:

```python
from spark.governance import PolicyRequest, PolicySubject

request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        roles=["developer"],
        attributes={"team": "platform", "level": "senior"}
    ),
    action="agent:tool_execute",
    resource="tool://web_search",
    context={
        "tool": {
            "name": "web_search",
            "arguments": {"query": "example"}
        },
        "estimated_cost": 0.01
    }
)

# context_map() returns:
# {
#     "action": "agent:tool_execute",
#     "resource": "tool://web_search",
#     "subject": {
#         "identifier": "user-123",
#         "roles": ["developer"],
#         "attributes": {"team": "platform", "level": "senior"},
#         "tags": {}
#     },
#     "tool": {
#         "name": "web_search",
#         "arguments": {"query": "example"}
#     },
#     "estimated_cost": 0.01
# }
```

Constraints can then reference any of these keys:

```python
PolicyConstraint(key="subject.attributes.team", equals="platform")
PolicyConstraint(key="tool.arguments.query", any_of=["safe_query_1", "safe_query_2"])
PolicyConstraint(key="estimated_cost", equals=None)  # Would need custom comparison logic
```

## Policy Sets

A `PolicySet` is a named collection of rules with a shared default effect.

### PolicySet Structure

```python
from spark.governance import PolicySet, PolicyEffect, PolicyRule

policy_set = PolicySet(
    name="production_policies",
    description="Governance policies for production environment",
    default_effect=PolicyEffect.DENY,  # Default when no rules match
    rules=[rule1, rule2, rule3]
)
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | No | Identifier for the policy set (default: "default") |
| `description` | str | No | Human-readable description |
| `default_effect` | PolicyEffect | No | Effect when no rules match (default: ALLOW) |
| `rules` | list[PolicyRule] | No | List of rules in this set |

### Default Effect

The `default_effect` is used when **no rules match** the request:

```python
# Permissive default: allow unless explicitly denied
policy_set = PolicySet(
    name="development",
    default_effect=PolicyEffect.ALLOW,
    rules=[
        PolicyRule(name="deny_dangerous", effect=PolicyEffect.DENY, ...)
    ]
)

# Restrictive default: deny unless explicitly allowed
policy_set = PolicySet(
    name="production",
    default_effect=PolicyEffect.DENY,
    rules=[
        PolicyRule(name="allow_safe_reads", effect=PolicyEffect.ALLOW, ...),
        PolicyRule(name="allow_safe_tools", effect=PolicyEffect.ALLOW, ...)
    ]
)
```

**Best Practice**: For production systems, use `default_effect=PolicyEffect.DENY` and explicitly allow safe operations.

## Rule Evaluation Order

Rules are evaluated in **strict priority order** (lower numbers evaluated first). The first matching rule determines the decision.

### Priority Assignment

```python
rules = [
    PolicyRule(
        name="critical_security",
        effect=PolicyEffect.DENY,
        priority=1  # Evaluated first
    ),
    PolicyRule(
        name="compliance_approval",
        effect=PolicyEffect.REQUIRE_APPROVAL,
        priority=10  # Evaluated second
    ),
    PolicyRule(
        name="general_access",
        effect=PolicyEffect.ALLOW,
        priority=100  # Evaluated last
    )
]
```

### Evaluation Flow

```python
def evaluate(request: PolicyRequest) -> PolicyDecision:
    # 1. Get rules sorted by priority
    ordered_rules = policy_set.ordered_rules()  # Sorts by priority ascending

    # 2. Evaluate each rule in order
    for rule in ordered_rules:
        if rule.matches(request):
            # First match wins - return immediately
            return PolicyDecision(
                effect=rule.effect,
                rule=rule.name,
                reason=rule.description,
                metadata=rule.metadata
            )

    # 3. No match - use default effect
    return PolicyDecision(
        effect=policy_set.default_effect,
        rule=None,
        reason="default_effect"
    )
```

### Priority Best Practices

Use a tiered priority scheme:

```python
# Priority ranges
PRIORITY_SECURITY = 1-10      # Deny dangerous operations
PRIORITY_COMPLIANCE = 11-30   # Regulatory requirements
PRIORITY_APPROVAL = 31-50     # Human oversight
PRIORITY_ACCESS = 51-100      # General access control
PRIORITY_PERMISSIVE = 101+    # Broad allow rules
```

Example:

```python
rules = [
    # Security (highest priority)
    PolicyRule(
        name="deny_shell_execution",
        effect=PolicyEffect.DENY,
        actions=["agent:tool_execute"],
        resources=["tool://shell_execute"],
        priority=1
    ),

    # Compliance
    PolicyRule(
        name="pci_data_approval",
        effect=PolicyEffect.REQUIRE_APPROVAL,
        actions=["data:access"],
        resources=["dataset://pci/*"],
        priority=15
    ),

    # Access control
    PolicyRule(
        name="allow_read_for_analysts",
        effect=PolicyEffect.ALLOW,
        actions=["data:read"],
        resources=["dataset://analytics/*"],
        subjects=["role:analyst"],
        priority=60
    ),

    # Permissive defaults
    PolicyRule(
        name="allow_safe_tools",
        effect=PolicyEffect.ALLOW,
        actions=["agent:tool_execute"],
        resources=["tool://web_search", "tool://calculator"],
        priority=110
    )
]
```

### Order Matters Example

```python
# These two rules have different outcomes depending on priority:

# Scenario 1: Deny first (higher priority)
rule_deny = PolicyRule(
    name="deny_all_deletes",
    effect=PolicyEffect.DENY,
    actions=["data:delete"],
    priority=10
)

rule_allow = PolicyRule(
    name="allow_admin_deletes",
    effect=PolicyEffect.ALLOW,
    actions=["data:delete"],
    subjects=["role:admin"],
    priority=20
)

# Result: All deletes denied (even by admins) because deny_all_deletes matches first

# Scenario 2: Allow first (higher priority)
rule_allow = PolicyRule(
    name="allow_admin_deletes",
    effect=PolicyEffect.ALLOW,
    actions=["data:delete"],
    subjects=["role:admin"],
    priority=10
)

rule_deny = PolicyRule(
    name="deny_all_deletes",
    effect=PolicyEffect.DENY,
    actions=["data:delete"],
    priority=20
)

# Result: Admins can delete (allow_admin_deletes matches first for admin subjects)
#         Non-admins denied (deny_all_deletes matches for non-admin subjects)
```

## Advanced Patterns

### Combining Multiple Constraints

All constraints must pass (AND logic):

```python
rule = PolicyRule(
    name="strict_production_access",
    effect=PolicyEffect.ALLOW,
    actions=["data:write"],
    resources=["dataset://production/*"],
    constraints=[
        # Must be in US region
        PolicyConstraint(key="region", any_of=["us-east-1", "us-west-2"]),
        # Must be production environment
        PolicyConstraint(key="environment", equals="production"),
        # Must have approval ticket
        PolicyConstraint(key="approval_ticket", exists=True),
        # Must NOT be emergency bypass
        PolicyConstraint(key="emergency_bypass", exists=False)
    ]
)
```

### Time-Based Policies

Use constraints to enforce time windows:

```python
# Constraint would check: context["timestamp"] in business hours
# Note: Actual time checking requires custom logic in context preparation

rule = PolicyRule(
    name="business_hours_only",
    effect=PolicyEffect.DENY,
    actions=["data:export"],
    resources=["dataset://sensitive/*"],
    constraints=[
        PolicyConstraint(key="is_business_hours", equals=False)
    ]
)

# When creating request, include time check:
import datetime

now = datetime.datetime.now()
is_business_hours = (9 <= now.hour < 17) and (now.weekday() < 5)

request = PolicyRequest(
    subject=subject,
    action="data:export",
    resource="dataset://sensitive/pii",
    context={"is_business_hours": is_business_hours}
)
```

### Cost-Based Policies

Enforce budget limits:

```python
rule = PolicyRule(
    name="high_cost_approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["agent:model_invoke", "agent:tool_execute"],
    resources=["*"],
    constraints=[
        # Cost exceeds threshold (requires cost in context)
        PolicyConstraint(key="estimated_cost", exists=True)
        # Additional custom logic needed to compare cost > threshold
    ]
)

# When creating request:
request = PolicyRequest(
    subject=subject,
    action="agent:model_invoke",
    resource="model://gpt-4",
    context={
        "estimated_cost": 2.50,  # Dollars
        "cost_threshold": 1.00
    }
)
```

### Role Hierarchy

Implement role-based access control:

```python
rules = [
    # Admin can do everything
    PolicyRule(
        name="admin_full_access",
        effect=PolicyEffect.ALLOW,
        actions=["*"],
        resources=["*"],
        subjects=["role:admin"],
        priority=10
    ),

    # Manager can approve
    PolicyRule(
        name="manager_approval_rights",
        effect=PolicyEffect.ALLOW,
        actions=["approval:grant", "approval:deny"],
        resources=["approval://*"],
        subjects=["role:manager"],
        priority=20
    ),

    # Developer can read/write development resources
    PolicyRule(
        name="developer_dev_access",
        effect=PolicyEffect.ALLOW,
        actions=["data:read", "data:write"],
        resources=["dataset://development/*"],
        subjects=["role:developer"],
        priority=30
    ),

    # Analyst can only read
    PolicyRule(
        name="analyst_read_only",
        effect=PolicyEffect.ALLOW,
        actions=["data:read", "data:list"],
        resources=["dataset://*"],
        subjects=["role:analyst"],
        priority=40
    )
]
```

### Multi-Tenant Isolation

Ensure tenants cannot access each other's resources:

```python
rule = PolicyRule(
    name="tenant_isolation",
    effect=PolicyEffect.DENY,
    actions=["*"],
    resources=["*"],
    constraints=[
        # Deny if subject.tenant_id != resource.tenant_id
        # This requires custom constraint logic in your implementation
        PolicyConstraint(key="cross_tenant_access", equals=True)
    ],
    priority=1  # Highest priority
)

# When creating request, detect cross-tenant access:
subject_tenant = request.subject.attributes.get("tenant_id")
resource_tenant = extract_tenant_from_resource(request.resource)
cross_tenant = subject_tenant != resource_tenant

request.context["cross_tenant_access"] = cross_tenant
```

## Testing Policies

### Unit Testing Rules

```python
import pytest
from spark.governance import PolicyRule, PolicyEffect, PolicyConstraint, PolicyEngine, PolicySet, PolicyRequest, PolicySubject

def test_rule_matches_action():
    """Test that rule matches expected actions."""
    rule = PolicyRule(
        name="test_rule",
        effect=PolicyEffect.ALLOW,
        actions=["data:read", "data:list"]
    )

    request_match = PolicyRequest(
        subject=PolicySubject(identifier="user-1"),
        action="data:read",
        resource="dataset://test"
    )

    request_no_match = PolicyRequest(
        subject=PolicySubject(identifier="user-1"),
        action="data:write",
        resource="dataset://test"
    )

    assert rule.matches(request_match)
    assert not rule.matches(request_no_match)

def test_constraint_evaluation():
    """Test constraint matching logic."""
    constraint = PolicyConstraint(
        key="environment",
        equals="production"
    )

    assert constraint.matches({"environment": "production"})
    assert not constraint.matches({"environment": "development"})
    assert not constraint.matches({})  # Key missing

@pytest.mark.parametrize("action,resource,subject_roles,expected_effect", [
    ("data:read", "dataset://public", ["guest"], PolicyEffect.ALLOW),
    ("data:write", "dataset://public", ["guest"], PolicyEffect.DENY),
    ("data:write", "dataset://production", ["admin"], PolicyEffect.REQUIRE_APPROVAL),
    ("data:delete", "dataset://production", ["admin"], PolicyEffect.REQUIRE_APPROVAL),
])
def test_policy_matrix(action, resource, subject_roles, expected_effect):
    """Test policy decisions across multiple scenarios."""
    rules = [
        PolicyRule(
            name="allow_public_read",
            effect=PolicyEffect.ALLOW,
            actions=["data:read"],
            resources=["dataset://public"],
            priority=10
        ),
        PolicyRule(
            name="production_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:write", "data:delete"],
            resources=["dataset://production/*"],
            subjects=["role:admin"],
            priority=20
        ),
        PolicyRule(
            name="deny_guest_writes",
            effect=PolicyEffect.DENY,
            actions=["data:write", "data:delete"],
            subjects=["role:guest"],
            priority=5
        )
    ]

    engine = PolicyEngine(PolicySet(
        default_effect=PolicyEffect.DENY,
        rules=rules
    ))

    request = PolicyRequest(
        subject=PolicySubject(identifier="test-user", roles=subject_roles),
        action=action,
        resource=resource
    )

    decision = engine.evaluate(request)
    assert decision.effect == expected_effect
```

## Next Steps

- [Policy Types](policy-types.md) - Common policy patterns and examples
- [Approval Workflows](approvals.md) - Integrate human approval for REQUIRE_APPROVAL decisions
- [Governance Patterns](patterns.md) - Enterprise-grade governance architectures
