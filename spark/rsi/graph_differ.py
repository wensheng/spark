"""Graph diff visualization system for RSI.

This module provides utilities for generating human-readable diffs between graph
specifications, supporting multiple output formats (text, Markdown, HTML, JSON).
"""

import json
from typing import Dict, Any, List
from dataclasses import dataclass, asdict

from spark.nodes.spec import GraphSpec
from spark.rsi.types import StructuralDiff, NodeModification, EdgeModification
from spark.rsi.change_applicator import ChangeApplicator


class GraphDiffer:
    """Generates detailed diffs between graph versions.

    Features:
    - Structural diff (nodes, edges added/removed/modified)
    - Configuration diff (what configs changed)
    - Visual diff representation for UI
    - Multiple output formats (text, Markdown, HTML, JSON)
    - Impact summary
    """

    def __init__(self):
        """Initialize GraphDiffer."""
        self.applicator = ChangeApplicator()

    def compute_diff(
        self,
        baseline: GraphSpec,
        modified: GraphSpec
    ) -> StructuralDiff:
        """Compute comprehensive graph diff.

        Args:
            baseline: Baseline graph specification
            modified: Modified graph specification

        Returns:
            Structural diff
        """
        return self.applicator.compute_structural_diff(baseline, modified)

    def format_diff_text(self, diff: StructuralDiff) -> str:
        """Format diff as human-readable text (similar to git diff).

        Args:
            diff: Structural diff

        Returns:
            Formatted text
        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append("GRAPH DIFF")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append(f"Summary: {diff.summary}")
        lines.append(f"Complexity Delta: {diff.complexity_delta:+d}")
        lines.append("")

        # Nodes added
        if diff.nodes_added:
            lines.append(f"+ NODES ADDED ({len(diff.nodes_added)}):")
            for node_id in diff.nodes_added:
                lines.append(f"  + {node_id}")
            lines.append("")

        # Nodes removed
        if diff.nodes_removed:
            lines.append(f"- NODES REMOVED ({len(diff.nodes_removed)}):")
            for node_id in diff.nodes_removed:
                lines.append(f"  - {node_id}")
            lines.append("")

        # Nodes modified
        if diff.nodes_modified:
            lines.append(f"~ NODES MODIFIED ({len(diff.nodes_modified)}):")
            for mod in diff.nodes_modified:
                lines.append(f"  ~ {mod.node_id}:")
                lines.append(f"      Field: {mod.field}")
                lines.append(f"      Old: {self._truncate_value(mod.old_value)}")
                lines.append(f"      New: {self._truncate_value(mod.new_value)}")
            lines.append("")

        # Edges added
        if diff.edges_added:
            lines.append(f"+ EDGES ADDED ({len(diff.edges_added)}):")
            for edge_id in diff.edges_added:
                lines.append(f"  + {edge_id}")
            lines.append("")

        # Edges removed
        if diff.edges_removed:
            lines.append(f"- EDGES REMOVED ({len(diff.edges_removed)}):")
            for edge_id in diff.edges_removed:
                lines.append(f"  - {edge_id}")
            lines.append("")

        # Edges modified
        if diff.edges_modified:
            lines.append(f"~ EDGES MODIFIED ({len(diff.edges_modified)}):")
            for mod in diff.edges_modified:
                lines.append(f"  ~ {mod.edge_id}:")
                lines.append(f"      Field: {mod.field}")
                lines.append(f"      Old: {self._truncate_value(mod.old_value)}")
                lines.append(f"      New: {self._truncate_value(mod.new_value)}")
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)

    def format_diff_markdown(self, diff: StructuralDiff) -> str:
        """Format diff as Markdown for documentation.

        Args:
            diff: Structural diff

        Returns:
            Formatted Markdown
        """
        lines = []

        # Header
        lines.append("# Graph Diff")
        lines.append("")
        lines.append(f"**Summary:** {diff.summary}")
        lines.append("")
        lines.append(f"**Complexity Delta:** {diff.complexity_delta:+d}")
        lines.append("")

        # Nodes added
        if diff.nodes_added:
            lines.append(f"## Nodes Added ({len(diff.nodes_added)})")
            lines.append("")
            for node_id in diff.nodes_added:
                lines.append(f"- ✅ `{node_id}`")
            lines.append("")

        # Nodes removed
        if diff.nodes_removed:
            lines.append(f"## Nodes Removed ({len(diff.nodes_removed)})")
            lines.append("")
            for node_id in diff.nodes_removed:
                lines.append(f"- ❌ `{node_id}`")
            lines.append("")

        # Nodes modified
        if diff.nodes_modified:
            lines.append(f"## Nodes Modified ({len(diff.nodes_modified)})")
            lines.append("")
            for mod in diff.nodes_modified:
                lines.append(f"### `{mod.node_id}`")
                lines.append("")
                lines.append(f"**Field:** `{mod.field}`")
                lines.append("")
                lines.append("```diff")
                lines.append(f"- {self._truncate_value(mod.old_value)}")
                lines.append(f"+ {self._truncate_value(mod.new_value)}")
                lines.append("```")
                lines.append("")

        # Edges added
        if diff.edges_added:
            lines.append(f"## Edges Added ({len(diff.edges_added)})")
            lines.append("")
            for edge_id in diff.edges_added:
                lines.append(f"- ✅ `{edge_id}`")
            lines.append("")

        # Edges removed
        if diff.edges_removed:
            lines.append(f"## Edges Removed ({len(diff.edges_removed)})")
            lines.append("")
            for edge_id in diff.edges_removed:
                lines.append(f"- ❌ `{edge_id}`")
            lines.append("")

        # Edges modified
        if diff.edges_modified:
            lines.append(f"## Edges Modified ({len(diff.edges_modified)})")
            lines.append("")
            for mod in diff.edges_modified:
                lines.append(f"### `{mod.edge_id}`")
                lines.append("")
                lines.append(f"**Field:** `{mod.field}`")
                lines.append("")
                lines.append("```diff")
                lines.append(f"- {self._truncate_value(mod.old_value)}")
                lines.append(f"+ {self._truncate_value(mod.new_value)}")
                lines.append("```")
                lines.append("")

        return "\n".join(lines)

    def format_diff_html(self, diff: StructuralDiff) -> str:
        """Format diff as HTML with syntax highlighting.

        Args:
            diff: Structural diff

        Returns:
            Formatted HTML
        """
        lines = []

        # Header
        lines.append("<div class='graph-diff'>")
        lines.append("<h1>Graph Diff</h1>")
        lines.append(f"<p><strong>Summary:</strong> {diff.summary}</p>")
        lines.append(f"<p><strong>Complexity Delta:</strong> {diff.complexity_delta:+d}</p>")

        # Nodes added
        if diff.nodes_added:
            lines.append(f"<h2>Nodes Added ({len(diff.nodes_added)})</h2>")
            lines.append("<ul class='added'>")
            for node_id in diff.nodes_added:
                lines.append(f"<li><span class='node-id'>{node_id}</span></li>")
            lines.append("</ul>")

        # Nodes removed
        if diff.nodes_removed:
            lines.append(f"<h2>Nodes Removed ({len(diff.nodes_removed)})</h2>")
            lines.append("<ul class='removed'>")
            for node_id in diff.nodes_removed:
                lines.append(f"<li><span class='node-id'>{node_id}</span></li>")
            lines.append("</ul>")

        # Nodes modified
        if diff.nodes_modified:
            lines.append(f"<h2>Nodes Modified ({len(diff.nodes_modified)})</h2>")
            for mod in diff.nodes_modified:
                lines.append("<div class='node-modification'>")
                lines.append(f"<h3>{mod.node_id}</h3>")
                lines.append(f"<p><strong>Field:</strong> {mod.field}</p>")
                lines.append("<pre class='diff'>")
                lines.append(f"<span class='removed'>- {self._escape_html(self._truncate_value(mod.old_value))}</span>")
                lines.append(f"<span class='added'>+ {self._escape_html(self._truncate_value(mod.new_value))}</span>")
                lines.append("</pre>")
                lines.append("</div>")

        # Edges added
        if diff.edges_added:
            lines.append(f"<h2>Edges Added ({len(diff.edges_added)})</h2>")
            lines.append("<ul class='added'>")
            for edge_id in diff.edges_added:
                lines.append(f"<li><span class='edge-id'>{edge_id}</span></li>")
            lines.append("</ul>")

        # Edges removed
        if diff.edges_removed:
            lines.append(f"<h2>Edges Removed ({len(diff.edges_removed)})</h2>")
            lines.append("<ul class='removed'>")
            for edge_id in diff.edges_removed:
                lines.append(f"<li><span class='edge-id'>{edge_id}</span></li>")
            lines.append("</ul>")

        # Edges modified
        if diff.edges_modified:
            lines.append(f"<h2>Edges Modified ({len(diff.edges_modified)})</h2>")
            for mod in diff.edges_modified:
                lines.append("<div class='edge-modification'>")
                lines.append(f"<h3>{mod.edge_id}</h3>")
                lines.append(f"<p><strong>Field:</strong> {mod.field}</p>")
                lines.append("<pre class='diff'>")
                lines.append(f"<span class='removed'>- {self._escape_html(self._truncate_value(mod.old_value))}</span>")
                lines.append(f"<span class='added'>+ {self._escape_html(self._truncate_value(mod.new_value))}</span>")
                lines.append("</pre>")
                lines.append("</div>")

        lines.append("</div>")

        return "\n".join(lines)

    def format_diff_json(self, diff: StructuralDiff) -> str:
        """Format diff as JSON for programmatic access.

        Args:
            diff: Structural diff

        Returns:
            Formatted JSON
        """
        # Convert to dict, handling dataclasses
        diff_dict = {
            'summary': diff.summary,
            'complexity_delta': diff.complexity_delta,
            'nodes_added': diff.nodes_added,
            'nodes_removed': diff.nodes_removed,
            'nodes_modified': [
                {
                    'node_id': mod.node_id,
                    'field': mod.field,
                    'old_value': str(mod.old_value) if not isinstance(mod.old_value, (str, int, float, bool, type(None))) else mod.old_value,
                    'new_value': str(mod.new_value) if not isinstance(mod.new_value, (str, int, float, bool, type(None))) else mod.new_value,
                }
                for mod in diff.nodes_modified
            ],
            'edges_added': diff.edges_added,
            'edges_removed': diff.edges_removed,
            'edges_modified': [
                {
                    'edge_id': mod.edge_id,
                    'field': mod.field,
                    'old_value': str(mod.old_value) if not isinstance(mod.old_value, (str, int, float, bool, type(None))) else mod.old_value,
                    'new_value': str(mod.new_value) if not isinstance(mod.new_value, (str, int, float, bool, type(None))) else mod.new_value,
                }
                for mod in diff.edges_modified
            ],
        }

        return json.dumps(diff_dict, indent=2)

    def generate_visual_diff(self, diff: StructuralDiff) -> Dict[str, Any]:
        """Generate visual representation (for UI).

        Returns data structure for graph visualization showing:
        - Nodes added (green), removed (red), modified (yellow)
        - Edges added (green), removed (red), modified (yellow)

        Args:
            diff: Structural diff

        Returns:
            Visual diff data
        """
        return {
            'nodes': {
                'added': [{'id': node_id, 'status': 'added'} for node_id in diff.nodes_added],
                'removed': [{'id': node_id, 'status': 'removed'} for node_id in diff.nodes_removed],
                'modified': [
                    {
                        'id': mod.node_id,
                        'status': 'modified',
                        'changes': {
                            'field': mod.field,
                            'old': self._truncate_value(mod.old_value),
                            'new': self._truncate_value(mod.new_value),
                        }
                    }
                    for mod in diff.nodes_modified
                ],
            },
            'edges': {
                'added': [{'id': edge_id, 'status': 'added'} for edge_id in diff.edges_added],
                'removed': [{'id': edge_id, 'status': 'removed'} for edge_id in diff.edges_removed],
                'modified': [
                    {
                        'id': mod.edge_id,
                        'status': 'modified',
                        'changes': {
                            'field': mod.field,
                            'old': self._truncate_value(mod.old_value),
                            'new': self._truncate_value(mod.new_value),
                        }
                    }
                    for mod in diff.edges_modified
                ],
            },
            'summary': diff.summary,
            'complexity_delta': diff.complexity_delta,
        }

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _truncate_value(self, value: Any, max_length: int = 100) -> str:
        """Truncate long values for display.

        Args:
            value: Value to truncate
            max_length: Maximum length

        Returns:
            Truncated string
        """
        value_str = str(value)
        if len(value_str) > max_length:
            return value_str[:max_length] + "..."
        return value_str

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))
