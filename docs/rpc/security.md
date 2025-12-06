---
title: RPC Security
parent: RPC
nav_order: 4
---
# RPC Security

Securing RPC services is critical for production deployments. This guide covers authentication, authorization, encryption, input validation, and other security best practices for Spark RPC systems.

## Security Layers

A secure RPC system requires multiple layers of defense:

```
┌─────────────────────────────────────┐
│  1. Transport Security (TLS/SSL)   │
├─────────────────────────────────────┤
│  2. Authentication (Who are you?)  │
├─────────────────────────────────────┤
│  3. Authorization (What can you do?)│
├─────────────────────────────────────┤
│  4. Rate Limiting (How much?)      │
├─────────────────────────────────────┤
│  5. Input Validation (Is it safe?) │
├─────────────────────────────────────┤
│  6. Audit Logging (What happened?) │
└─────────────────────────────────────┘
```

## Transport Security (TLS/SSL)

### Enable HTTPS/WSS

Always use TLS in production:

```python
from spark.nodes.rpc import RpcNode

# Production server with TLS
node = RpcNode(
    host="0.0.0.0",
    port=8443,
    ssl_certfile="/etc/ssl/certs/server.crt",
    ssl_keyfile="/etc/ssl/private/server.key",
    ssl_ca_certs="/etc/ssl/certs/ca-bundle.crt"  # Optional CA chain
)
await node.start_server()
```

Client automatically uses HTTPS:

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig

# Client automatically uses HTTPS and WSS
config = RemoteRpcProxyConfig(
    endpoint="https://secure-server.com:8443",  # https://
    transport="websocket"  # Auto-converts to wss://
)
proxy = RemoteRpcProxyNode(config=config)
```

### Certificate Management

#### Production Certificates

Use certificates from a trusted Certificate Authority (CA):

```bash
# Let's Encrypt (free, automated)
certbot certonly --standalone -d your-domain.com

# Commercial CA
# Purchase certificate from Digicert, GlobalSign, etc.
```

#### Self-Signed Certificates (Development/Testing Only)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/C=US/ST=State/L=City/O=Org/CN=localhost"

# Generate with Subject Alternative Names (SAN)
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"
```

**Warning**: Never use self-signed certificates in production.

#### Client Certificate Verification

For mutual TLS (mTLS):

```python
# Server: Require client certificates
import ssl

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile="server.crt", keyfile="server.key")
ssl_context.load_verify_locations(cafile="client-ca.crt")
ssl_context.verify_mode = ssl.CERT_REQUIRED

# Client: Provide certificate
import httpx
import ssl

ssl_context = ssl.create_default_context()
ssl_context.load_cert_chain(certfile="client.crt", keyfile="client.key")

# Use with httpx in RemoteRpcProxyNode (requires custom transport)
```

### TLS Best Practices

1. **Use TLS 1.2 or higher**: Disable older protocols
2. **Strong cipher suites**: Prefer ECDHE, AES-GCM
3. **Certificate pinning**: Pin certificates for critical services
4. **Regular rotation**: Rotate certificates before expiry
5. **Secure key storage**: Protect private keys (filesystem permissions, HSM)

## Authentication

Verify the identity of clients before processing requests.

### Token-Based Authentication

#### Implementation

```python
from spark.nodes.rpc import RpcNode
import secrets
import time

class AuthenticatedRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # In production, use a database or cache (Redis)
        self.valid_tokens = {
            "token1": {"user": "alice", "expires": time.time() + 3600},
            "token2": {"user": "bob", "expires": time.time() + 3600}
        }

    async def before_request(self, method, params, request_id):
        """Validate authentication token."""
        # Extract token from params (or better: from HTTP headers)
        token = params.get('auth_token') if isinstance(params, dict) else None

        if not token:
            raise PermissionError("Authentication token required")

        # Validate token
        token_data = self.valid_tokens.get(token)
        if not token_data:
            raise PermissionError("Invalid authentication token")

        # Check expiry
        if token_data['expires'] < time.time():
            raise PermissionError("Token expired")

        # Store user info for authorization
        if not hasattr(self, 'current_user'):
            self.current_user = {}
        self.current_user[request_id] = token_data['user']

    async def after_request(self, method, params, request_id, result, error):
        """Clean up user info."""
        if hasattr(self, 'current_user') and request_id in self.current_user:
            del self.current_user[request_id]

    # RPC method can access current user
    async def rpc_getData(self, params, context):
        user = self.current_user.get(params.get('request_id'))
        return {'data': f'Data for {user}'}
```

