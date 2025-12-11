---
title: Tool Development
parent: Tools
nav_order: 2
---
# Tool Development
---

Tool development goes beyond basic function decoration. This guide covers:

- Creating custom tools with complex logic
- Parameter validation with Pydantic
- Return value handling and serialization
- Error handling and recovery
- Long-running and streaming tools
- Tool composition patterns
- Dynamic context-aware tools
- Testing strategies

## Creating Custom Tools

### Basic Custom Tool

Start with a well-structured tool:

```python
from spark.tools.decorator import tool
from typing import Optional

@tool
def process_document(
    file_path: str,
    output_format: str = "json",
    include_metadata: bool = True
) -> dict:
    """Process a document and extract structured data.

    This tool reads various document formats (PDF, DOCX, TXT) and
    extracts structured information using NLP techniques.

    Args:
        file_path: Path to the document file
        output_format: Output format (json, xml, csv)
        include_metadata: Whether to include file metadata

    Returns:
        Dictionary containing:
        - content: Extracted text content
        - entities: Named entities found
        - metadata: File metadata (if requested)

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If output_format is not supported
    """
    # Validate inputs
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if output_format not in ["json", "xml", "csv"]:
        raise ValueError(f"Unsupported format: {output_format}")

    # Process document
    content = extract_text(file_path)
    entities = extract_entities(content)

    result = {
        "content": content,
        "entities": entities
    }

    if include_metadata:
        result["metadata"] = get_file_metadata(file_path)

    return result
```

### Complex Tool with State

Tools that maintain internal state:

```python
from spark.tools.decorator import tool
from typing import Optional
import time

class RateLimiter:
    """Rate limiter for API calls."""

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = []

    def can_proceed(self) -> bool:
        """Check if we can make another call."""
        now = time.time()
        # Remove old calls outside window
        self.calls = [t for t in self.calls if now - t < self.window_seconds]
        return len(self.calls) < self.max_calls

    def record_call(self):
        """Record a new call."""
        self.calls.append(time.time())

# Create rate limiter instance
api_rate_limiter = RateLimiter(max_calls=10, window_seconds=60)

@tool
async def api_call(endpoint: str, params: Optional[dict] = None) -> dict:
    """Call external API with rate limiting.

    Args:
        endpoint: API endpoint to call
        params: Optional query parameters

    Returns:
        API response as dictionary

    Raises:
        RateLimitError: If rate limit is exceeded
    """
    if not api_rate_limiter.can_proceed():
        raise RateLimitError("Rate limit exceeded. Please try again later.")

    api_rate_limiter.record_call()

    # Make API call
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint, params=params or {})
        return response.json()
```

### Tool with Configuration

Tools that accept configuration:

```python
from spark.tools.decorator import tool
from pydantic import BaseModel
from typing import Optional

class SearchConfig(BaseModel):
    """Configuration for search tool."""
    max_results: int = 10
    include_snippets: bool = True
    sort_by: str = "relevance"
    timeout_seconds: float = 5.0

# Global config instance
search_config = SearchConfig()

@tool
async def search(
    query: str,
    config_override: Optional[dict] = None
) -> list[dict]:
    """Search with configurable options.

    Args:
        query: The search query
        config_override: Optional config overrides

    Returns:
        List of search results
    """
    # Merge config with overrides
    config = search_config.copy()
    if config_override:
        config = config.copy(update=config_override)

    # Perform search with config
    results = await perform_search(
        query=query,
        max_results=config.max_results,
        timeout=config.timeout_seconds
    )

    if config.include_snippets:
        results = add_snippets(results)

    return results

# Update global config
def configure_search(max_results: int = 10, timeout: float = 5.0):
    """Update search configuration."""
    global search_config
    search_config = SearchConfig(
        max_results=max_results,
        timeout_seconds=timeout
    )
```

## Parameter Validation with Pydantic

### Custom Validators

Add validation logic using Pydantic:

```python
from spark.tools.decorator import tool
from pydantic import BaseModel, validator, Field
from typing import List

class SearchParams(BaseModel):
    """Validated search parameters."""

    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(10, ge=1, le=100)
    categories: List[str] = Field(default_factory=list)
    min_score: float = Field(0.0, ge=0.0, le=1.0)

    @validator('query')
    def query_not_empty(cls, v):
        """Ensure query is not just whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()

    @validator('categories')
    def valid_categories(cls, v):
        """Ensure categories are valid."""
        valid = {'tech', 'science', 'business', 'health'}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}")
        return v

@tool
def search_with_validation(params: SearchParams) -> list[dict]:
    """Search with validated parameters.

    Args:
        params: Validated search parameters

    Returns:
        Search results matching parameters
    """
    # Parameters are already validated by Pydantic
    return perform_search(
        query=params.query,
        max_results=params.max_results,
        categories=params.categories,
        min_score=params.min_score
    )

# Usage - validation happens automatically
try:
    results = search_with_validation(SearchParams(
        query="   ",  # Invalid: whitespace only
        max_results=1000  # Invalid: exceeds max
    ))
except ValidationError as e:
    print(f"Validation failed: {e}")
```

### Constrained Types

Use Pydantic's constrained types:

```python
from pydantic import BaseModel, constr, conint, confloat, conlist
from spark.tools.decorator import tool

class DocumentRequest(BaseModel):
    """Validated document request."""

    # String constraints
    doc_id: constr(min_length=5, max_length=50, regex=r'^DOC-\d+$')

    # Integer constraints
    max_pages: conint(ge=1, le=1000)

    # Float constraints
    confidence_threshold: confloat(ge=0.0, le=1.0)

    # List constraints
    extract_sections: conlist(str, min_items=1, max_items=10)

@tool
def get_document(request: DocumentRequest) -> dict:
    """Get document with validated constraints.

    Args:
        request: Validated document request

    Returns:
        Document data
    """
    return fetch_document(
        doc_id=request.doc_id,
        max_pages=request.max_pages,
        threshold=request.confidence_threshold,
        sections=request.extract_sections
    )
```

### Union Types and Discriminators

Handle multiple input formats:

```python
from pydantic import BaseModel, Field
from typing import Union, Literal
from spark.tools.decorator import tool

class IdSearch(BaseModel):
    """Search by ID."""
    type: Literal["id"] = "id"
    value: str

class TextSearch(BaseModel):
    """Search by text."""
    type: Literal["text"] = "text"
    query: str
    fuzzy: bool = False

class TagSearch(BaseModel):
    """Search by tags."""
    type: Literal["tags"] = "tags"
    tags: list[str]
    match_all: bool = False

SearchRequest = Union[IdSearch, TextSearch, TagSearch]

@tool
def flexible_search(request: SearchRequest) -> list[dict]:
    """Search with multiple search types.

    Args:
        request: Search request (id, text, or tags)

    Returns:
        Search results
    """
    if isinstance(request, IdSearch):
        return search_by_id(request.value)
    elif isinstance(request, TextSearch):
        return search_by_text(request.query, fuzzy=request.fuzzy)
    elif isinstance(request, TagSearch):
        return search_by_tags(request.tags, match_all=request.match_all)
```

## Return Value Handling

### Structured Returns

Return well-structured data:

```python
from spark.tools.decorator import tool
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ProcessingResult(BaseModel):
    """Structured processing result."""
    success: bool
    data: Optional[dict] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)

@tool
def process_data(input_data: dict) -> ProcessingResult:
    """Process data and return structured result.

    Args:
        input_data: Data to process

    Returns:
        Structured processing result
    """
    errors = []
    warnings = []
    result_data = None

    try:
        # Validate input
        if not input_data:
            errors.append("Input data is empty")
            return ProcessingResult(success=False, errors=errors)

        # Process data
        result_data = transform_data(input_data)

        # Check for issues
        if result_data.get('incomplete'):
            warnings.append("Some data could not be processed")

        return ProcessingResult(
            success=True,
            data=result_data,
            warnings=warnings,
            metadata={"processed_count": len(result_data.get('items', []))}
        )

    except Exception as e:
        errors.append(f"Processing failed: {str(e)}")
        return ProcessingResult(success=False, errors=errors)
```

### Large Result Handling

Handle large results efficiently:

```python
from spark.tools.decorator import tool
from typing import Iterator, Optional

@tool
def query_database(
    query: str,
    limit: int = 1000,
    return_summary: bool = False
) -> dict:
    """Query database with large result handling.

    Args:
        query: SQL query to execute
        limit: Maximum results to return
        return_summary: If True, return summary instead of full results

    Returns:
        Query results or summary
    """
    results = execute_query(query, limit=limit)

    if return_summary:
        # Return compact summary for large result sets
        return {
            "count": len(results),
            "sample": results[:10],  # First 10 rows
            "columns": list(results[0].keys()) if results else [],
            "truncated": len(results) >= limit
        }

    # Return full results
    return {
        "count": len(results),
        "data": results,
        "truncated": len(results) >= limit
    }
```

