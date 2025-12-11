---
title: RPC Examples & Patterns
parent: RPC
nav_order: 5
---
# RPC Examples & Patterns
---

This guide demonstrates common patterns and real-world examples for building distributed systems with Spark RPC.

## Table of Contents

- [Basic Patterns](#basic-patterns)
- [Microservices Architecture](#microservices-architecture)
- [Multi-Agent Coordination](#multi-agent-coordination)
- [Multi-Datacenter Workflows](#multi-datacenter-workflows)
- [Service-Oriented Architecture](#service-oriented-architecture)
- [Load Balancing](#load-balancing)
- [Health Checks & Monitoring](#health-checks--monitoring)
- [Testing Distributed Systems](#testing-distributed-systems)

## Basic Patterns

### Pattern 1: Simple Request/Response

Single node calling remote service:

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig
from spark.nodes import Node
from spark.graphs import Graph

class PrepareRequest(Node):
    async def process(self, context):
        return {
            'method': 'processData',
            'data': {'values': [1, 2, 3, 4, 5]}
        }

class HandleResponse(Node):
    async def process(self, context):
        result = context.inputs.content
        print(f"Received: {result}")
        return {'success': True}

# Create proxy
proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service:8000")
)

# Build graph
prepare = PrepareRequest()
handle = HandleResponse()

prepare >> proxy >> handle

# Run
graph = Graph(start=prepare)
await graph.run()
```

### Pattern 2: Fan-Out/Fan-In

Call multiple services in parallel:

```python
from spark.nodes import Node

class FanOut(Node):
    """Prepare data for multiple services."""
    async def process(self, context):
        data = context.inputs.content
        return {
            'service1': {'method': 'analyze', 'data': data},
            'service2': {'method': 'classify', 'data': data},
            'service3': {'method': 'summarize', 'data': data}
        }

class FanIn(Node):
    """Combine results from multiple services."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.results = {}

    async def process(self, context):
        # Collect result from one service
        service = context.inputs.metadata.get('service')
        self.results[service] = context.inputs.content

        # Wait for all results
        if len(self.results) == 3:
            combined = {
                'analysis': self.results.get('service1'),
                'classification': self.results.get('service2'),
                'summary': self.results.get('service3')
            }
            self.results = {}  # Reset for next run
            return combined

        return None  # Not ready yet

# Create proxies
proxy1 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service1:8000")
)
proxy2 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service2:8000")
)
proxy3 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service3:8000")
)

# Build graph (simplified - actual implementation needs routing)
fan_out = FanOut()
fan_in = FanIn()

# Connect in parallel
# (Implementation depends on graph routing logic)
```

### Pattern 3: Chain of Services

Pipeline of remote services:

```python
# Service chain: Ingest → Process → Store

ingest_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://ingest:8000")
)
process_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://process:8000")
)
store_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://store:8000")
)

# Create transformation nodes
class PrepareIngest(Node):
    async def process(self, context):
        return {'method': 'ingest', 'source': 'file.csv'}

class PrepareProcess(Node):
    async def process(self, context):
        ingest_result = context.inputs.content
        return {
            'method': 'process',
            'data_id': ingest_result['data_id']
        }

class PrepareStore(Node):
    async def process(self, context):
        process_result = context.inputs.content
        return {
            'method': 'store',
            'processed_data': process_result['data']
        }

# Build chain
prepare_ingest = PrepareIngest()
prepare_process = PrepareProcess()
prepare_store = PrepareStore()

prepare_ingest >> ingest_proxy >> prepare_process >> process_proxy >> prepare_store >> store_proxy

graph = Graph(start=prepare_ingest)
```

## Microservices Architecture

### Example: E-Commerce Platform

```python
"""
Microservices:
- User Service: Authentication and user management
- Product Service: Product catalog
- Order Service: Order processing
- Payment Service: Payment processing
- Notification Service: Email/SMS notifications
"""

from spark.nodes.rpc import RpcNode
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig
from spark.nodes import Node
from spark.graphs import Graph

# ============================================================================
# Service Definitions
# ============================================================================

class UserService(RpcNode):
    """User authentication and management."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.users = {}

    async def rpc_authenticate(self, params, context):
        username = params['username']
        password = params['password']
        # Validate credentials...
        return {
            'success': True,
            'user_id': 'user123',
            'token': 'auth_token_xyz'
        }

    async def rpc_getUser(self, params, context):
        user_id = params['user_id']
        # Fetch user...
        return {
            'user_id': user_id,
            'username': 'alice',
            'email': 'alice@example.com'
        }

class ProductService(RpcNode):
    """Product catalog management."""

    async def rpc_getProduct(self, params, context):
        product_id = params['product_id']
        # Fetch product...
        return {
            'product_id': product_id,
            'name': 'Widget',
            'price': 29.99,
            'stock': 100
        }

    async def rpc_reserveStock(self, params, context):
        product_id = params['product_id']
        quantity = params['quantity']
        # Reserve stock...
        return {'success': True, 'reservation_id': 'res123'}

class OrderService(RpcNode):
    """Order processing."""

    async def rpc_createOrder(self, params, context):
        user_id = params['user_id']
        items = params['items']
        # Create order...
        return {
            'success': True,
            'order_id': 'order123',
            'total': 59.98
        }

    async def rpc_getOrder(self, params, context):
        order_id = params['order_id']
        # Fetch order...
        return {
            'order_id': order_id,
            'status': 'processing',
            'items': []
        }

# ============================================================================
# Orchestration Graph
# ============================================================================

class CheckoutWorkflow(Node):
    """Orchestrate checkout across microservices."""

    def __init__(
        self,
        user_service_url,
        product_service_url,
        order_service_url
    ):
        super().__init__()

        # Create service proxies
        self.user_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint=user_service_url)
        )
        self.product_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint=product_service_url)
        )
        self.order_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint=order_service_url)
        )

    async def process(self, context):
        """Execute checkout workflow."""
        order_data = context.inputs.content

        # Step 1: Authenticate user
        from spark.nodes.types import ExecutionContext, NodeMessage
        auth_context = ExecutionContext(
            inputs=NodeMessage(content={
                'method': 'authenticate',
                'username': order_data['username'],
                'password': order_data['password']
            })
        )
        auth_result = await self.user_service.process(auth_context)

        if not auth_result.content['success']:
            return {'success': False, 'error': 'Authentication failed'}

        user_id = auth_result.content['user_id']

        # Step 2: Reserve stock for each item
        for item in order_data['items']:
            reserve_context = ExecutionContext(
                inputs=NodeMessage(content={
                    'method': 'reserveStock',
                    'product_id': item['product_id'],
                    'quantity': item['quantity']
                })
            )
            reserve_result = await self.product_service.process(reserve_context)

            if not reserve_result.content['success']:
                return {
                    'success': False,
                    'error': f"Stock unavailable for {item['product_id']}"
                }

        # Step 3: Create order
        order_context = ExecutionContext(
            inputs=NodeMessage(content={
                'method': 'createOrder',
                'user_id': user_id,
                'items': order_data['items']
            })
        )
        order_result = await self.order_service.process(order_context)

        return {
            'success': True,
            'order_id': order_result.content['order_id'],
            'total': order_result.content['total']
        }

# ============================================================================
# Deployment
# ============================================================================

async def deploy_services():
    """Deploy all microservices."""

    # Start services on different ports
    user_svc = UserService(host="0.0.0.0", port=8001)
    product_svc = ProductService(host="0.0.0.0", port=8002)
    order_svc = OrderService(host="0.0.0.0", port=8003)

    # Start servers (in production, run in separate processes/containers)
    await asyncio.gather(
        user_svc.start_server(),
        product_svc.start_server(),
        order_svc.start_server()
    )

async def run_checkout():
    """Run checkout workflow."""

    workflow = CheckoutWorkflow(
        user_service_url="http://localhost:8001",
        product_service_url="http://localhost:8002",
        order_service_url="http://localhost:8003"
    )

    from spark.nodes.types import ExecutionContext, NodeMessage
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'username': 'alice',
            'password': 'secret',
            'items': [
                {'product_id': 'prod1', 'quantity': 2},
                {'product_id': 'prod2', 'quantity': 1}
            ]
        })
    )

    result = await workflow.process(context)
    print(result)
