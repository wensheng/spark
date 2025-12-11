---
title: Config Files
parent: Config
nav_order: 1
---
# Configuration Files
---

Spark uses configuration files for settings that are:
- Too complex for environment variables
- Shared across multiple environments
- Need version control and review
- Require structured data (JSON, YAML)

Configuration files are typically loaded at application startup and can be overridden by environment variables or code configuration.

## File Locations and Search Order

Spark searches for configuration files in standard locations with a defined precedence order:

### Standard Search Order

1. **Explicit path**: Path provided directly in code
2. **Environment variable**: Path specified via environment variable
3. **Current directory**: `./config_file.ext`
4. **User directory**: `~/.spark/config_file.ext`
5. **Package default**: `<spark-install>/submodule/config_file.ext`
6. **Hardcoded fallback**: Built-in default values

### Configuration Directory Structure

Recommended directory structure for Spark configuration:

```
~/.spark/                        # User configuration directory
├── model_pricing.json           # Custom model pricing
├── policies/                    # Governance policies
│   ├── security_policy.json
│   ├── compliance_policy.json
│   └── approval_policy.json
├── telemetry/                   # Telemetry configuration
│   └── telemetry_config.json
├── checkpoints/                 # Agent checkpoints
│   ├── agent_state_*.json
│   └── graph_state_*.json
└── cache/                       # Cache directory (see SPARK_CACHE_DIR)
    └── llm-responses/
```

**Creating the directory structure**:
```bash
mkdir -p ~/.spark/{policies,telemetry,checkpoints,cache}
```

## Model Pricing Configuration

### `model_pricing.json`

**Purpose**: Define per-token pricing for LLM models used in cost tracking.

**Location Search Order**:
1. `SPARK_PRICING_CONFIG` environment variable
2. `./model_pricing.json` (current directory)
3. `~/.spark/model_pricing.json` (user home)
4. `<spark>/agents/model_pricing.json` (package default)
5. Hardcoded fallback values

**File Format**:
```json
{
  "_comment": "Pricing per 1M tokens (USD)",
  "openai": {
    "gpt-4o": {
      "input": 5.00,
      "output": 15.00
    },
    "gpt-4o-mini": {
      "input": 0.15,
      "output": 0.60
    }
  },
  "anthropic": {
    "claude-3-opus": {
      "input": 15.00,
      "output": 75.00
    },
    "claude-3-sonnet": {
      "input": 3.00,
      "output": 15.00
    }
  },
  "aws_bedrock": {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {
      "input": 3.00,
      "output": 15.00
    },
    "us.amazon.nova-pro-v1:0": {
      "input": 0.80,
      "output": 3.20
    }
  },
  "gemini": {
    "gemini-2.5-pro": {
      "input": 1.25,
      "output": 10.00
    }
  },
  "default": {
    "input": 5.00,
    "output": 15.00
  }
}
```

**Schema**:
- **Root level**: Provider categories (e.g., "openai", "anthropic", "aws_bedrock", "gemini")
- **Provider level**: Model IDs as keys
- **Model level**: Object with "input" and "output" fields
  - `input`: Price per 1 million input tokens (USD)
  - `output`: Price per 1 million output tokens (USD)
- **Special key**: `"default"` - Fallback pricing for unknown models

**Field Reference**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_comment` | string | No | Documentation comment (ignored by parser) |
| Provider category | object | Yes | Container for provider's models |
| Model ID | object | Yes | Pricing for specific model |
| `input` | number | Yes | Input token price per 1M tokens (USD) |
| `output` | number | Yes | Output token price per 1M tokens (USD) |
| `default` | object | No | Fallback pricing for unknown models |

**Usage**:
```python
from spark.agents.cost_tracker import CostTracker

# Load pricing from standard locations
tracker = CostTracker()

# Load pricing from custom path
tracker = CostTracker(pricing_config_path="/path/to/pricing.json")

# Reload pricing at runtime
tracker.reload_pricing("/path/to/updated_pricing.json")
```

**Updating Pricing**:

Pricing should be updated regularly to reflect current API pricing:

```bash
# Download latest pricing (example)
curl -o ~/.spark/model_pricing.json https://example.com/pricing/latest.json

# Or manually edit
nano ~/.spark/model_pricing.json
```

**Validation**:
```python
import json

