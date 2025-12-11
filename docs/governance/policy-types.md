---
title: Policy Types
parent: Governance
nav_order: 2
---
# Policy Types
---

This guide provides ready-to-use policy patterns for common governance scenarios. Each section includes complete, runnable examples that you can adapt for your use cases.

## Table of Contents

- [Resource Policies](#resource-policies)
- [Security Policies](#security-policies)
- [Access Control Policies](#access-control-policies)
- [Compliance Policies](#compliance-policies)
- [Cost Policies](#cost-policies)
- [Approval Policies](#approval-policies)
- [Custom Policy Types](#custom-policy-types)

## Resource Policies

Resource policies control access to computational resources like models, APIs, and tools.

### Model Usage Control

Restrict which models can be used by which users:

```python
from spark.governance import PolicySet, PolicyRule, PolicyEffect, PolicyConstraint

# Deny expensive models to non-admin users
expensive_model_policy = PolicyRule(
    name="deny_expensive_models_for_non_admins",
    description="Only admins can use GPT-4 and Claude Opus",
    effect=PolicyEffect.DENY,
    actions=["agent:model_invoke"],
    resources=["model://gpt-4*", "model://claude-opus*"],
    subjects=["role:admin"],  # Will DENY when role is NOT admin
    priority=10
)

# Allow approved models for everyone
approved_models_policy = PolicyRule(
    name="allow_approved_models",
    description="Allow GPT-4o-mini and Claude Sonnet for all users",
    effect=PolicyEffect.ALLOW,
    actions=["agent:model_invoke"],
    resources=["model://gpt-4o-mini", "model://claude-sonnet*"],
    priority=20
)

# Note: The deny rule needs to be inverted - here's the correct approach:
# Use default_effect=DENY and explicitly allow only for admins

model_policy_set = PolicySet(
    name="model_usage",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Admins can use expensive models
        PolicyRule(
            name="admin_expensive_models",
            effect=PolicyEffect.ALLOW,
            actions=["agent:model_invoke"],
            resources=["model://gpt-4*", "model://claude-opus*"],
            subjects=["role:admin"],
            priority=5
        ),
        # Everyone can use approved models
        PolicyRule(
            name="allow_approved_models",
            effect=PolicyEffect.ALLOW,
            actions=["agent:model_invoke"],
            resources=["model://gpt-4o-mini", "model://claude-sonnet*"],
            priority=10
        )
    ]
)
```

### API Rate Limiting

Control API access rates (requires external rate tracking):

```python
# Deny high-frequency requests (requires rate tracking in context)
rate_limit_policy = PolicyRule(
    name="api_rate_limit",
    description="Block requests exceeding rate limit",
    effect=PolicyEffect.DENY,
    actions=["agent:model_invoke", "agent:tool_execute"],
    resources=["*"],
    constraints=[
        PolicyConstraint(key="rate_limit_exceeded", equals=True)
    ],
    priority=1
)

# Usage example:
from spark.governance import PolicyEngine, PolicyRequest, PolicySubject

# Track request counts externally (e.g., Redis, in-memory counter)
def check_rate_limit(user_id: str, limit: int, window_seconds: int) -> bool:
    """Check if user has exceeded rate limit."""
    # Implementation depends on your rate tracking system
    count = get_user_request_count(user_id, window_seconds)
    return count > limit

# Apply policy
request = PolicyRequest(
    subject=PolicySubject(identifier="user-123"),
    action="agent:model_invoke",
    resource="model://gpt-4o",
    context={
        "rate_limit_exceeded": check_rate_limit("user-123", limit=100, window_seconds=60)
    }
)

engine = PolicyEngine(PolicySet(rules=[rate_limit_policy]))
decision = engine.evaluate(request)
```

### Tool Access Control

Restrict access to specific tools:

```python
# Allow only safe tools by default
safe_tools_policy = PolicySet(
    name="tool_access",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Allow safe read-only tools for everyone
        PolicyRule(
            name="allow_safe_tools",
            effect=PolicyEffect.ALLOW,
            actions=["agent:tool_execute"],
            resources=[
                "tool://web_search",
                "tool://calculator",
                "tool://weather_api",
                "tool://date_time"
            ],
            priority=10
        ),

        # Allow file operations for developers
        PolicyRule(
            name="dev_file_access",
            effect=PolicyEffect.ALLOW,
            actions=["agent:tool_execute"],
            resources=["tool://read_file", "tool://write_file"],
            subjects=["role:developer", "role:admin"],
            priority=20
        ),

        # Require approval for database tools
        PolicyRule(
            name="db_tools_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["agent:tool_execute"],
            resources=["tool://sql_query", "tool://db_update"],
            subjects=["role:developer", "role:analyst"],
            priority=15
        )
    ]
)
```

## Security Policies

Security policies prevent dangerous operations and protect sensitive data.

### Block Dangerous Operations

Prevent execution of inherently risky tools:

```python
# Deny dangerous tools completely
dangerous_tools_policy = PolicyRule(
    name="block_dangerous_tools",
    description="Block shell execution and code evaluation for security",
    effect=PolicyEffect.DENY,
    actions=["agent:tool_execute"],
    resources=[
        "tool://shell_execute",
        "tool://eval_code",
        "tool://exec_python",
        "tool://system_command"
    ],
    priority=1  # Highest priority
)

# Exception: Allow for admin in development
admin_dev_exception = PolicyRule(
    name="admin_dev_dangerous_tools",
    description="Admins can use dangerous tools in dev environment only",
    effect=PolicyEffect.ALLOW,
    actions=["agent:tool_execute"],
    resources=["tool://shell_execute", "tool://eval_code"],
    subjects=["role:admin"],
    constraints=[
        PolicyConstraint(key="environment", equals="development")
    ],
    priority=2  # Still high priority but after the deny
)

security_policy_set = PolicySet(
    name="security",
    default_effect=PolicyEffect.ALLOW,
    rules=[admin_dev_exception, dangerous_tools_policy]
    # Note: admin_dev_exception has lower priority number (2 < 1 is wrong)
    # Correct version:
)

# Corrected version:
security_policy_set = PolicySet(
    name="security",
    default_effect=PolicyEffect.ALLOW,
    rules=[
        # Admin exception (evaluated first)
        PolicyRule(
            name="admin_dev_dangerous_tools",
            effect=PolicyEffect.ALLOW,
            actions=["agent:tool_execute"],
            resources=["tool://shell_execute", "tool://eval_code"],
            subjects=["role:admin"],
            constraints=[
                PolicyConstraint(key="environment", equals="development")
            ],
            priority=1
        ),
        # General block (evaluated second)
        PolicyRule(
            name="block_dangerous_tools",
            effect=PolicyEffect.DENY,
            actions=["agent:tool_execute"],
            resources=["tool://shell_execute", "tool://eval_code"],
            priority=2
        )
    ]
)
```

### Sensitive Data Protection

Protect PII and confidential data:

```python
# Deny access to PII data
pii_protection_policy = PolicyRule(
    name="protect_pii",
    description="Block direct access to PII datasets",
    effect=PolicyEffect.DENY,
    actions=["data:read", "data:export"],
    resources=["dataset://pii/*", "dataset://*/ssn", "dataset://*/credit_card"],
    priority=1
)

# Require approval for anonymized PII access
anonymized_pii_policy = PolicyRule(
    name="pii_anonymized_approval",
    description="Allow anonymized PII access with approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["data:read"],
    resources=["dataset://pii_anonymized/*"],
    subjects=["role:analyst", "role:data_scientist"],
    constraints=[
        PolicyConstraint(key="anonymization_verified", equals=True)
    ],
    priority=5
)

# Allow aggregated PII statistics
aggregated_pii_policy = PolicyRule(
    name="allow_aggregated_pii",
    description="Allow reading aggregated PII statistics",
    effect=PolicyEffect.ALLOW,
    actions=["data:read"],
    resources=["dataset://pii_aggregated/*"],
    subjects=["role:analyst", "role:data_scientist"],
    priority=10
)
```

### Injection Attack Prevention

Prevent injection attacks in tool arguments:

```python
# Deny requests with suspicious patterns
injection_prevention_policy = PolicyRule(
    name="prevent_sql_injection",
    description="Block potential SQL injection attempts",
    effect=PolicyEffect.DENY,
    actions=["agent:tool_execute"],
    resources=["tool://sql_query", "tool://db_*"],
    constraints=[
        # Custom logic to detect injection patterns
        PolicyConstraint(key="contains_sql_injection", equals=True)
    ],
    priority=1
)

# Usage:
import re

def detect_sql_injection(query: str) -> bool:
    """Simple SQL injection detection."""
    suspicious_patterns = [
        r";\s*DROP\s+TABLE",
        r";\s*DELETE\s+FROM",
        r"'\s*OR\s+'1'\s*=\s*'1",
        r"--\s*$",
        r"/\*.*\*/"
    ]
    return any(re.search(pattern, query, re.IGNORECASE) for pattern in suspicious_patterns)

# Apply in request context
from spark.tools.decorator import tool

@tool
def sql_query(query: str) -> str:
    """Execute SQL query."""
    # Policy check happens before execution
    return execute_query(query)

# In agent execution:
request = PolicyRequest(
    subject=PolicySubject(identifier="user-123"),
    action="agent:tool_execute",
    resource="tool://sql_query",
    context={
        "tool": {"arguments": {"query": user_query}},
        "contains_sql_injection": detect_sql_injection(user_query)
    }
)
```

## Access Control Policies

Access control policies define who can access what resources.

### Role-Based Access Control (RBAC)

```python
rbac_policy_set = PolicySet(
    name="rbac",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Admin: Full access
        PolicyRule(
            name="admin_full_access",
            effect=PolicyEffect.ALLOW,
            actions=["*"],
            resources=["*"],
            subjects=["role:admin"],
            priority=1
        ),

        # Manager: Approval rights
        PolicyRule(
            name="manager_approvals",
            effect=PolicyEffect.ALLOW,
            actions=["approval:*", "data:read", "data:write"],
            resources=["*"],
            subjects=["role:manager"],
            priority=10
        ),

        # Developer: Dev environment full access
        PolicyRule(
            name="dev_environment_access",
            effect=PolicyEffect.ALLOW,
            actions=["data:*", "node:execute", "agent:*"],
            resources=["*"],
            subjects=["role:developer"],
            constraints=[
                PolicyConstraint(key="environment", equals="development")
            ],
            priority=20
        ),

        # Developer: Production read-only
        PolicyRule(
            name="dev_production_readonly",
            effect=PolicyEffect.ALLOW,
            actions=["data:read", "data:list"],
            resources=["*"],
            subjects=["role:developer"],
            constraints=[
                PolicyConstraint(key="environment", equals="production")
            ],
            priority=21
        ),

        # Analyst: Read-only everywhere
        PolicyRule(
            name="analyst_readonly",
            effect=PolicyEffect.ALLOW,
            actions=["data:read", "data:list"],
            resources=["dataset://*"],
            subjects=["role:analyst"],
            priority=30
        ),

        # Guest: Public data only
        PolicyRule(
            name="guest_public_only",
            effect=PolicyEffect.ALLOW,
            actions=["data:read"],
            resources=["dataset://public/*"],
            subjects=["role:guest"],
            priority=40
        )
    ]
)
```

### Attribute-Based Access Control (ABAC)

```python
# Access based on attributes beyond roles
abac_policy = PolicyRule(
    name="clearance_based_access",
    description="Allow access based on security clearance",
    effect=PolicyEffect.ALLOW,
    actions=["data:read"],
    resources=["dataset://classified/*"],
    subjects=[],  # Check via constraints instead
    constraints=[
        PolicyConstraint(key="subject.attributes.clearance_level", any_of=["top_secret", "secret"]),
        PolicyConstraint(key="subject.attributes.background_check", equals=True),
        PolicyConstraint(key="subject.attributes.training_complete", equals=True)
    ],
    priority=10
)

# Usage:
request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        roles=["analyst"],
        attributes={
            "clearance_level": "secret",
            "background_check": True,
            "training_complete": True,
            "department": "intelligence"
        }
    ),
    action="data:read",
    resource="dataset://classified/operation_x"
)
```

### Multi-Tenant Isolation

```python
# Ensure tenants can only access their own resources
tenant_isolation_rules = [
    # Block cross-tenant access
    PolicyRule(
        name="block_cross_tenant",
        description="Deny access to resources from other tenants",
        effect=PolicyEffect.DENY,
        actions=["*"],
        resources=["*"],
        constraints=[
            # Requires custom logic: check if subject.tenant_id != resource.tenant_id
            PolicyConstraint(key="cross_tenant_access", equals=True)
        ],
        priority=1
    ),

    # Allow same-tenant access
    PolicyRule(
        name="allow_same_tenant",
        effect=PolicyEffect.ALLOW,
        actions=["*"],
        resources=["*"],
        constraints=[
            PolicyConstraint(key="cross_tenant_access", equals=False)
        ],
        priority=10
    )
]

# Helper to detect cross-tenant access:
def is_cross_tenant_access(subject: PolicySubject, resource: str) -> bool:
    """Check if subject is accessing resource from different tenant."""
    subject_tenant = subject.tags.get("tenant_id")

    # Extract tenant from resource (e.g., "dataset://tenant123/data")
    match = re.match(r"dataset://([^/]+)/", resource)
    resource_tenant = match.group(1) if match else None

    return subject_tenant != resource_tenant

# Apply in request:
request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        tags={"tenant_id": "tenant_a"}
    ),
    action="data:read",
    resource="dataset://tenant_b/sales",
    context={
        "cross_tenant_access": is_cross_tenant_access(subject, "dataset://tenant_b/sales")
    }
)
```

## Compliance Policies

Compliance policies enforce regulatory requirements like GDPR, HIPAA, PCI-DSS.

### GDPR Compliance

```python
gdpr_policy_set = PolicySet(
    name="gdpr_compliance",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Data residency: EU data stays in EU
        PolicyRule(
            name="eu_data_residency",
            description="GDPR: EU citizen data must stay in EU regions",
            effect=PolicyEffect.DENY,
            actions=["data:export", "data:transfer"],
            resources=["dataset://eu_citizens/*"],
            constraints=[
                PolicyConstraint(
                    key="destination_region",
                    not_any_of=["eu-west-1", "eu-central-1", "eu-north-1"]
                )
            ],
            priority=1
        ),

        # Right to erasure
        PolicyRule(
            name="gdpr_right_to_erasure",
            description="GDPR: Allow data deletion for erasure requests",
            effect=PolicyEffect.ALLOW,
            actions=["data:delete"],
            resources=["dataset://user_data/*"],
            constraints=[
                PolicyConstraint(key="erasure_request_verified", equals=True)
            ],
            priority=5
        ),

        # Purpose limitation
        PolicyRule(
            name="gdpr_purpose_limitation",
            description="GDPR: Deny access without documented purpose",
            effect=PolicyEffect.DENY,
            actions=["data:read", "data:process"],
            resources=["dataset://personal_data/*"],
            constraints=[
                PolicyConstraint(key="processing_purpose", exists=False)
            ],
            priority=2
        ),

        # Consent verification
        PolicyRule(
            name="gdpr_consent_required",
            description="GDPR: Require consent for personal data processing",
            effect=PolicyEffect.DENY,
            actions=["data:process"],
            resources=["dataset://personal_data/*"],
            constraints=[
                PolicyConstraint(key="user_consent_verified", equals=False)
            ],
            priority=3
        )
    ]
)
```

### HIPAA Compliance

```python
hipaa_policy_set = PolicySet(
    name="hipaa_compliance",
    default_effect=PolicyEffect.DENY,
    rules=[
        # PHI access requires approval
        PolicyRule(
            name="phi_access_approval",
            description="HIPAA: All PHI access requires approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:read", "data:export"],
            resources=["dataset://phi/*"],
            constraints=[
                PolicyConstraint(key="medical_necessity_documented", equals=True)
            ],
            priority=1
        ),

        # Minimum necessary principle
        PolicyRule(
            name="minimum_necessary",
            description="HIPAA: Deny bulk PHI exports",
            effect=PolicyEffect.DENY,
            actions=["data:export"],
            resources=["dataset://phi/*"],
            constraints=[
                PolicyConstraint(key="record_count", exists=True)
                # Additional logic: check if record_count > threshold
            ],
            priority=2
        ),

        # Audit logging required
        PolicyRule(
            name="phi_audit_required",
            description="HIPAA: Block PHI access without audit logging",
            effect=PolicyEffect.DENY,
            actions=["data:*"],
            resources=["dataset://phi/*"],
            constraints=[
                PolicyConstraint(key="audit_logging_enabled", equals=False)
            ],
            priority=1
        ),

        # Training requirement
        PolicyRule(
            name="hipaa_training_required",
            description="HIPAA: Users must complete training",
            effect=PolicyEffect.DENY,
            actions=["data:*"],
            resources=["dataset://phi/*"],
            constraints=[
                PolicyConstraint(key="subject.attributes.hipaa_training_complete", equals=False)
            ],
            priority=1
        )
    ]
)
```

### PCI-DSS Compliance

```python
pci_policy_set = PolicySet(
    name="pci_dss_compliance",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Card data encryption required
        PolicyRule(
            name="card_data_encryption",
            description="PCI-DSS: Card data must be encrypted",
            effect=PolicyEffect.DENY,
            actions=["data:write", "data:store"],
            resources=["dataset://card_data/*"],
            constraints=[
                PolicyConstraint(key="encryption_enabled", equals=False)
            ],
            priority=1
        ),

        # Access logging required
        PolicyRule(
            name="card_data_logging",
            description="PCI-DSS: All card data access must be logged",
            effect=PolicyEffect.DENY,
            actions=["data:read", "data:write"],
            resources=["dataset://card_data/*"],
            constraints=[
                PolicyConstraint(key="access_logging_enabled", equals=False)
            ],
            priority=1
        ),

        # Network segmentation
        PolicyRule(
            name="pci_network_segmentation",
            description="PCI-DSS: Card data access only from secure network",
            effect=PolicyEffect.DENY,
            actions=["data:*"],
            resources=["dataset://card_data/*"],
            constraints=[
                PolicyConstraint(key="network_zone", not_any_of=["pci_zone", "secure_zone"])
            ],
            priority=1
        )
    ]
)
```

## Cost Policies

Cost policies enforce budget limits and prevent expensive operations.

### Budget Caps

```python
# Deny operations exceeding budget
budget_cap_policy = PolicyRule(
    name="monthly_budget_cap",
    description="Deny operations exceeding monthly budget",
    effect=PolicyEffect.DENY,
    actions=["agent:model_invoke", "agent:tool_execute"],
    resources=["*"],
    constraints=[
        # Requires tracking cumulative monthly cost
        PolicyConstraint(key="monthly_budget_exceeded", equals=True)
    ],
    priority=1
)

# Usage with cost tracking:
class CostTracker:
    """Track monthly spending per user."""

    def __init__(self):
        self.monthly_costs = {}  # user_id -> {month: cost}

    def add_cost(self, user_id: str, cost: float):
        month = datetime.now().strftime("%Y-%m")
        if user_id not in self.monthly_costs:
            self.monthly_costs[user_id] = {}
        self.monthly_costs[user_id][month] = self.monthly_costs[user_id].get(month, 0) + cost

    def check_budget(self, user_id: str, budget_limit: float) -> bool:
        month = datetime.now().strftime("%Y-%m")
        current_cost = self.monthly_costs.get(user_id, {}).get(month, 0)
        return current_cost >= budget_limit

tracker = CostTracker()

# Before operation:
request = PolicyRequest(
    subject=PolicySubject(identifier="user-123"),
    action="agent:model_invoke",
    resource="model://gpt-4",
    context={
        "monthly_budget_exceeded": tracker.check_budget("user-123", budget_limit=100.0)
    }
)
```

### Per-Operation Cost Limits

```python
# Require approval for expensive operations
expensive_operation_policy = PolicyRule(
    name="high_cost_approval",
    description="Require approval for operations > $1",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["agent:model_invoke", "agent:tool_execute"],
    resources=["*"],
    constraints=[
        # Requires cost estimation
        PolicyConstraint(key="estimated_cost_high", equals=True)
    ],
    priority=5
)

# Cost estimation helper:
MODEL_COSTS = {
    "gpt-4": {"input": 30.0, "output": 60.0},  # per 1M tokens (USD)
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-opus": {"input": 15.0, "output": 75.0},
    "claude-sonnet": {"input": 3.0, "output": 15.0},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD."""
    costs = MODEL_COSTS.get(model, {"input": 5.0, "output": 15.0})
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    return input_cost + output_cost

# Apply in request:
estimated_cost = estimate_cost("gpt-4", input_tokens=2000, output_tokens=500)

request = PolicyRequest(
    subject=PolicySubject(identifier="user-123"),
    action="agent:model_invoke",
    resource="model://gpt-4",
    context={
        "estimated_cost": estimated_cost,
        "estimated_cost_high": estimated_cost > 1.0
    }
)
```

### Tiered Cost Controls

```python
# Different cost limits for different roles
tiered_cost_policies = [
    # Intern: $10/month
    PolicyRule(
        name="intern_cost_limit",
        effect=PolicyEffect.DENY,
        actions=["agent:*"],
        resources=["*"],
        subjects=["role:intern"],
        constraints=[
            PolicyConstraint(key="monthly_cost_exceeds_10", equals=True)
        ],
        priority=5
    ),

    # Developer: $100/month
    PolicyRule(
        name="developer_cost_limit",
        effect=PolicyEffect.DENY,
        actions=["agent:*"],
        resources=["*"],
        subjects=["role:developer"],
        constraints=[
            PolicyConstraint(key="monthly_cost_exceeds_100", equals=True)
        ],
        priority=6
    ),

    # Manager: $1000/month
    PolicyRule(
        name="manager_cost_limit",
        effect=PolicyEffect.DENY,
        actions=["agent:*"],
        resources=["*"],
        subjects=["role:manager"],
        constraints=[
            PolicyConstraint(key="monthly_cost_exceeds_1000", equals=True)
        ],
        priority=7
    )
]
```

## Approval Policies

Approval policies define which operations require human oversight.

### Production Changes

```python
# Require approval for all production changes
production_approval_policy = PolicyRule(
    name="production_changes_approval",
    description="All production changes require manager approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["data:write", "data:delete", "graph:deploy"],
    resources=["*production*"],
    priority=10
)
```

### Data Deletion

```python
# Require approval for data deletion
deletion_approval_policy = PolicyRule(
    name="deletion_requires_approval",
    description="Data deletion requires dual approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    actions=["data:delete"],
    resources=["dataset://*"],
    constraints=[
        # Only require approval for non-temporary data
        PolicyConstraint(key="data_type", not_any_of=["temporary", "cache"])
    ],
    priority=5
)
```

### High-Risk Operations

```python
# Comprehensive high-risk approval policy
high_risk_approval_set = PolicySet(
    name="high_risk_approvals",
    default_effect=PolicyEffect.ALLOW,
    rules=[
        # Bulk operations
        PolicyRule(
            name="bulk_operation_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:delete", "data:update"],
            resources=["*"],
            constraints=[
                PolicyConstraint(key="record_count", exists=True)
                # Logic: record_count > 1000
            ],
            priority=10
        ),

        # Production deployments
        PolicyRule(
            name="production_deployment_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["graph:deploy", "graph:update"],
            resources=["graph://production/*"],
            priority=10
        ),

        # External API calls
        PolicyRule(
            name="external_api_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["agent:tool_execute"],
            resources=["tool://http_*", "tool://api_*"],
            constraints=[
                PolicyConstraint(key="external_domain", equals=True)
            ],
            priority=10
        ),

        # Schema changes
        PolicyRule(
            name="schema_change_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:alter_schema", "data:drop_table"],
            resources=["*"],
            priority=5
        )
    ]
)
```

## Custom Policy Types

Create custom policy types for your specific use cases.

### Time-Based Access

```python
from datetime import datetime, time

def is_business_hours() -> bool:
    """Check if current time is during business hours (9 AM - 5 PM, Mon-Fri)."""
    now = datetime.now()
    return (
        now.weekday() < 5  # Monday = 0, Friday = 4
        and time(9, 0) <= now.time() <= time(17, 0)
    )

business_hours_policy = PolicyRule(
    name="business_hours_only",
    description="Sensitive operations only during business hours",
    effect=PolicyEffect.DENY,
    actions=["data:export", "data:delete"],
    resources=["dataset://sensitive/*"],
    constraints=[
        PolicyConstraint(key="is_business_hours", equals=False)
    ],
    priority=5
)

# Apply in request:
request = PolicyRequest(
    subject=subject,
    action="data:export",
    resource="dataset://sensitive/customer_data",
    context={"is_business_hours": is_business_hours()}
)
```

### Geographic Restrictions

```python
# Block access from certain regions
geographic_policy = PolicyRule(
    name="block_embargoed_countries",
    description="Block access from embargoed countries",
    effect=PolicyEffect.DENY,
    actions=["*"],
    resources=["*"],
    constraints=[
        PolicyConstraint(
            key="subject.attributes.country_code",
            any_of=["KP", "IR", "SY", "CU"]  # Embargoed country codes
        )
    ],
    priority=1
)

# Usage:
def get_country_from_ip(ip_address: str) -> str:
    """Get country code from IP address using GeoIP."""
    # Implementation using GeoIP library
    pass

request = PolicyRequest(
    subject=PolicySubject(
        identifier="user-123",
        attributes={"country_code": get_country_from_ip(request_ip)}
    ),
    action="data:read",
    resource="dataset://classified/intelligence"
)
```

### Data Classification

```python
# Policy based on data classification levels
classification_policy_set = PolicySet(
    name="data_classification",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Public: Everyone
        PolicyRule(
            name="public_data_access",
            effect=PolicyEffect.ALLOW,
            actions=["data:read"],
            resources=["*"],
            constraints=[
                PolicyConstraint(key="data_classification", equals="public")
            ],
            priority=40
        ),

        # Internal: Employees only
        PolicyRule(
            name="internal_data_access",
            effect=PolicyEffect.ALLOW,
            actions=["data:read"],
            resources=["*"],
            subjects=["role:employee"],
            constraints=[
                PolicyConstraint(key="data_classification", equals="internal")
            ],
            priority=30
        ),

        # Confidential: Specific roles with approval
        PolicyRule(
            name="confidential_data_access",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:read"],
            resources=["*"],
            subjects=["role:manager", "role:executive"],
            constraints=[
                PolicyConstraint(key="data_classification", equals="confidential")
            ],
            priority=20
        ),

        # Secret: Admins only with strict controls
        PolicyRule(
            name="secret_data_access",
            effect=PolicyEffect.ALLOW,
            actions=["data:read"],
            resources=["*"],
            subjects=["role:admin"],
            constraints=[
                PolicyConstraint(key="data_classification", equals="secret"),
                PolicyConstraint(key="subject.attributes.clearance_level", equals="top_secret"),
                PolicyConstraint(key="audit_logging_enabled", equals=True)
            ],
            priority=10
        )
    ]
)
```

## Combining Policies

Real-world systems often combine multiple policy types:

```python
from spark.governance import PolicyEngine, PolicySet, PolicyRule, PolicyEffect

# Comprehensive enterprise policy set
enterprise_policy_set = PolicySet(
    name="enterprise_governance",
    default_effect=PolicyEffect.DENY,
    rules=[
        # Security (highest priority)
        PolicyRule(
            name="block_dangerous_tools",
            effect=PolicyEffect.DENY,
            actions=["agent:tool_execute"],
            resources=["tool://shell_execute", "tool://eval_code"],
            priority=1
        ),

        # Compliance
        PolicyRule(
            name="gdpr_data_residency",
            effect=PolicyEffect.DENY,
            actions=["data:export"],
            resources=["dataset://eu_citizens/*"],
            constraints=[
                PolicyConstraint(key="destination_region", not_any_of=["eu-west-1", "eu-central-1"])
            ],
            priority=5
        ),

        # Cost control
        PolicyRule(
            name="budget_exceeded",
            effect=PolicyEffect.DENY,
            actions=["agent:*"],
            resources=["*"],
            constraints=[
                PolicyConstraint(key="monthly_budget_exceeded", equals=True)
            ],
            priority=10
        ),

        # Approval for high-risk
        PolicyRule(
            name="production_approval",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["data:write", "data:delete", "graph:deploy"],
            resources=["*production*"],
            priority=15
        ),

        # RBAC - Admin
        PolicyRule(
            name="admin_access",
            effect=PolicyEffect.ALLOW,
            actions=["*"],
            resources=["*"],
            subjects=["role:admin"],
            constraints=[
                PolicyConstraint(key="monthly_budget_exceeded", equals=False)
            ],
            priority=20
        ),

        # RBAC - Developer (dev environment)
        PolicyRule(
            name="dev_environment",
            effect=PolicyEffect.ALLOW,
            actions=["data:*", "agent:*", "node:execute"],
            resources=["*"],
            subjects=["role:developer"],
            constraints=[
                PolicyConstraint(key="environment", equals="development")
            ],
            priority=30
        ),

        # RBAC - Analyst (read-only)
        PolicyRule(
            name="analyst_readonly",
            effect=PolicyEffect.ALLOW,
            actions=["data:read", "data:list"],
            resources=["dataset://*"],
            subjects=["role:analyst"],
            priority=40
        )
    ]
)

# Create engine
engine = PolicyEngine(enterprise_policy_set)

# Use in production
from spark.graphs import Graph

graph = Graph(
    start=my_node,
    policy_set=enterprise_policy_set
)
```

## Next Steps

- [Approval Workflows](approvals.md) - Implement human approval for REQUIRE_APPROVAL decisions
- [Governance Patterns](patterns.md) - Enterprise-grade governance architectures
- [Governance Overview](overview.md) - Core concepts and architecture