#### Client Usage

```python
# Client sends token with each request
class AuthenticatedClient(Node):
    def __init__(self, token, **kwargs):
        super().__init__(**kwargs)
        self.token = token

    async def process(self, context):
        return {
            'method': 'getData',
            'auth_token': self.token,  # Include token
            'id': 'data123'
        }
```

### HTTP Header Authentication (Recommended)

Better approach: Use HTTP headers instead of params:

```python
from spark.nodes.rpc import RpcNode
from starlette.requests import Request

class HeaderAuthRpcNode(RpcNode):
    def _build_app(self):
        """Override to add custom middleware."""
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route, WebSocketRoute

        # Custom middleware for authentication
        async def auth_middleware(request, call_next):
            # Extract Authorization header
            auth_header = request.headers.get('Authorization')

            if not auth_header or not auth_header.startswith('Bearer '):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    {"error": "Authentication required"},
                    status_code=401
                )

            token = auth_header.replace('Bearer ', '')
            if not self._validate_token(token):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    {"error": "Invalid token"},
                    status_code=401
                )

            # Store user info in request state
            request.state.user = self._get_user_from_token(token)

            return await call_next(request)

        return Starlette(
            routes=[
                Route("/", self._handle_http_rpc, methods=["POST"]),
                Route("/health", self._health_check, methods=["GET"]),
                WebSocketRoute("/ws", self._handle_websocket),
            ],
            middleware=[Middleware(auth_middleware)],
            on_shutdown=[self._on_app_shutdown],
        )

    def _validate_token(self, token):
        """Validate authentication token."""
        return token in self.valid_tokens

    def _get_user_from_token(self, token):
        """Get user info from token."""
        return self.valid_tokens.get(token, {}).get('user')
```

Client with header authentication:

```python
config = RemoteRpcProxyConfig(
    endpoint="https://api.example.com",
    headers={
        "Authorization": "Bearer your-token-here"
    }
)
proxy = RemoteRpcProxyNode(config=config)
```

### API Key Authentication

Simple API key per client:

```python
class ApiKeyRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_keys = {
            "key1": {"client": "app1", "rate_limit": 100},
            "key2": {"client": "app2", "rate_limit": 1000}
        }

    async def before_request(self, method, params, request_id):
        api_key = params.get('api_key') if isinstance(params, dict) else None

        if not api_key or api_key not in self.api_keys:
            raise PermissionError("Invalid API key")

        # Store client info
        self.current_client = self.api_keys[api_key]['client']
```

### OAuth 2.0 / JWT

For enterprise applications:

```python
import jwt
from datetime import datetime, timedelta

class JWTAuthRpcNode(RpcNode):
    def __init__(self, jwt_secret, **kwargs):
        super().__init__(**kwargs)
        self.jwt_secret = jwt_secret

    def _validate_jwt(self, token):
        """Validate JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"]
            )
            # Check expiry
            exp = payload.get('exp')
            if exp and datetime.fromtimestamp(exp) < datetime.now():
                return None
            return payload
        except jwt.InvalidTokenError:
            return None

    async def before_request(self, method, params, request_id):
        token = params.get('jwt_token')
        payload = self._validate_jwt(token)

        if not payload:
            raise PermissionError("Invalid or expired JWT token")

        # Store user info
        self.current_user[request_id] = payload.get('user')
```

## Authorization

Control what authenticated users can do.

### Role-Based Access Control (RBAC)