```

## Multi-Agent Coordination

### Pattern: Distributed Agent Team

Multiple specialized agents working together:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool
from spark.nodes.rpc import RpcNode
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig

# ============================================================================
# Agent Services
# ============================================================================

class ResearchAgentService(RpcNode):
    """Research agent exposed as RPC service."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Create agent
        model = OpenAIModel(model_id="gpt-4o")
        self.agent = Agent(
            config=AgentConfig(
                model=model,
                system_prompt="You are a research assistant. Find and summarize information.",
                tools=[self._search_web]
            )
        )

    @tool
    def _search_web(self, query: str) -> str:
        """Search the web for information."""
        # Implement web search...
        return f"Search results for: {query}"

    async def rpc_research(self, params, context):
        """Research a topic."""
        topic = params['topic']
        result = await self.agent.run(f"Research: {topic}")
        return {'research': result}

class AnalysisAgentService(RpcNode):
    """Analysis agent exposed as RPC service."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        model = OpenAIModel(model_id="gpt-4o")
        self.agent = Agent(
            config=AgentConfig(
                model=model,
                system_prompt="You are an analysis expert. Analyze data and provide insights."
            )
        )

    async def rpc_analyze(self, params, context):
        """Analyze research data."""
        data = params['data']
        result = await self.agent.run(f"Analyze this data: {data}")
        return {'analysis': result}

# ============================================================================
# Coordinator
# ============================================================================

class MultiAgentCoordinator(Node):
    """Coordinate multiple agents."""

    def __init__(self):
        super().__init__()

        # Create proxies to agent services
        self.research_agent = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint="http://research-agent:8000")
        )
        self.analysis_agent = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint="http://analysis-agent:8001")
        )

    async def process(self, context):
        """Coordinate agents to solve problem."""
        task = context.inputs.content

        # Step 1: Research
        from spark.nodes.types import ExecutionContext, NodeMessage
        research_context = ExecutionContext(
            inputs=NodeMessage(content={
                'method': 'research',
                'topic': task['topic']
            })
        )
        research_result = await self.research_agent.process(research_context)

        # Step 2: Analyze
        analysis_context = ExecutionContext(
            inputs=NodeMessage(content={
                'method': 'analyze',
                'data': research_result.content['research']
            })
        )
        analysis_result = await self.analysis_agent.process(analysis_context)

        return {
            'research': research_result.content['research'],
            'analysis': analysis_result.content['analysis']
        }

# ============================================================================
# Usage
# ============================================================================

async def run_multi_agent_task():
    # Deploy agents (in production: separate machines/containers)
    # research_svc = ResearchAgentService(host="0.0.0.0", port=8000)
    # analysis_svc = AnalysisAgentService(host="0.0.0.0", port=8001)

    # Create coordinator
    coordinator = MultiAgentCoordinator()

    # Run task
    from spark.nodes.types import ExecutionContext, NodeMessage
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'topic': 'Quantum Computing Applications'
        })
    )
    result = await coordinator.process(context)
    print(result)
```