# Validate pricing file structure
def validate_pricing(filepath):
    with open(filepath) as f:
        pricing = json.load(f)

    for provider, models in pricing.items():
        if provider.startswith('_'):
            continue  # Skip metadata

        if provider == 'default':
            assert 'input' in models and 'output' in models
            continue

        for model_id, prices in models.items():
            assert 'input' in prices, f"Missing 'input' for {provider}/{model_id}"
            assert 'output' in prices, f"Missing 'output' for {provider}/{model_id}"
            assert prices['input'] >= 0, f"Negative input price for {provider}/{model_id}"
            assert prices['output'] >= 0, f"Negative output price for {provider}/{model_id}"

    print("✓ Pricing file is valid")

validate_pricing("~/.spark/model_pricing.json")
```

## Telemetry Configuration Files

### Backend-Specific Configuration

Telemetry backends can be configured via JSON files for complex setups.

#### SQLite Configuration

**File**: `telemetry_sqlite.json` (optional)

```json
{
  "backend": "sqlite",
  "backend_config": {
    "db_path": "/var/lib/spark/telemetry.db"
  },
  "sampling_rate": 1.0,
  "export_interval": 10.0,
  "buffer_size": 1000,
  "retention_days": 30,
  "enable_metrics": true,
  "enable_events": true,
  "enable_traces": true
}
```

**Loading from file**:
```python
import json
from spark.telemetry import TelemetryConfig

with open("telemetry_sqlite.json") as f:
    config_dict = json.load(f)

config = TelemetryConfig(**config_dict)
```

#### PostgreSQL Configuration

**File**: `telemetry_postgres.json` (optional)

```json
{
  "backend": "postgresql",
  "backend_config": {
    "host": "postgres.example.com",
    "port": 5432,
    "database": "spark_telemetry",
    "user": "spark",
    "password": "${POSTGRES_PASSWORD}",
    "min_pool_size": 2,
    "max_pool_size": 10
  },
  "sampling_rate": 0.1,
  "export_interval": 30.0,
  "buffer_size": 5000,
  "retention_days": 90
}
```

**Note**: Use environment variable substitution for sensitive values like passwords.

#### OTLP Configuration

**File**: `telemetry_otlp.json` (optional)

```json
{
  "backend": "otlp",
  "backend_config": {
    "endpoint": "https://otlp.example.com:4317",
    "protocol": "grpc",
    "insecure": false,
    "timeout_seconds": 10,
    "headers": {
      "api-key": "${OTLP_API_KEY}"
    }
  },
  "resource_attributes": {
    "service.name": "spark-production",
    "service.version": "2.0.0",
    "deployment.environment": "production"
  }
}
```

## Policy Definition Files

### Governance Policy Files

**Purpose**: Define governance policies for controlling agent and graph behavior.

**Location**: Typically stored in `~/.spark/policies/` or project-specific policy directories.

#### Security Policy

**File**: `security_policy.json`

```json
{
  "policy_set": {
    "name": "security_policies",
    "rules": [
      {
        "name": "prevent_dangerous_tools",
        "effect": "DENY",
        "conditions": {
          "tool_name": {
            "in": ["shell_exec", "file_delete", "unsafe_python"]
          }
        },
        "description": "Prevent execution of dangerous tools"
      },
      {
        "name": "require_approval_sensitive_data",
        "effect": "REQUIRE_APPROVAL",
        "conditions": {
          "resource_type": "sensitive_data",
          "action": "access"
        },
        "description": "Require human approval for sensitive data access"
      }
    ]
  }
}
```

#### Cost Control Policy

**File**: `cost_policy.json`

```json
{
  "policy_set": {
    "name": "cost_controls",
    "rules": [
      {
        "name": "expensive_model_approval",
        "effect": "REQUIRE_APPROVAL",
        "conditions": {
          "model": {
            "in": ["gpt-4", "claude-opus", "o3-pro"]
          },
          "estimated_cost": {
            "gt": 1.0
          }
        },
        "constraints": {
          "max_cost": 10.0,
          "require_justification": true
        },
        "description": "Require approval for expensive model usage"
      },
      {
        "name": "daily_cost_limit",
        "effect": "DENY",
        "conditions": {
          "daily_cost": {
            "gte": 100.0
          }
        },
        "description": "Block execution when daily cost exceeds limit"
      }
    ]
  }
}
```

#### Compliance Policy

**File**: `compliance_policy.json`

```json
{
  "policy_set": {
    "name": "compliance_policies",
    "rules": [
      {
        "name": "data_residency",
        "effect": "DENY",
        "conditions": {
          "model_region": {
            "not_in": ["us-east-1", "us-west-2"]
          }
        },
        "description": "Enforce data residency requirements"
      },
      {
        "name": "audit_trail_required",
        "effect": "REQUIRE",
        "conditions": {
          "operation": "data_modification"
        },
        "constraints": {
          "audit_log_enabled": true,
          "min_retention_days": 365
        },
        "description": "Require audit trail for data modifications"
      }
    ]
  }
}
```

**Loading policy files**:
```python
import json
from spark.governance import PolicyEngine, PolicyRule, PolicyEffect

