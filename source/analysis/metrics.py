"""Metric definitions and numeric calculation helpers for simulation analysis."""

from __future__ import annotations

from typing import Any

COMPARISON_METRICS: list[dict[str, Any]] = [
    {
        "field": "schedule_latency",
        "label": "Schedule Latency",
        "description": "Wall-clock scheduling decision time, without subexperiment generation (s)",
        "unit": "Seconds (s)",
        "lower_is_better": True,
    },
    {
        "field": "cutting_time",
        "label": "Cutting Time",
        "description": "Wall-clock time generating subcircuits and QPD subexperiments (s)",
        "unit": "Seconds (s)",
        "lower_is_better": True,
    },
    {
        "field": "makespan",
        "label": "Makespan",
        "description": "Total virtual execution time (s)",
        "unit": "Seconds (s)",
        "lower_is_better": True,
    },
    {
        "field": "average_turnaround_time",
        "label": "Avg Turnaround Time",
        "description": "Mean turnaround time across jobs (s)",
        "unit": "Seconds (s)",
        "lower_is_better": True,
    },
    {
        "field": "average_waiting_time",
        "label": "Avg Waiting Time",
        "description": "Mean actual waiting time in queue (s)",
        "unit": "Seconds (s)",
        "lower_is_better": True,
    },
    {
        "field": "average_fidelity",
        "label": "Avg Fidelity (Qubit-wt)",
        "description": "Mean quantum circuit fidelity weighted by circuit qubits",
        "unit": "Score (0-1)",
        "lower_is_better": False,
    },
    {
        "field": "cluster_qubit_utilization",
        "label": "Cluster Qubit Utilization",
        "description": "Qubit space-time allocation over total cluster capacity * makespan",
        "unit": "Ratio (0-1)",
        "lower_is_better": False,
    },
    {
        "field": "total_cutting_overhead",
        "label": "Cutting Overhead",
        "description": "Total sampling overhead incurred from circuit cutting",
        "unit": "Sampling factor",
        "lower_is_better": True,
    },
    {
        "field": "crosstalk_exposure",
        "label": "Crosstalk Exposure",
        "description": "Share of executed two-qubit gates running next to a simultaneous neighbouring one",
        "unit": "Ratio (0-1)",
        "lower_is_better": True,
    },
]


def safe_float(value: str | float | None) -> float | None:
    """Convert string or numeric value to float, returning None if invalid."""
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value: str | int | None) -> int | None:
    """Convert string or numeric value to int, returning None if invalid."""
    if value == "" or value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def format_value_for_display(val: float | None) -> str:
    """Format floating point numbers cleanly for chart labels and report tables."""
    if val is None:
        return "N/A"
    if val == 0:
        return "0.0"
    abs_val = abs(val)
    if abs_val >= 100:
        return f"{val:.1f}"
    if abs_val >= 1:
        return f"{val:.4f}".rstrip("0").rstrip(".")
    if abs_val >= 0.001:
        return f"{val:.5f}".rstrip("0").rstrip(".")
    return f"{val:.3e}"


def calculate_difference(
    algo_val: float | None, baseline_val: float | None
) -> tuple[float | None, str]:
    """Calculate absolute difference: algo_val - baseline_val."""
    if algo_val is None or baseline_val is None:
        return (None, "N/A")
    diff = algo_val - baseline_val
    sign = "+" if diff > 0 else ""
    return (diff, f"{sign}{format_value_for_display(diff)}")


def calculate_percentage_difference(
    algo_val: float | None, baseline_val: float | None
) -> str:
    """Calculate percentage difference relative to baseline: ((algo - baseline) / baseline) * 100."""
    if algo_val is None or baseline_val is None:
        return "N/A"
    if baseline_val == 0:
        if algo_val == 0:
            return "0.0%"
        return "+inf%" if algo_val > 0 else "-inf%"

    pct_diff = ((algo_val - baseline_val) / abs(baseline_val)) * 100.0
    sign = "+" if pct_diff > 0 else ""
    return f"{sign}{pct_diff:.2f}%"