## Multi-Datacenter Workflows

### Pattern: Geographically Distributed Processing

Process data close to where it's stored:

```python
class GeoDistributedWorkflow(Node):
    """Route processing to appropriate datacenter."""

    def __init__(self):
        super().__init__()

        # Proxies to services in different datacenters
        self.us_east_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(
                endpoint="https://us-east.example.com:8000",
                transport="http"
            )
        )
        self.eu_west_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(
                endpoint="https://eu-west.example.com:8000",
                transport="http"
            )
        )
        self.asia_pacific_service = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(
                endpoint="https://asia-pacific.example.com:8000",
                transport="http"
            )
        )

    def _select_datacenter(self, data):
        """Select datacenter based on data residency requirements."""
        region = data.get('region', 'us-east')

        if region.startswith('us'):
            return self.us_east_service
        elif region.startswith('eu'):
            return self.eu_west_service
        else:
            return self.asia_pacific_service

    async def process(self, context):
        """Route to appropriate datacenter."""
        data = context.inputs.content

        # Select datacenter
        service = self._select_datacenter(data)

        # Route request
        from spark.nodes.types import ExecutionContext, NodeMessage
        service_context = ExecutionContext(
            inputs=NodeMessage(content={
                'method': 'processData',
                'data': data
            })
        )
        result = await service.process(service_context)

        return result.content
```

