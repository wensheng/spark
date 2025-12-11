---
title: Config
nav_order: 15
---
# Config
---

Spark uses environment variables for configuration that typically varies between environments (development, staging, production) or contains sensitive information like API keys. Environment variables take precedence over default values but are often overridden by explicit configuration in code.

## Model Provider Configuration

### OpenAI and OpenAI-Compatible Providers

#### `OPENAI_API_KEY`

**Type**: String
**Default**: None (required for OpenAI models)
**Description**: API key for authenticating with OpenAI services.

**Usage**:
```bash
export OPENAI_API_KEY="sk-..."
```

**Notes**:
- Required when using `OpenAIModel` without explicitly passing `api_key` in `client_args`
- The OpenAI Python SDK reads this variable automatically
- Never commit API keys to version control

**Example**:
```python
from spark.models.openai import OpenAIModel

# Uses OPENAI_API_KEY environment variable
model = OpenAIModel(model_id="gpt-4o")
```

#### `OPENAI_BASE_URL`

**Type**: String (URL)
**Default**: `"https://api.openai.com/v1"` (OpenAI's official endpoint)
**Description**: Base URL for OpenAI-compatible API endpoints. Use this to point to alternative providers that implement the OpenAI API specification.

**Usage**:
```bash
# Use OpenAI (default)
export OPENAI_BASE_URL="https://api.openai.com/v1"

# Use Azure OpenAI
export OPENAI_BASE_URL="https://your-resource.openai.azure.com"

# Use local provider (e.g., vLLM, LocalAI)
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

**Supported Providers**:
- **OpenAI**: Official OpenAI API (default)
- **Azure OpenAI**: Microsoft's Azure OpenAI Service
- **vLLM**: High-performance inference server
- **LocalAI**: Local model serving
- **Ollama**: Local model runner with OpenAI-compatible API
- Any service implementing the OpenAI Chat Completions API

**Example**:
```python
from spark.models.openai import OpenAIModel

# Will use OPENAI_BASE_URL if set
model = OpenAIModel(model_id="gpt-4o")

# Override environment variable
model = OpenAIModel(
    model_id="gpt-4o",
    client_args={"base_url": "http://localhost:8000/v1"}
)
```

### AWS Bedrock

#### `AWS_REGION`

**Type**: String
**Default**: `"us-west-2"`
**Description**: AWS region for Bedrock service calls.

**Usage**:
```bash
export AWS_REGION="us-east-1"
```

**Example**:
```python
from spark.models.bedrock import BedrockModel

# Uses AWS_REGION environment variable
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
```

#### AWS Credentials

AWS credentials are managed by the AWS SDK (boto3) and follow standard AWS credential resolution:

1. **Environment variables**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
2. **Shared credentials file**: `~/.aws/credentials`
3. **AWS config file**: `~/.aws/config`
4. **IAM role** (when running on EC2, ECS, Lambda, etc.)

**Usage**:
```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."  # Optional, for temporary credentials
```

**Best Practices**:
- Use IAM roles when running on AWS infrastructure
- Use credential files or AWS SSO for local development
- Never commit AWS credentials to version control
- Use least-privilege IAM policies

**Example**:
```python
from spark.models.bedrock import BedrockModel
import boto3

# Uses default AWS credential chain
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")

# Use custom session with explicit credentials
session = boto3.Session(
    aws_access_key_id="...",
    aws_secret_access_key="...",
    region_name="us-east-1"
)
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    boto_session=session
)
```

### Google Gemini

Google Gemini uses the Google Cloud SDK for authentication. Credentials are typically configured via:

1. **Application Default Credentials (ADC)**
2. **Service Account Key File**: `GOOGLE_APPLICATION_CREDENTIALS`
3. **gcloud CLI**: Authenticated via `gcloud auth login`

**Usage**:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

## Cost Tracking Configuration

### `SPARK_PRICING_CONFIG`

**Type**: String (file path)
**Default**: None (falls back to search order)
**Description**: Path to custom model pricing configuration file for cost tracking.

**Search Order** (if not set):
1. `SPARK_PRICING_CONFIG` environment variable
2. `./model_pricing.json` (current directory)
3. `~/.spark/model_pricing.json` (user home directory)
4. `<spark-package>/agents/model_pricing.json` (package default)
5. Hardcoded fallback values

**Usage**:
```bash
export SPARK_PRICING_CONFIG="/path/to/custom_pricing.json"
```

**File Format** (see [Configuration Files](files.md#model_pricingjson) for details):
```json
{
  "openai": {
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60}
  },
  "anthropic": {
    "claude-3-opus": {"input": 15.00, "output": 75.00}
  },
  "default": {"input": 5.00, "output": 15.00}
}
```

**Example**:
```python
from spark.agents.cost_tracker import CostTracker

# Uses SPARK_PRICING_CONFIG if set, otherwise searches default locations
tracker = CostTracker()