### Serialization Handling

Ensure return values are JSON-serializable:

```python
from spark.tools.decorator import tool
from datetime import datetime, date
from decimal import Decimal
import json

class CustomJSONEncoder(json.JSONEncoder):
    """Custom encoder for non-standard types."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)

@tool
def get_financial_data(account_id: str) -> dict:
    """Get financial data with proper serialization.

    Args:
        account_id: Account identifier

    Returns:
        Financial data with serializable types
    """
    # Fetch data (may contain datetime, Decimal, etc.)
    raw_data = fetch_account_data(account_id)

    # Ensure serializable
    serialized = json.loads(
        json.dumps(raw_data, cls=CustomJSONEncoder)
    )

    return serialized
```

## Error Handling

### Custom Exceptions

Define tool-specific exceptions:

```python
from spark.tools.decorator import tool

class ToolError(Exception):
    """Base exception for tool errors."""
    pass

class ValidationError(ToolError):
    """Validation error."""
    pass

class AuthenticationError(ToolError):
    """Authentication error."""
    pass

class RateLimitError(ToolError):
    """Rate limit exceeded."""
    pass

@tool
async def secure_api_call(
    endpoint: str,
    api_key: str,
    params: dict
) -> dict:
    """Make secure API call with error handling.

    Args:
        endpoint: API endpoint
        api_key: Authentication key
        params: Request parameters

    Returns:
        API response

    Raises:
        ValidationError: Invalid parameters
        AuthenticationError: Invalid or expired API key
        RateLimitError: Rate limit exceeded
    """
    # Validate parameters
    if not endpoint.startswith("https://"):
        raise ValidationError("Endpoint must use HTTPS")

    # Make API call
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                params=params
            )

            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired API key")

            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")

            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        raise ToolError(f"HTTP error: {e}")
```

### Retry Logic

Implement retry with backoff:

```python
from spark.tools.decorator import tool
import asyncio
from typing import Optional

async def retry_with_backoff(
    func,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
):
    """Retry function with exponential backoff."""
    delay = initial_delay

    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise  # Last attempt, re-raise
            print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
            await asyncio.sleep(delay)
            delay *= backoff_factor

@tool
async def fetch_with_retry(
    url: str,
    max_attempts: int = 3
) -> dict:
    """Fetch data with automatic retry.

    Args:
        url: URL to fetch
        max_attempts: Maximum retry attempts

    Returns:
        Fetched data
    """
    async def fetch():
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    return await retry_with_backoff(fetch, max_attempts=max_attempts)
```

### Graceful Degradation

Provide fallbacks for failures:

```python
from spark.tools.decorator import tool
from typing import Optional

@tool
async def get_data_with_fallback(
    source: str,
    fallback_source: Optional[str] = None
) -> dict:
    """Get data with fallback source.

    Args:
        source: Primary data source
        fallback_source: Optional fallback source

    Returns:
        Data from primary or fallback source
    """
    try:
        # Try primary source
        data = await fetch_from_source(source)
        return {"source": "primary", "data": data}

    except Exception as e:
        print(f"Primary source failed: {e}")

        if fallback_source:
            try:
                # Try fallback source
                data = await fetch_from_source(fallback_source)
                return {"source": "fallback", "data": data}
            except Exception as e2:
                print(f"Fallback source failed: {e2}")

        # Return empty result with error info
        return {
            "source": "none",
            "data": None,
            "error": str(e)
        }
```

## Long-Running Tools

### Progress Reporting

Report progress for long operations:

```python
from spark.tools.decorator import tool
from spark.tools.types import ToolContext
from typing import Optional

@tool
async def process_large_dataset(
    dataset_path: str,
    context: ToolContext = None
) -> dict:
    """Process large dataset with progress reporting.

    Args:
        dataset_path: Path to dataset
        context: Tool context for progress updates

    Returns:
        Processing results
    """
    items = load_dataset(dataset_path)
    total = len(items)
    processed = 0
    results = []

    for i, item in enumerate(items):
        # Process item
        result = process_item(item)
        results.append(result)
        processed += 1

        # Report progress every 10%
        if processed % (total // 10) == 0:
            progress = (processed / total) * 100
            print(f"Progress: {progress:.0f}% ({processed}/{total})")

            # Could also emit events via context
            if context and hasattr(context, 'metadata'):
                context.metadata['progress'] = progress

    return {
        "total": total,
        "processed": processed,
        "results": results
    }
```

### Cancellation Support