## Service-Oriented Architecture

### Pattern: Reusable Service Composition

Build complex workflows from reusable services:

```python
"""
Service Layer:
- Authentication Service
- Data Validation Service
- Business Logic Service
- Audit Logging Service
- Notification Service

Composition Layer:
- Compose services into workflows
"""

class ServiceRegistry:
    """Registry of available services."""

    def __init__(self):
        self.services = {
            'auth': RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint="http://auth-service:8000")
            ),
            'validation': RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint="http://validation-service:8001")
            ),
            'business_logic': RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint="http://logic-service:8002")
            ),
            'audit': RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint="http://audit-service:8003")
            ),
            'notification': RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint="http://notification-service:8004")
            )
        }

    def get(self, service_name):
        """Get service proxy."""
        return self.services.get(service_name)

class WorkflowComposer(Node):
    """Compose services into workflow."""

    def __init__(self, registry: ServiceRegistry):
        super().__init__()
        self.registry = registry

    async def execute_workflow(self, steps, data):
        """Execute workflow with specified steps."""
        current_data = data

        for step in steps:
            service_name = step['service']
            method = step['method']

            service = self.registry.get(service_name)
            if not service:
                raise ValueError(f"Service not found: {service_name}")

            # Call service
            from spark.nodes.types import ExecutionContext, NodeMessage
            context = ExecutionContext(
                inputs=NodeMessage(content={
                    'method': method,
                    **current_data
                })
            )
            result = await service.process(context)
            current_data = result.content

        return current_data

# Usage
registry = ServiceRegistry()
composer = WorkflowComposer(registry)

# Define workflow
workflow = [
    {'service': 'auth', 'method': 'authenticate'},
    {'service': 'validation', 'method': 'validate'},
    {'service': 'business_logic', 'method': 'process'},
    {'service': 'audit', 'method': 'log'},
    {'service': 'notification', 'method': 'notify'}
]

result = await composer.execute_workflow(workflow, {'user': 'alice', 'action': 'transfer'})
```

## Load Balancing

### Pattern: Client-Side Load Balancing

```python
import random

class LoadBalancedProxy(Node):
    """Client-side load balancing across multiple endpoints."""

    def __init__(self, endpoints, strategy='round_robin'):
        super().__init__()
        self.endpoints = endpoints
        self.strategy = strategy
        self.current_index = 0

        # Create proxies
        self.proxies = [
            RemoteRpcProxyNode(config=RemoteRpcProxyConfig(endpoint=ep))
            for ep in endpoints
        ]

    def _select_proxy(self):
        """Select proxy based on strategy."""
        if self.strategy == 'round_robin':
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return proxy

        elif self.strategy == 'random':
            return random.choice(self.proxies)

        elif self.strategy == 'least_connections':
            # Track active connections per proxy
            # Return proxy with fewest connections
            pass

        else:
            return self.proxies[0]

    async def process(self, context):
        """Route request to selected proxy."""
        proxy = self._select_proxy()

        try:
            return await proxy.process(context)
        except Exception as e:
            # Retry with different proxy
            print(f"Error with proxy, retrying: {e}")
            proxy = self._select_proxy()
            return await proxy.process(context)

# Usage
load_balanced = LoadBalancedProxy(
    endpoints=[
        "http://service-1:8000",
        "http://service-2:8000",
        "http://service-3:8000"
    ],
    strategy='round_robin'
)
```