# Explicitly specify pricing config
tracker = CostTracker(pricing_config_path="/path/to/pricing.json")
```

## Cache Configuration

### `SPARK_CACHE_DIR`

**Type**: String (directory path)
**Default**: `"~/.cache/spark/"`
**Description**: Directory for caching LLM responses and other temporary data.

**Usage**:
```bash
export SPARK_CACHE_DIR="/custom/cache/path"
```

**Cache Structure**:
```
~/.cache/spark/
├── llm-responses/          # LLM response cache
│   ├── openai/             # Per-provider cache
│   │   └── <cache-key>.json
│   ├── bedrock/
│   └── gemini/
└── telemetry/              # Telemetry data (if using file-based backend)
```

**Notes**:
- Cache is automatically created with appropriate permissions
- Response cache uses SHA-256 hashes of request parameters as keys
- Cache respects TTL (time-to-live) settings
- Cache is thread-safe

**Example**:
```python
from spark.models.openai import OpenAIModel

# Enable caching with custom cache directory
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

# Cache stored in SPARK_CACHE_DIR/llm-responses/openai/
```

## Telemetry Configuration

Telemetry backends can be configured via environment variables when using backend-specific connection strings.

### SQLite Backend

No environment variables required. Configuration is specified in code:

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_sqlite(
    db_path="/path/to/telemetry.db",
    sampling_rate=1.0
)
```

### PostgreSQL Backend

PostgreSQL connection parameters can be configured via standard PostgreSQL environment variables:

#### `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

**Type**: String
**Default**: Varies by variable
**Description**: PostgreSQL connection parameters.

**Usage**:
```bash
export PGHOST="localhost"
export PGPORT="5432"
export PGDATABASE="spark_telemetry"
export PGUSER="spark"
export PGPASSWORD="..."
```

**Example**:
```python
from spark.telemetry import TelemetryConfig

# Uses PG* environment variables if not explicitly set
config = TelemetryConfig.create_postgresql(
    host="localhost",      # Overrides PGHOST
    port=5432,             # Overrides PGPORT
    database="telemetry",  # Overrides PGDATABASE
    user="spark",          # Overrides PGUSER
    password="..."         # Overrides PGPASSWORD
)
```

### OTLP Backend

OpenTelemetry Protocol (OTLP) exporters use standard OpenTelemetry environment variables:

#### `OTEL_EXPORTER_OTLP_ENDPOINT`

**Type**: String (URL)
**Default**: `"http://localhost:4317"` (gRPC) or `"http://localhost:4318"` (HTTP)
**Description**: OTLP collector endpoint.

**Usage**:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp.example.com:4317"
```

#### `OTEL_EXPORTER_OTLP_HEADERS`

**Type**: String (comma-separated key=value pairs)
**Default**: None
**Description**: Additional headers for OTLP requests (e.g., authentication).

**Usage**:
```bash
export OTEL_EXPORTER_OTLP_HEADERS="api-key=...,x-custom-header=value"
```

#### `OTEL_SERVICE_NAME`

**Type**: String
**Default**: `"spark-service"`
**Description**: Service name reported in telemetry.

**Usage**:
```bash
export OTEL_SERVICE_NAME="my-spark-app"
```

**Example**:
```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig(
    enabled=True,
    backend='otlp',
    backend_config={
        'endpoint': 'http://localhost:4317',  # Or use OTEL_EXPORTER_OTLP_ENDPOINT
        'insecure': True
    },
    resource_attributes={
        'service.name': 'my-app',
        'service.version': '1.0.0'
    }
)
```

## Debug and Logging

### Python Logging Configuration

Spark uses Python's standard `logging` module. Configure logging level via environment variables or code:

**Usage**:
```bash
# Set logging level for all Spark modules
export SPARK_LOG_LEVEL="DEBUG"

# Standard Python logging
export PYTHONUNBUFFERED=1  # Disable output buffering
```

**In Code**:
```python
import logging

# Configure Spark logging
logging.basicConfig(level=logging.INFO)
spark_logger = logging.getLogger("spark")
spark_logger.setLevel(logging.DEBUG)

# Reduce noise from dependencies
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
```

## Custom Environment Variables

Applications built with Spark can define their own environment variables. Here are common patterns:

### Application Configuration

```bash
# Application-specific settings
export SPARK_APP_ENV="production"
export SPARK_APP_DEBUG="false"
export SPARK_APP_MAX_WORKERS="4"
```

### Feature Flags

```bash
# Enable/disable features
export SPARK_ENABLE_RSI="true"
export SPARK_ENABLE_TELEMETRY="true"
export SPARK_ENABLE_GOVERNANCE="true"
```

### Custom Integrations

```bash
# Third-party service configuration
export SPARK_SLACK_WEBHOOK="https://hooks.slack.com/..."
export SPARK_DATADOG_API_KEY="..."
export SPARK_SENTRY_DSN="..."
```

**Example**:
```python
import os

