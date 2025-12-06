# Workspace and Artifacts

This reference covers workspace management and artifact handling for isolated execution environments and file generation in Spark workflows.

## Overview

The **workspace system** provides isolated execution environments for graphs, while the **artifacts system** manages generated files, data, and outputs. Together, they enable:
- Sandboxed execution with controlled file access
- Secure secret management
- Generated file tracking and lifecycle
- Output persistence and retrieval
- Clean separation between execution and artifacts

## Workspace Concept

A **workspace** is an isolated execution environment that provides:
- Virtual filesystem mounting
- Secret injection and management
- Environment variable isolation
- Controlled resource access
- Cleanup and disposal

### Workspace Use Cases

1. **Multi-tenant execution**: Isolate different users or workflows
2. **Security**: Limit file system access and secrets exposure
3. **Testing**: Clean environments for reproducible tests
4. **Development**: Sandbox experimental code
5. **Production**: Controlled execution boundaries

## Virtual Filesystems

Virtual filesystems provide isolated directory structures for each workspace.

### MountPoint

Define mount points to control file access:

```python
from spark.graphs.workspace import Workspace, MountPoint

# Create workspace with mount points
workspace = Workspace(
    workspace_id='task_123',
    mount_points=[
        MountPoint(
            name='input',
            path='/data/input',
            mode='ro'  # Read-only
        ),
        MountPoint(
            name='output',
            path='/data/output',
            mode='rw'  # Read-write
        ),
        MountPoint(
            name='temp',
            path='/tmp/workspace_123',
            mode='rw'
        )
    ]
)
```

### MountPoint Configuration

```python
MountPoint(
    name: str,           # Mount point identifier
    path: str,           # Filesystem path
    mode: str = 'ro'     # Access mode: 'ro' (read-only) or 'rw' (read-write)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique name for this mount point |
| `path` | `str` | Required | Absolute path to mount |
| `mode` | `str` | `'ro'` | Access mode: `'ro'` or `'rw'` |

### Accessing Mounted Paths

```python
from spark.nodes import Node

class ProcessingNode(Node):
    async def process(self, context):
        # Access workspace from context
        workspace = context.workspace

        # Get mount point paths
        input_path = workspace.get_mount('input')
        output_path = workspace.get_mount('output')

        # Read from input mount
        with open(f"{input_path}/data.txt", 'r') as f:
            data = f.read()

        # Write to output mount
        with open(f"{output_path}/result.txt", 'w') as f:
            f.write(processed_data)

        return {'success': True}
```

### Sandboxing Example

```python
from spark.graphs import Graph
from spark.graphs.workspace import Workspace, MountPoint
import tempfile

# Create temporary directories
input_dir = tempfile.mkdtemp()
output_dir = tempfile.mkdtemp()

# Write input data
with open(f"{input_dir}/input.txt", 'w') as f:
    f.write("test data")

# Create sandboxed workspace
workspace = Workspace(
    workspace_id='sandbox_test',
    mount_points=[
        MountPoint(name='input', path=input_dir, mode='ro'),
        MountPoint(name='output', path=output_dir, mode='rw')
    ]
)

# Create graph with workspace
graph = Graph(start=ProcessingNode())
graph.workspace = workspace

# Run in sandbox
result = await graph.run()

# Check output
with open(f"{output_dir}/result.txt", 'r') as f:
    output = f.read()
    print(output)
```

## Secret Management

Securely inject secrets into workspace without exposing them globally.

### Adding Secrets

```python
from spark.graphs.workspace import Workspace

workspace = Workspace(workspace_id='prod_task')

# Add secrets
workspace.add_secret('API_KEY', 'sk-abc123')
workspace.add_secret('DB_PASSWORD', 'secure_password')
workspace.add_secret('ENCRYPTION_KEY', 'encryption_key_value')
```

### Accessing Secrets

```python
from spark.nodes import Node

class APICallNode(Node):
    async def process(self, context):
        # Access secret from workspace
        api_key = context.workspace.get_secret('API_KEY')

        # Use secret
        response = await call_api(api_key=api_key)

        return {'response': response}