### Pattern: Weighted Load Balancing

```python
class WeightedLoadBalancer(Node):
    """Load balancer with weighted distribution."""

    def __init__(self, endpoints_with_weights):
        super().__init__()
        # endpoints_with_weights: [(endpoint, weight), ...]
        self.endpoints_with_weights = endpoints_with_weights

        # Create proxies
        self.proxies = []
        for endpoint, weight in endpoints_with_weights:
            proxy = RemoteRpcProxyNode(
                config=RemoteRpcProxyConfig(endpoint=endpoint)
            )
            # Add proxy 'weight' times for weighted selection
            self.proxies.extend([proxy] * weight)

    async def process(self, context):
        """Select proxy based on weights."""
        proxy = random.choice(self.proxies)
        return await proxy.process(context)

# Usage: Give service-1 twice the traffic of service-2
weighted_lb = WeightedLoadBalancer([
    ("http://service-1:8000", 2),  # 2x weight
    ("http://service-2:8000", 1)   # 1x weight
])
```

## Health Checks & Monitoring

### Pattern: Health Check Monitoring

```python
import asyncio
import httpx

class ServiceHealthMonitor:
    """Monitor health of RPC services."""

    def __init__(self, services):
        # services: {name: endpoint}
        self.services = services
        self.health_status = {}

    async def check_health(self, service_name, endpoint):
        """Check health of a service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{endpoint}/health",
                    timeout=5.0
                )
                if response.status_code == 200:
                    data = response.json()
                    self.health_status[service_name] = {
                        'status': 'healthy',
                        'data': data,
                        'timestamp': time.time()
                    }
                else:
                    self.health_status[service_name] = {
                        'status': 'unhealthy',
                        'error': f"Status code: {response.status_code}",
                        'timestamp': time.time()
                    }
        except Exception as e:
            self.health_status[service_name] = {
                'status': 'unreachable',
                'error': str(e),
                'timestamp': time.time()
            }

    async def monitor(self, interval=30):
        """Continuously monitor service health."""
        while True:
            tasks = [
                self.check_health(name, endpoint)
                for name, endpoint in self.services.items()
            ]
            await asyncio.gather(*tasks)

            # Log health status
            print("\n=== Service Health ===")
            for name, status in self.health_status.items():
                print(f"{name}: {status['status']}")

            await asyncio.sleep(interval)

# Usage
monitor = ServiceHealthMonitor({
    'user-service': 'http://user-service:8000',
    'product-service': 'http://product-service:8001',
    'order-service': 'http://order-service:8002'
})

# Run monitoring in background
asyncio.create_task(monitor.monitor(interval=30))
```

### Pattern: Circuit Breaker

```python
import time

class CircuitBreaker:
    """Circuit breaker pattern for RPC calls."""

    def __init__(
        self,
        failure_threshold=5,
        timeout=60,
        success_threshold=2
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.failure_count = 0
        self.success_count = 0
        self.state = 'closed'  # closed, open, half_open
        self.last_failure_time = None

    def call(self, func):
        """Execute function with circuit breaker."""
        # Check state
        if self.state == 'open':
            # Check if timeout has passed
            if time.time() - self.last_failure_time > self.timeout:
                self.state = 'half_open'
                self.success_count = 0
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func()

            # Success
            if self.state == 'half_open':
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = 'closed'
                    self.failure_count = 0
            elif self.state == 'closed':
                self.failure_count = 0

            return result

        except Exception as e:
            # Failure
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = 'open'

            raise

class CircuitBreakerProxy(Node):
    """Proxy with circuit breaker."""

    def __init__(self, endpoint, **kwargs):
        super().__init__(**kwargs)
        self.proxy = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint=endpoint)
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60
        )

    async def process(self, context):
        """Process with circuit breaker protection."""
        def call():
            return asyncio.create_task(self.proxy.process(context))

        try:
            task = self.circuit_breaker.call(call)
            return await task
        except Exception as e:
            # Circuit is open or service failed
            print(f"Circuit breaker error: {e}")
            # Return fallback response
            return {'error': 'Service temporarily unavailable'}
```

