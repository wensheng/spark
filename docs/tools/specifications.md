---
title: Tool Specifications
parent: Tools
nav_order: 4
---
# Tool Specifications
---

Tool specifications are JSON documents that describe tools to LLMs and agents. They define:

- Tool name and description
- Input parameters with types and constraints
- Parameter validation rules
- Provider-specific formatting

Spark automatically generates specifications from Python functions decorated with `@tool`, but understanding the underlying format is important for:

- Debugging tool integration issues
- Creating tools manually
- Validating tool schemas
- Converting between provider formats

## ToolSpec Structure

### Base Structure

A tool specification has this basic structure:

```json
{
  "name": "tool_name",
  "description": "What the tool does",
  "input_schema": {
    "type": "object",
    "properties": {
      "param1": {
        "type": "string",
        "description": "First parameter"
      },
      "param2": {
        "type": "integer",
        "description": "Second parameter"
      }
    },
    "required": ["param1"]
  }
}
```

### Complete Example

Here's a comprehensive tool specification:

```json
{
  "name": "search_database",
  "description": "Search the database for matching records using various criteria",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query string",
        "minLength": 1,
        "maxLength": 500
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of results to return",
        "minimum": 1,
        "maximum": 100,
        "default": 10
      },
      "sort_by": {
        "type": "string",
        "description": "Field to sort results by",
        "enum": ["relevance", "date", "name"],
        "default": "relevance"
      },
      "include_archived": {
        "type": "boolean",
        "description": "Whether to include archived records",
        "default": false
      },
      "filters": {
        "type": "object",
        "description": "Additional filter criteria",
        "properties": {
          "category": {
            "type": "string"
          },
          "min_score": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0
          }
        },
        "additionalProperties": false
      }
    },
    "required": ["query"],
    "additionalProperties": false
  }
}
```

## Field Specifications

### name (Required)

The unique identifier for the tool.

**Type**: `string`

**Constraints**:
- Must be unique within a registry
- Should be descriptive and action-oriented
- Use snake_case by convention
- No spaces or special characters (except underscore)

**Examples**:
```json
"name": "search_database"
"name": "send_email"
"name": "calculate_tax"
"name": "get_weather"
```

### description (Required)

Human-readable description of what the tool does.

**Type**: `string`

**Best practices**:
- Start with a verb (imperative form)
- Be concise but complete (1-3 sentences)
- Explain what the tool does, not how it works
- Include important constraints or limitations
- LLMs read this to decide when to use the tool

**Examples**:
```json
"description": "Search the database for matching records using full-text search"

"description": "Send an email to a recipient with subject and body. The email is sent asynchronously and this function returns immediately."

"description": "Calculate sales tax based on amount and jurisdiction. Supports US state and local tax rates."
```

### input_schema (Required)

JSON Schema definition of the tool's parameters.

**Type**: `object` (JSON Schema)

**Root level properties**:
- `type`: Must be `"object"`
- `properties`: Object defining each parameter
- `required`: Array of required parameter names
- `additionalProperties`: Whether to allow extra properties (usually `false`)

## Parameter Type Definitions

### String Parameters

**Basic string**:
```json
{
  "type": "string",
  "description": "User's email address"
}
```

**String with constraints**:
```json
{
  "type": "string",
  "description": "User's username",
  "minLength": 3,
  "maxLength": 20,
  "pattern": "^[a-zA-Z0-9_]+$"
}
```

**String with enumeration**:
```json
{
  "type": "string",
  "description": "Output format",
  "enum": ["json", "xml", "csv"],
  "default": "json"
}
```

**String with format**:
```json
{
  "type": "string",
  "description": "Event timestamp",
  "format": "date-time"
}
```

**Common formats**:
- `"date-time"`: ISO 8601 datetime
- `"date"`: ISO 8601 date
- `"time"`: ISO 8601 time
- `"email"`: Email address
- `"uri"`: URI/URL
- `"uuid"`: UUID string

### Integer Parameters

**Basic integer**:
```json
{
  "type": "integer",
  "description": "Number of results"
}
```

**Integer with constraints**:
```json
{
  "type": "integer",
  "description": "Page size",
  "minimum": 1,
  "maximum": 100,
  "default": 10
}
```

