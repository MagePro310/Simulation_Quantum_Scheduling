#!/usr/bin/env python3
"""Analysis and comparison of batch scheduling results.

Reads a timestamped CSV from run_batch.py and generates a Markdown report
with PNG charts comparing all algorithms in the batch.

Automatically adapts to any number of algorithms configured in batch_config.py.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent

COMPARISON_METRICS: list[dict[str, Any]] = [
    {
        "field": "schedule_latency",
        "label": "Schedule Latency",
        "description": "Wall-clock scheduling decision time (s)",
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
        "description": "Qubit space-time allocation over total cluster capacity × makespan",
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
]


def load_batch_results(csv_path: Path) -> list[dict[str, Any]]:
    """Load all result rows from the batch CSV file."""
    results = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results


def parse_nested_json(value: str) -> Any:
    """Parse JSON string field, return empty dict/list if empty or invalid."""
    if not value or value == "":
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def check_compatibility(results: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Check if results are compatible for comparison.

    Returns (is_compatible, warnings) tuple.
    """
    warnings = []

    if len(results) < 2:
        warnings.append("Less than 2 results found in CSV")
        return (False, warnings)

    # Check workload fingerprints
    fingerprints = set(r.get("workload_fingerprint", "") for r in results if r.get("process_status") == "SUCCESS")
    if len(fingerprints) > 1:
        warnings.append(f"Different workload fingerprints detected: {fingerprints}")

    # Check machine configs
    machines = set(r.get("machine_config", "") for r in results if r.get("process_status") == "SUCCESS")
    if len(machines) > 1:
        warnings.append(f"Different machine configurations detected")

    # Check seeds
    seeds = set(r.get("seed", "") for r in results if r.get("process_status") == "SUCCESS")
    if len(seeds) > 1:
        warnings.append(f"Different seeds used: {seeds}")

    # Check queue policies
    policies = set(r.get("queue_policy", "") for r in results if r.get("process_status") == "SUCCESS")
    if len(policies) > 1:
        warnings.append(f"Different queue policies used: {policies}")

    # Check cutting policies
    cutting_policies = set(r.get("cutting_policy", "") for r in results if r.get("process_status") == "SUCCESS")
    if len(cutting_policies) > 1:
        warnings.append(f"Different cutting policies used: {cutting_policies}")

    return (True, warnings)


def safe_float(value: str | float) -> float | None:
    """Convert string to float, return None if empty or invalid."""
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value: str | int) -> int | None:
    """Convert string to int, return None if empty or invalid."""
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
        return f"{val:.2f}"
    if abs_val >= 1:
        return f"{val:.4f}"
    if abs_val >= 0.001:
        return f"{val:.4f}"
    return f"{val:.4g}"


def calculate_difference(algo_val: float | None, baseline_val: float | None) -> tuple[float | None, str]:
    """Calculate algorithm - baseline difference.

    Returns (difference, formatted_string) tuple.
    """
    if algo_val is None or baseline_val is None:
        return (None, "N/A")

    diff = algo_val - baseline_val
    sign = "+" if diff > 0 else ""

    abs_d = abs(diff)
    if abs_d == 0:
        return (diff, "0.0")
    if abs_d < 0.0001:
        return (diff, f"{sign}{diff:.4g}")
    return (diff, f"{sign}{diff:.4f}")


def calculate_percentage_difference(algo_val: float | None, baseline_val: float | None) -> str:
    """Calculate percentage difference, handle zero baseline.

    Returns formatted string with explanation if baseline is zero.
    """
    if algo_val is None or baseline_val is None:
        return "N/A"

    if baseline_val == 0:
        if algo_val == 0:
            return "0% (both zero)"
        else:
            return "N/A (baseline is zero)"

    pct_diff = ((algo_val - baseline_val) / baseline_val) * 100
    if pct_diff > 0:
        return f"+{pct_diff:.2f}%"
    else:
        return f"{pct_diff:.2f}%"