```

### Secret Configuration

```python
class Workspace:
    def add_secret(
        self,
        name: str,
        value: str,
        sensitive: bool = True  # Mark as sensitive for logging
    ) -> None:
        """Add a secret to the workspace."""

    def get_secret(
        self,
        name: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """Retrieve a secret value."""

    def has_secret(self, name: str) -> bool:
        """Check if secret exists."""

    def remove_secret(self, name: str) -> None:
        """Remove a secret from workspace."""
```

### Secret Best Practices

```python
# Good: Use workspace secrets
class SecureNode(Node):
    async def process(self, context):
        api_key = context.workspace.get_secret('API_KEY')
        if not api_key:
            raise ValueError("API_KEY not configured")
        # Use api_key securely

# Bad: Hardcoded secrets
class InsecureNode(Node):
    async def process(self, context):
        api_key = "sk-abc123"  # Never do this!

# Good: Load from secure store
workspace = Workspace(workspace_id='task')
workspace.add_secret('API_KEY', load_from_vault('api_key'))

# Bad: Expose in logs
logger.info(f"Using API key: {api_key}")  # Exposes secret!

# Good: Mask in logs
logger.info("Using API key: ***")  # Safe
```

## Environment Isolation

Isolate environment variables per workspace.

### Setting Environment Variables

```python
workspace = Workspace(workspace_id='task')

# Set environment variables
workspace.set_env('ENVIRONMENT', 'production')
workspace.set_env('LOG_LEVEL', 'INFO')
workspace.set_env('MAX_WORKERS', '4')
```

### Accessing Environment Variables

```python
class ConfigurableNode(Node):
    async def process(self, context):
        # Get environment variables from workspace
        env = context.workspace.get_env('ENVIRONMENT', 'development')
        log_level = context.workspace.get_env('LOG_LEVEL', 'DEBUG')

        # Configure based on environment
        if env == 'production':
            # Production behavior
            pass
        else:
            # Development behavior
            pass

        return {'env': env}
```

### Environment Isolation Example

```python
# Development workspace
dev_workspace = Workspace(workspace_id='dev')
dev_workspace.set_env('ENVIRONMENT', 'development')
dev_workspace.set_env('DEBUG', 'true')

# Production workspace
prod_workspace = Workspace(workspace_id='prod')
prod_workspace.set_env('ENVIRONMENT', 'production')
prod_workspace.set_env('DEBUG', 'false')

# Same graph, different environments
graph = Graph(start=ConfigurableNode())

# Run in dev
graph.workspace = dev_workspace
dev_result = await graph.run()

# Run in prod
graph.workspace = prod_workspace
prod_result = await graph.run()
```

## Artifacts System

The artifacts system manages generated files, data, and outputs from graph execution.

### Artifact Types

Spark supports multiple artifact types:

| Type | Description | Use Case |
|------|-------------|----------|
| `file` | Generic file | Any file output |
| `image` | Image file | Generated images, plots |
| `report` | Report document | PDF, HTML reports |
| `data` | Data file | CSV, JSON, Parquet |
| `model` | ML model | Model checkpoints |
| `log` | Log file | Execution logs |

### Creating Artifacts

```python
from spark.graphs.artifacts import Artifact, ArtifactManager

# Create artifact
artifact = Artifact(
    artifact_id='report_001',
    artifact_type='report',
    path='/output/report.pdf',
    metadata={
        'generated_at': datetime.now().isoformat(),
        'format': 'pdf',
        'size_bytes': 1024000
    }
)

# Register artifact
manager = ArtifactManager.get_instance()
await manager.register_artifact(artifact)
```

### Artifact in Nodes

```python
from spark.nodes import Node
from spark.graphs.artifacts import Artifact
import matplotlib.pyplot as plt

class ChartGeneratorNode(Node):
    async def process(self, context):
        # Generate chart
        plt.figure()
        plt.plot([1, 2, 3, 4], [1, 4, 9, 16])

        # Save to workspace output
        output_path = context.workspace.get_mount('output')
        chart_path = f"{output_path}/chart.png"
        plt.savefig(chart_path)

        # Create artifact
        artifact = Artifact(
            artifact_id=f"chart_{context.graph_id}",
            artifact_type='image',
            path=chart_path,
            metadata={
                'format': 'png',
                'width': 800,
                'height': 600
            }
        )

        # Register artifact
        context.artifact_manager.register_artifact(artifact)

        return {
            'chart_path': chart_path,
            'artifact_id': artifact.artifact_id
        }
```

## Artifact Lifecycle Management

Manage the full lifecycle of artifacts from creation to cleanup.

### Artifact States

```python
from spark.graphs.artifacts import ArtifactState

# Artifact states
ArtifactState.CREATING    # Being generated
ArtifactState.READY       # Ready for use
ArtifactState.ARCHIVED    # Moved to archive
ArtifactState.DELETED     # Marked for deletion
```

### Lifecycle Methods

```python
from spark.graphs.artifacts import ArtifactManager

manager = ArtifactManager.get_instance()

# Create artifact
artifact = Artifact(
    artifact_id='output_123',
    artifact_type='data',
    path='/output/results.json',
    state=ArtifactState.CREATING
)

# Register
await manager.register_artifact(artifact)

# Update state when ready
await manager.update_artifact_state(
    artifact_id='output_123',
    state=ArtifactState.READY
)

# Archive old artifacts
await manager.archive_artifact('output_123')

# Delete artifact
await manager.delete_artifact('output_123')
```

### Automatic Cleanup

```python
from spark.graphs.artifacts import ArtifactManager, CleanupPolicy

# Configure cleanup policy
policy = CleanupPolicy(
    max_age_days=30,        # Delete artifacts older than 30 days
    max_artifacts=100,      # Keep max 100 artifacts
    archive_before_delete=True  # Archive before deletion
)

manager = ArtifactManager.get_instance()
manager.set_cleanup_policy(policy)

# Run cleanup
deleted_count = await manager.cleanup_artifacts()
print(f"Deleted {deleted_count} old artifacts")
```

## Storage Backends for Artifacts

Store artifacts in different backends based on requirements.

### LocalStorageBackend

Store artifacts on local filesystem (default).

```python
from spark.graphs.artifacts import LocalStorageBackend

backend = LocalStorageBackend(
    base_path='/var/lib/spark/artifacts',
    create_dirs=True  # Auto-create directories
)

manager = ArtifactManager.get_instance()
manager.set_backend(backend)
```

**Characteristics:**
- Simple and fast
- Good for single-machine deployments
- Easy to inspect and debug
- No network overhead

### S3StorageBackend

Store artifacts in AWS S3.

```python
from spark.graphs.artifacts import S3StorageBackend

backend = S3StorageBackend(
    bucket='spark-artifacts',
    prefix='production/',
    region='us-east-1',
    credentials={
        'access_key_id': 'AKIAIOSFODNN7EXAMPLE',
        'secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
    }
)

manager = ArtifactManager.get_instance()
manager.set_backend(backend)
```

**Characteristics:**
- Scalable and durable
- Suitable for distributed systems
- High availability
- Pay-per-use pricing

### DatabaseStorageBackend

Store artifact metadata in database, files in filesystem.

```python
from spark.graphs.artifacts import DatabaseStorageBackend

backend = DatabaseStorageBackend(
    connection_string='postgresql://user:pass@localhost/spark',
    file_storage_path='/var/lib/spark/artifacts'
)

manager = ArtifactManager.get_instance()
manager.set_backend(backend)
```

**Characteristics:**
- Queryable metadata
- Efficient retrieval
- Centralized management
- Suitable for multi-instance deployments

## Artifact Metadata and Versioning

Track artifact metadata and versions.

### Metadata Fields

```python
artifact = Artifact(
    artifact_id='model_v1',
    artifact_type='model',
    path='/models/model.pkl',
    metadata={
        # Standard fields
        'created_at': datetime.now().isoformat(),
        'created_by': 'training_pipeline',
        'version': '1.0.0',

        # Custom fields
        'accuracy': 0.95,
        'training_samples': 100000,
        'model_type': 'random_forest',
        'hyperparameters': {
            'n_estimators': 100,
            'max_depth': 10
        }
    }
)
```

### Versioning Artifacts

```python
from spark.graphs.artifacts import ArtifactVersion

class ModelTrainingNode(Node):
    async def process(self, context):
        # Train model
        model = train_model()

        # Get version from graph state
        version = await context.graph_state.get('model_version', 0)
        version += 1
        await context.graph_state.set('model_version', version)

        # Save versioned artifact
        model_path = f"/models/model_v{version}.pkl"
        save_model(model, model_path)

        # Create versioned artifact
        artifact = Artifact(
            artifact_id=f'model_v{version}',
            artifact_type='model',
            path=model_path,
            version=f'v{version}',
            metadata={
                'version': version,
                'parent_version': version - 1 if version > 1 else None,
                'accuracy': model.score(X_test, y_test)
            }
        )

        await context.artifact_manager.register_artifact(artifact)

        return {'model_version': version, 'artifact_id': artifact.artifact_id}
```

## Retrieval and Cleanup

Query and retrieve artifacts efficiently.

### Querying Artifacts

```python
from spark.graphs.artifacts import ArtifactManager, ArtifactQuery

manager = ArtifactManager.get_instance()

# Query by type
images = await manager.query_artifacts(
    ArtifactQuery(artifact_type='image')
)

# Query by graph
graph_artifacts = await manager.query_artifacts(
    ArtifactQuery(graph_id='pipeline_123')
)

# Query by metadata
high_accuracy_models = await manager.query_artifacts(
    ArtifactQuery(
        artifact_type='model',
        metadata_filter={'accuracy': lambda x: x > 0.9}
    )
)

# Query by date range
from datetime import datetime, timedelta
recent_artifacts = await manager.query_artifacts(
    ArtifactQuery(
        created_after=datetime.now() - timedelta(days=7)
    )
)
```

### Retrieving Artifacts

```python
# Get artifact by ID
artifact = await manager.get_artifact('report_001')

# Access artifact data
with open(artifact.path, 'rb') as f:
    data = f.read()

# Download artifact (for remote backends)
local_path = await manager.download_artifact('report_001', '/tmp/report.pdf')
```

### Cleanup Strategies

```python
# Cleanup by age
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(days=30)
deleted = await manager.cleanup_artifacts_before(cutoff)
print(f"Deleted {deleted} artifacts older than 30 days")

# Cleanup by type
deleted = await manager.cleanup_artifacts_by_type('temp', max_age_days=7)

# Cleanup by graph
deleted = await manager.cleanup_artifacts_by_graph('old_graph_id')

# Selective cleanup
def should_delete(artifact):
    # Keep high-accuracy models
    if artifact.artifact_type == 'model':
        accuracy = artifact.metadata.get('accuracy', 0)
        return accuracy < 0.8
    return True

deleted = await manager.cleanup_artifacts_with_filter(should_delete)
```

## Use Cases

### File Generation Workflow

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.graphs.workspace import Workspace, MountPoint
from spark.graphs.artifacts import Artifact
import csv

class DataExportNode(Node):
    async def process(self, context):
        # Get data
        data = await fetch_data()

        # Write to workspace output
        output_path = context.workspace.get_mount('output')
        csv_path = f"{output_path}/export.csv"

        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        # Register as artifact
        artifact = Artifact(
            artifact_id=f"export_{context.graph_id}",
            artifact_type='data',
            path=csv_path,
            metadata={
                'format': 'csv',
                'rows': len(data),
                'columns': len(data[0].keys())
            }
        )

        await context.artifact_manager.register_artifact(artifact)

        return {'artifact_id': artifact.artifact_id, 'rows': len(data)}

# Setup workspace
workspace = Workspace(
    workspace_id='export_job',
    mount_points=[
        MountPoint(name='output', path='/var/output', mode='rw')
    ]
)

graph = Graph(start=DataExportNode())
graph.workspace = workspace

result = await graph.run()
```

### Data Persistence

```python
class DataPersistenceNode(Node):
    async def process(self, context):
        # Process data
        processed_data = process_large_dataset()

        # Persist to workspace
        output_path = context.workspace.get_mount('output')
        data_path = f"{output_path}/processed_data.parquet"

        # Save using efficient format
        processed_data.to_parquet(data_path, compression='snappy')

        # Create artifact with versioning
        version = await context.graph_state.get('data_version', 0) + 1
        await context.graph_state.set('data_version', version)

        artifact = Artifact(
            artifact_id=f'processed_data_v{version}',
            artifact_type='data',
            path=data_path,
            version=f'v{version}',
            metadata={
                'format': 'parquet',
                'compression': 'snappy',
                'rows': len(processed_data),
                'size_mb': os.path.getsize(data_path) / 1024 / 1024
            }
        )

        await context.artifact_manager.register_artifact(artifact)

        return {'version': version, 'artifact_id': artifact.artifact_id}
```

### Output Management

```python
class ReportGeneratorNode(Node):
    async def process(self, context):
        # Generate multiple outputs
        outputs = []

        output_path = context.workspace.get_mount('output')

        # Generate HTML report
        html_path = f"{output_path}/report.html"
        generate_html_report(html_path)
        outputs.append(Artifact(
            artifact_id=f'report_html_{context.graph_id}',
            artifact_type='report',
            path=html_path,
            metadata={'format': 'html'}
        ))

        # Generate PDF report
        pdf_path = f"{output_path}/report.pdf"
        generate_pdf_report(pdf_path)
        outputs.append(Artifact(
            artifact_id=f'report_pdf_{context.graph_id}',
            artifact_type='report',
            path=pdf_path,
            metadata={'format': 'pdf'}
        ))

        # Generate charts
        chart_path = f"{output_path}/charts.png"
        generate_charts(chart_path)
        outputs.append(Artifact(
            artifact_id=f'charts_{context.graph_id}',
            artifact_type='image',
            path=chart_path,
            metadata={'format': 'png'}
        ))

        # Register all artifacts
        for artifact in outputs:
            await context.artifact_manager.register_artifact(artifact)

        return {
            'artifacts': [a.artifact_id for a in outputs],
            'count': len(outputs)
        }
```

## Testing with Workspaces

Use workspaces for isolated testing.

### Test Workspace Setup

```python
import pytest
import tempfile
from spark.graphs.workspace import Workspace, MountPoint

@pytest.fixture
def test_workspace():
    """Create isolated test workspace."""
    # Create temporary directories
    input_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()

    # Setup test data
    with open(f"{input_dir}/test_data.txt", 'w') as f:
        f.write("test input")

    # Create workspace
    workspace = Workspace(
        workspace_id='test',
        mount_points=[
            MountPoint(name='input', path=input_dir, mode='ro'),
            MountPoint(name='output', path=output_dir, mode='rw')
        ]
    )

    # Add test secrets
    workspace.add_secret('TEST_API_KEY', 'test_key_123')

    yield workspace

    # Cleanup
    import shutil
    shutil.rmtree(input_dir)
    shutil.rmtree(output_dir)

@pytest.mark.asyncio
async def test_node_with_workspace(test_workspace):
    """Test node in isolated workspace."""
    graph = Graph(start=TestNode())
    graph.workspace = test_workspace

    result = await graph.run()

    # Verify outputs in workspace
    output_path = test_workspace.get_mount('output')
    assert os.path.exists(f"{output_path}/result.txt")
```

## Best Practices

1. **Use Workspaces for Isolation**: Always use workspaces in production
2. **Mount Points Read-Only by Default**: Minimize write access
3. **Never Hardcode Secrets**: Use workspace secret management
4. **Register All Artifacts**: Track all generated files
5. **Version Important Artifacts**: Use versioning for models and reports
6. **Clean Up Regularly**: Implement cleanup policies
7. **Test with Isolated Workspaces**: Use temporary workspaces in tests
8. **Document Artifacts**: Provide rich metadata

## Performance Considerations

### Workspace Overhead

- Minimal overhead for mount point resolution (~0.1ms)
- Secret access is fast (in-memory dictionary)
- No overhead if workspace not used

### Artifact Registration

- Registration is async and non-blocking
- Batch register when possible
- Use appropriate storage backend for scale

### Storage Backend Selection

| Backend | Best For | Latency | Cost |
|---------|----------|---------|------|
| Local | Single machine | Lowest | Storage only |
| S3 | Distributed | Medium | Pay-per-use |
| Database | Multi-instance | Low-Medium | DB costs |

## Next Steps

- **[Graph State](graph-state.md)**: Coordinate with state management
- **[Checkpointing](checkpointing.md)**: Checkpoint artifacts
- **[Testing Nodes](../nodes/testing.md)**: Test with workspaces
- **[Fundamentals](fundamentals.md)**: Review graph basics