## Testing Distributed Systems

### Pattern: Mock RPC Services

```python
import pytest

class MockRpcService(RpcNode):
    """Mock RPC service for testing."""

    def __init__(self, responses=None, **kwargs):
        super().__init__(**kwargs)
        self.responses = responses or {}
        self.call_log = []

    async def _dispatch_rpc_method(self, method, params, context):
        """Override to return mock responses."""
        # Log call
        self.call_log.append({
            'method': method,
            'params': params,
            'timestamp': time.time()
        })

        # Return mock response
        if method in self.responses:
            return self.responses[method]
        else:
            return {'mock': True, 'method': method}

@pytest.mark.asyncio
async def test_workflow_with_mocks():
    """Test workflow with mock services."""

    # Create mock service
    mock = MockRpcService(
        responses={
            'getData': {'data': 'test_data', 'found': True},
            'processData': {'result': 'processed', 'success': True}
        },
        host="127.0.0.1",
        port=8888
    )

    # Start mock server
    server_task = asyncio.create_task(mock.start_server())
    await asyncio.sleep(1)  # Wait for server to start

    try:
        # Create workflow
        proxy = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint="http://127.0.0.1:8888")
        )

        # Test calls
        from spark.nodes.types import ExecutionContext, NodeMessage
        context = ExecutionContext(
            inputs=NodeMessage(content={'method': 'getData', 'id': 'test'})
        )
        result = await proxy.process(context)

        # Assertions
        assert result.content['found'] == True
        assert len(mock.call_log) == 1
        assert mock.call_log[0]['method'] == 'getData'

    finally:
        # Cleanup
        await mock.shutdown()
        server_task.cancel()
```

### Pattern: Integration Testing

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_integration():
    """Integration test with real services."""

    # Deploy services (Docker Compose, Kubernetes, etc.)
    # Wait for services to be ready

    # Create workflow
    workflow = CheckoutWorkflow(
        user_service_url="http://test-user-service:8000",
        product_service_url="http://test-product-service:8001",
        order_service_url="http://test-order-service:8002"
    )

    # Execute workflow
    from spark.nodes.types import ExecutionContext, NodeMessage
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'username': 'test_user',
            'password': 'test_pass',
            'items': [{'product_id': 'test_product', 'quantity': 1}]
        })
    )

    result = await workflow.process(context)

    # Verify
    assert result['success'] == True
    assert 'order_id' in result
```

## Best Practices Summary

1. **Service Boundaries**: Clear separation of concerns
2. **Idempotency**: Design RPC methods to be idempotent
3. **Timeouts**: Set appropriate timeouts at all levels
4. **Retries**: Implement exponential backoff
5. **Circuit Breakers**: Prevent cascading failures
6. **Health Checks**: Monitor service health continuously
7. **Load Balancing**: Distribute load across instances
8. **Observability**: Comprehensive logging and metrics
9. **Testing**: Mock services for unit tests, integration tests for workflows
10. **Security**: Authentication, authorization, encryption

## Next Steps

- [RPC Overview](./overview.md) - Understand RPC fundamentals
- [RPC Server](./server.md) - Build RPC services
- [RPC Client](./client.md) - Call RPC services
- [RPC Security](./security.md) - Secure your services
