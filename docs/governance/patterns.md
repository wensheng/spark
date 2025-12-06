---
title: Governance Patterns
parent: Governance
nav_order: 4
---
# Governance Patterns

This guide presents enterprise-grade governance patterns for production deployments. These patterns demonstrate how to combine policies, approvals, and organizational controls into comprehensive governance frameworks.

## Table of Contents

- [Enterprise Governance](#enterprise-governance)
- [Multi-Tenant Isolation](#multi-tenant-isolation)
- [Budget Enforcement](#budget-enforcement)
- [Security Hardening](#security-hardening)
- [Compliance Automation](#compliance-automation)
- [Audit Trail Generation](#audit-trail-generation)
- [Deployment Patterns](#deployment-patterns)

## Enterprise Governance

A comprehensive governance framework for enterprise deployments combining security, compliance, cost control, and operational policies.

### Architecture

```python
from spark.governance import (
    PolicyEngine, PolicySet, PolicyRule, PolicyEffect, PolicyConstraint
)

class EnterpriseGovernanceFramework:
    """Comprehensive enterprise governance framework."""

    def __init__(self):
        self.policy_set = self._build_policy_set()
        self.engine = PolicyEngine(self.policy_set)

    def _build_policy_set(self) -> PolicySet:
        """Build comprehensive enterprise policy set."""
        return PolicySet(
            name="enterprise_governance",
            description="Complete enterprise governance framework",
            default_effect=PolicyEffect.DENY,  # Deny by default for security
            rules=[
                # Layer 1: Security (Priority 1-10)
                *self._security_policies(),

                # Layer 2: Compliance (Priority 11-30)
                *self._compliance_policies(),

                # Layer 3: Cost Control (Priority 31-50)
                *self._cost_policies(),

                # Layer 4: Operational Approvals (Priority 51-70)
                *self._approval_policies(),

                # Layer 5: Access Control (Priority 71-100)
                *self._access_control_policies(),

                # Layer 6: Permissive Defaults (Priority 101+)
                *self._permissive_policies()
            ]
        )

    def _security_policies(self) -> list[PolicyRule]:
        """Critical security policies - highest priority."""
        return [
            PolicyRule(
                name="block_dangerous_tools",
                description="Block inherently dangerous operations",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=[
                    "tool://shell_execute",
                    "tool://eval_code",
                    "tool://exec_python",
                    "tool://system_command"
                ],
                priority=1
            ),
            PolicyRule(
                name="block_sql_injection",
                description="Block potential SQL injection attempts",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=["tool://sql_*", "tool://db_*"],
                constraints=[
                    PolicyConstraint(key="contains_sql_injection", equals=True)
                ],
                priority=2
            ),
            PolicyRule(
                name="block_unauthorized_external_apis",
                description="Block unapproved external API calls",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=["tool://http_*"],
                constraints=[
                    PolicyConstraint(key="domain_approved", equals=False)
                ],
                priority=3
            )
        ]

    def _compliance_policies(self) -> list[PolicyRule]:
        """Regulatory compliance policies."""
        return [
            PolicyRule(
                name="gdpr_data_residency",
                description="GDPR: EU data stays in EU",
                effect=PolicyEffect.DENY,
                actions=["data:export", "data:transfer"],
                resources=["dataset://eu_citizens/*"],
                constraints=[
                    PolicyConstraint(
                        key="destination_region",
                        not_any_of=["eu-west-1", "eu-central-1", "eu-north-1"]
                    )
                ],
                priority=11
            ),
            PolicyRule(
                name="hipaa_phi_approval",
                description="HIPAA: PHI access requires approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                actions=["data:read", "data:export"],
                resources=["dataset://phi/*"],
                constraints=[
                    PolicyConstraint(key="medical_necessity_documented", equals=True),
                    PolicyConstraint(key="subject.attributes.hipaa_training", equals=True)
                ],
                priority=12
            ),
            PolicyRule(
                name="pci_card_data_encryption",
                description="PCI-DSS: Card data must be encrypted",
                effect=PolicyEffect.DENY,
                actions=["data:write", "data:store"],
                resources=["dataset://card_data/*"],
                constraints=[
                    PolicyConstraint(key="encryption_enabled", equals=False)
                ],
                priority=13
            )
        ]

    def _cost_policies(self) -> list[PolicyRule]:
        """Cost control policies."""
        return [
            PolicyRule(
                name="monthly_budget_exceeded",
                description="Block operations when monthly budget exceeded",
                effect=PolicyEffect.DENY,
                actions=["agent:model_invoke", "agent:tool_execute"],
                resources=["*"],
                constraints=[
                    PolicyConstraint(key="monthly_budget_exceeded", equals=True)
                ],
                priority=31
            ),
            PolicyRule(
                name="expensive_model_approval",
                description="Expensive models require manager approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                actions=["agent:model_invoke"],
                resources=["model://gpt-4", "model://claude-opus*"],
                constraints=[
                    PolicyConstraint(key="estimated_cost", exists=True)
                ],
                priority=32
            )
        ]

    def _approval_policies(self) -> list[PolicyRule]:
        """Operational approval requirements."""
        return [
            PolicyRule(
                name="production_changes_approval",
                description="All production changes require approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                actions=["data:write", "data:delete", "graph:deploy"],
                resources=["*production*"],
                constraints=[
                    PolicyConstraint(key="environment", equals="production")
                ],
                priority=51
            ),
            PolicyRule(
                name="bulk_deletion_approval",
                description="Bulk deletions require approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                actions=["data:delete"],
                resources=["*"],
                constraints=[
                    PolicyConstraint(key="record_count_high", equals=True)
                ],
                priority=52
            )
        ]

    def _access_control_policies(self) -> list[PolicyRule]:
        """Role-based access control."""
        return [
            PolicyRule(
                name="admin_full_access",
                description="Admins have full access (budget permitting)",
                effect=PolicyEffect.ALLOW,
                actions=["*"],
                resources=["*"],
                subjects=["role:admin"],
                constraints=[
                    PolicyConstraint(key="monthly_budget_exceeded", equals=False)
                ],
                priority=71
            ),
            PolicyRule(
                name="developer_dev_env",
                description="Developers have full access in dev",
                effect=PolicyEffect.ALLOW,
                actions=["*"],
                resources=["*"],
                subjects=["role:developer"],
                constraints=[
                    PolicyConstraint(key="environment", equals="development")
                ],
                priority=81
            ),
            PolicyRule(
                name="developer_prod_readonly",
                description="Developers read-only in production",
                effect=PolicyEffect.ALLOW,
                actions=["data:read", "data:list"],
                resources=["*"],
                subjects=["role:developer"],
                constraints=[
                    PolicyConstraint(key="environment", equals="production")
                ],
                priority=82
            ),
            PolicyRule(
                name="analyst_readonly",
                description="Analysts have read-only access",
                effect=PolicyEffect.ALLOW,
                actions=["data:read", "data:list"],
                resources=["dataset://*"],
                subjects=["role:analyst"],
                priority=91
            )
        ]

    def _permissive_policies(self) -> list[PolicyRule]:
        """Permissive policies for safe operations."""
        return [
            PolicyRule(
                name="allow_safe_tools",
                description="Allow safe read-only tools",
                effect=PolicyEffect.ALLOW,
                actions=["agent:tool_execute"],
                resources=[
                    "tool://web_search",
                    "tool://calculator",
                    "tool://date_time",
                    "tool://weather_api"
                ],
                priority=101
            ),
            PolicyRule(
                name="allow_public_data_read",
                description="Allow public data reading",
                effect=PolicyEffect.ALLOW,
                actions=["data:read"],
                resources=["dataset://public/*"],
                priority=102
            )
        ]

# Usage
framework = EnterpriseGovernanceFramework()

# Apply to graphs
from spark.graphs import Graph

graph = Graph(
    start=my_node,
    policy_set=framework.policy_set
)

# Apply to agents
from spark.agents import Agent, AgentConfig

config = AgentConfig(
    model=my_model,
    tools=my_tools,
    policy_set=framework.policy_set
)
agent = Agent(config=config)
```

### Layered Defense

The enterprise framework uses **defense in depth** with multiple policy layers:

1. **Security Layer**: Blocks inherently dangerous operations
2. **Compliance Layer**: Enforces regulatory requirements
3. **Cost Layer**: Prevents budget overruns
4. **Approval Layer**: Requires human oversight for critical operations
5. **Access Control Layer**: Role-based permissions
6. **Permissive Layer**: Explicitly allows safe operations

Each layer has a priority range, ensuring critical security policies always evaluate first.

## Multi-Tenant Isolation

Ensure complete isolation between tenants in a multi-tenant SaaS environment.

### Tenant Isolation Pattern

```python
from spark.governance import PolicySet, PolicyRule, PolicyEffect, PolicyConstraint
import re

class TenantIsolationGovernance:
    """Complete tenant isolation governance."""

    def __init__(self):
        self.policy_set = PolicySet(
            name="tenant_isolation",
            description="Enforce complete tenant isolation",
            default_effect=PolicyEffect.DENY,
            rules=[
                # Highest priority: Block cross-tenant access
                PolicyRule(
                    name="block_cross_tenant_access",
                    description="Block any cross-tenant resource access",
                    effect=PolicyEffect.DENY,
                    actions=["*"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="cross_tenant_access", equals=True)
                    ],
                    priority=1
                ),

                # Allow same-tenant access
                PolicyRule(
                    name="allow_same_tenant",
                    description="Allow access within same tenant",
                    effect=PolicyEffect.ALLOW,
                    actions=["*"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="cross_tenant_access", equals=False),
                        PolicyConstraint(key="tenant_verified", equals=True)
                    ],
                    priority=10
                ),

                # Require approval for tenant admin actions
                PolicyRule(
                    name="tenant_admin_approval",
                    description="Tenant admin actions require approval",
                    effect=PolicyEffect.REQUIRE_APPROVAL,
                    actions=["tenant:delete", "tenant:transfer"],
                    resources=["tenant://*"],
                    subjects=["role:tenant_admin"],
                    priority=5
                )
            ]
        )

    @staticmethod
    def extract_tenant_id(resource: str) -> str | None:
        """Extract tenant ID from resource identifier."""
        # Examples:
        # "dataset://tenant123/sales" -> "tenant123"
        # "graph://tenant456/workflows/prod" -> "tenant456"
        match = re.match(r"[^:]+://([^/]+)/", resource)
        return match.group(1) if match else None

    @staticmethod
    def check_cross_tenant_access(subject_tenant: str, resource: str) -> bool:
        """Check if request is accessing resource from different tenant."""
        resource_tenant = TenantIsolationGovernance.extract_tenant_id(resource)

        # If no tenant in resource, consider it cross-tenant for safety
        if not resource_tenant:
            return True

        return subject_tenant != resource_tenant

    @staticmethod
    def prepare_request_context(subject, action: str, resource: str) -> dict:
        """Prepare context with tenant isolation checks."""
        subject_tenant = subject.tags.get("tenant_id")

        if not subject_tenant:
            # No tenant ID = deny
            return {
                "cross_tenant_access": True,
                "tenant_verified": False,
                "error": "Subject missing tenant_id"
            }

        cross_tenant = TenantIsolationGovernance.check_cross_tenant_access(
            subject_tenant, resource
        )

        return {
            "cross_tenant_access": cross_tenant,
            "tenant_verified": not cross_tenant,
            "subject_tenant": subject_tenant,
            "resource_tenant": TenantIsolationGovernance.extract_tenant_id(resource)
        }

# Usage in application
from spark.governance import PolicyEngine, PolicyRequest, PolicySubject

governance = TenantIsolationGovernance()
engine = PolicyEngine(governance.policy_set)

# Request from tenant A to access tenant B's data
subject = PolicySubject(
    identifier="user-123",
    roles=["developer"],
    tags={"tenant_id": "tenant_a"}
)

action = "data:read"
resource = "dataset://tenant_b/sales"  # Different tenant!

# Prepare context with tenant checks
context = governance.prepare_request_context(subject, action, resource)

# Create request
request = PolicyRequest(
    subject=subject,
    action=action,
    resource=resource,
    context=context
)

# This will be denied due to cross-tenant access
from spark.governance import PolicyViolationError

try:
    decision = engine.enforce(request)
except PolicyViolationError as e:
    print(f"Blocked: {e}")
    print(f"Rule: {e.decision.rule}")  # "block_cross_tenant_access"
```

### Tenant Resource Naming

Enforce consistent tenant resource naming:

```python
class TenantResourceNaming:
    """Enforce tenant-scoped resource naming."""

    @staticmethod
    def validate_resource_name(resource: str, tenant_id: str) -> tuple[bool, str]:
        """Validate that resource name includes tenant scope."""
        # All resources must start with tenant ID
        # Valid: "dataset://tenant123/..."
        # Invalid: "dataset://global/..."

        if not resource.startswith(f"dataset://{tenant_id}/") and \
           not resource.startswith(f"graph://{tenant_id}/") and \
           not resource.startswith(f"model://{tenant_id}/"):
            return False, f"Resource must be scoped to tenant {tenant_id}"

        return True, "OK"

# Integrate with policy
tenant_naming_policy = PolicyRule(
    name="enforce_tenant_resource_naming",
    description="Resources must be tenant-scoped",
    effect=PolicyEffect.DENY,
    actions=["data:create", "graph:create"],
    resources=["*"],
    constraints=[
        PolicyConstraint(key="resource_naming_valid", equals=False)
    ],
    priority=2
)

# Usage
def prepare_context(subject, resource):
    tenant_id = subject.tags.get("tenant_id")
    valid, message = TenantResourceNaming.validate_resource_name(resource, tenant_id)

    return {
        "resource_naming_valid": valid,
        "validation_message": message
    }
```

## Budget Enforcement

Comprehensive cost control with per-user, per-team, and organization-level budgets.

### Hierarchical Budget System

```python
from typing import Dict
from datetime import datetime
import asyncio

class HierarchicalBudgetEnforcement:
    """Multi-level budget tracking and enforcement."""

    def __init__(self):
        # Budget limits (USD per month)
        self.user_limits = {}  # user_id -> limit
        self.team_limits = {}  # team_id -> limit
        self.org_limit = 10000.0

        # Current spending
        self.user_spending = {}  # user_id -> {month: amount}
        self.team_spending = {}  # team_id -> {month: amount}
        self.org_spending = {}  # {month: amount}

        # Policy set
        self.policy_set = PolicySet(
            name="hierarchical_budgets",
            default_effect=PolicyEffect.ALLOW,
            rules=[
                # Organization budget (highest priority)
                PolicyRule(
                    name="org_budget_exceeded",
                    description="Organization monthly budget exceeded",
                    effect=PolicyEffect.DENY,
                    actions=["agent:model_invoke", "agent:tool_execute"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="org_budget_exceeded", equals=True)
                    ],
                    priority=1
                ),

                # Team budget
                PolicyRule(
                    name="team_budget_exceeded",
                    description="Team monthly budget exceeded",
                    effect=PolicyEffect.DENY,
                    actions=["agent:model_invoke", "agent:tool_execute"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="team_budget_exceeded", equals=True)
                    ],
                    priority=2
                ),

                # User budget
                PolicyRule(
                    name="user_budget_exceeded",
                    description="User monthly budget exceeded",
                    effect=PolicyEffect.DENY,
                    actions=["agent:model_invoke", "agent:tool_execute"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="user_budget_exceeded", equals=True)
                    ],
                    priority=3
                ),

                # High-cost operation approval
                PolicyRule(
                    name="high_cost_approval",
                    description="Operations > $5 require approval",
                    effect=PolicyEffect.REQUIRE_APPROVAL,
                    actions=["agent:model_invoke"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="estimated_cost_high", equals=True)
                    ],
                    priority=10
                )
            ]
        )

    def set_user_limit(self, user_id: str, limit: float):
        """Set monthly budget limit for user."""
        self.user_limits[user_id] = limit

    def set_team_limit(self, team_id: str, limit: float):
        """Set monthly budget limit for team."""
        self.team_limits[team_id] = limit

    def record_cost(self, user_id: str, team_id: str, cost: float):
        """Record cost against user, team, and org budgets."""
        month = datetime.now().strftime("%Y-%m")

        # User
        if user_id not in self.user_spending:
            self.user_spending[user_id] = {}
        self.user_spending[user_id][month] = \
            self.user_spending[user_id].get(month, 0) + cost

        # Team
        if team_id not in self.team_spending:
            self.team_spending[team_id] = {}
        self.team_spending[team_id][month] = \
            self.team_spending[team_id].get(month, 0) + cost

        # Org
        self.org_spending[month] = self.org_spending.get(month, 0) + cost

    def check_budgets(self, user_id: str, team_id: str) -> Dict[str, bool]:
        """Check if any budget limits are exceeded."""
        month = datetime.now().strftime("%Y-%m")

        # User budget
        user_spent = self.user_spending.get(user_id, {}).get(month, 0)
        user_limit = self.user_limits.get(user_id, float('inf'))
        user_exceeded = user_spent >= user_limit

        # Team budget
        team_spent = self.team_spending.get(team_id, {}).get(month, 0)
        team_limit = self.team_limits.get(team_id, float('inf'))
        team_exceeded = team_spent >= team_limit

        # Org budget
        org_spent = self.org_spending.get(month, 0)
        org_exceeded = org_spent >= self.org_limit

        return {
            "user_budget_exceeded": user_exceeded,
            "team_budget_exceeded": team_exceeded,
            "org_budget_exceeded": org_exceeded,
            "user_spent": user_spent,
            "user_limit": user_limit,
            "team_spent": team_spent,
            "team_limit": team_limit,
            "org_spent": org_spent,
            "org_limit": self.org_limit
        }

    def prepare_request_context(
        self,
        user_id: str,
        team_id: str,
        estimated_cost: float
    ) -> dict:
        """Prepare context with budget checks."""
        budget_status = self.check_budgets(user_id, team_id)

        return {
            **budget_status,
            "estimated_cost": estimated_cost,
            "estimated_cost_high": estimated_cost > 5.0
        }

# Usage
budget_system = HierarchicalBudgetEnforcement()

# Set budget limits
budget_system.set_user_limit("user-123", limit=100.0)  # $100/month per user
budget_system.set_team_limit("team-platform", limit=1000.0)  # $1000/month per team
# Org limit is $10,000/month (set in __init__)

# Before expensive operation
user_id = "user-123"
team_id = "team-platform"
estimated_cost = 2.50

context = budget_system.prepare_request_context(user_id, team_id, estimated_cost)

request = PolicyRequest(
    subject=PolicySubject(
        identifier=user_id,
        attributes={"team_id": team_id}
    ),
    action="agent:model_invoke",
    resource="model://gpt-4",
    context=context
)

# Enforce budget policy
engine = PolicyEngine(budget_system.policy_set)
try:
    decision = engine.enforce(request)
    # Operation allowed, record cost after execution
    actual_cost = 2.35
    budget_system.record_cost(user_id, team_id, actual_cost)
except PolicyViolationError as e:
    print(f"Budget exceeded: {e.decision.reason}")
```

### Budget Alerts

```python
class BudgetAlertSystem:
    """Send alerts when budgets approach limits."""

    def __init__(self, budget_system: HierarchicalBudgetEnforcement):
        self.budget_system = budget_system
        self.alert_thresholds = [0.8, 0.9, 0.95]  # 80%, 90%, 95%
        self.alerts_sent = {}  # Track which alerts have been sent

    async def check_and_alert(self, user_id: str, team_id: str):
        """Check budget status and send alerts if thresholds crossed."""
        status = self.budget_system.check_budgets(user_id, team_id)

        # User budget alert
        if status["user_limit"] != float('inf'):
            user_pct = status["user_spent"] / status["user_limit"]
            await self._send_alert_if_needed(
                f"user_{user_id}",
                user_pct,
                f"User {user_id}",
                status["user_spent"],
                status["user_limit"]
            )

        # Team budget alert
        if status["team_limit"] != float('inf'):
            team_pct = status["team_spent"] / status["team_limit"]
            await self._send_alert_if_needed(
                f"team_{team_id}",
                team_pct,
                f"Team {team_id}",
                status["team_spent"],
                status["team_limit"]
            )

        # Org budget alert
        org_pct = status["org_spent"] / status["org_limit"]
        await self._send_alert_if_needed(
            "org",
            org_pct,
            "Organization",
            status["org_spent"],
            status["org_limit"]
        )

    async def _send_alert_if_needed(
        self,
        entity: str,
        percentage: float,
        entity_name: str,
        spent: float,
        limit: float
    ):
        """Send alert if threshold crossed and not already sent."""
        month = datetime.now().strftime("%Y-%m")
        key = f"{entity}_{month}"

        if key not in self.alerts_sent:
            self.alerts_sent[key] = set()

        for threshold in self.alert_thresholds:
            if percentage >= threshold and threshold not in self.alerts_sent[key]:
                await self._send_alert(
                    entity_name,
                    percentage,
                    spent,
                    limit,
                    threshold
                )
                self.alerts_sent[key].add(threshold)

    async def _send_alert(
        self,
        entity_name: str,
        percentage: float,
        spent: float,
        limit: float,
        threshold: float
    ):
        """Send budget alert (implement your notification method)."""
        message = (
            f"Budget Alert: {entity_name} has used {percentage*100:.1f}% "
            f"of monthly budget (${spent:.2f} / ${limit:.2f})"
        )
        print(f"ALERT: {message}")
        # Send email, Slack, PagerDuty, etc.
```

## Security Hardening

Defense-in-depth security policies for production environments.

### Complete Security Policy Set

```python
class SecurityHardeningGovernance:
    """Complete security hardening policies."""

    def __init__(self):
        self.policy_set = PolicySet(
            name="security_hardening",
            description="Defense-in-depth security policies",
            default_effect=PolicyEffect.DENY,
            rules=[
                # Layer 1: Block dangerous operations
                *self._dangerous_operations(),

                # Layer 2: Injection prevention
                *self._injection_prevention(),

                # Layer 3: Data exfiltration prevention
                *self._exfiltration_prevention(),

                # Layer 4: Authentication & authorization
                *self._auth_policies(),

                # Layer 5: Audit & monitoring
                *self._audit_policies()
            ]
        )

    def _dangerous_operations(self) -> list[PolicyRule]:
        """Block inherently dangerous operations."""
        return [
            PolicyRule(
                name="block_code_execution",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=[
                    "tool://eval",
                    "tool://exec",
                    "tool://compile",
                    "tool://__import__"
                ],
                priority=1
            ),
            PolicyRule(
                name="block_shell_access",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=[
                    "tool://shell_execute",
                    "tool://system_command",
                    "tool://subprocess_*"
                ],
                priority=1
            ),
            PolicyRule(
                name="block_file_system_writes",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=[
                    "tool://write_file",
                    "tool://delete_file",
                    "tool://modify_file"
                ],
                constraints=[
                    PolicyConstraint(key="path_whitelisted", equals=False)
                ],
                priority=2
            )
        ]

    def _injection_prevention(self) -> list[PolicyRule]:
        """Prevent injection attacks."""
        return [
            PolicyRule(
                name="block_sql_injection",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=["tool://sql_*", "tool://db_*"],
                constraints=[
                    PolicyConstraint(key="contains_sql_injection", equals=True)
                ],
                priority=3
            ),
            PolicyRule(
                name="block_command_injection",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=["tool://*"],
                constraints=[
                    PolicyConstraint(key="contains_command_injection", equals=True)
                ],
                priority=3
            ),
            PolicyRule(
                name="block_path_traversal",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute", "data:read"],
                resources=["*"],
                constraints=[
                    PolicyConstraint(key="contains_path_traversal", equals=True)
                ],
                priority=3
            )
        ]

    def _exfiltration_prevention(self) -> list[PolicyRule]:
        """Prevent data exfiltration."""
        return [
            PolicyRule(
                name="block_large_exports",
                effect=PolicyEffect.DENY,
                actions=["data:export"],
                resources=["*"],
                constraints=[
                    PolicyConstraint(key="export_size_bytes", exists=True)
                    # Additional logic: size > threshold
                ],
                priority=5
            ),
            PolicyRule(
                name="block_external_apis",
                effect=PolicyEffect.DENY,
                actions=["agent:tool_execute"],
                resources=["tool://http_*", "tool://api_call"],
                constraints=[
                    PolicyConstraint(key="domain_whitelisted", equals=False)
                ],
                priority=5
            ),
            PolicyRule(
                name="require_approval_bulk_export",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                actions=["data:export"],
                resources=["dataset://*"],
                constraints=[
                    PolicyConstraint(key="record_count_high", equals=True)
                ],
                priority=6
            )
        ]

    def _auth_policies(self) -> list[PolicyRule]:
        """Authentication and authorization policies."""
        return [
            PolicyRule(
                name="require_mfa_for_sensitive",
                effect=PolicyEffect.DENY,
                actions=["data:delete", "data:export"],
                resources=["dataset://sensitive/*"],
                constraints=[
                    PolicyConstraint(key="subject.attributes.mfa_verified", equals=False)
                ],
                priority=10
            ),
            PolicyRule(
                name="require_recent_auth",
                effect=PolicyEffect.DENY,
                actions=["data:delete", "graph:deploy"],
                resources=["*production*"],
                constraints=[
                    PolicyConstraint(key="auth_age_minutes", exists=True)
                    # Additional logic: age > 15 minutes
                ],
                priority=11
            )
        ]

    def _audit_policies(self) -> list[PolicyRule]:
        """Auditing and monitoring policies."""
        return [
            PolicyRule(
                name="require_audit_logging",
                effect=PolicyEffect.DENY,
                actions=["data:*", "agent:*"],
                resources=["*"],
                constraints=[
                    PolicyConstraint(key="audit_logging_enabled", equals=False)
                ],
                priority=15
            )
        ]

# Security validation helpers
class SecurityValidation:
    """Security validation utilities."""

    @staticmethod
    def check_sql_injection(query: str) -> bool:
        """Detect potential SQL injection patterns."""
        import re
        patterns = [
            r";\s*DROP\s+TABLE",
            r";\s*DELETE\s+FROM",
            r"'\s*OR\s+'1'\s*=\s*'1",
            r"--\s*$",
            r"/\*.*\*/",
            r";\s*EXEC\s*\(",
            r"UNION\s+SELECT",
        ]
        return any(re.search(p, query, re.IGNORECASE) for p in patterns)

    @staticmethod
    def check_command_injection(command: str) -> bool:
        """Detect potential command injection patterns."""
        dangerous = [";", "|", "&", "`", "$", "(", ")", "<", ">", "\n", "\\"]
        return any(char in command for char in dangerous)

    @staticmethod
    def check_path_traversal(path: str) -> bool:
        """Detect path traversal attempts."""
        import os
        normalized = os.path.normpath(path)
        return ".." in normalized or normalized.startswith("/")

    @staticmethod
    def is_domain_whitelisted(domain: str, whitelist: list[str]) -> bool:
        """Check if domain is in whitelist."""
        return domain in whitelist

# Usage
security = SecurityHardeningGovernance()
engine = PolicyEngine(security.policy_set)

# Validate and prepare context
def prepare_security_context(action: str, resource: str, arguments: dict) -> dict:
    context = {
        "audit_logging_enabled": True,  # Always enable in production
    }

    # SQL injection check
    if "query" in arguments:
        context["contains_sql_injection"] = SecurityValidation.check_sql_injection(
            arguments["query"]
        )

    # Command injection check
    if "command" in arguments:
        context["contains_command_injection"] = SecurityValidation.check_command_injection(
            arguments["command"]
        )

    # Path traversal check
    if "path" in arguments:
        context["contains_path_traversal"] = SecurityValidation.check_path_traversal(
            arguments["path"]
        )

    # Domain whitelist check
    if "url" in arguments:
        from urllib.parse import urlparse
        domain = urlparse(arguments["url"]).netloc
        whitelist = ["api.example.com", "safe-api.com"]
        context["domain_whitelisted"] = SecurityValidation.is_domain_whitelisted(
            domain, whitelist
        )

    return context
```

## Compliance Automation

Automate compliance checks and reporting for multiple regulatory frameworks.

### Multi-Framework Compliance

```python
from enum import Enum
from typing import List, Dict
from dataclasses import dataclass

class ComplianceFramework(str, Enum):
    """Supported compliance frameworks."""
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    ISO27001 = "iso27001"

@dataclass
class ComplianceRequirement:
    """Single compliance requirement."""
    framework: ComplianceFramework
    requirement_id: str
    description: str
    policy_rule: PolicyRule
    evidence_needed: List[str]

class ComplianceAutomationSystem:
    """Automated compliance management."""

    def __init__(self):
        self.requirements = self._define_requirements()
        self.policy_set = self._build_policy_set()

    def _define_requirements(self) -> List[ComplianceRequirement]:
        """Define compliance requirements."""
        return [
            # GDPR
            ComplianceRequirement(
                framework=ComplianceFramework.GDPR,
                requirement_id="GDPR-Art6",
                description="Data processing requires legal basis",
                policy_rule=PolicyRule(
                    name="gdpr_legal_basis",
                    effect=PolicyEffect.DENY,
                    actions=["data:process"],
                    resources=["dataset://personal_data/*"],
                    constraints=[
                        PolicyConstraint(key="legal_basis", exists=False)
                    ],
                    priority=10
                ),
                evidence_needed=["legal_basis_documentation", "consent_records"]
            ),
            ComplianceRequirement(
                framework=ComplianceFramework.GDPR,
                requirement_id="GDPR-Art17",
                description="Right to erasure (right to be forgotten)",
                policy_rule=PolicyRule(
                    name="gdpr_right_to_erasure",
                    effect=PolicyEffect.ALLOW,
                    actions=["data:delete"],
                    resources=["dataset://personal_data/*"],
                    constraints=[
                        PolicyConstraint(key="erasure_request_verified", equals=True)
                    ],
                    priority=5
                ),
                evidence_needed=["erasure_request", "deletion_confirmation"]
            ),

            # HIPAA
            ComplianceRequirement(
                framework=ComplianceFramework.HIPAA,
                requirement_id="HIPAA-164.308",
                description="Administrative safeguards - access controls",
                policy_rule=PolicyRule(
                    name="hipaa_phi_access_control",
                    effect=PolicyEffect.REQUIRE_APPROVAL,
                    actions=["data:read", "data:export"],
                    resources=["dataset://phi/*"],
                    constraints=[
                        PolicyConstraint(key="subject.attributes.hipaa_training", equals=True),
                        PolicyConstraint(key="medical_necessity", equals=True)
                    ],
                    priority=10
                ),
                evidence_needed=["access_logs", "training_certificates", "approval_records"]
            ),

            # PCI-DSS
            ComplianceRequirement(
                framework=ComplianceFramework.PCI_DSS,
                requirement_id="PCI-3.4",
                description="Cardholder data must be encrypted",
                policy_rule=PolicyRule(
                    name="pci_encryption_required",
                    effect=PolicyEffect.DENY,
                    actions=["data:store", "data:write"],
                    resources=["dataset://card_data/*"],
                    constraints=[
                        PolicyConstraint(key="encryption_enabled", equals=False)
                    ],
                    priority=10
                ),
                evidence_needed=["encryption_certificates", "key_management_logs"]
            ),

            # SOC 2
            ComplianceRequirement(
                framework=ComplianceFramework.SOC2,
                requirement_id="SOC2-CC6.1",
                description="Logical and physical access controls",
                policy_rule=PolicyRule(
                    name="soc2_access_control",
                    effect=PolicyEffect.DENY,
                    actions=["*"],
                    resources=["*"],
                    constraints=[
                        PolicyConstraint(key="access_authorized", equals=False)
                    ],
                    priority=10
                ),
                evidence_needed=["access_control_matrix", "access_logs", "review_records"]
            )
        ]

    def _build_policy_set(self) -> PolicySet:
        """Build combined policy set from all requirements."""
        rules = [req.policy_rule for req in self.requirements]
        return PolicySet(
            name="compliance_automation",
            description="Automated compliance enforcement",
            default_effect=PolicyEffect.ALLOW,
            rules=rules
        )

    async def generate_compliance_report(
        self,
        framework: ComplianceFramework,
        graph_state: Any
    ) -> Dict:
        """Generate compliance report for framework."""
        from spark.governance import ApprovalGateManager

        # Get requirements for framework
        framework_reqs = [
            req for req in self.requirements
            if req.framework == framework
        ]

        # Get policy events
        policy_events = await graph_state.get('policy_events', [])

        # Get approval requests
        manager = ApprovalGateManager(state=graph_state)
        approvals = await manager.list_requests()

        report = {
            "framework": framework.value,
            "generated_at": datetime.now().isoformat(),
            "requirements": [],
            "summary": {
                "total_requirements": len(framework_reqs),
                "compliant": 0,
                "non_compliant": 0,
                "requires_review": 0
            }
        }

        for req in framework_reqs:
            # Check compliance status
            status = self._check_requirement_compliance(
                req, policy_events, approvals
            )

            report["requirements"].append({
                "requirement_id": req.requirement_id,
                "description": req.description,
                "status": status["status"],
                "evidence": status["evidence"],
                "violations": status.get("violations", [])
            })

            # Update summary
            report["summary"][status["status"]] += 1

        return report

    def _check_requirement_compliance(
        self,
        req: ComplianceRequirement,
        policy_events: List,
        approvals: List
    ) -> Dict:
        """Check if requirement is compliant."""
        # This is a simplified example
        # Real implementation would have complex compliance checking logic

        relevant_events = [
            e for e in policy_events
            if e.get("rule") == req.policy_rule.name
        ]

        violations = [
            e for e in relevant_events
            if e.get("decision") == "deny"
        ]

        if violations:
            return {
                "status": "non_compliant",
                "evidence": [f"Policy violations: {len(violations)}"],
                "violations": violations
            }

        return {
            "status": "compliant",
            "evidence": [f"No violations found"],
        }

# Usage
compliance = ComplianceAutomationSystem()

# Apply policies
graph = Graph(
    start=my_node,
    policy_set=compliance.policy_set
)

# Generate reports
gdpr_report = await compliance.generate_compliance_report(
    ComplianceFramework.GDPR,
    graph.state
)

hipaa_report = await compliance.generate_compliance_report(
    ComplianceFramework.HIPAA,
    graph.state
)

print(f"GDPR Compliance: {gdpr_report['summary']}")
print(f"HIPAA Compliance: {hipaa_report['summary']}")
```

## Audit Trail Generation

Comprehensive audit logging for security and compliance.

### Complete Audit System

```python
import json
from datetime import datetime
from typing import Any, Dict, List

class AuditTrailSystem:
    """Comprehensive audit trail generation and management."""

    def __init__(self, storage_path: str = "audit_logs"):
        self.storage_path = storage_path
        self.log_buffer = []

    async def log_policy_decision(
        self,
        request: PolicyRequest,
        decision: PolicyDecision
    ):
        """Log policy evaluation decision."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "policy_decision",
            "subject": {
                "identifier": request.subject.identifier,
                "roles": request.subject.roles,
                "attributes": request.subject.attributes
            },
            "action": request.action,
            "resource": request.resource,
            "decision": decision.effect.value,
            "rule": decision.rule,
            "reason": decision.reason,
            "context": request.context
        }
        await self._persist_entry(entry)

    async def log_approval_decision(
        self,
        approval: ApprovalRequest
    ):
        """Log approval request and resolution."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "approval_decision",
            "approval_id": approval.approval_id,
            "action": approval.action,
            "resource": approval.resource,
            "subject": approval.subject,
            "status": approval.status.value,
            "decided_by": approval.decided_by,
            "decided_at": datetime.fromtimestamp(approval.decided_at).isoformat() if approval.decided_at else None,
            "notes": approval.notes
        }
        await self._persist_entry(entry)

    async def log_data_access(
        self,
        user: str,
        action: str,
        resource: str,
        success: bool,
        details: Dict = None
    ):
        """Log data access event."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "data_access",
            "user": user,
            "action": action,
            "resource": resource,
            "success": success,
            "details": details or {}
        }
        await self._persist_entry(entry)

    async def _persist_entry(self, entry: Dict):
        """Persist audit log entry."""
        self.log_buffer.append(entry)

        # Flush buffer if it gets large
        if len(self.log_buffer) >= 100:
            await self.flush()

    async def flush(self):
        """Flush buffered logs to storage."""
        if not self.log_buffer:
            return

        # Write to daily log file
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = f"{self.storage_path}/audit_{date_str}.jsonl"

        with open(log_file, 'a') as f:
            for entry in self.log_buffer:
                f.write(json.dumps(entry) + "\n")

        self.log_buffer = []

    async def query_logs(
        self,
        start_date: datetime,
        end_date: datetime,
        event_type: str = None,
        user: str = None
    ) -> List[Dict]:
        """Query audit logs with filters."""
        # Implementation would read from log files
        # This is a simplified example
        pass

# Integration with governance
class AuditingPolicyEngine:
    """PolicyEngine with automatic audit logging."""

    def __init__(self, policy_set: PolicySet, audit_system: AuditTrailSystem):
        self.engine = PolicyEngine(policy_set)
        self.audit_system = audit_system

    async def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """Evaluate with audit logging."""
        decision = self.engine.evaluate(request)
        await self.audit_system.log_policy_decision(request, decision)
        return decision

    async def enforce(self, request: PolicyRequest) -> PolicyDecision:
        """Enforce with audit logging."""
        try:
            decision = self.engine.enforce(request)
            await self.audit_system.log_policy_decision(request, decision)
            return decision
        except (PolicyViolationError, PolicyApprovalRequired) as e:
            await self.audit_system.log_policy_decision(request, e.decision)
            raise

# Usage
audit_system = AuditTrailSystem(storage_path="/var/log/spark_audit")
engine = AuditingPolicyEngine(enterprise_policy_set, audit_system)

# All policy decisions are automatically audited
request = PolicyRequest(
    subject=PolicySubject(identifier="user-123", roles=["developer"]),
    action="data:read",
    resource="dataset://production/sales"
)

decision = await engine.evaluate(request)
# Audit log entry created automatically
```

## Deployment Patterns

Patterns for deploying governance in production environments.

### Gradual Rollout

```python
class GradualGovernanceRollout:
    """Gradually enable governance policies."""

    def __init__(self):
        self.rollout_percentage = 0.0  # 0% to 100%
        self.strict_policy_set = self._build_strict_policies()
        self.permissive_policy_set = self._build_permissive_policies()

    def _build_strict_policies(self) -> PolicySet:
        """Full governance policies."""
        # ... (your complete policy set)
        pass

    def _build_permissive_policies(self) -> PolicySet:
        """Permissive policies for gradual rollout."""
        # ... (relaxed policies)
        pass

    def get_policy_set_for_request(self, request_id: str) -> PolicySet:
        """Get policy set based on rollout percentage."""
        import hashlib

        # Consistent hashing to determine if request gets strict policies
        hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        percentile = (hash_val % 100) / 100.0

        if percentile < self.rollout_percentage:
            return self.strict_policy_set
        else:
            return self.permissive_policy_set

    def set_rollout_percentage(self, percentage: float):
        """Update rollout percentage (0-100)."""
        self.rollout_percentage = percentage / 100.0

# Usage
rollout = GradualGovernanceRollout()

# Start with 10% of traffic
rollout.set_rollout_percentage(10)

# Gradually increase
rollout.set_rollout_percentage(25)
rollout.set_rollout_percentage(50)
rollout.set_rollout_percentage(100)  # Full rollout
```

## Summary

These patterns demonstrate production-ready governance architectures:

- **Enterprise Governance**: Complete multi-layer defense
- **Multi-Tenant Isolation**: Perfect tenant separation
- **Budget Enforcement**: Hierarchical cost control
- **Security Hardening**: Defense-in-depth security
- **Compliance Automation**: Multi-framework compliance
- **Audit Trail**: Comprehensive logging and reporting
- **Deployment**: Gradual rollout strategies

Combine and adapt these patterns for your organization's specific requirements.

## Next Steps

- [Governance Overview](overview.md) - Core concepts
- [Policy Rules & Effects](policies.md) - Detailed policy syntax
- [Policy Types](policy-types.md) - Common policy examples
- [Approval Workflows](approvals.md) - Human-in-the-loop integration