```python
class RBACRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Define roles and permissions
        self.roles = {
            'admin': ['read', 'write', 'delete', 'admin'],
            'editor': ['read', 'write'],
            'viewer': ['read']
        }
        self.user_roles = {
            'alice': 'admin',
            'bob': 'editor',
            'charlie': 'viewer'
        }

    def _check_permission(self, user, required_permission):
        """Check if user has required permission."""
        role = self.user_roles.get(user)
        if not role:
            return False
        return required_permission in self.roles.get(role, [])

    async def rpc_getData(self, params, context):
        """Read-only operation."""
        user = self.current_user.get(params.get('request_id'))
        if not self._check_permission(user, 'read'):
            raise PermissionError("Insufficient permissions")

        return {'data': 'sensitive data'}

    async def rpc_updateData(self, params, context):
        """Write operation."""
        user = self.current_user.get(params.get('request_id'))
        if not self._check_permission(user, 'write'):
            raise PermissionError("Insufficient permissions")

        # Update data...
        return {'success': True}

    async def rpc_deleteData(self, params, context):
        """Delete operation."""
        user = self.current_user.get(params.get('request_id'))
        if not self._check_permission(user, 'delete'):
            raise PermissionError("Insufficient permissions")

        # Delete data...
        return {'success': True}
```

### Method-Level Authorization

```python
class MethodAuthRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Define which roles can call which methods
        self.method_permissions = {
            'getData': ['viewer', 'editor', 'admin'],
            'updateData': ['editor', 'admin'],
            'deleteData': ['admin'],
            'adminStats': ['admin']
        }

    async def before_request(self, method, params, request_id):
        """Check method-level permissions."""
        # Authenticate first
        user = self._authenticate(params)

        # Check authorization
        allowed_roles = self.method_permissions.get(method, [])
        user_role = self.user_roles.get(user)

        if user_role not in allowed_roles:
            raise PermissionError(
                f"Role '{user_role}' not authorized to call '{method}'"
            )

        self.current_user[request_id] = user
```

### Resource-Level Authorization

Control access to specific resources:

```python
class ResourceAuthRpcNode(RpcNode):
    async def rpc_getData(self, params, context):
        data_id = params.get('id')
        user = self.current_user.get(params.get('request_id'))

        # Check if user owns this resource
        if not self._user_owns_resource(user, data_id):
            raise PermissionError(f"User '{user}' cannot access resource '{data_id}'")

        return {'data': self.get_data(data_id)}

    def _user_owns_resource(self, user, resource_id):
        """Check if user owns or has access to resource."""
        # Check database, ACLs, etc.
        owner = self.resource_owners.get(resource_id)
        return owner == user
```

## Rate Limiting

Prevent abuse and ensure fair resource usage.

### Token Bucket Algorithm

```python
from collections import defaultdict
import time

class RateLimitedRpcNode(RpcNode):
    def __init__(
        self,
        max_requests=100,
        window_seconds=60,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_times = defaultdict(list)

    async def before_request(self, method, params, request_id):
        # Get client identifier
        client_id = self._get_client_id(params)

        now = time.time()
        requests = self.request_times[client_id]

        # Remove expired timestamps
        requests[:] = [t for t in requests if now - t < self.window_seconds]

        # Check limit
        if len(requests) >= self.max_requests:
            from spark.nodes.rpc import JsonRpcError
            raise Exception(
                f"Rate limit exceeded: {self.max_requests} requests "
                f"per {self.window_seconds}s"
            )

        # Add current request
        requests.append(now)

    def _get_client_id(self, params):
        """Extract client identifier."""
        # Use authenticated user, API key, or IP address
        return params.get('user_id', 'anonymous')
```

### Per-Method Rate Limits

Different limits for different methods:

```python
class MethodRateLimitedRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Method -> rate limit config
        self.method_limits = {
            'getData': {'max': 1000, 'window': 60},
            'updateData': {'max': 100, 'window': 60},
            'deleteData': {'max': 10, 'window': 60}
        }
        self.request_times = defaultdict(lambda: defaultdict(list))

    async def before_request(self, method, params, request_id):
        client_id = self._get_client_id(params)
        limit_config = self.method_limits.get(method)

        if not limit_config:
            return  # No limit for this method

        now = time.time()
        requests = self.request_times[client_id][method]
        window = limit_config['window']

        requests[:] = [t for t in requests if now - t < window]

        if len(requests) >= limit_config['max']:
            raise Exception(
                f"Rate limit for '{method}': {limit_config['max']} "
                f"requests per {window}s"
            )

        requests.append(now)
```

