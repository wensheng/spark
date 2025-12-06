# Governance and Agents

This guide covers integrating Spark's governance system with agents to enforce policies, manage costs, implement approval workflows, ensure security, and maintain compliance.

## Table of Contents

- [Overview](#overview)
- [Policy Enforcement for Agents](#policy-enforcement-for-agents)
- [Cost Caps and Budgets](#cost-caps-and-budgets)
- [Approval Workflows for Agents](#approval-workflows-for-agents)
- [Security Policies](#security-policies)
- [Compliance Integration](#compliance-integration)
- [Audit Trail Generation](#audit-trail-generation)

## Overview

Governance provides policy-based control over agent behavior, ensuring agents operate within defined boundaries for cost, security, and compliance. This is critical for production deployments where agents must be trustworthy and accountable.

**Key Concepts**:
- **PolicyEngine**: Evaluates policies and makes access decisions
- **PolicyRule**: Declarative rules with conditions and effects
- **PolicyEffect**: ALLOW, DENY, or REQUIRE_APPROVAL
- **HumanApprovalNode**: Human-in-the-loop decision points

## Policy Enforcement for Agents

### Basic Policy Setup

```python
from spark.governance import PolicyEngine, PolicyRule, PolicyEffect
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Create policy engine
engine = PolicyEngine()

# Define policies
cost_policy = PolicyRule(
    name="high_cost_model_restriction",
    effect=PolicyEffect.DENY,
    conditions={
        'model': {'in': ['gpt-4', 'claude-opus-3']},
        'user_role': {'not_in': ['admin', 'power_user']}
    },
    description="Only admins can use expensive models"
)

rate_limit_policy = PolicyRule(
    name="api_rate_limit",
    effect=PolicyEffect.DENY,
    conditions={
        'requests_per_minute': {'gt': 60}
    },
    description="Limit API calls to 60/minute"
)

# Add policies to engine
engine.add_rule(cost_policy)
engine.add_rule(rate_limit_policy)

# Evaluate before agent creation
from spark.governance.policy import PolicyRequest

request = PolicyRequest(
    subject={'user': 'alice', 'role': 'developer'},
    action='agent.create',
    resource={'model': 'gpt-4'}
)

decision = await engine.evaluate(request)

if decision.effect == PolicyEffect.DENY:
    print(f"Policy denied: {decision.reason}")
else:
    # Create agent
    agent = Agent(config=AgentConfig(
        model=OpenAIModel(model_id="gpt-4")
    ))
```

### Agent-Level Policy Enforcement

Integrate policy checks into agent nodes:

```python
class GovernedAgentNode(Node):
    """Agent node with policy enforcement."""

    def __init__(
        self,
        agent: Agent,
        policy_engine: PolicyEngine,
        user_context: dict,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.agent = agent
        self.policy_engine = policy_engine
        self.user_context = user_context

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Check policy before execution
        request = PolicyRequest(
            subject=self.user_context,
            action='agent.run',
            resource={
                'agent_name': self.agent.config.name,
                'model': self.agent.config.model.model_id,
                'query': query
            }
        )

        decision = await self.policy_engine.evaluate(request)

        if decision.effect == PolicyEffect.DENY:
            return {
                'error': f"Policy denied: {decision.reason}",
                'success': False
            }

        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            # Request approval (see approval section)
            approved = await self.request_approval(query, decision.reason)
            if not approved:
                return {
                    'error': 'Approval not granted',
                    'success': False
                }

        # Execute agent
        result = await self.agent.run(query)

        return {
            'response': result.output,
            'success': True,
            'policy_checked': True
        }

# Usage
agent = Agent(config=AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    name="ProductionAgent"
))

governed_agent = GovernedAgentNode(
    agent=agent,
    policy_engine=engine,
    user_context={'user': 'alice', 'role': 'developer'}
)
```

## Cost Caps and Budgets

Enforce spending limits on agent operations:

### Agent-Level Budget

```python
from spark.agents import AgentConfig, AgentBudgetConfig

# Configure agent with budget
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    budget=AgentBudgetConfig(
        max_total_cost=1.00,        # $1.00 total budget
        max_cost_per_call=0.10,     # $0.10 per agent.run()
        max_llm_calls=10,            # Maximum 10 LLM API calls
        max_tool_calls=50            # Maximum 50 tool executions
    )
)

agent = Agent(config=config)

# Agent will raise AgentBudgetExceededError when budget exceeded
try:
    result = await agent.run("Expensive query requiring many LLM calls")
except AgentBudgetExceededError as e:
    print(f"Budget exceeded: {e}")
    # Handle budget exhaustion
```

### Policy-Based Budget Enforcement

```python
# Budget policy
budget_policy = PolicyRule(
    name="daily_budget_limit",
    effect=PolicyEffect.DENY,
    conditions={
        'daily_spend': {'gt': 100.00},  # $100/day limit
        'user_role': {'not_in': ['admin']}
    },
    description="Limit daily spend to $100 for non-admins"
)

engine.add_rule(budget_policy)

# Track spending in policy context
class BudgetTrackingAgentNode(Node):
    """Agent with budget tracking and policy enforcement."""

    def __init__(self, agent, policy_engine, user_id, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.policy_engine = policy_engine
        self.user_id = user_id
        self.spending_tracker = SpendingTracker()

    async def process(self, context):
        # Get current daily spend
        daily_spend = await self.spending_tracker.get_daily_spend(self.user_id)

        # Check budget policy
        request = PolicyRequest(
            subject={'user_id': self.user_id},
            action='agent.run',
            resource={
                'daily_spend': daily_spend,
                'estimated_cost': 0.01  # Estimate before execution
            }
        )

        decision = await self.policy_engine.evaluate(request)

        if decision.effect == PolicyEffect.DENY:
            return {
                'error': 'Daily budget exceeded',
                'daily_spend': daily_spend,
                'success': False
            }

        # Execute agent
        result = await self.agent.run(context.inputs.content['query'])

        # Record actual cost
        actual_cost = self.agent.get_cost_stats().total_cost
        await self.spending_tracker.record_spend(self.user_id, actual_cost)

        return {
            'response': result.output,
            'cost': actual_cost,
            'success': True
        }
```

### Workflow-Level Budget

Control total budget for entire workflow:

```python
from spark.graphs import Graph, Task, Budget

# Create workflow with budget
graph = Graph(start=agent_node)

# Run with budget constraint
task = Task(
    inputs={'query': 'Complex analysis'},
    budget=Budget(
        max_cost=5.00,           # $5.00 total budget
        max_tokens=100000,        # 100k tokens total
        max_seconds=300           # 5 minutes max
    )
)

try:
    result = await graph.run(task)
except BudgetExceededError as e:
    print(f"Workflow budget exceeded: {e}")
```

## Approval Workflows for Agents

Require human approval for sensitive operations:

### Approval Policy

```python
# Require approval for sensitive operations
approval_policy = PolicyRule(
    name="sensitive_operation_approval",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    conditions={
        'operation': {'in': ['delete', 'modify', 'deploy']},
        'resource': {'matches': '.*production.*'}
    },
    constraints={
        'approver_role': 'admin',
        'approval_timeout_seconds': 3600  # 1 hour
    },
    description="Production operations require admin approval"
)

engine.add_rule(approval_policy)
```

### Agent with Human-in-the-Loop

```python
from spark.agents import HumanInteractionPolicy, HumanApprovalRequired

# Configure agent with approval policy
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    tools=[delete_tool, modify_tool, deploy_tool],
    human_policy=HumanInteractionPolicy(
        require_tool_approval=True,
        auto_approved_tools=['read_tool', 'search_tool'],  # Safe tools
        stop_token='emergency_stop'
    )
)

agent = Agent(config=config)

# Agent will raise HumanApprovalRequired for restricted tools
try:
    result = await agent.run("Delete production database")
except HumanApprovalRequired as e:
    print(f"Approval required: {e}")
    # Present to human reviewer
    approved = await present_for_approval(e.details)
    if approved:
        # Continue with approval token
        result = await agent.run("Delete production database", approval_granted=True)
```

### Approval Node in Graph

```python
from spark.governance.approval import HumanApprovalNode

# Build workflow with approval gate
agent_node = AgentNode(agent=agent)
approval_node = HumanApprovalNode(
    approval_policy=approval_policy,
    name="ApprovalGate"
)
execution_node = ExecutionNode()

# Flow: Agent -> Approval -> Execution
agent_node >> approval_node
approval_node.on(approved=True) >> execution_node
approval_node.on(approved=False) >> rejection_node

graph = Graph(start=agent_node)
```

## Security Policies

Enforce security constraints on agent operations:

### Tool Access Control

```python
# Restrict dangerous tools
tool_access_policy = PolicyRule(
    name="restricted_tool_access",
    effect=PolicyEffect.DENY,
    conditions={
        'tool': {'in': ['execute_code', 'shell_command', 'file_write']},
        'user_role': {'not_in': ['admin', 'developer']}
    },
    description="Only developers can use potentially dangerous tools"
)

engine.add_rule(tool_access_policy)

# Check before adding tools to agent
from spark.tools.decorator import tool

@tool
def execute_code(code: str) -> str:
    """Execute arbitrary code (dangerous)."""
    return eval(code)

# Validate tool access
request = PolicyRequest(
    subject={'user': 'alice', 'role': 'analyst'},
    action='tool.register',
    resource={'tool': 'execute_code'}
)

decision = await engine.evaluate(request)
if decision.effect == PolicyEffect.ALLOW:
    config = AgentConfig(
        model=model,
        tools=[execute_code]
    )
else:
    print("Tool access denied by policy")
```

### Data Access Policies

```python
# Restrict access to sensitive data
data_access_policy = PolicyRule(
    name="pii_access_restriction",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    conditions={
        'data_classification': {'eq': 'pii'},
        'purpose': {'not_in': ['authorized_support']}
    },
    description="PII access requires approval unless for authorized support"
)

class SecureDataAccessNode(Node):
    """Node with data access policies."""

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Check if query might access PII
        if self.contains_pii_keywords(query):
            request = PolicyRequest(
                subject=context.metadata.get('user_context'),
                action='data.access',
                resource={'data_classification': 'pii'}
            )

            decision = await self.policy_engine.evaluate(request)

            if decision.effect == PolicyEffect.DENY:
                return {'error': 'Access to PII denied'}

            if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
                # Request approval
                approved = await self.request_pii_access(query)
                if not approved:
                    return {'error': 'PII access not approved'}

        # Execute query
        result = await self.agent.run(query)
        return {'response': result.output}
```

### Rate Limiting Policies

```python
# Rate limit by user
rate_limit_policy = PolicyRule(
    name="user_rate_limit",
    effect=PolicyEffect.DENY,
    conditions={
        'requests_last_minute': {'gt': 10}
    },
    description="Limit to 10 requests per minute"
)

class RateLimitedAgentNode(Node):
    """Agent with rate limiting."""

    def __init__(self, agent, policy_engine, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.policy_engine = policy_engine
        self.request_tracker = RequestTracker()

    async def process(self, context):
        user_id = context.metadata.get('user_id')

        # Check rate limit
        recent_requests = await self.request_tracker.count_recent(
            user_id,
            window_seconds=60
        )

        request = PolicyRequest(
            subject={'user_id': user_id},
            action='agent.run',
            resource={'requests_last_minute': recent_requests}
        )

        decision = await self.policy_engine.evaluate(request)

        if decision.effect == PolicyEffect.DENY:
            return {
                'error': 'Rate limit exceeded',
                'retry_after': 60,
                'success': False
            }

        # Record request
        await self.request_tracker.record(user_id)

        # Execute agent
        result = await self.agent.run(context.inputs.content['query'])
        return {'response': result.output, 'success': True}
```

## Compliance Integration

Ensure agent operations comply with regulations:

### Audit Logging Policy

```python
# Require audit logging for all operations
audit_policy = PolicyRule(
    name="audit_all_operations",
    effect=PolicyEffect.ALLOW,
    conditions={},  # Apply to all
    constraints={
        'require_audit_log': True,
        'log_level': 'detailed'
    },
    description="All operations must be audited"
)

class AuditedAgentNode(Node):
    """Agent with comprehensive audit logging."""

    async def process(self, context):
        audit_id = uuid.uuid4()
        user_id = context.metadata.get('user_id')
        query = context.inputs.content.get('query')

        # Log request
        await self.audit_log.log({
            'audit_id': audit_id,
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'action': 'agent.run',
            'request': query,
            'ip_address': context.metadata.get('ip_address')
        })

        try:
            # Execute agent
            result = await self.agent.run(query)

            # Log success
            await self.audit_log.log({
                'audit_id': audit_id,
                'status': 'success',
                'response': result.output,
                'cost': self.agent.get_cost_stats().total_cost
            })

            return {'response': result.output, 'audit_id': str(audit_id)}

        except Exception as e:
            # Log failure
            await self.audit_log.log({
                'audit_id': audit_id,
                'status': 'error',
                'error': str(e)
            })
            raise
```

### Data Retention Policies

```python
# Enforce data retention
retention_policy = PolicyRule(
    name="conversation_retention",
    effect=PolicyEffect.ALLOW,
    conditions={},
    constraints={
        'retention_days': 90,
        'require_encryption': True
    },
    description="Conversations retained for 90 days, encrypted"
)

class RetentionCompliantAgentNode(Node):
    """Agent with data retention compliance."""

    async def process(self, context):
        # Check retention policy
        request = PolicyRequest(
            subject={},
            action='conversation.store',
            resource={}
        )

        decision = await self.policy_engine.evaluate(request)
        constraints = decision.constraints

        # Execute agent
        result = await self.agent.run(context.inputs.content['query'])

        # Store conversation with retention policy
        await self.conversation_store.store(
            conversation=self.agent.messages,
            retention_days=constraints.get('retention_days', 90),
            encrypted=constraints.get('require_encryption', True),
            user_id=context.metadata.get('user_id')
        )

        return {'response': result.output}
```

## Audit Trail Generation

Comprehensive audit trails for compliance:

### Complete Audit Trail

```python
class ComprehensiveAuditNode(Node):
    """Node with complete audit trail."""

    async def process(self, context):
        audit_record = {
            'timestamp': datetime.now().isoformat(),
            'trace_id': context.metadata.get('trace_id'),
            'user_id': context.metadata.get('user_id'),
            'session_id': context.metadata.get('session_id'),
            'agent_name': self.agent.config.name,
            'agent_model': self.agent.config.model.model_id,
            'request': {
                'query': context.inputs.content.get('query'),
                'ip_address': context.metadata.get('ip_address'),
                'user_agent': context.metadata.get('user_agent')
            }
        }

        try:
            # Execute agent
            result = await self.agent.run(context.inputs.content['query'])

            # Get tool execution trace
            tool_trace = self.agent.state.get('tool_traces', [])

            # Complete audit record
            audit_record.update({
                'status': 'success',
                'response': result.output,
                'steps_taken': result.steps,
                'tools_used': [t['tool_name'] for t in tool_trace],
                'cost': self.agent.get_cost_stats().total_cost,
                'tokens': self.agent.get_cost_stats().total_tokens,
                'duration_seconds': result.metadata.get('duration')
            })

            # Store audit record
            await self.audit_store.store(audit_record)

            return {'response': result.output, 'audit_id': audit_record['trace_id']}

        except Exception as e:
            audit_record.update({
                'status': 'error',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'error_traceback': traceback.format_exc()
            })

            await self.audit_store.store(audit_record)
            raise
```

### Audit Query API

```python
class AuditQueryService:
    """Service for querying audit trails."""

    async def get_user_activity(self, user_id: str, date_range: tuple) -> list:
        """Get all activity for a user."""
        return await self.audit_store.query({
            'user_id': user_id,
            'timestamp': {'gte': date_range[0], 'lte': date_range[1]}
        })

    async def get_policy_violations(self, date_range: tuple) -> list:
        """Get all policy violations."""
        return await self.audit_store.query({
            'status': 'error',
            'error_type': 'PolicyViolationError',
            'timestamp': {'gte': date_range[0], 'lte': date_range[1]}
        })

    async def get_high_cost_operations(self, threshold: float) -> list:
        """Get operations exceeding cost threshold."""
        return await self.audit_store.query({
            'cost': {'gt': threshold}
        })
```

## Best Practices

1. **Policy as Code**: Define policies declaratively, version control them
2. **Least Privilege**: Grant minimum necessary permissions
3. **Defense in Depth**: Layer multiple controls (policies, budgets, approvals)
4. **Comprehensive Auditing**: Log all operations, not just failures
5. **Regular Reviews**: Periodically review policies and audit logs
6. **Automated Enforcement**: Use policy engine, don't rely on manual checks
7. **Clear Policies**: Make policies understandable to users
8. **Graceful Degradation**: Provide helpful error messages when policies block actions

## Related Documentation

- [Governance System Reference](/docs/governance/overview.md) - Complete governance guide
- [Policy Rules](/docs/governance/policies.md) - Policy definition
- [Agent System Reference](/docs/agents/fundamentals.md) - Agent configuration
- [Security Best Practices](/docs/best-practices/security.md) - Security guidance
