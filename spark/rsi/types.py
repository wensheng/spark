"""Core data types for RSI system."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime


# ============================================================================
# Enums
# ============================================================================

class HypothesisType(str, Enum):
    """Types of improvement hypotheses."""
    PROMPT_OPTIMIZATION = "prompt_optimization"
    NODE_REPLACEMENT = "node_replacement"
    EDGE_MODIFICATION = "edge_modification"
    PARALLELIZATION = "parallelization"
    PARAMETER_TUNING = "parameter_tuning"
    TOOL_ADDITION = "tool_addition"
    CACHING = "caching"
    CUSTOM = "custom"


class RiskLevel(str, Enum):
    """Risk levels for changes."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Diagnostic Report Types
# ============================================================================

@dataclass
class AnalysisPeriod:
    """Time period for analysis."""
    start: str  # ISO format timestamp
    end: str    # ISO format timestamp


@dataclass
class PerformanceSummary:
    """Overall performance summary."""
    total_executions: int
    success_rate: float
    avg_duration: float
    p50_duration: float
    p95_duration: float
    p99_duration: float
    total_cost: Optional[float] = None


@dataclass
class NodeMetrics:
    """Performance metrics for a single node."""
    node_id: str
    node_name: str
    executions: int
    successes: int
    failures: int
    success_rate: float
    error_rate: float
    avg_duration: float
    p95_duration: float


@dataclass
class Bottleneck:
    """Identified performance bottleneck."""
    node_id: str
    node_name: str
    issue: str  # high_latency, high_error_rate
    severity: str  # low, medium, high, critical
    impact_score: float
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FailurePattern:
    """Common failure pattern."""
    node_id: str
    node_name: str
    error_type: str
    count: int
    sample_messages: List[str] = field(default_factory=list)


@dataclass
class DiagnosticReport:
    """Complete diagnostic report."""
    graph_id: str
    graph_version: str = "unknown"
    analysis_period: Optional[AnalysisPeriod] = None
    summary: Optional[PerformanceSummary] = None
    node_metrics: Dict[str, NodeMetrics] = field(default_factory=dict)
    bottlenecks: List[Bottleneck] = field(default_factory=list)
    failures: List[FailurePattern] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    generated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = datetime.now()


# ============================================================================
# Phase 2: Hypothesis Types
# ============================================================================

@dataclass
class ExpectedImprovement:
    """Expected improvement from a hypothesis."""
    success_rate_delta: float = 0.0  # e.g., +0.10 for 10% improvement
    latency_delta: float = 0.0  # seconds (negative is improvement)
    cost_delta: float = 0.0  # percentage (negative is improvement)
    quality_delta: Optional[float] = None


@dataclass
class ChangeSpec:
    """Specification of a change to apply."""
    type: str  # node_config_update, node_add, node_remove, edge_add, etc.
    target_node_id: Optional[str] = None
    target_edge_id: Optional[str] = None
    config_path: Optional[str] = None  # Path to config value (e.g., "prompt_template")
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    additional_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementHypothesis:
    """A hypothesis for improving a graph."""
    hypothesis_id: str
    graph_id: str
    graph_version_baseline: str
    hypothesis_type: HypothesisType
    target_node: Optional[str] = None

    # Reasoning
    rationale: str = ""
    diagnostic_evidence: Dict[str, Any] = field(default_factory=dict)

    # Expected outcomes
    expected_improvement: Optional[ExpectedImprovement] = None

    # Changes
    changes: List[ChangeSpec] = field(default_factory=list)

    # Risk assessment
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_factors: List[str] = field(default_factory=list)

    # Metadata
    created_at: Optional[datetime] = None
    created_by: str = "rsi_system"

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.expected_improvement is None:
            self.expected_improvement = ExpectedImprovement()


# ============================================================================
# Phase 2: Validation Types
# ============================================================================

@dataclass
class ValidationViolation:
    """A validation rule violation."""
    rule: str
    severity: str  # error, warning
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validating a hypothesis."""
    approved: bool
    risk_level: RiskLevel
    risk_score: float
    violations: List[ValidationViolation] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ============================================================================
# Phase 3: Testing Types
# ============================================================================

class TestStatus(str, Enum):
    """Status of hypothesis test."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