# Read custom environment variables
app_env = os.getenv("SPARK_APP_ENV", "development")
debug_mode = os.getenv("SPARK_APP_DEBUG", "false").lower() == "true"
max_workers = int(os.getenv("SPARK_APP_MAX_WORKERS", "1"))

# Use in configuration
if app_env == "production":
    telemetry_config = TelemetryConfig.create_postgresql(...)
else:
    telemetry_config = TelemetryConfig.create_memory()
```

## Environment Variable Priority

When configuration is specified in multiple places, Spark uses this priority order (highest to lowest):

1. **Explicit code configuration**: Values passed directly to constructors
2. **Environment variables**: `os.getenv()` or system environment
3. **Configuration files**: Files loaded from standard locations
4. **Default values**: Hardcoded defaults in the framework

**Example**:
```python
from spark.models.openai import OpenAIModel
import os

# Priority demonstration
os.environ["OPENAI_BASE_URL"] = "http://localhost:8000"

# 1. Explicit config (highest priority)
model = OpenAIModel(
    model_id="gpt-4o",
    client_args={"base_url": "http://custom:8000"}  # This wins
)

# 2. Environment variable
model = OpenAIModel(model_id="gpt-4o")  # Uses OPENAI_BASE_URL

# 3. Default value
del os.environ["OPENAI_BASE_URL"]
model = OpenAIModel(model_id="gpt-4o")  # Uses default OpenAI endpoint
```

## Security Best Practices

### Sensitive Information

**Never commit sensitive values to version control**:
```bash
# .gitignore
.env
.env.*
*.key
credentials.json
```

**Use environment-specific files**:
```bash
# .env.development (local development)
OPENAI_API_KEY=sk-dev-...

# .env.production (production, managed by deployment system)
OPENAI_API_KEY=sk-prod-...
```

### Secret Management

For production deployments, use proper secret management:

**AWS Secrets Manager**:
```python
import boto3
import json

def load_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

secrets = load_secret("spark/production/api-keys")
os.environ["OPENAI_API_KEY"] = secrets["openai_api_key"]
```

**HashiCorp Vault**:
```python
import hvac

client = hvac.Client(url='https://vault.example.com')
client.auth.approle.login(role_id=os.getenv('VAULT_ROLE_ID'))
secret = client.secrets.kv.v2.read_secret_version(path='spark/api-keys')
os.environ["OPENAI_API_KEY"] = secret['data']['data']['openai_api_key']
```

**Kubernetes Secrets**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: spark-secrets
type: Opaque
data:
  openai-api-key: c2stLi4u  # base64 encoded
---
apiVersion: v1
kind: Pod
metadata:
  name: spark-app
spec:
  containers:
  - name: app
    env:
    - name: OPENAI_API_KEY
      valueFrom:
        secretKeyRef:
          name: spark-secrets
          key: openai-api-key
```

## Development vs Production

### Development Configuration

```bash
# .env.development
OPENAI_API_KEY=sk-dev-...
OPENAI_BASE_URL=http://localhost:8000  # Local vLLM
SPARK_CACHE_DIR=./cache
SPARK_PRICING_CONFIG=./dev_pricing.json
SPARK_LOG_LEVEL=DEBUG
```

### Production Configuration

```bash
# .env.production (managed by secret manager)
OPENAI_API_KEY=sk-prod-...
AWS_REGION=us-east-1
SPARK_CACHE_DIR=/var/cache/spark
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.production.com
SPARK_LOG_LEVEL=INFO
```

## Validation and Troubleshooting

### Check Current Configuration

```python
import os

# Print all SPARK-related environment variables
for key, value in os.environ.items():
    if key.startswith('SPARK_') or key in ['OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AWS_REGION']:
        # Mask sensitive values
        display_value = value if 'KEY' not in key and 'SECRET' not in key else '***'
        print(f"{key}={display_value}")
```

### Common Issues

**Issue**: Model API calls failing with authentication errors

**Solution**: Verify API key is set correctly:
```bash
# Check if variable is set
echo $OPENAI_API_KEY

# Test with curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Issue**: Telemetry not connecting to database

**Solution**: Verify connection parameters:
```bash
# Test PostgreSQL connection
psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -c "SELECT 1"
```

**Issue**: Cache directory permission errors

**Solution**: Ensure directory is writable:
```bash
# Check permissions
ls -la $SPARK_CACHE_DIR

# Fix permissions
chmod 755 $SPARK_CACHE_DIR
```

## See Also

- [Configuration Files](files.md) - File-based configuration options
- [Model Configuration](../models/models.md) - Model-specific settings
- [Telemetry Configuration](telemetry-config.md) - TelemetryConfig reference
- [Security Best Practices](../architecture/security.md) - Security guidelines