Handle cancellation gracefully:

```python
from spark.tools.decorator import tool
import asyncio

@tool
async def cancellable_operation(
    task_id: str,
    timeout_seconds: float = 300.0
) -> dict:
    """Long-running operation with cancellation support.

    Args:
        task_id: Task identifier
        timeout_seconds: Operation timeout

    Returns:
        Operation results
    """
    try:
        # Run with timeout
        result = await asyncio.wait_for(
            perform_long_operation(task_id),
            timeout=timeout_seconds
        )
        return {"status": "completed", "result": result}

    except asyncio.TimeoutError:
        # Timeout reached
        print(f"Operation timed out after {timeout_seconds}s")
        return {"status": "timeout", "result": None}

    except asyncio.CancelledError:
        # Task was cancelled
        print(f"Operation cancelled: {task_id}")
        cleanup_operation(task_id)
        raise  # Re-raise to propagate cancellation
```

### Streaming Results

Stream results for real-time processing:

```python
from spark.tools.decorator import tool
from typing import AsyncIterator

async def stream_data(source: str) -> AsyncIterator[dict]:
    """Stream data from source."""
    async for item in fetch_stream(source):
        yield item

@tool
async def process_stream(
    source: str,
    max_items: int = 100
) -> dict:
    """Process streaming data.

    Args:
        source: Data source to stream from
        max_items: Maximum items to process

    Returns:
        Summary of processed items
    """
    processed_count = 0
    results = []

    async for item in stream_data(source):
        result = process_item(item)
        results.append(result)
        processed_count += 1

        if processed_count >= max_items:
            break

    return {
        "processed": processed_count,
        "results": results[:10],  # Return sample
        "truncated": processed_count >= max_items
    }
```

## Tool Composition

### Combining Tools

Create higher-level tools from simpler ones:

```python
from spark.tools.decorator import tool

@tool
def fetch_user(user_id: str) -> dict:
    """Fetch user data."""
    return {"id": user_id, "name": "John Doe"}

@tool
def fetch_orders(user_id: str) -> list[dict]:
    """Fetch user orders."""
    return [{"order_id": "001", "amount": 100.0}]

@tool
def fetch_preferences(user_id: str) -> dict:
    """Fetch user preferences."""
    return {"theme": "dark", "language": "en"}

@tool
async def get_user_profile(user_id: str) -> dict:
    """Get complete user profile (composite tool).

    Combines multiple tools to build a complete profile.

    Args:
        user_id: User identifier

    Returns:
        Complete user profile
    """
    # Call component tools
    user = fetch_user(user_id)
    orders = fetch_orders(user_id)
    preferences = fetch_preferences(user_id)

    # Combine results
    return {
        "user": user,
        "orders": orders,
        "preferences": preferences,
        "order_count": len(orders),
        "total_spent": sum(o["amount"] for o in orders)
    }
```

### Tool Pipelines

Chain tools in a pipeline:

```python
from spark.tools.decorator import tool
from typing import Any

@tool
def extract_text(file_path: str) -> str:
    """Extract text from file."""
    return read_file(file_path)

@tool
def clean_text(text: str) -> str:
    """Clean and normalize text."""
    return text.strip().lower()

@tool
def analyze_sentiment(text: str) -> dict:
    """Analyze text sentiment."""
    return {"sentiment": "positive", "score": 0.8}

@tool
def process_document_pipeline(file_path: str) -> dict:
    """Process document through pipeline.

    Pipeline: extract -> clean -> analyze

    Args:
        file_path: Path to document

    Returns:
        Analysis results
    """
    # Execute pipeline
    text = extract_text(file_path)
    cleaned = clean_text(text)
    analysis = analyze_sentiment(cleaned)

    return {
        "file": file_path,
        "text_length": len(text),
        "cleaned_length": len(cleaned),
        "analysis": analysis
    }
```

## Dynamic Tools

### Context-Aware Tool Generation

Generate tools dynamically based on context:

```python
from spark.tools.decorator import tool
from typing import Callable

def create_scoped_tool(scope: str, permissions: list[str]) -> Callable:
    """Create a tool scoped to specific context.

    Args:
        scope: Scope identifier (e.g., 'user', 'admin')
        permissions: List of allowed permissions

    Returns:
        Dynamically created tool function
    """
    @tool
    def scoped_operation(action: str, target: str) -> dict:
        f"""Perform {scope} operation.

        Args:
            action: Action to perform
            target: Target of the action

        Returns:
            Operation result
        """
        # Check permissions
        if action not in permissions:
            raise PermissionError(
                f"Action '{action}' not allowed in scope '{scope}'"
            )

        # Perform action
        return perform_scoped_action(scope, action, target)

    # Update tool metadata
    scoped_operation.__name__ = f"{scope}_operation"
    return scoped_operation

# Create context-specific tools
user_tool = create_scoped_tool("user", ["read", "update"])
admin_tool = create_scoped_tool("admin", ["read", "update", "delete"])
```