### External Rate Limiting (Redis)

For distributed systems:

```python
import aioredis

class RedisRateLimitedRpcNode(RpcNode):
    def __init__(self, redis_url, **kwargs):
        super().__init__(**kwargs)
        self.redis_url = redis_url
        self.redis = None

    async def start_server(self):
        # Connect to Redis
        self.redis = await aioredis.from_url(self.redis_url)
        await super().start_server()

    async def before_request(self, method, params, request_id):
        client_id = self._get_client_id(params)
        key = f"rate_limit:{client_id}"

        # Increment counter
        count = await self.redis.incr(key)

        # Set expiry on first request
        if count == 1:
            await self.redis.expire(key, 60)

        # Check limit
        if count > 100:
            raise Exception("Rate limit exceeded")
```

## Input Validation

Validate all inputs to prevent injection attacks and data corruption.

### Parameter Validation

```python
from spark.nodes.rpc import InvalidParamsError

class ValidatedRpcNode(RpcNode):
    async def rpc_createUser(self, params, context):
        """Create user with validated inputs."""
        # Required fields
        username = params.get('username')
        email = params.get('email')

        if not username:
            raise InvalidParamsError("Missing required field: username")
        if not email:
            raise InvalidParamsError("Missing required field: email")

        # Type validation
        if not isinstance(username, str):
            raise InvalidParamsError("username must be a string")
        if not isinstance(email, str):
            raise InvalidParamsError("email must be a string")

        # Format validation
        if len(username) < 3 or len(username) > 50:
            raise InvalidParamsError("username must be 3-50 characters")

        import re
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            raise InvalidParamsError("Invalid email format")

        # Sanitize inputs
        username = self._sanitize(username)
        email = self._sanitize(email)

        # Create user...
        return {'user_id': 123, 'username': username}

    def _sanitize(self, value):
        """Sanitize string input."""
        # Remove dangerous characters
        return value.strip()
```

### Pydantic Validation

Use Pydantic for complex validation:

```python
from pydantic import BaseModel, EmailStr, Field, validator

class CreateUserParams(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, regex=r'^[a-zA-Z0-9_]+$')
    email: EmailStr
    age: int = Field(..., ge=18, le=120)
    role: str = Field(default='user')

    @validator('role')
    def validate_role(cls, v):
        allowed = ['user', 'editor', 'admin']
        if v not in allowed:
            raise ValueError(f"Role must be one of {allowed}")
        return v

class ValidatedRpcNode(RpcNode):
    async def rpc_createUser(self, params, context):
        try:
            # Validate with Pydantic
            validated = CreateUserParams(**params)
        except Exception as e:
            raise InvalidParamsError(f"Validation error: {str(e)}")

        # Use validated data
        return {
            'user_id': 123,
            'username': validated.username,
            'email': validated.email
        }
```

### SQL Injection Prevention

Always use parameterized queries:

```python
class DatabaseRpcNode(RpcNode):
    async def rpc_getUser(self, params, context):
        user_id = params.get('user_id')

        # WRONG: String concatenation (vulnerable to SQL injection)
        # query = f"SELECT * FROM users WHERE id = {user_id}"

        # CORRECT: Parameterized query
        query = "SELECT * FROM users WHERE id = ?"
        result = await self.db.execute(query, (user_id,))

        return {'user': result}
```

### Command Injection Prevention

Never pass user input to shell commands:

```python
class FileRpcNode(RpcNode):
    async def rpc_processFile(self, params, context):
        filename = params.get('filename')

        # WRONG: Shell command with user input
        # os.system(f"process_file {filename}")

        # CORRECT: Use subprocess with list arguments
        import subprocess
        result = subprocess.run(
            ['process_file', filename],  # List, not string
            capture_output=True,
            check=True
        )

        return {'success': True}
```

