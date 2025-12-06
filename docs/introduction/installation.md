# Installation

This guide covers installing Spark ADK and its dependencies for different use cases.

## System Requirements

- **Python**: 3.12 or higher
- **Operating System**: Linux, macOS, or Windows
- **Memory**: 4GB RAM minimum (8GB+ recommended for RSI and large graphs)
- **Storage**: 500MB for base installation, additional space for telemetry data

## Quick Installation

Install Spark via pip:

```bash
pip install spark
```

Verify installation:

```bash
python -c "from spark.nodes import Node; from spark.graphs import Graph; print('Spark installed successfully!')"
```

## Installation Methods

### 1. Basic Installation

For basic node and graph functionality:

```bash
pip install spark
```

This also installs core dependencies.

### 2. Development Installation

To work on Spark itself or run examples from the repository:

```bash
# Clone repository
git clone https://github.com/wensheng/spark.git
cd spark

# Install in editable mode
pip install -e .

# Install development and test dependencies
pip install pytest pytest-asyncio black boto3 google-genai ddgs
```

Verify:

```bash
# Run tests
pytest

# Run example
python -m examples.e001_hello
```

### 3. Docker Installation

Use Docker for isolated environments:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install Spark
RUN pip install spark

# Copy your application
COPY . .

CMD ["python", "your_app.py"]
```

Build and run:

```bash
docker build -t spark-app .
docker run spark-app
```

## Optional Dependencies

Spark uses optional dependencies for specific features. Install only what you need.

### LLM Models

OpenAI package is installed when you install `spark`.

**Environment setup:**
```bash
export OPENAI_API_KEY="sk-..."

# For custom providers
export OPENAI_API_BASE="http://localhost:11434/v1"  # Ollama example
```

**Usage:**
```python
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-5-mini")
```

#### AWS Bedrock

```bash
pip install boto3
```

Required for:
- `BedrockModel` class
- AWS Bedrock models (Claude, Titan, etc.)

**AWS credentials setup:**
```bash
# Option 1: AWS CLI
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"
```

**Usage:**
```python
from spark.models.bedrock import BedrockModel

model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
```

#### Google Gemini

```bash
pip install google-genai
```

Required for:
- `GeminiModel` class
- Google Gemini models

**Environment setup:**
```bash
export GOOGLE_API_KEY="..."
```

**Usage:**
```python
from spark.models.gemini import GeminiModel

model = GeminiModel(model_id="gemini-2.5-flash")
```

### Telemetry Backends

#### PostgreSQL Backend (Production)

```bash
pip install asyncpg
```

Required for:
- PostgreSQL telemetry backend
- Production-grade persistent storage

**Database setup:**
```bash
# Create database
createdb spark_telemetry

# Set connection URL
export DATABASE_URL="postgresql://user:pass@localhost/spark_telemetry"
```

**Usage:**
```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_postgres(
    connection_string="postgresql://user:pass@localhost/spark_telemetry"
)
```

#### OTLP Backend (Observability Platforms)

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

Required for:
- OTLP telemetry backend
- Export to Jaeger, Zipkin, Honeycomb, etc.

**Usage:**
```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_otlp(
    endpoint="http://localhost:4317"
)
```

### Tools and Utilities

#### Web Search

```bash
pip install ddgs search-tool
```

Required for:
- `search_web()` utility function
- DuckDuckGo web search

**Usage:**
```python
from spark.utils.common import search_web

results = search_web("Python async programming")
```

#### Response Caching (Optional)

```bash
pip install filelock
```

Optional for:
- Thread-safe file operations in model response cache
- Graceful fallback if not installed


### Complete Installation (All Features)

```bash
pip install spark \
    httpx asyncpg \
    opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp \
    ddgs search-tool filelock
```

## Environment Configuration

### Configuration File

Create `.env` file in your project:

```bash
# LLM Providers
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
GOOGLE_API_KEY=...

# Telemetry
DATABASE_URL=postgresql://user:pass@localhost/spark_telemetry

# Custom Settings
SPARK_LOG_LEVEL=INFO
SPARK_CACHE_DIR=~/.cache/spark
SPARK_PRICING_CONFIG=./model_pricing.json
```

Load with `python-dotenv`:

```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()
```

### Cache Directory

Spark uses `~/.cache/spark/` for:
- LLM response caching (`llm-responses/`)
- Experience database (`rsi/experience.db`)
- Downloaded models or data

Override with environment variable:

```bash
export SPARK_CACHE_DIR="/custom/path"
```

### Logging Configuration

Configure logging level:

```bash
export SPARK_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