**Integer with exclusive bounds**:
```json
{
  "type": "integer",
  "description": "Port number",
  "exclusiveMinimum": 1024,
  "exclusiveMaximum": 65536
}
```

### Number Parameters

**Basic number** (float):
```json
{
  "type": "number",
  "description": "Temperature in Celsius"
}
```

**Number with constraints**:
```json
{
  "type": "number",
  "description": "Confidence score",
  "minimum": 0.0,
  "maximum": 1.0
}
```

**Number with multiplier**:
```json
{
  "type": "number",
  "description": "Price in dollars",
  "multipleOf": 0.01
}
```

### Boolean Parameters

```json
{
  "type": "boolean",
  "description": "Whether to include metadata",
  "default": false
}
```

### Array Parameters

**Array of strings**:
```json
{
  "type": "array",
  "description": "List of tags",
  "items": {
    "type": "string"
  }
}
```

**Array with constraints**:
```json
{
  "type": "array",
  "description": "Selected items",
  "items": {
    "type": "string"
  },
  "minItems": 1,
  "maxItems": 10,
  "uniqueItems": true
}
```

**Array of objects**:
```json
{
  "type": "array",
  "description": "User records",
  "items": {
    "type": "object",
    "properties": {
      "id": {"type": "string"},
      "name": {"type": "string"}
    },
    "required": ["id"]
  }
}
```

### Object Parameters

**Basic object**:
```json
{
  "type": "object",
  "description": "User profile",
  "properties": {
    "name": {"type": "string"},
    "age": {"type": "integer"}
  }
}
```

**Object with required fields**:
```json
{
  "type": "object",
  "description": "Address",
  "properties": {
    "street": {"type": "string"},
    "city": {"type": "string"},
    "state": {"type": "string"},
    "zip": {"type": "string"}
  },
  "required": ["street", "city", "state", "zip"],
  "additionalProperties": false
}
```

**Object with additional properties**:
```json
{
  "type": "object",
  "description": "Metadata dictionary",
  "additionalProperties": {
    "type": "string"
  }
}
```

### Union Types

Union types use `anyOf`, `oneOf`, or `allOf`:

**anyOf** (matches any):
```json
{
  "description": "Identifier (string or integer)",
  "anyOf": [
    {"type": "string"},
    {"type": "integer"}
  ]
}
```

**oneOf** (matches exactly one):
```json
{
  "description": "Search query",
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "text": {"type": "string"}
      },
      "required": ["text"]
    },
    {
      "type": "object",
      "properties": {
        "id": {"type": "string"}
      },
      "required": ["id"]
    }
  ]
}
```

### Null and Optional Types

**Nullable parameter**:
```json
{
  "description": "Optional comment",
  "anyOf": [
    {"type": "string"},
    {"type": "null"}
  ]
}
```

**Optional parameter** (not in required array):
```json
{
  "type": "object",
  "properties": {
    "required_field": {"type": "string"},
    "optional_field": {"type": "string"}
  },
  "required": ["required_field"]
}
```

## JSON Schema Generation

### From Python Functions

Spark automatically generates schemas from Python type hints:

```python
from spark.tools.decorator import tool
from typing import Optional, List

@tool
def example_tool(
    query: str,
    limit: int = 10,
    tags: Optional[List[str]] = None
) -> dict:
    """Example tool with various parameter types.

    Args:
        query: The search query
        limit: Maximum results (default: 10)
        tags: Optional filter tags
    """
    pass
```

**Generated schema**:
```json
{
  "name": "example_tool",
  "description": "Example tool with various parameter types.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query"
      },
      "limit": {
        "type": "integer",
        "description": "Maximum results (default: 10)",
        "default": 10
      },
      "tags": {
        "anyOf": [
          {
            "type": "array",
            "items": {"type": "string"}
          },
          {"type": "null"}
        ],
        "description": "Optional filter tags",
        "default": null
      }
    },
    "required": ["query"]
  }
}
```

### Type Mapping

Python types map to JSON Schema types:

| Python Type | JSON Schema Type |
|-------------|------------------|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list`, `List[T]` | `{"type": "array", "items": {...}}` |
| `dict`, `Dict[K, V]` | `{"type": "object"}` |
| `Optional[T]` | `{"anyOf": [{...}, {"type": "null"}]}` |
| `Union[T1, T2]` | `{"anyOf": [{...}, {...}]}` |
| `Literal["a", "b"]` | `{"enum": ["a", "b"]}` |

### Pydantic Models

Pydantic models generate rich schemas:

```python
from pydantic import BaseModel, Field
from spark.tools.decorator import tool

class SearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(10, ge=1, le=100)
    sort_by: str = Field("relevance", pattern="^(relevance|date|name)$")

@tool
def search(params: SearchParams) -> list:
    """Search with validated parameters."""
    pass
```

**Generated schema** (includes Pydantic constraints):
```json
{
  "name": "search",
  "description": "Search with validated parameters.",
  "input_schema": {
    "type": "object",
    "properties": {
      "params": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 10
          },
          "sort_by": {
            "type": "string",
            "pattern": "^(relevance|date|name)$",
            "default": "relevance"
          }
        },
        "required": ["query"]
      }
    },
    "required": ["params"]
  }
}
```

## Provider-Specific Formats

Different LLM providers expect different tool specification formats.

### OpenAI Format

OpenAI uses a `function` type with `parameters` field:

```json
{
  "type": "function",
  "function": {
    "name": "search_database",
    "description": "Search the database for matching records",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The search query"
        },
        "limit": {
          "type": "integer",
          "description": "Maximum results",
          "default": 10
        }
      },
      "required": ["query"]
    }
  }
}
```

**Key differences from Spark format**:
- Wrapped in `type: "function"` and `function` object
- Uses `parameters` instead of `input_schema`
- Otherwise standard JSON Schema

### Bedrock/Claude Format

Bedrock (Claude) uses `toolSpec` structure:

```json
{
  "toolSpec": {
    "name": "search_database",
    "description": "Search the database for matching records",
    "inputSchema": {
      "json": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "The search query"
          },
          "limit": {
            "type": "integer",
            "description": "Maximum results"
          }
        },
        "required": ["query"]
      }
    }
  }
}
```

**Key differences**:
- Wrapped in `toolSpec` object
- Uses `inputSchema.json` for the schema
- Otherwise standard JSON Schema

### Gemini Format

Google Gemini uses `function_declarations`:

```json
{
  "function_declarations": [
    {
      "name": "search_database",
      "description": "Search the database for matching records",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "The search query"
          },
          "limit": {
            "type": "integer",
            "description": "Maximum results"
          }
        },
        "required": ["query"]
      }
    }
  ]
}
```

**Key differences**:
- Array of function declarations
- Uses `parameters` instead of `input_schema`
- Otherwise standard JSON Schema

### Spark Internal Format

Spark uses a simpler internal format:

```json
{
  "name": "search_database",
  "description": "Search the database for matching records",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query"
      },
      "limit": {
        "type": "integer",
        "description": "Maximum results"
      }
    },
    "required": ["query"]
  }
}
```

Models in Spark handle conversion to provider-specific formats automatically.

## Spec Validation

### Manual Validation

Use `ToolRegistry.validate_tool_spec()` to validate specs:

```python
from spark.tools.registry import ToolRegistry

registry = ToolRegistry()

spec = {
    "name": "my_tool",
    "description": "Does something useful",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string"}
        },
        "required": ["param"]
    }
}

is_valid, error = registry.validate_tool_spec(spec)
if not is_valid:
    print(f"Validation failed: {error}")
```

### Common Validation Errors

**Missing required fields**:
```python
# Missing 'description'
spec = {
    "name": "my_tool",
    "input_schema": {...}
}
# Error: "Missing required field 'description'"
```

**Invalid schema structure**:
```python
# Wrong root type
spec = {
    "name": "my_tool",
    "description": "...",
    "input_schema": {
        "type": "string"  # Should be "object"
    }
}
# Error: "input_schema must be of type 'object'"
```

**Required parameter not in properties**:
```python
spec = {
    "name": "my_tool",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string"}
        },
        "required": ["param1", "param2"]  # param2 not defined
    }
}
# Error: "Required parameter 'param2' not found in properties"
```

### Schema Validation with jsonschema

Use the `jsonschema` library for deep validation:

```python
import jsonschema