def load_policy_file(filepath):
    with open(filepath) as f:
        data = json.load(f)

    engine = PolicyEngine()
    for rule_data in data['policy_set']['rules']:
        rule = PolicyRule(
            name=rule_data['name'],
            effect=PolicyEffect[rule_data['effect']],
            conditions=rule_data.get('conditions', {}),
            constraints=rule_data.get('constraints', {})
        )
        engine.add_rule(rule)

    return engine

# Load policies
security_engine = load_policy_file("~/.spark/policies/security_policy.json")
cost_engine = load_policy_file("~/.spark/policies/cost_policy.json")
```

## Checkpoint Configuration Files

### Agent Checkpoint Files

**Purpose**: Save and restore complete agent state for resilience and debugging.

**Location**: Typically stored in `~/.spark/checkpoints/` or project-specific directories.

**File Format**: `agent_checkpoint_<timestamp>.json`

```json
{
  "checkpoint_version": "1.0",
  "timestamp": "2025-01-13T10:30:00Z",
  "config": {
    "model": {
      "type": "OpenAIModel",
      "model_id": "gpt-4o"
    },
    "system_prompt": "You are a helpful assistant.",
    "max_steps": 100,
    "parallel_tool_execution": true,
    "reasoning_strategy": {
      "name": "react"
    }
  },
  "memory": {
    "history": [
      {
        "role": "user",
        "content": [{"text": "Hello"}]
      },
      {
        "role": "assistant",
        "content": [{"text": "Hi! How can I help you?"}]
      }
    ],
    "policy": "rolling_window",
    "window": 10
  },
  "state": {
    "tool_traces": [],
    "last_result": null,
    "last_error": null
  },
  "cost_tracking": {
    "calls": [
      {
        "model_id": "gpt-4o",
        "input_tokens": 150,
        "output_tokens": 80,
        "total_cost": 0.00195
      }
    ],
    "total_cost": 0.00195,
    "total_tokens": 230
  },
  "strategy_state": {
    "type": "react",
    "history": [
      {"thought": "...", "action": "...", "observation": "..."}
    ]
  }
}
```

**Saving checkpoint**:
```python
from spark.agents import Agent

agent = Agent(config=config)
# ... use agent ...

# Save checkpoint
agent.save_checkpoint("~/.spark/checkpoints/agent_checkpoint_20250113.json")
```

**Loading checkpoint**:
```python
from spark.agents import Agent

# Restore from checkpoint
agent = Agent.load_checkpoint(
    "~/.spark/checkpoints/agent_checkpoint_20250113.json",
    config=config  # Config with model instance
)

# Continue from where we left off
response = await agent.run("Continue the task")
```

### Graph Checkpoint Files

**Purpose**: Save complete graph state including all node states.

**File Format**: `graph_checkpoint_<timestamp>.json`

```json
{
  "checkpoint_version": "1.0",
  "timestamp": "2025-01-13T10:30:00Z",
  "graph_id": "my_workflow",
  "graph_version": "1.0.0",
  "global_state": {
    "counter": 42,
    "results": ["result1", "result2"],
    "status": "in_progress"
  },
  "node_states": {
    "node1": {
      "context_snapshot": {...},
      "processing": false,
      "process_count": 5
    },
    "node2": {
      "context_snapshot": {...},
      "processing": true,
      "process_count": 3
    }
  }
}
```

## Graph Specification Files

### Graph JSON Specifications

**Purpose**: Serialize graphs to JSON for version control, portability, and code generation.

**Location**: Project-specific, typically in `specs/` or `graphs/` directory.

**File Format**: `<graph_name>_spec.json`

```json
{
  "spark_version": "2.0",
  "graph": {
    "name": "my_workflow",
    "description": "Example workflow",
    "start_node": "node1",
    "nodes": [
      {
        "id": "node1",
        "type": "ProcessingNode",
        "config": {
          "retry": {
            "max_attempts": 3,
            "backoff_seconds": 1.0
          }
        }
      },
      {
        "id": "node2",
        "type": "TransformNode",
        "config": {}
      }
    ],
    "edges": [
      {
        "from_node": "node1",
        "to_node": "node2",
        "condition": {
          "type": "simple",
          "key": "success",
          "value": true
        }
      }
    ],
    "initial_state": {
      "counter": 0
    }
  }
}
```

**CLI Operations**:
```bash
# Export graph to JSON
spark-spec export mymodule:create_graph -o graph.json