Or in code:

```python
import logging
logging.getLogger('spark').setLevel(logging.DEBUG)
```

## Verification and Testing

### Verify Core Installation

```python
# test_spark.py
from spark.nodes import Node
from spark.graphs import Graph
from spark.utils import arun

class HelloNode(Node):
    async def process(self, context):
        print("Spark is working!")
        return {'done': True}

if __name__ == "__main__":
    node = HelloNode()
    arun(node.run())
```

Run:

```bash
python test_spark.py
# Output: Spark is working!
```

### Verify Agent System

```python
# test_agent.py
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o-mini")
config = AgentConfig(model=model)
agent = Agent(config=config)

result = agent.run("Say hello!")
print(result)
```

### Verify Telemetry

```python
# test_telemetry.py
from spark.telemetry import TelemetryConfig, TelemetryManager
from spark.graphs import Graph
from spark.nodes import Node
from spark.utils import arun

class TestNode(Node):
    async def process(self, context):
        return {'done': True}

async def main():
    config = TelemetryConfig.create_memory()
    graph = Graph(start=TestNode(), telemetry_config=config)
    await graph.run()

    manager = TelemetryManager.get_instance()
    await manager.flush()
    traces = await manager.query_traces()
    print(f"Collected {len(traces)} traces")

arun(main())
```

### Run Test Suite

If installed from source:

```bash
# Run all tests
pytest

# Run specific test
pytest tests/unit/test_base.py

# Run with coverage
pytest --cov=spark --cov-report=html
```

### Run Examples

```bash
# Basic examples
python -m examples.e001_hello
python -m examples.e002_simple_flow

# Agent examples
python -m examples.e006_llm_tool
python -m examples.e010_reasoning_strategies

# Telemetry example
python -m examples.e011_telemetry

# RSI examples
python -m examples.e012_rsi_phase1
python -m examples.e013_rsi_phase2
```

## IDE Setup

### VS Code

Install Python extension and create `.vscode/settings.json`:

```json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length", "120"],
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "editor.formatOnSave": true,
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

### PyCharm

1. Set Python interpreter to 3.12+
2. Enable pytest in Settings → Tools → Python Integrated Tools
3. Set line length to 120 in Settings → Tools → Black
4. Mark `spark/` as Sources Root

### Type Checking

Install mypy for type checking:

```bash
pip install mypy
```

Create `mypy.ini`:

```ini
[mypy]
python_version = 3.12
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False
ignore_missing_imports = True
```

Run type checker:

```bash
mypy spark/
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'spark'`

**Solution**: Install Spark or add to PYTHONPATH:
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/spark"
```

### Dependency Conflicts

**Problem**: Conflicting package versions

**Solution**: Use virtual environment:
```bash
python -m venv spark-env
source spark-env/bin/activate  # Linux/Mac
# or
spark-env\Scripts\activate  # Windows
pip install spark-adk
```

### API Key Issues

**Problem**: `Authentication failed` or `API key not found`

**Solution**: Verify environment variables:
```bash
echo $OPENAI_API_KEY
# Should print your key
```

### Database Connection Issues

**Problem**: PostgreSQL connection fails

**Solution**: Check connection string and database exists:
```bash
psql $DATABASE_URL -c "SELECT 1"
```

### Permission Errors

**Problem**: `Permission denied` when accessing cache

**Solution**: Check cache directory permissions:
```bash
chmod 755 ~/.cache/spark
```

## Next Steps

Now that Spark is installed, continue to:
- **[Quick Start](quickstart.md)**: Build your first Spark application
- **[Core Concepts](concepts.md)**: Understand Spark's architecture
- **[Tutorials](../tutorials/README.md)**: Step-by-step guides
- **[Examples](../../examples/)**: Working code examples

## Getting Help

- Check the [Troubleshooting Guide](../guides/troubleshooting.md)
- Review [Examples](../../examples/) for working code
- Open an issue on [GitHub](https://github.com/yourusername/spark/issues)
- Search existing issues for solutions