# Define meta-schema for tool specs
TOOL_SPEC_SCHEMA = {
    "type": "object",
    "required": ["name", "description", "input_schema"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
        "input_schema": {
            "type": "object",
            "required": ["type", "properties"],
            "properties": {
                "type": {"const": "object"},
                "properties": {"type": "object"},
                "required": {"type": "array", "items": {"type": "string"}}
            }
        }
    }
}

def validate_spec(spec: dict):
    """Validate tool spec against meta-schema."""
    try:
        jsonschema.validate(spec, TOOL_SPEC_SCHEMA)
        return True, None
    except jsonschema.ValidationError as e:
        return False, str(e)

# Validate a spec
is_valid, error = validate_spec(my_spec)
```

## Tool Metadata

### Extended Metadata

Specs can include extended metadata for documentation and tooling:

```json
{
  "name": "search_database",
  "description": "Search the database for matching records",
  "input_schema": {...},
  "metadata": {
    "version": "1.2.0",
    "author": "Data Team",
    "category": "database",
    "tags": ["search", "query", "database"],
    "examples": [
      {
        "description": "Basic search",
        "input": {
          "query": "user data",
          "limit": 10
        }
      }
    ],
    "performance": {
      "avg_duration_ms": 150,
      "rate_limit": "100/min"
    },
    "changelog": [
      {
        "version": "1.2.0",
        "date": "2024-01-15",
        "changes": ["Added sort_by parameter"]
      }
    ]
  }
}
```

### Usage Examples in Specs

Include usage examples to help LLMs:

```json
{
  "name": "calculate_tax",
  "description": "Calculate sales tax for a purchase",
  "input_schema": {...},
  "examples": [
    {
      "input": {
        "amount": 100.0,
        "state": "CA"
      },
      "output": {
        "tax": 8.25,
        "total": 108.25
      }
    },
    {
      "input": {
        "amount": 50.0,
        "state": "NY"
      },
      "output": {
        "tax": 4.00,
        "total": 54.00
      }
    }
  ]
}
```

## Testing Specifications

### Validate Generated Specs

Test that tools generate correct specs:

```python
import pytest
from spark.tools.decorator import tool
from spark.tools.registry import ToolRegistry

@tool
def my_tool(param1: str, param2: int = 10) -> dict:
    """Tool description.

    Args:
        param1: First parameter
        param2: Second parameter
    """
    return {}

def test_tool_spec_generation():
    """Test that tool generates correct spec."""
    registry = ToolRegistry()
    registry.process_tools([my_tool])

    specs = registry.get_all_tool_specs()
    assert len(specs) == 1

    spec = specs[0]
    assert spec["name"] == "my_tool"
    assert "Tool description" in spec["description"]

    # Validate schema structure
    schema = spec["input_schema"]
    assert schema["type"] == "object"
    assert "param1" in schema["properties"]
    assert "param2" in schema["properties"]
    assert schema["properties"]["param1"]["type"] == "string"
    assert schema["properties"]["param2"]["type"] == "integer"
    assert "param1" in schema["required"]
    assert "param2" not in schema["required"]
```

### Round-Trip Testing

Test that specs can be serialized and deserialized:

```python
import json

def test_spec_serialization():
    """Test spec JSON serialization."""
    spec = {
        "name": "test_tool",
        "description": "Test description",
        "input_schema": {
            "type": "object",
            "properties": {
                "param": {"type": "string"}
            }
        }
    }

    # Serialize
    json_str = json.dumps(spec)

    # Deserialize
    restored = json.loads(json_str)

    assert restored == spec
```

## Summary

Tool specifications provide:

- **Standard format** for describing tools to LLMs
- **JSON Schema** for parameter validation
- **Provider compatibility** with automatic format conversion
- **Rich metadata** for documentation and tooling
- **Validation** to catch specification errors

**Key components**:
- `name`: Unique tool identifier
- `description`: What the tool does
- `input_schema`: JSON Schema for parameters
- `metadata`: Extended information (optional)

**Best practices**:
- Use descriptive names and documentation
- Validate all specs before deployment
- Include examples for complex tools
- Test spec generation from Python code
- Leverage Pydantic for rich validation

Next steps:
- See [Tool Fundamentals](fundamentals.md) for creating tools
- See [Tool Registry](registry.md) for managing tools
- See [Tool Development](development.md) for advanced patterns
- See [Agent Documentation](/docs/agents/) for using tools with agents