### Parameter-Driven Tools

Tools that adapt behavior based on parameters:

```python
from spark.tools.decorator import tool
from typing import Literal, Optional

@tool
def flexible_query(
    query_type: Literal["sql", "nosql", "graph"],
    query: str,
    database: str,
    options: Optional[dict] = None
) -> dict:
    """Execute query on different database types.

    Args:
        query_type: Type of query (sql, nosql, graph)
        query: Query string
        database: Database name
        options: Optional query options

    Returns:
        Query results
    """
    options = options or {}

    if query_type == "sql":
        return execute_sql_query(query, database, **options)
    elif query_type == "nosql":
        return execute_nosql_query(query, database, **options)
    elif query_type == "graph":
        return execute_graph_query(query, database, **options)
```

## Tool Testing Patterns

### Mocking External Dependencies

Test tools with mocked dependencies:

```python
from spark.tools.decorator import tool
import pytest
from unittest.mock import patch, AsyncMock

@tool
async def fetch_weather(city: str) -> dict:
    """Fetch weather data."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.weather.com/{city}")
        return response.json()

@pytest.mark.asyncio
async def test_fetch_weather_success(httpx_mock):
    """Test successful weather fetch."""
    # Mock HTTP response
    httpx_mock.add_response(
        url="https://api.weather.com/Seattle",
        json={"temp": 72, "condition": "sunny"}
    )

    result = await fetch_weather("Seattle")

    assert result["temp"] == 72
    assert result["condition"] == "sunny"

@pytest.mark.asyncio
async def test_fetch_weather_error(httpx_mock):
    """Test weather fetch error."""
    # Mock HTTP error
    httpx_mock.add_response(
        url="https://api.weather.com/InvalidCity",
        status_code=404
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_weather("InvalidCity")
```

### Testing with Fixtures

Use pytest fixtures for common setup:

```python
import pytest
from spark.tools.decorator import tool

@tool
def process_data(data: dict, config: dict) -> dict:
    """Process data with config."""
    return transform(data, config)

@pytest.fixture
def sample_data():
    """Sample test data."""
    return {"key": "value", "count": 10}

@pytest.fixture
def default_config():
    """Default configuration."""
    return {"format": "json", "validate": True}

def test_process_with_defaults(sample_data, default_config):
    """Test processing with default config."""
    result = process_data(sample_data, default_config)
    assert result is not None

def test_process_with_custom_config(sample_data):
    """Test processing with custom config."""
    custom_config = {"format": "xml", "validate": False}
    result = process_data(sample_data, custom_config)
    assert result is not None
```

### Parameterized Testing

Test multiple scenarios efficiently:

```python
import pytest
from spark.tools.decorator import tool

@tool
def calculate(operation: str, x: float, y: float) -> float:
    """Perform calculation."""
    if operation == "add":
        return x + y
    elif operation == "subtract":
        return x - y
    elif operation == "multiply":
        return x * y
    elif operation == "divide":
        return x / y

@pytest.mark.parametrize("operation,x,y,expected", [
    ("add", 2, 3, 5),
    ("subtract", 5, 3, 2),
    ("multiply", 4, 3, 12),
    ("divide", 10, 2, 5),
])
def test_calculate(operation, x, y, expected):
    """Test calculation operations."""
    result = calculate(operation, x, y)
    assert result == expected
```

## Summary

Advanced tool development includes:

- **Custom tools** with complex logic and state management
- **Pydantic validation** for robust parameter checking
- **Structured returns** for consistent tool outputs
- **Error handling** with custom exceptions and retry logic
- **Long-running tools** with progress reporting and cancellation
- **Tool composition** for building higher-level abstractions
- **Dynamic tools** that adapt to context
- **Comprehensive testing** with mocks, fixtures, and parametrization

Next steps:
- See [Tool Fundamentals](fundamentals.md) for basic concepts
- See [Tool Registry](registry.md) for managing tools
- See [Tool Depot](depot.md) for pre-built tools
- See [Tool Specifications](specifications.md) for spec details
