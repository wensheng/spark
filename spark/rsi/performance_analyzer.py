"""Performance analyzer for identifying bottlenecks and opportunities."""

from spark.nodes import Node
from spark.rsi.types import (
    DiagnosticReport,
    AnalysisPeriod,
    PerformanceSummary,
    NodeMetrics,
    Bottleneck,
    FailurePattern,
)
from typing import Dict, List, Any, Optional
import statistics
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Check for telemetry availability
try:
    from spark.telemetry import TelemetryManager, EventType, SpanStatus
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    logger.warning("Telemetry not available - PerformanceAnalyzerNode requires telemetry")


class PerformanceAnalyzerNode(Node):
    """Analyzes telemetry data to identify performance issues and opportunities.

    This node queries the telemetry system to aggregate performance metrics,
    detect bottlenecks, and generate diagnostic reports for RSI.

    Usage:
        analyzer = PerformanceAnalyzerNode(
            analysis_window_hours=24,
            min_executions=10
        )
        result = await analyzer.run({'graph_id': 'my_graph'})
        report = result['report']
    """

    def __init__(
        self,
        name: str = "PerformanceAnalyzer",
        analysis_window_hours: int = 24,
        min_executions: int = 10,
        **kwargs
    ):
        """Initialize PerformanceAnalyzerNode.

        Args:
            name: Node name
            analysis_window_hours: Hours of historical data to analyze
            min_executions: Minimum executions needed for analysis
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.analysis_window_hours = analysis_window_hours
        self.min_executions = min_executions
        self.telemetry_manager = None

        if not TELEMETRY_AVAILABLE:
            logger.warning(
                "Telemetry system not available. Install telemetry dependencies "
                "or PerformanceAnalyzerNode will not function."
            )

    async def on_start(self, context):
        """Initialize telemetry manager connection."""
        if TELEMETRY_AVAILABLE:
            self.telemetry_manager = TelemetryManager.get_instance()
        else:
            logger.error("Cannot initialize telemetry manager - telemetry not available")

    async def process(self, context):
        """Generate diagnostic report from telemetry data.

        Args:
            context: Execution context with inputs:
                - graph_id: ID of graph to analyze (required)
                - graph_version: Version tag (optional)
                - start_time: Override start time (optional)
                - end_time: Override end time (optional)

        Returns:
            Dict with:
                - has_issues: bool indicating if issues found
                - report: DiagnosticReport or None
                - reason: str if no analysis performed
        """
        if not TELEMETRY_AVAILABLE or self.telemetry_manager is None:
            return {
                'has_issues': False,
                'reason': 'Telemetry system not available',
                'report': None
            }

        # Get inputs
        graph_id = context.inputs.content.get('graph_id')
        if not graph_id:
            logger.error("graph_id is required for performance analysis")
            return {
                'has_issues': False,
                'reason': 'graph_id is required',
                'report': None
            }

        graph_version = context.inputs.content.get('graph_version', 'unknown')

        # Define analysis period
        end_time = context.inputs.content.get('end_time')
        start_time = context.inputs.content.get('start_time')

        if end_time is None:
            end_time = datetime.now().timestamp()
        if start_time is None:
            start_time = (datetime.now() - timedelta(hours=self.analysis_window_hours)).timestamp()

        logger.info(
            f"Analyzing graph '{graph_id}' from {datetime.fromtimestamp(start_time)} "
            f"to {datetime.fromtimestamp(end_time)}"
        )

        # Query telemetry data
        traces = await self.telemetry_manager.query_traces(
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )

        if len(traces) < self.min_executions:
            logger.info(
                f"Insufficient data for analysis: {len(traces)} executions "
                f"(minimum: {self.min_executions})"
            )
            return {
                'has_issues': False,
                'reason': f'Insufficient data: {len(traces)} executions (minimum: {self.min_executions})',
                'report': None
            }

        # Generate report
        report = await self._generate_report(
            graph_id,
            graph_version,
            traces,
            start_time,
            end_time
        )

        # Determine if there are issues
        has_issues = (
            report.summary.success_rate < 0.95 or
            len(report.bottlenecks) > 0 or
            len(report.failures) > 0
        )

        return {
            'has_issues': has_issues,
            'report': report,
            'summary': {
                'total_executions': report.summary.total_executions,
                'success_rate': report.summary.success_rate,
                'avg_duration': report.summary.avg_duration,
                'bottlenecks_count': len(report.bottlenecks),
                'failures_count': len(report.failures),
            }
        }

    async def _generate_report(
        self,
        graph_id: str,
        graph_version: str,
        traces: List[Any],
        start_time: float,
        end_time: float
    ) -> DiagnosticReport:
        """Generate diagnostic report from traces.

        Args:
            graph_id: Graph identifier
            graph_version: Graph version
            traces: List of trace objects
            start_time: Analysis start timestamp
            end_time: Analysis end timestamp

        Returns:
            DiagnosticReport with findings
        """
        # Overall metrics
        total_executions = len(traces)
        successful = sum(1 for t in traces if t.status.value == 'ok')
        failed = total_executions - successful
        durations = [t.duration for t in traces if t.duration is not None]

        summary = PerformanceSummary(
            total_executions=total_executions,
            success_rate=successful / total_executions if total_executions > 0 else 0,
            avg_duration=statistics.mean(durations) if durations else 0,
            p50_duration=statistics.median(durations) if durations else 0,
            p95_duration=self._percentile(durations, 0.95) if durations else 0,
            p99_duration=self._percentile(durations, 0.99) if durations else 0,
        )

        logger.info(
            f"Summary: {total_executions} executions, "
            f"{summary.success_rate:.1%} success rate, "
            f"{summary.avg_duration:.3f}s avg duration"
        )

        # Analyze per-node performance
        node_metrics = await self._analyze_node_performance(traces)
        logger.info(f"Analyzed {len(node_metrics)} nodes")

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(node_metrics, summary)
        logger.info(f"Identified {len(bottlenecks)} bottlenecks")

        # Identify failure patterns
        failures = await self._analyze_failures(traces)
        logger.info(f"Identified {len(failures)} failure patterns")

        # Generate opportunities
        opportunities = self._generate_opportunities(bottlenecks, failures, node_metrics)
        logger.info(f"Generated {len(opportunities)} improvement opportunities")

        return DiagnosticReport(
            graph_id=graph_id,
            graph_version=graph_version,
            analysis_period=AnalysisPeriod(
                start=datetime.fromtimestamp(start_time).isoformat(),
                end=datetime.fromtimestamp(end_time).isoformat(),
            ),
            summary=summary,
            node_metrics=node_metrics,
            bottlenecks=bottlenecks,
            failures=failures,
            opportunities=opportunities,
        )

    async def _analyze_node_performance(self, traces: List[Any]) -> Dict[str, NodeMetrics]:
        """Analyze performance metrics per node.

        Args:
            traces: List of trace objects

        Returns:
            Dict mapping node_id to NodeMetrics
        """
        node_stats = {}

        for trace in traces:
            # Query spans for this trace
            spans = await self.telemetry_manager.query_spans(trace_id=trace.trace_id)

            for span in spans:
                node_id = span.attributes.get('node.id', 'unknown')

                if node_id not in node_stats:
                    node_stats[node_id] = {
                        'executions': 0,
                        'successes': 0,
                        'failures': 0,
                        'durations': [],
                        'node_name': span.attributes.get('node.name', node_id),
                    }

                stats = node_stats[node_id]
                stats['executions'] += 1

                if span.status.value == 'ok':
                    stats['successes'] += 1
                else:
                    stats['failures'] += 1

                if span.duration is not None:
                    stats['durations'].append(span.duration)

        # Calculate aggregated metrics
        result = {}
        for node_id, stats in node_stats.items():
            durations = stats['durations']
            result[node_id] = NodeMetrics(
                node_id=node_id,
                node_name=stats['node_name'],
                executions=stats['executions'],
                successes=stats['successes'],
                failures=stats['failures'],
                success_rate=stats['successes'] / stats['executions'] if stats['executions'] > 0 else 0,
                error_rate=stats['failures'] / stats['executions'] if stats['executions'] > 0 else 0,
                avg_duration=statistics.mean(durations) if durations else 0,
                p95_duration=self._percentile(durations, 0.95) if durations else 0,
            )

        return result

    def _identify_bottlenecks(
        self,
        node_metrics: Dict[str, NodeMetrics],
        summary: PerformanceSummary
    ) -> List[Bottleneck]:
        """Identify performance bottlenecks.

        Args:
            node_metrics: Per-node metrics
            summary: Overall performance summary

        Returns:
            List of identified bottlenecks
        """
        bottlenecks = []

        # Calculate average node duration for comparison
        if node_metrics:
            node_durations = [m.avg_duration for m in node_metrics.values()]
            avg_node_duration = sum(node_durations) / len(node_durations) if node_durations else 0
        else:
            avg_node_duration = 0

        for node_id, metrics in node_metrics.items():
            # Check for high latency (> 2x average node duration)
            if avg_node_duration > 0 and metrics.avg_duration > avg_node_duration * 2:
                severity = 'high' if metrics.avg_duration > avg_node_duration * 5 else 'medium'
                bottlenecks.append(Bottleneck(
                    node_id=node_id,
                    node_name=metrics.node_name,
                    issue='high_latency',
                    severity=severity,
                    impact_score=metrics.avg_duration / avg_node_duration if avg_node_duration > 0 else 0,
                    metrics={
                        'avg_duration': metrics.avg_duration,
                        'p95_duration': metrics.p95_duration,
                    }
                ))

            # Check for high error rate (> 5%)
            if metrics.error_rate > 0.05:
                severity = 'critical' if metrics.error_rate > 0.20 else 'high'
                bottlenecks.append(Bottleneck(
                    node_id=node_id,
                    node_name=metrics.node_name,
                    issue='high_error_rate',
                    severity=severity,
                    impact_score=metrics.error_rate * 10,  # Weight errors heavily
                    metrics={
                        'error_rate': metrics.error_rate,
                        'executions': metrics.executions,
                        'failures': metrics.failures,
                    }
                ))

        # Sort by impact score
        bottlenecks.sort(key=lambda x: x.impact_score, reverse=True)

        return bottlenecks

    async def _analyze_failures(self, traces: List[Any]) -> List[FailurePattern]:
        """Analyze failure patterns.

        Args:
            traces: List of trace objects

        Returns:
            List of common failure patterns
        """
        failures = []
        error_counts = {}

        for trace in traces:
            if trace.status.value != 'error':
                continue

            # Query events for this trace
            events = await self.telemetry_manager.query_events(
                trace_id=trace.trace_id,
                type=EventType.NODE_FAILED
            )

            for event in events:
                node_id = event.attributes.get('node.id', 'unknown')
                error_type = event.attributes.get('error.type', 'unknown_error')

                key = f"{node_id}:{error_type}"
                if key not in error_counts:
                    error_counts[key] = {
                        'node_id': node_id,
                        'node_name': event.attributes.get('node.name', node_id),
                        'error_type': error_type,
                        'count': 0,
                        'sample_messages': [],
                    }

                error_counts[key]['count'] += 1

                # Keep sample error messages (max 3)
                error_message = event.attributes.get('error.message', '')
                if len(error_counts[key]['sample_messages']) < 3 and error_message:
                    error_counts[key]['sample_messages'].append(error_message)

        # Convert to list and sort by frequency
        for data in error_counts.values():
            failures.append(FailurePattern(
                node_id=data['node_id'],
                node_name=data['node_name'],
                error_type=data['error_type'],
                count=data['count'],
                sample_messages=data['sample_messages'],
            ))

        failures.sort(key=lambda x: x.count, reverse=True)

        return failures

    def _generate_opportunities(
        self,
        bottlenecks: List[Bottleneck],
        failures: List[FailurePattern],
        node_metrics: Dict[str, NodeMetrics]
    ) -> List[str]:
        """Generate improvement opportunities from analysis.

        Args:
            bottlenecks: Identified bottlenecks
            failures: Identified failure patterns
            node_metrics: Per-node metrics

        Returns:
            List of improvement opportunity descriptions
        """
        opportunities = []

        # Opportunities from bottlenecks (top 3)
        for bottleneck in bottlenecks[:3]:
            if bottleneck.issue == 'high_latency':
                opportunities.append(
                    f"Optimize {bottleneck.node_name} - high latency "
                    f"({bottleneck.metrics.get('avg_duration', 0):.2f}s average)"
                )
            elif bottleneck.issue == 'high_error_rate':
                opportunities.append(
                    f"Fix {bottleneck.node_name} - high error rate "
                    f"({bottleneck.metrics.get('error_rate', 0):.1%})"
                )

        # Opportunities from failures (top 3)
        for failure in failures[:3]:
            opportunities.append(
                f"Handle {failure.error_type} in {failure.node_name} "
                f"({failure.count} occurrences)"
            )

        return opportunities

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """Calculate percentile of a list of numbers.

        Args:
            data: List of values
            percentile: Percentile to calculate (0.0 to 1.0)

        Returns:
            Percentile value
        """
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]
