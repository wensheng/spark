"""Command-line tool for managing RSI human reviews.

Usage:
    python -m spark.rsi.review_cli list-pending
    python -m spark.rsi.review_cli show <request_id>
    python -m spark.rsi.review_cli approve <request_id> --reviewer <name> [--feedback <text>]
    python -m spark.rsi.review_cli reject <request_id> --reviewer <name> --reason <text> [--feedback <text>]
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from spark.rsi.human_review import ReviewRequestStore, ReviewDecision


def format_request_summary(request_data: dict) -> str:
    """Format a request as a summary line."""
    request_id = request_data['request_id']
    hypothesis_id = request_data['hypothesis_id']
    hypothesis_type = request_data['hypothesis'].get('hypothesis_type', 'unknown')
    risk_level = request_data['hypothesis'].get('risk_level', 'unknown')
    created_at = request_data['created_at'][:19]  # Trim microseconds

    return f"{request_id} | {hypothesis_id} | {hypothesis_type} | Risk: {risk_level} | Created: {created_at}"


def format_request_details(request_data: dict) -> str:
    """Format a request with full details."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"Review Request: {request_data['request_id']}")
    lines.append("=" * 80)
    lines.append("")

    # Hypothesis info
    hypothesis = request_data['hypothesis']
    lines.append(f"Hypothesis ID: {hypothesis['hypothesis_id']}")
    lines.append(f"Type: {hypothesis['hypothesis_type']}")
    lines.append(f"Target Node: {hypothesis.get('target_node', 'N/A')}")
    lines.append(f"Risk Level: {hypothesis['risk_level']}")
    lines.append("")

    # Rationale
    lines.append("Rationale:")
    lines.append(f"  {hypothesis['rationale']}")
    lines.append("")

    # Expected improvement
    improvement = hypothesis.get('expected_improvement', {})
    lines.append("Expected Improvement:")
    lines.append(f"  Success Rate Delta: {improvement.get('success_rate_delta', 0):+.2%}")
    lines.append(f"  Latency Delta: {improvement.get('latency_delta', 0):+.2f}s")
    lines.append(f"  Cost Delta: {improvement.get('cost_delta', 0):+.2%}")
    lines.append("")

    # Changes
    changes = hypothesis.get('changes', [])
    lines.append(f"Changes ({len(changes)}):")
    for i, change in enumerate(changes, 1):
        lines.append(f"  {i}. Type: {change['type']}")
        if change.get('target_node_id'):
            lines.append(f"     Target Node: {change['target_node_id']}")
        if change.get('target_edge_id'):
            lines.append(f"     Target Edge: {change['target_edge_id']}")
    lines.append("")

    # Risk factors
    risk_factors = hypothesis.get('risk_factors', [])
    if risk_factors:
        lines.append("Risk Factors:")
        for factor in risk_factors:
            lines.append(f"  - {factor}")
        lines.append("")

    # Validation result
    validation = request_data.get('validation_result', {})
    lines.append("Validation Result:")
    lines.append(f"  Approved: {validation.get('approved', False)}")
    lines.append(f"  Risk Score: {validation.get('risk_score', 0):.2f}")

    violations = validation.get('violations', [])
    if violations:
        lines.append("  Violations:")
        for v in violations:
            lines.append(f"    - [{v['severity']}] {v['rule']}: {v['message']}")

    recommendations = validation.get('recommendations', [])
    if recommendations:
        lines.append("  Recommendations:")
        for rec in recommendations:
            lines.append(f"    - {rec}")
    lines.append("")

    # Request metadata
    lines.append("Request Metadata:")
    lines.append(f"  Created: {request_data['created_at']}")
    lines.append(f"  Expires: {request_data['expires_at']}")
    lines.append(f"  Status: {request_data['status']}")
    lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