def generate_markdown_report(
    results: list[dict[str, Any]],
    output_path: Path,
    warnings: list[str],
) -> None:
    """Generate a Markdown report comparing algorithm results."""

    # Group results by algorithm
    results_by_algo = {}
    for result in results:
        algo = result.get("algorithm", "Unknown")
        results_by_algo[algo] = result

    algorithm_names = list(results_by_algo.keys())
    successful_algos = [
        algo for algo in algorithm_names
        if results_by_algo[algo].get("process_status") == "SUCCESS"
    ]

    # Select baseline algorithm (first successful one, or first in list)
    baseline_algo = successful_algos[0] if successful_algos else algorithm_names[0]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Quantum Scheduling Batch Results Comparison\n\n")

        # Compatibility warnings
        if warnings:
            f.write("## ⚠️ Compatibility Warnings\n\n")
            for warning in warnings:
                f.write(f"- {warning}\n")
            f.write("\n")

        # Process status
        f.write("## Execution Status\n\n")
        f.write("| Algorithm | Status | Error |\n")
        f.write("|-----------|--------|-------|\n")

        for result in results:
            algo = result.get("algorithm", "Unknown")
            status = result.get("process_status", "UNKNOWN")
            error = result.get("error_message", "")
            status_icon = "✅" if status == "SUCCESS" else "❌"
            f.write(f"| {algo} | {status_icon} {status} | {error[:100]} |\n")
        f.write("\n")

        # Check if we have enough successful runs to compare
        if len(successful_algos) < 2:
            f.write(f"**⚠️ Need at least 2 successful runs for comparison (found {len(successful_algos)})**\n\n")
            return

        baseline_result = results_by_algo[baseline_algo]

        # Workload and Configuration
        f.write("## Workload and Configuration\n\n")
        f.write(f"- **Circuits**: {baseline_result.get('num_circuits', 'N/A')} ({baseline_result.get('name_circuits', 'N/A')})\n")
        f.write(f"- **Average Qubits**: {baseline_result.get('average_qubits', 'N/A')}\n")
        f.write(f"- **Machines**: {baseline_result.get('name_machines', 'N/A')}\n")
        f.write(f"- **Seed**: {baseline_result.get('seed', 'N/A')}\n")
        f.write(f"- **Cutting Policy**: {baseline_result.get('cutting_policy', 'N/A')} (scope: {baseline_result.get('cutting_scope', 'N/A')})\n")
        f.write(f"- **Queue / Backfill Policy**: {baseline_result.get('queue_policy', 'N/A')}\n")
        f.write(f"- **Baseline Algorithm**: {baseline_algo}\n\n")

        # Scheduling Latency
        f.write("## Scheduling Latency (wall-clock)\n\n")
        f.write("| Algorithm | Latency (s) | Difference from baseline |\n")
        f.write("|-----------|-------------|-------------------------|\n")

        baseline_latency = safe_float(baseline_result.get("schedule_latency"))

        for algo in algorithm_names:
            result = results_by_algo[algo]
            if result.get("process_status") != "SUCCESS":
                continue

            latency = safe_float(result.get("schedule_latency"))
            if algo == baseline_algo:
                f.write(f"| {algo} | {format_value_for_display(latency)} | baseline |\n")
            else:
                diff, diff_str = calculate_difference(latency, baseline_latency)
                f.write(f"| {algo} | {format_value_for_display(latency)} | {diff_str} |\n")
        f.write("\n")

        # Execution Summary Metrics
        f.write("## Execution Summary Metrics\n\n")
        f.write("All times in seconds (virtual execution time) unless specified otherwise.\n\n")

        # Build table header dynamically
        header = "| Metric | " + " | ".join(algorithm_names) + " |"
        separator = "|" + "|".join(["--------"] * (len(algorithm_names) + 1)) + "|"
        f.write(header + "\n")
        f.write(separator + "\n")

        for metric_info in COMPARISON_METRICS:
            field = metric_info["field"]
            label = metric_info["label"]
            row_values = [label]
            for algo in algorithm_names:
                result = results_by_algo[algo]
                if result.get("process_status") != "SUCCESS":
                    row_values.append("N/A")
                    continue

                val = safe_float(result.get(field))
                if val is not None:
                    # Add difference from baseline in parentheses for non-baseline algorithms
                    if algo != baseline_algo:
                        baseline_val = safe_float(baseline_result.get(field))
                        diff, diff_str = calculate_difference(val, baseline_val)
                        pct_str = calculate_percentage_difference(val, baseline_val)
                        row_values.append(f"{format_value_for_display(val)} ({diff_str}, {pct_str})")
                    else:
                        row_values.append(f"{format_value_for_display(val)}")
                else:
                    row_values.append("N/A")

            f.write("| " + " | ".join(row_values) + " |\n")

        f.write("\n**Metric Definitions:**\n\n")
        for metric_info in COMPARISON_METRICS:
            f.write(f"- **{metric_info['label']}**: {metric_info['description']}\n")
        f.write("\n**Note**: Values in parentheses show (difference from baseline, % change)\n\n")

        # Job Outcomes
        f.write("## Job Outcomes\n\n")
        f.write("| Algorithm | Succeeded | Failed | Blocked | Total |\n")
        f.write("|-----------|-----------|--------|---------|-------|\n")

        for algo in algorithm_names:
            result = results_by_algo[algo]
            if result.get("process_status") != "SUCCESS":
                f.write(f"| {algo} | N/A | N/A | N/A | N/A |\n")
                continue

            succeeded = safe_int(result.get("succeeded_jobs")) or 0
            failed = safe_int(result.get("failed_jobs")) or 0
            blocked = safe_int(result.get("blocked_jobs")) or 0
            total = succeeded + failed + blocked
            f.write(f"| {algo} | {succeeded} | {failed} | {blocked} | {total} |\n")
        f.write("\n")

        # Machine Utilization
        f.write("## Machine Utilization\n\n")

        # Collect all machine names from all algorithms
        all_machines_data = {}
        for algo in algorithm_names:
            result = results_by_algo[algo]
            if result.get("process_status") == "SUCCESS":
                machines_json = parse_nested_json(result.get("machines_json", ""))
                all_machines_data[algo] = machines_json

        if all_machines_data:
            all_machine_names = sorted(set(
                name for machines in all_machines_data.values() for name in machines.keys()
            ))

            # Dynamic header
            header_cols = ["Machine"] + [f"{algo} Util" for algo in algorithm_names] + [f"{algo} Busy Time" for algo in algorithm_names]
            f.write("| " + " | ".join(header_cols) + " |\n")
            f.write("|" + "|".join(["---"] * len(header_cols)) + "|\n")

            for machine_name in all_machine_names:
                row = [machine_name]

                # Utilization columns
                for algo in algorithm_names:
                    machines = all_machines_data.get(algo, {})
                    machine_data = machines.get(machine_name, {})
                    util = safe_float(machine_data.get("utilization"))
                    row.append(f"{util:.4f}" if util is not None else "N/A")

                # Busy time columns
                for algo in algorithm_names:
                    machines = all_machines_data.get(algo, {})
                    machine_data = machines.get(machine_name, {})
                    busy = safe_float(machine_data.get("busy_time"))
                    row.append(f"{busy:.2f}s" if busy is not None else "N/A")

                f.write("| " + " | ".join(row) + " |\n")

            f.write("\n")
            f.write("**Note**: Utilization measures logical qubit allocation over capacity × makespan.\n\n")
        else:
            f.write("No machine utilization data available.\n\n")

        # Batch Execution Timeline
        f.write("## Batch Execution Records\n\n")

        for algo in algorithm_names:
            result = results_by_algo[algo]
            if result.get("process_status") != "SUCCESS":
                continue

            batches = parse_nested_json(result.get("batches_json", ""))

            f.write(f"### {algo} Batches\n\n")
            if batches and isinstance(batches, list) and len(batches) > 0:
                f.write(f"Total batches: {len(batches)}\n\n")
                f.write("| Batch | Machine | Jobs | Shots | Start | End | Duration | Status |\n")
                f.write("|-------|---------|------|-------|-------|-----|----------|--------|\n")

                for batch in batches[:20]:  # Limit to first 20 for readability
                    batch_id = batch.get("batch_id", "?")
                    machine = batch.get("machine_name", "?")
                    jobs = batch.get("job_ids", [])
                    job_count = len(jobs) if isinstance(jobs, list) else "?"
                    shots = batch.get("shots", "?")
                    start = safe_float(batch.get("start_time"))
                    end = safe_float(batch.get("end_time"))
                    duration = f"{end - start:.2f}s" if start is not None and end is not None else "N/A"
                    status = batch.get("status", "?")

                    start_display = f"{start:.2f}s" if start is not None else "N/A"
                    end_display = f"{end:.2f}s" if end is not None else "N/A"

                    f.write(f"| {batch_id} | {machine} | {job_count} | {shots} | {start_display} | {end_display} | {duration} | {status} |\n")

                if len(batches) > 20:
                    f.write(f"\n*Showing first 20 of {len(batches)} batches*\n")
                f.write("\n")
            else:
                f.write("No batch data available.\n\n")

        # Visualizations
        f.write("## Visualizations\n\n")
        f.write("### Overview Metrics Comparison\n\n")
        f.write("![Metrics Overview](metrics_comparison.png)\n\n")
        f.write("### Individual Metric Comparisons\n\n")
        for metric_info in COMPARISON_METRICS:
            f.write(f"#### {metric_info['label']}\n\n")
            f.write(f"![{metric_info['label']}]({metric_info['field']}.png)\n\n")
        f.write("### Job Outcomes\n\n")
        f.write("![Job Outcomes](job_outcomes.png)\n\n")
        f.write("### Machine Utilization\n\n")
        f.write("![Machine Utilization](machine_utilization.png)\n\n")