# Validate specification
spark-spec validate graph.json --semantic

# Generate Python code from spec
spark-spec compile graph.json -o ./generated --style production

# Analyze graph structure
spark-spec analyze graph.json --report report.html
```

**Loading in code**:
```python
from spark.nodes.serde import load_graph_spec

# Load specification
spec = load_graph_spec("graph.json")

# Use spec for validation, analysis, or code generation
```

## Configuration File Best Practices

### Version Control

**Do commit**:
- Policy definitions
- Graph specifications
- Template configurations (with placeholders)
- Example configurations

**Do NOT commit**:
- API keys or secrets
- Environment-specific values (paths, URLs)
- Checkpoint files with sensitive data
- Telemetry databases

**Example `.gitignore`**:
```
# Sensitive configuration
.env
.env.*
*_secrets.json
credentials.json

# Checkpoints with state
checkpoints/*.json
agent_state_*.json
graph_state_*.json

# Telemetry data
*.db
telemetry/

# Cache
cache/
__pycache__/
```

### Configuration Validation

**Validate on load**:
```python
import json
from pathlib import Path

def load_and_validate_config(filepath, schema=None):
    """Load and validate configuration file."""
    path = Path(filepath).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {filepath}")

    with open(path) as f:
        config = json.load(f)

    if schema:
        # Validate against JSON schema
        import jsonschema
        jsonschema.validate(config, schema)

    return config

# Usage
config = load_and_validate_config("~/.spark/policies/security_policy.json")
```

### Environment-Specific Configuration

**Use templating**:
```json
{
  "backend_config": {
    "host": "${DB_HOST}",
    "port": "${DB_PORT}",
    "database": "${DB_NAME}",
    "user": "${DB_USER}",
    "password": "${DB_PASSWORD}"
  }
}
```

**Substitute at runtime**:
```python
import os
import json
import re

def load_config_with_env(filepath):
    with open(filepath) as f:
        content = f.read()

    # Replace ${VAR_NAME} with environment variable
    def replace_env(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    content = re.sub(r'\$\{([A-Z_]+)\}', replace_env, content)
    return json.loads(content)

config = load_config_with_env("telemetry_postgres.json")
```

### Configuration Precedence

When using multiple configuration sources, establish clear precedence:

```python
def load_final_config():
    """Load configuration with precedence: code > env > file > default"""

    # 1. Start with defaults
    config = {
        'sampling_rate': 1.0,
        'buffer_size': 1000,
    }

    # 2. Load from file if exists
    if os.path.exists('~/.spark/telemetry.json'):
        file_config = load_config_with_env('~/.spark/telemetry.json')
        config.update(file_config)

    # 3. Override with environment variables
    if 'SPARK_SAMPLING_RATE' in os.environ:
        config['sampling_rate'] = float(os.getenv('SPARK_SAMPLING_RATE'))

    # 4. Code-level overrides happen at instantiation
    return config
```

## File Format Reference

### Supported Formats

| Format | Use Case | Extensions | Notes |
|--------|----------|------------|-------|
| JSON | Primary configuration | `.json` | Strict schema, no comments |
| JSON5 | Human-friendly config | `.json5` | Supports comments, trailing commas |
| YAML | Complex hierarchies | `.yaml`, `.yml` | More readable for nested data |
| TOML | Python config | `.toml` | Native Python support |

**JSON (recommended)**:
- Strict validation
- Wide tool support
- Machine-readable

**YAML (alternative)**:
- More readable
- Supports comments
- Better for complex nested structures

### Migration Between Formats

**JSON to YAML**:
```python
import json
import yaml

with open('config.json') as f:
    config = json.load(f)

with open('config.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False)
```

**YAML to JSON**:
```python
import json
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
```

## See Also

- [Environment Variables](environment.md) - Environment-based configuration
- [NodeConfig Reference](node-config.md) - Node configuration options
- [AgentConfig Reference](agent-config.md) - Agent configuration options
- [TelemetryConfig Reference](telemetry-config.md) - Telemetry configuration
- [RSIMetaGraphConfig Reference](rsi-config.md) - RSI configuration
- [Governance Policies](../architecture/governance.md) - Policy system details