async def list_pending(args):
    """List all pending review requests."""
    store = ReviewRequestStore(args.storage_dir)
    requests = await store.get_pending_requests()

    if not requests:
        print("No pending review requests.")
        return

    print(f"Pending Review Requests ({len(requests)}):")
    print()
    for request in requests:
        # Load full data for summary
        request_path = store._get_request_path(request.request_id)
        with open(request_path, 'r') as f:
            request_data = json.load(f)
        print(format_request_summary(request_data))


async def show_request(args):
    """Show detailed information about a request."""
    store = ReviewRequestStore(args.storage_dir)

    # Check pending first
    request_path = store._get_request_path(args.request_id, "pending")
    if not request_path.exists():
        # Check completed
        request_path = store._get_request_path(args.request_id, "completed")
        if not request_path.exists():
            print(f"Request not found: {args.request_id}")
            return

    with open(request_path, 'r') as f:
        request_data = json.load(f)

    print(format_request_details(request_data))


async def approve_request(args):
    """Approve a review request."""
    store = ReviewRequestStore(args.storage_dir)

    # Check if request exists
    request = await store.get_request(args.request_id)
    if request is None:
        print(f"Request not found: {args.request_id}")
        return

    if request.status != "pending":
        print(f"Request is not pending (status: {request.status})")
        return

    # Create decision
    decision = ReviewDecision(
        request_id=args.request_id,
        approved=True,
        reviewer=args.reviewer,
        reviewed_at=datetime.now(),
        feedback=args.feedback or "",
        reason="approved",
    )

    # Submit decision
    await store.submit_decision(decision)

    print(f"✓ Approved request {args.request_id}")
    print(f"  Reviewer: {args.reviewer}")
    if args.feedback:
        print(f"  Feedback: {args.feedback}")


async def reject_request(args):
    """Reject a review request."""
    store = ReviewRequestStore(args.storage_dir)

    # Check if request exists
    request = await store.get_request(args.request_id)
    if request is None:
        print(f"Request not found: {args.request_id}")
        return

    if request.status != "pending":
        print(f"Request is not pending (status: {request.status})")
        return

    # Create decision
    decision = ReviewDecision(
        request_id=args.request_id,
        approved=False,
        reviewer=args.reviewer,
        reviewed_at=datetime.now(),
        feedback=args.feedback or "",
        reason=args.reason,
    )

    # Submit decision
    await store.submit_decision(decision)

    print(f"✗ Rejected request {args.request_id}")
    print(f"  Reviewer: {args.reviewer}")
    print(f"  Reason: {args.reason}")
    if args.feedback:
        print(f"  Feedback: {args.feedback}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage RSI human review requests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--storage-dir',
        default='~/.cache/spark/rsi/reviews',
        help='Directory for review storage (default: ~/.cache/spark/rsi/reviews)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # list-pending command
    list_parser = subparsers.add_parser('list-pending', help='List all pending review requests')

    # show command
    show_parser = subparsers.add_parser('show', help='Show details of a review request')
    show_parser.add_argument('request_id', help='Review request ID')

    # approve command
    approve_parser = subparsers.add_parser('approve', help='Approve a review request')
    approve_parser.add_argument('request_id', help='Review request ID')
    approve_parser.add_argument('--reviewer', required=True, help='Your name/identifier')
    approve_parser.add_argument('--feedback', help='Optional feedback message')

    # reject command
    reject_parser = subparsers.add_parser('reject', help='Reject a review request')
    reject_parser.add_argument('request_id', help='Review request ID')
    reject_parser.add_argument('--reviewer', required=True, help='Your name/identifier')
    reject_parser.add_argument('--reason', required=True, help='Reason for rejection')
    reject_parser.add_argument('--feedback', help='Optional additional feedback')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == 'list-pending':
        asyncio.run(list_pending(args))
    elif args.command == 'show':
        asyncio.run(show_request(args))
    elif args.command == 'approve':
        asyncio.run(approve_request(args))
    elif args.command == 'reject':
        asyncio.run(reject_request(args))


if __name__ == '__main__':
    main()
