---
title: Model Classes
parent: API
nav_order: 1
---
# Model Classes
---

This document provides the complete API reference for Spark's model system, including the abstract Model base class, provider implementations (OpenAI, Bedrock, Gemini), and the response caching system.

## Table of Contents

- [Model (Abstract Base)](#model-abstract-base)
- [OpenAIModel](#openaimodel)
- [BedrockModel](#bedrockmodel)
- [GeminiModel](#geminimodel)
- [EchoModel](#echomodel)
- [CacheManager](#cachemanager)
- [CacheConfig](#cacheconfig)

---

## Model (Abstract Base)

**Module**: `spark.models.base`

Abstract base class for all model providers in Spark. Provides a standardized interface for LLM interactions with optional response caching.

### Constructor

```python
def __init__(self) -> None
```

Initializes model with optional cache support (disabled by default).

### Abstract Methods

#### get_text

```python
@abstractmethod
async def get_text(
    self,
    messages: Messages,
    system_prompt: Optional[str] = None,
    tool_specs: list[ToolSpec] | None = None,
    tool_choice: ToolChoice | None = None,
    **kwargs: Any
) -> ChatCompletionAssistantMessage
```

Get text completion from the model.

**Parameters:**
- `messages` (Messages): List of message dictionaries with `role` and `content`
- `system_prompt` (str, optional): System prompt to guide model behavior
- `tool_specs` (list[ToolSpec], optional): Tool specifications for function calling
- `tool_choice` (ToolChoice, optional): Tool selection strategy
- `**kwargs`: Provider-specific parameters (temperature, max_tokens, etc.)

**Returns:** ChatCompletionAssistantMessage with:
- `content`: Text content or structured output
- `stop_reason`: Reason generation stopped ("end_turn", "tool_use", etc.)
- `tool_calls`: Tool calls if any (for tool_use stop_reason)
- `raw`: Raw provider response

**Example:**
```python
messages = [
    {"role": "user", "content": [{"text": "What is 2+2?"}]}
]

response = await model.get_text(
    messages=messages,
    system_prompt="You are a helpful assistant.",
    temperature=0.7
)

print(response['content'])  # "2+2 equals 4"
```

#### get_json

```python
@abstractmethod
async def get_json(
    self,
    output_model: Type[T],
    messages: Messages,
    system_prompt: Optional[str] = None,
    tool_specs: list[ToolSpec] | None = None,
    tool_choice: ToolChoice | None = None,
    **kwargs: Any
) -> ChatCompletionAssistantMessage
```

Get structured JSON output from the model.

**Parameters:**
- `output_model` (Type[BaseModel]): Pydantic model defining expected output structure
- `messages` (Messages): List of message dictionaries
- `system_prompt` (str, optional): System prompt
- `tool_specs` (list[ToolSpec], optional): Tool specifications
- `tool_choice` (ToolChoice, optional): Tool selection strategy
- `**kwargs`: Provider-specific parameters

**Returns:** ChatCompletionAssistantMessage with structured output in `content` field.

**Raises:**
- `ValidationException`: If response doesn't match output_model schema

**Example:**
```python
from pydantic import BaseModel

class Answer(BaseModel):
    result: int
    explanation: str

messages = [{"role": "user", "content": [{"text": "What is 2+2?"}]}]

response = await model.get_json(
    output_model=Answer,
    messages=messages
)

# response['content'] is a dict matching Answer schema
print(response['content']['result'])  # 4
```

#### update_config

```python
@abstractmethod
def update_config(self, **model_config: Any) -> None
```

Update the model configuration with provided arguments.

**Parameters:**
- `**model_config`: Configuration overrides

#### get_config

```python
@abstractmethod
def get_config(self) -> Any
```

Get the current model configuration.

**Returns:** Model configuration dictionary.

### Caching Methods

#### _init_cache (internal)

```python
def _init_cache(self, cache_config: Optional[Any] = None) -> None
```

Initialize cache manager if caching is enabled. Called automatically during model initialization.

**Parameters:**
- `cache_config` (CacheConfig, optional): Cache configuration

#### _get_from_cache (internal)

```python
def _get_from_cache(
    self,
    messages: Messages,
    system_prompt: Optional[str] = None,
    tool_specs: Optional[list[ToolSpec]] = None,
    **kwargs: Any
) -> Optional[ChatCompletionAssistantMessage]
```

Try to retrieve response from cache. Returns None if cache miss or caching disabled.

#### _save_to_cache (internal)

```python
def _save_to_cache(
    self,
    messages: Messages,
    response: ChatCompletionAssistantMessage,
    system_prompt: Optional[str] = None,
    tool_specs: Optional[list[ToolSpec]] = None,
    **kwargs: Any
) -> None
```

Save response to cache. No-op if caching disabled.

### Serialization

#### to_spec_dict

```python
def to_spec_dict(self) -> dict[str, Any]
```

Serialize model to spec-compatible dictionary.

**Returns:** Dictionary with type, provider, model_id, and config.

**Example:**
```python
spec = model.to_spec_dict()
# {
#   "type": "OpenAIModel",
#   "provider": "openai",
#   "model_id": "gpt-5-mini",
#   "config": {...}
# }
```

#### from_spec_dict (classmethod)

```python
@classmethod
def from_spec_dict(cls: Type[ModelType], spec: dict[str, Any]) -> ModelType
```

Deserialize model from spec dictionary. Must be overridden by subclasses.

**Parameters:**
- `spec`: Dictionary containing model configuration

**Returns:** Model instance.

**Raises:**
- `NotImplementedError`: If subclass doesn't override this method

---

## OpenAIModel

**Module**: `spark.models.openai`

OpenAI model provider supporting GPT-4, GPT-3.5, and compatible APIs.

### Constructor

```python
def __init__(
    self,
    client_args: Optional[dict[str, Any]] = None,
    **model_config: Unpack[OpenAIConfig]
) -> None
```

**Parameters:**
- `client_args` (dict, optional): Arguments for the OpenAI client
  - `api_key`: API key (defaults to OPENAI_API_KEY env var)
  - `base_url`: Custom base URL for OpenAI-compatible providers
  - `timeout`: Request timeout
  - `max_retries`: Maximum retry attempts
- `**model_config`: Configuration options (see OpenAIConfig)

### Configuration (OpenAIConfig)

```python
class OpenAIConfig(TypedDict, total=False):
    model_id: Required[str]
    params: Optional[dict[str, Any]]
    enable_cache: bool
    cache_ttl_seconds: int
```

**Fields:**
- **model_id** (str, required): Model identifier
    - GPT-4 models: `"gpt-5-mini"`, `"gpt-5-mini"`, `"gpt-4-turbo"`
  - GPT-3.5 models: `"gpt-3.5-turbo"`
  - See [OpenAI Models](https://platform.openai.com/docs/models) for full list
- **params** (dict, optional): Model parameters
  - `temperature` (float): Randomness (0.0-2.0, default: 1.0)
  - `max_tokens` (int): Maximum tokens to generate
  - `top_p` (float): Nucleus sampling (0.0-1.0)
  - `frequency_penalty` (float): Penalize frequent tokens (-2.0-2.0)
  - `presence_penalty` (float): Penalize present tokens (-2.0-2.0)
  - `stop` (list[str]): Stop sequences
  - See [OpenAI API Reference](https://platform.openai.com/docs/api-reference/chat/create)
- **enable_cache** (bool): Enable response caching (default: False)
- **cache_ttl_seconds** (int): Cache TTL in seconds (default: 86400 = 24 hours)

### Methods

#### update_config

```python
def update_config(self, **model_config: Unpack[OpenAIConfig]) -> None
```

Update configuration with provided arguments.

#### get_config

```python
def get_config(self) -> OpenAIConfig
```

Get current OpenAI configuration.

**Returns:** OpenAIConfig dictionary.

### Examples

#### Basic Usage

```python
from spark.models.openai import OpenAIModel

model = OpenAIModel(
    model_id="gpt-5-mini",
    params={
        "temperature": 0.7,
        "max_tokens": 1000
    }
)

messages = [{"role": "user", "content": [{"text": "Hello!"}]}]
response = await model.get_text(messages=messages)
print(response['content'])
```

#### With Caching

```python
model = OpenAIModel(
    model_id="gpt-5-mini",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

# First call hits API
response1 = await model.get_text(messages=messages)

# Second identical call returns cached response
response2 = await model.get_text(messages=messages)  # Cache hit!
```

#### With Custom Base URL (OpenAI-compatible providers)

```python
model = OpenAIModel(
    client_args={
        "base_url": "https://api.together.xyz/v1",
        "api_key": "your-together-api-key"
    },
    model_id="mistralai/Mixtral-8x7B-Instruct-v0.1"
)
```

#### With Structured Output

```python
from pydantic import BaseModel

class UserInfo(BaseModel):
    name: str
    age: int
    occupation: str

model = OpenAIModel(model_id="gpt-5-mini")

messages = [
    {"role": "user", "content": [{"text": "Extract info: John is 30 and works as a teacher"}]}
]

response = await model.get_json(
    output_model=UserInfo,
    messages=messages
)

# response['content'] matches UserInfo schema
```

---

## BedrockModel

**Module**: `spark.models.bedrock`

AWS Bedrock model provider supporting Claude, Titan, and other Bedrock models.

### Constructor

```python
def __init__(
    self,
    *,
    boto_session: Optional[boto3.Session] = None,
    boto_client_config: Optional[BotocoreConfig] = None,
    region_name: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    **model_config: Unpack[BedrockConfig]
) -> None
```

**Parameters:**
- `boto_session` (boto3.Session, optional): Boto3 session for AWS credentials
- `boto_client_config` (BotocoreConfig, optional): Boto client configuration
- `region_name` (str, optional): AWS region (defaults to AWS_REGION env var or "us-west-2")
- `endpoint_url` (str, optional): Custom endpoint URL for VPC endpoints (PrivateLink)
- `**model_config`: Configuration options (see BedrockConfig)

### Configuration (BedrockConfig)

```python
class BedrockConfig(TypedDict, total=False):
    model_id: str
    max_tokens: Optional[int]
    temperature: Optional[float]
    top_p: Optional[float]
    stop_sequences: Optional[list[str]]
    streaming: Optional[bool]
    cache_prompt: Optional[str]
    cache_tools: Optional[str]
    guardrail_id: Optional[str]
    guardrail_version: Optional[str]
    guardrail_trace: Optional[Literal["enabled", "disabled", "enabled_full"]]
    guardrail_stream_processing_mode: Optional[Literal["sync", "async"]]
    include_tool_result_status: Optional[Literal["auto"] | bool]
    additional_args: Optional[dict[str, Any]]
    additional_request_fields: Optional[dict[str, Any]]
    additional_response_field_paths: Optional[list[str]]
    enable_cache: bool
    cache_ttl_seconds: int
```

**Key Fields:**
- **model_id** (str): Bedrock model identifier
  - Claude models: `"us.anthropic.claude-sonnet-4-5-20250929-v1:0"`, `"anthropic.claude-3-5-sonnet-20240620-v1:0"`
  - See [AWS Bedrock Models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
- **max_tokens** (int): Maximum tokens to generate (default: model-specific)
- **temperature** (float): Randomness (0.0-1.0)
- **top_p** (float): Nucleus sampling (0.0-1.0)
- **stop_sequences** (list[str]): Sequences to stop generation
- **streaming** (bool): Enable streaming (default: True)
- **cache_prompt** (str): Cache point type for system prompt ("default", "aggressive")
- **cache_tools** (str): Cache point type for tools
- **guardrail_id** (str): Guardrail ID to apply
- **guardrail_version** (str): Guardrail version
- **include_tool_result_status** ("auto" | bool): Include status in tool results (default: "auto")

### Methods

#### update_config

```python
def update_config(self, **model_config: Unpack[BedrockConfig]) -> None
```

Update configuration with provided arguments.

#### get_config

```python
def get_config(self) -> BedrockConfig
```

Get current Bedrock configuration.

### Examples

#### Basic Usage

```python
from spark.models.bedrock import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-west-2",
    max_tokens=2000,
    temperature=0.7
)

messages = [{"role": "user", "content": [{"text": "Hello!"}]}]
response = await model.get_text(messages=messages)
```

#### With Custom AWS Session

```python
import boto3

session = boto3.Session(
    aws_access_key_id="...",
    aws_secret_access_key="...",
    region_name="us-east-1"
)

model = BedrockModel(
    boto_session=session,
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
```

#### With Prompt Caching

```python
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    cache_prompt="default",  # Cache system prompt
    cache_tools="default"     # Cache tools
)

# System prompt and tools will be cached for faster repeated calls
```

#### With Guardrails

```python
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    guardrail_id="your-guardrail-id",
    guardrail_version="1",
    guardrail_trace="enabled"
)

# Model calls will be filtered through configured guardrails
```

#### With VPC PrivateLink

```python
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    endpoint_url="https://your-vpc-endpoint.amazonaws.com",
    region_name="us-west-2"
)
```

---

## GeminiModel

**Module**: `spark.models.gemini`

Google Gemini model provider supporting Gemini Pro, Flash, and other Gemini models.

### Constructor

```python
def __init__(
    self,
    model_id: str = "gemini-1.5-pro",
    api_key: Optional[str] = None,
    **model_config
) -> None
```

**Parameters:**
- `model_id` (str): Gemini model identifier (default: "gemini-1.5-pro")
  - Available models: `"gemini-1.5-pro"`, `"gemini-1.5-flash"`, `"gemini-1.0-pro"`
- `api_key` (str, optional): Google API key (defaults to GOOGLE_API_KEY env var)
- `**model_config`: Additional configuration options

### Examples

```python
from spark.models.gemini import GeminiModel

model = GeminiModel(
    model_id="gemini-1.5-pro",
    api_key="your-google-api-key"
)

messages = [{"role": "user", "content": [{"text": "Hello!"}]}]
response = await model.get_text(messages=messages)
```

---

## EchoModel

**Module**: `spark.models.echo`

Mock model that echoes inputs. Useful for testing and development.

### Constructor

```python
def __init__(self, model_id: str = "echo-model") -> None
```

**Parameters:**
- `model_id` (str): Model identifier for the echo model

### Behavior

- Returns the last user message as the response
- Supports both text and JSON output modes
- No actual API calls made
- Useful for testing agent logic without API costs

### Example

```python
from spark.models.echo import EchoModel

model = EchoModel()

messages = [{"role": "user", "content": [{"text": "Test message"}]}]
response = await model.get_text(messages=messages)

# response['content'] == "Test message"
```

---

## CacheManager

**Module**: `spark.models.cache`

Manages LLM response caching across all model providers. Singleton instance provides thread-safe caching with file-based storage.

### Constructor

```python
def __init__(self, config: Optional[CacheConfig] = None) -> None
```

**Parameters:**
- `config` (CacheConfig, optional): Cache configuration

### Class Methods

#### get_instance

```python
@classmethod
def get_instance(cls, config: Optional[CacheConfig] = None) -> CacheManager
```

Get or create singleton cache manager instance.

**Parameters:**
- `config`: Cache configuration (only used if instance doesn't exist yet)

**Returns:** Singleton CacheManager instance.

#### reset_instance

```python
@classmethod
def reset_instance(cls) -> None
```

Reset the singleton instance. Useful for testing.

### Methods

#### generate_cache_key

```python
def generate_cache_key(
    self,
    provider: str,
    model_id: str,
    messages: list[dict[str, Any]],
    system_prompt: Optional[str] = None,
    tool_specs: Optional[list[dict[str, Any]]] = None,
    **kwargs: Any
) -> str
```

Generate deterministic cache key from request parameters.

**Parameters:**
- `provider`: Model provider name (e.g., "openai", "bedrock")
- `model_id`: Model identifier
- `messages`: Messages array
- `system_prompt`: Optional system prompt
- `tool_specs`: Optional tool specifications
- `**kwargs`: Additional parameters (temperature, top_p, etc.)

**Returns:** SHA-256 hash string as cache key.

**Example:**
```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()
cache_key = manager.generate_cache_key(
    provider="openai",
    model_id="gpt-5-mini-mini",
    messages=[...],
    system_prompt="You are helpful",
    temperature=0.7
)
```

#### get

```python
def get(self, cache_key: str, provider: str) -> Optional[dict[str, Any]]
```

Retrieve cached response if exists and not expired.

**Parameters:**
- `cache_key`: Cache key to look up
- `provider`: Model provider name

**Returns:** Cached response dict or None if not found/expired.

#### set

```python
def set(
    self,
    cache_key: str,
    provider: str,
    model_id: str,
    request: dict[str, Any],
    response: dict[str, Any]
) -> None
```

Store response in cache.

**Parameters:**
- `cache_key`: Cache key
- `provider`: Model provider name
- `model_id`: Model identifier
- `request`: Request data to cache
- `response`: Response data to cache

#### cleanup_expired

```python
def cleanup_expired(self) -> int
```

Remove expired cache entries.

**Returns:** Count of removed entries.

#### clear_all

```python
def clear_all(self) -> None
```

Clear all cache entries.

#### get_stats

```python
def get_stats(self) -> dict[str, Any]
```

Get cache statistics.

**Returns:** Dictionary with:
- `total_entries`: Total number of cached entries
- `total_size_bytes`: Total size in bytes
- `by_provider`: Breakdown by provider with entries and size

**Example:**
```python
manager = CacheManager.get_instance()
stats = manager.get_stats()
print(f"Total entries: {stats['total_entries']}")
print(f"Total size: {stats['total_size_bytes'] / 1024 / 1024:.2f} MB")

# Cleanup expired entries
removed = manager.cleanup_expired()
print(f"Removed {removed} expired entries")

# Clear all cache
manager.clear_all()
```

---

## CacheConfig

**Module**: `spark.models.cache`

Configuration for LLM response cache.

```python
@dataclass
class CacheConfig:
    enabled: bool = False
    cache_dir: Optional[Path] = None
    ttl_seconds: int = 86400  # 24 hours
    max_cache_size_mb: int = 1000  # 1GB
    cleanup_interval_seconds: int = 3600  # 1 hour
```

**Fields:**
- **enabled** (bool): Whether caching is enabled (default: False)
- **cache_dir** (Path, optional): Directory for cache storage (default: ~/.cache/spark/llm-responses)
- **ttl_seconds** (int): Time-to-live for cache entries in seconds (default: 86400 = 24 hours)
- **max_cache_size_mb** (int): Maximum cache size in MB (default: 1000 = 1GB)
- **cleanup_interval_seconds** (int): Interval for automatic cleanup in seconds (default: 3600 = 1 hour)

### Example

```python
from spark.models.cache import CacheConfig, CacheManager
from pathlib import Path

config = CacheConfig(
    enabled=True,
    cache_dir=Path("/custom/cache/dir"),
    ttl_seconds=7200,  # 2 hours
    max_cache_size_mb=500
)

manager = CacheManager(config)

# Or use environment variable to override cache dir
import os
os.environ['SPARK_CACHE_DIR'] = '/tmp/spark-cache'
```

---

## Response Caching

All models support optional response caching to avoid redundant API calls and improve performance.

### How It Works

1. **Cache Key Generation**: Deterministic hash from provider, model_id, messages, prompts, tools, and parameters
2. **Cache Lookup**: Before making API call, check if response exists in cache
3. **Cache Storage**: After API call, store response with TTL
4. **Automatic Expiration**: Entries expire after TTL
5. **Thread-Safe**: File locks prevent concurrent access issues

### Cache Location

Cache is stored in the filesystem:
- Default: `~/.cache/spark/llm-responses/<provider>/<cache_key>.json`
- Override via `SPARK_CACHE_DIR` environment variable
- Organized by provider (openai, bedrock, gemini, etc.)

### Enabling Cache

```python
from spark.models.openai import OpenAIModel

# Enable with default TTL (24 hours)
model = OpenAIModel(
    model_id="gpt-5-mini-mini",
    enable_cache=True
)

# Enable with custom TTL
model = OpenAIModel(
    model_id="gpt-5-mini-mini",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)
```

### Cache Benefits

- **Speed**: Cache hits return instantly (100-500x faster than API calls)
- **Cost Savings**: Avoid redundant API charges for identical requests
- **Rate Limiting**: Reduce API call volume
- **Development**: Faster iteration during testing

### Cache Management

```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# Get statistics
stats = manager.get_stats()
print(f"Total entries: {stats['total_entries']}")
print(f"Total size: {stats['total_size_bytes'] / 1024 / 1024:.2f} MB")

# Cleanup expired entries
removed = manager.cleanup_expired()

# Clear all cache
manager.clear_all()
```

### Important Notes

- Caching is **disabled by default** for safe, predictable behavior
- Cache keys are generated from ALL parameters that affect output
- Changing temperature, max_tokens, etc. creates different cache keys
- Cache is persistent across Python sessions
- Cache hits are logged for debugging

---

## Complete Example

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.models.bedrock import BedrockModel
from spark.tools.decorator import tool

# Define a tool
@tool
def search_web(query: str) -> str:
    """Search the web."""
    return f"Results for: {query}"

# OpenAI model with caching
openai_model = OpenAIModel(
    model_id="gpt-5-mini-mini",
    enable_cache=True,
    cache_ttl_seconds=3600,
    params={
        "temperature": 0.7,
        "max_tokens": 1000
    }
)

# Bedrock model with prompt caching
bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-west-2",
    cache_prompt="default",
    cache_tools="default",
    temperature=0.7
)

# Use with agent
config = AgentConfig(
    model=openai_model,  # or bedrock_model
    tools=[search_web],
    system_prompt="You are a helpful assistant."
)

agent = Agent(config=config)

# First call - API request
result1 = await agent.process(context)

# Second identical call - cache hit!
result2 = await agent.process(context)
```

---

## See Also

- [Agent Classes](agents.md) - Using models with agents
- [Tool Classes](tools.md) - Tool calling with models
- [Examples](/examples/) - Complete model examples