## Audit Logging

Log all security-relevant events for compliance and forensics.

### Comprehensive Logging

```python
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class AuditedRpcNode(RpcNode):
    async def before_request(self, method, params, request_id):
        """Log request details."""
        # Authenticate first
        user = self._authenticate(params)

        # Log request
        audit_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': 'rpc_request',
            'user': user,
            'method': method,
            'request_id': request_id,
            'ip_address': self._get_client_ip(),
            'params': self._sanitize_sensitive_data(params)
        }
        logger.info(json.dumps(audit_log))

    async def after_request(self, method, params, request_id, result, error):
        """Log response details."""
        audit_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': 'rpc_response',
            'method': method,
            'request_id': request_id,
            'success': error is None,
            'error': error
        }
        logger.info(json.dumps(audit_log))

    def _sanitize_sensitive_data(self, params):
        """Remove sensitive data from logs."""
        if not isinstance(params, dict):
            return params

        # Remove sensitive fields
        sanitized = params.copy()
        for key in ['password', 'auth_token', 'api_key', 'jwt_token']:
            if key in sanitized:
                sanitized[key] = '***REDACTED***'

        return sanitized

    def _get_client_ip(self):
        """Get client IP address."""
        # Extract from HTTP request or WebSocket
        return 'unknown'  # Implementation depends on transport
```

### Structured Logging

Use structured logging for better analysis:

```python
import structlog

logger = structlog.get_logger()

class StructuredAuditRpcNode(RpcNode):
    async def before_request(self, method, params, request_id):
        logger.info(
            "rpc_request",
            method=method,
            request_id=request_id,
            user=self._get_user(),
            ip=self._get_client_ip()
        )

    async def after_request(self, method, params, request_id, result, error):
        if error:
            logger.error(
                "rpc_error",
                method=method,
                request_id=request_id,
                error=error
            )
        else:
            logger.info(
                "rpc_success",
                method=method,
                request_id=request_id
            )
```

## Security Checklist

### Deployment Checklist

- [ ] TLS/SSL enabled for all production endpoints
- [ ] Valid certificates from trusted CA
- [ ] Authentication required for all requests
- [ ] Authorization checks on all methods
- [ ] Rate limiting configured
- [ ] Input validation on all parameters
- [ ] SQL injection prevention (parameterized queries)
- [ ] Command injection prevention
- [ ] Audit logging enabled
- [ ] Sensitive data redacted from logs
- [ ] Error messages don't leak sensitive info
- [ ] CORS configured appropriately
- [ ] Security headers set (CSP, HSTS, etc.)
- [ ] Regular security updates
- [ ] Penetration testing completed
- [ ] Incident response plan in place

### Code Review Checklist

- [ ] No hardcoded secrets or credentials
- [ ] No user input directly in queries/commands
- [ ] All external inputs validated
- [ ] Error handling doesn't reveal internals
- [ ] Secure random for tokens/IDs
- [ ] Timing attack prevention for auth
- [ ] No debug code in production
- [ ] Dependencies up to date
- [ ] Security logging comprehensive

## Security Best Practices

1. **Defense in Depth**: Multiple layers of security
2. **Principle of Least Privilege**: Grant minimum necessary permissions
3. **Fail Secure**: Default deny, not default allow
4. **No Security by Obscurity**: Don't rely on hidden implementations
5. **Keep It Simple**: Complex systems have more vulnerabilities
6. **Regular Updates**: Keep dependencies and libraries current
7. **Security Testing**: Automated security tests in CI/CD
8. **Incident Response**: Plan for security incidents
9. **Security Training**: Educate developers on secure coding
10. **Regular Audits**: Periodic security audits and reviews

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [TLS Best Practices](https://wiki.mozilla.org/Security/Server_Side_TLS)
- [JWT Best Practices](https://datatracker.ietf.org/doc/html/rfc8725)

## Next Steps

- [RPC Patterns](./patterns.md) - Implement secure patterns
- [RPC Server](./server.md) - Server implementation details
- [RPC Client](./client.md) - Client configuration