def generate_individual_metric_chart(
    metric_info: dict[str, Any],
    results_by_algo: dict[str, dict[str, Any]],
    algorithm_names: list[str],
    colors: list[Any],
    output_dir: Path,
) -> Path:
    """Generate an individual comparison bar chart PNG for a specific metric."""
    field = metric_info["field"]
    label = metric_info["label"]
    unit = metric_info.get("unit", "")
    lower_is_better = metric_info.get("lower_is_better")

    fig, ax = plt.subplots(figsize=(max(6, len(algorithm_names) * 1.5), 5))

    values = []
    labels = []
    bar_colors = []

    for idx, algo in enumerate(algorithm_names):
        result = results_by_algo[algo]
        val = safe_float(result.get(field))
        if val is not None:
            values.append(val)
            labels.append(algo)
            bar_colors.append(colors[idx])

    if values:
        bars = ax.bar(
            labels,
            values,
            color=bar_colors,
            width=min(0.55, 0.2 + 0.1 * len(labels)),
            edgecolor="black",
            linewidth=0.8,
            alpha=0.85,
            zorder=3,
        )
        ax.set_axisbelow(True)
        ax.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)

        # Value labels above bars
        for bar, val in zip(bars, values):
            height = bar.get_height()
            formatted = format_value_for_display(val)
            ax.annotate(
                formatted,
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )

        pref_text = ""
        if lower_is_better is True:
            pref_text = " (lower is better)"
        elif lower_is_better is False:
            pref_text = " (higher is better)"

        ax.set_title(f"{label} Comparison{pref_text}", fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("Algorithm", fontsize=11, fontweight="medium")
        ax.set_ylabel(unit, fontsize=11, fontweight="medium")
        ax.tick_params(axis="x", labelsize=10)
        ax.tick_params(axis="y", labelsize=10)

        if min(values) >= 0:
            ax.set_ylim(bottom=0)
        ax.margins(y=0.18)
    else:
        ax.text(0.5, 0.5, "Data N/A", ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.set_title(f"{label} Comparison", fontsize=13, fontweight="bold")

    plt.tight_layout()
    chart_path = output_dir / f"{field}.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return chart_path


def generate_charts(results: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    """Generate comparison charts as PNG files.

    Returns list of generated chart paths.
    """
    chart_paths = []

    # Group results by algorithm
    results_by_algo = {}
    for result in results:
        algo = result.get("algorithm", "")
        if result.get("process_status") == "SUCCESS":
            results_by_algo[algo] = result

    if len(results_by_algo) < 2:
        return chart_paths

    algorithm_names = list(results_by_algo.keys())
    num_algos = len(algorithm_names)

    # Define color palette for algorithms (distinct categorical colors)
    colors = [plt.cm.tab10(i % 10) for i in range(num_algos)]

    # 1. Individual Metric Charts (each metric saved to its own PNG)
    for metric_info in COMPARISON_METRICS:
        single_chart_path = generate_individual_metric_chart(
            metric_info=metric_info,
            results_by_algo=results_by_algo,
            algorithm_names=algorithm_names,
            colors=colors,
            output_dir=output_dir,
        )
        chart_paths.append(single_chart_path)

    # 2. All Metrics Comparison Grid (dynamically sized based on number of metrics)
    num_metrics = len(COMPARISON_METRICS)
    cols = 4
    rows = (num_metrics + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 4.5 * rows))
    fig.suptitle("Algorithm Comparison: All Metrics", fontsize=16, fontweight="bold", y=0.98)
    axes_flat = axes.flatten()

    for idx, metric_info in enumerate(COMPARISON_METRICS):
        ax = axes_flat[idx]
        field = metric_info["field"]
        label = metric_info["label"]
        lower_is_better = metric_info.get("lower_is_better")

        values = []
        labels = []
        colors_used = []

        for algo_idx, algo in enumerate(algorithm_names):
            result = results_by_algo[algo]
            val = safe_float(result.get(field))
            if val is not None:
                values.append(val)
                labels.append(algo)
                colors_used.append(colors[algo_idx])

        if values:
            bars = ax.bar(
                labels,
                values,
                color=colors_used,
                width=min(0.55, 0.2 + 0.1 * len(labels)),
                edgecolor="black",
                linewidth=0.6,
                alpha=0.85,
                zorder=3,
            )
            ax.set_axisbelow(True)
            ax.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)

            pref_str = " (↓)" if lower_is_better is True else (" (↑)" if lower_is_better is False else "")
            ax.set_title(f"{label}{pref_str}", fontsize=11, fontweight="bold")
            ax.set_ylabel(metric_info.get("unit", "Value"), fontsize=9)
            ax.tick_params(axis="x", rotation=30, labelsize=9)
            ax.tick_params(axis="y", labelsize=8)

            for bar, val in zip(bars, values):
                height = bar.get_height()
                formatted = format_value_for_display(val)
                ax.annotate(
                    formatted,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            if min(values) >= 0:
                ax.set_ylim(bottom=0)
            ax.margins(y=0.18)
        else:
            ax.text(0.5, 0.5, "Data\nN/A", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(label, fontsize=11, fontweight="bold")

    # Hide any unused subplot axes in the grid
    for j in range(num_metrics, len(axes_flat)):
        fig.delaxes(axes_flat[j])

    plt.tight_layout()
    chart_path = output_dir / "metrics_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    chart_paths.append(chart_path)


    # Chart 2: Job Outcomes (multiple pie charts or stacked bar)
    if num_algos <= 4:
        # Use pie charts for up to 4 algorithms
        fig, axes = plt.subplots(1, num_algos, figsize=(5 * num_algos, 4))
        if num_algos == 1:
            axes = [axes]
        fig.suptitle("Job Outcomes Comparison", fontsize=14, fontweight="bold")

        for idx, algo in enumerate(algorithm_names):
            result = results_by_algo[algo]
            succeeded = safe_int(result.get("succeeded_jobs")) or 0
            failed = safe_int(result.get("failed_jobs")) or 0
            blocked = safe_int(result.get("blocked_jobs")) or 0

            axes[idx].pie(
                [succeeded, failed, blocked],
                labels=["Succeeded", "Failed", "Blocked"],
                autopct="%1.1f%%",
                colors=["#2ecc71", "#e74c3c", "#95a5a6"],
                startangle=90,
            )
            axes[idx].set_title(algo)
    else:
        # Use stacked bar chart for many algorithms
        fig, ax = plt.subplots(figsize=(max(10, num_algos * 1.5), 6))
        fig.suptitle("Job Outcomes Comparison", fontsize=14, fontweight="bold")

        succeeded_data = []
        failed_data = []
        blocked_data = []

        for algo in algorithm_names:
            result = results_by_algo[algo]
            succeeded_data.append(safe_int(result.get("succeeded_jobs")) or 0)
            failed_data.append(safe_int(result.get("failed_jobs")) or 0)
            blocked_data.append(safe_int(result.get("blocked_jobs")) or 0)

        x = np.arange(len(algorithm_names))
        width = 0.6

        ax.bar(x, succeeded_data, width, label="Succeeded", color="#2ecc71")
        ax.bar(x, failed_data, width, bottom=succeeded_data, label="Failed", color="#e74c3c")
        ax.bar(x, blocked_data, width,
               bottom=np.array(succeeded_data) + np.array(failed_data),
               label="Blocked", color="#95a5a6")

        ax.set_xlabel("Algorithm")
        ax.set_ylabel("Number of Jobs")
        ax.set_xticks(x)
        ax.set_xticklabels(algorithm_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    chart_path = output_dir / "job_outcomes.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    chart_paths.append(chart_path)

    # Chart 3: Machine Utilization
    all_machines_data = {}
    for algo in algorithm_names:
        result = results_by_algo[algo]
        machines_json = parse_nested_json(result.get("machines_json", ""))
        all_machines_data[algo] = machines_json

    if all_machines_data and any(all_machines_data.values()):
        all_machine_names = sorted(set(
            name for machines in all_machines_data.values() for name in machines.keys()
        ))

        fig, ax = plt.subplots(figsize=(max(12, len(all_machine_names) * 2), 6))

        x = np.arange(len(all_machine_names))
        width = 0.8 / num_algos

        for idx, algo in enumerate(algorithm_names):
            machines = all_machines_data.get(algo, {})
            utils = [safe_float(machines.get(m, {}).get("utilization")) or 0 for m in all_machine_names]

            offset = (idx - num_algos / 2) * width + width / 2
            ax.bar(x + offset, utils, width, label=algo, color=colors[idx])

        ax.set_xlabel("Machine")
        ax.set_ylabel("Utilization")
        ax.set_title("Machine Utilization Comparison", fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(all_machine_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        chart_path = output_dir / "machine_utilization.png"
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        chart_paths.append(chart_path)

    return chart_paths


def main() -> int:
    """Main entry point for result comparison."""
    parser = argparse.ArgumentParser(
        description="Compare quantum scheduling batch results"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to batch results CSV, relative to the working directory or project root"
    )
    args = parser.parse_args()

    csv_path = args.csv_file.expanduser()
    if not csv_path.is_absolute() and not csv_path.exists():
        csv_path = PROJECT_ROOT / csv_path
    csv_path = csv_path.resolve()

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        return 1

    # Create analysis directory
    csv_stem = csv_path.stem
    analysis_dir = csv_path.parent / f"analysis_{csv_stem}"
    analysis_dir.mkdir(exist_ok=True)

    print(f"Loading results from: {csv_path}")
    results = load_batch_results(csv_path)
    print(f"  Loaded {len(results)} result rows")

    # Check compatibility
    is_compatible, warnings = check_compatibility(results)
    if warnings:
        print("\nCompatibility warnings:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")

    # Generate markdown report
    report_path = analysis_dir / "comparison_report.md"
    print(f"\nGenerating report: {report_path}")
    generate_markdown_report(results, report_path, warnings)

    # Generate charts
    print(f"Generating charts...")
    chart_paths = generate_charts(results, analysis_dir)
    for chart_path in chart_paths:
        print(f"  Created: {chart_path}")

    print(f"\n✅ Analysis complete. Results in: {analysis_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