@dataclass
class TestMetrics:
    """Performance metrics collected during testing."""
    num_runs: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration: float
    p50_duration: float
    p95_duration: float
    p99_duration: float
    total_cost: Optional[float] = None
    error_types: Dict[str, int] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    """Result of comparing baseline vs candidate performance."""
    baseline_metrics: TestMetrics
    candidate_metrics: TestMetrics

    # Deltas (candidate - baseline)
    success_rate_delta: float
    avg_duration_delta: float
    p95_duration_delta: float

    # Statistical significance
    is_significant: bool
    confidence_level: float  # e.g., 0.95 for 95% confidence

    # Verdict
    is_improvement: bool
    is_regression: bool
    meets_success_criteria: bool

    # Optional fields
    cost_delta: Optional[float] = None
    p_value: Optional[float] = None
    summary: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Complete test result for a hypothesis."""
    hypothesis_id: str
    test_id: str
    status: TestStatus

    # Test configuration
    num_baseline_runs: int
    num_candidate_runs: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Results
    comparison: Optional[ComparisonResult] = None

    # Success criteria
    success_criteria_met: bool = False
    success_criteria: Dict[str, Any] = field(default_factory=dict)

    # Error info
    error_message: Optional[str] = None

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.started_at is None:
            self.started_at = datetime.now()


# ============================================================================
# Phase 6: Structural Change Types
# ============================================================================

@dataclass
class NodeReplacementCandidate:
    """A candidate node for replacement."""
    replacement_node_type: str
    replacement_node_name: str
    compatibility_score: float  # 0.0 to 1.0
    expected_improvement: Optional[ExpectedImprovement] = None
    compatibility_notes: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)


@dataclass
class CompatibilityReport:
    """Report on replacement node compatibility."""
    is_compatible: bool
    compatibility_score: float
    input_compatibility: bool
    output_compatibility: bool
    interface_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ImpactEstimate:
    """Estimated impact of a change."""
    latency_impact: float  # Percentage change (negative is improvement)
    cost_impact: float  # Percentage change
    reliability_impact: float  # Percentage change
    complexity_delta: int  # Change in graph complexity
    confidence: float  # 0.0 to 1.0
    assumptions: List[str] = field(default_factory=list)


@dataclass
class RedundantEdge:
    """An edge that is rarely or never traversed."""
    from_node: str
    to_node: str
    edge_condition: Optional[str] = None
    traversal_count: int = 0
    total_executions: int = 0
    traversal_rate: float = 0.0
    recommendation: str = ""


@dataclass
class ShortcutOpportunity:
    """An opportunity to add a shortcut edge."""
    from_node: str
    to_node: str
    skipped_nodes: List[str] = field(default_factory=list)
    frequency: int = 0  # How often this path is taken
    potential_latency_savings: float = 0.0  # Seconds
    confidence: float = 0.0  # 0.0 to 1.0
    condition_suggestion: Optional[str] = None


@dataclass
class OptimizedCondition:
    """An optimized edge condition."""
    original_condition: str
    optimized_condition: str
    improvement_type: str  # "simplify", "strengthen", "weaken"
    expected_benefit: str
    rationale: str


@dataclass
class ParallelizableSequence:
    """A sequence of nodes that can be parallelized."""
    sequential_nodes: List[str]
    entry_node: str
    exit_node: str
    has_dependencies: bool = False
    dependency_details: Dict[str, Any] = field(default_factory=dict)
    estimated_speedup: float = 0.0  # Multiplier (e.g., 2.0 = 2x faster)
    confidence: float = 0.0


@dataclass
class ParallelizationBenefit:
    """Expected benefit from parallelization."""
    latency_reduction: float  # Seconds
    speedup_multiplier: float
    resource_increase: float  # Percentage increase in resource usage
    complexity_increase: int
    confidence: float


@dataclass
class ParallelGraphStructure:
    """A parallel graph structure."""
    parallel_branches: List[List[str]]  # Each inner list is a parallel branch
    merge_node_id: Optional[str] = None
    requires_merge: bool = False
    merge_strategy: str = "wait_all"  # wait_all, wait_any, custom


@dataclass
class NodeModification:
    """A modification to a node."""
    node_id: str
    field: str
    old_value: Any
    new_value: Any


@dataclass
class EdgeModification:
    """A modification to an edge."""
    edge_id: str
    field: str
    old_value: Any
    new_value: Any


@dataclass
class StructuralDiff:
    """Detailed structural diff between two graphs."""
    nodes_added: List[str] = field(default_factory=list)
    nodes_removed: List[str] = field(default_factory=list)
    nodes_modified: List[NodeModification] = field(default_factory=list)
    edges_added: List[str] = field(default_factory=list)
    edges_removed: List[str] = field(default_factory=list)
    edges_modified: List[EdgeModification] = field(default_factory=list)
    complexity_delta: int = 0
    summary: str = ""


@dataclass
class StructuralValidationResult:
    """Result of structural integrity validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reachable_nodes: List[str] = field(default_factory=list)
    orphaned_nodes: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
