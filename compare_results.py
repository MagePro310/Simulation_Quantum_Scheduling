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


def calculate_difference(lpt_val: float | None, ffd_val: float | None) -> tuple[float | None, str]:
    """Calculate LPT - FFD difference.

    Returns (difference, formatted_string) tuple.
    """
    if lpt_val is None or ffd_val is None:
        return (None, "N/A")

    diff = lpt_val - ffd_val

    # Format with sign
    if diff > 0:
        return (diff, f"+{diff:.4f}")
    else:
        return (diff, f"{diff:.4f}")


def calculate_percentage_difference(lpt_val: float | None, ffd_val: float | None) -> str:
    """Calculate percentage difference, handle zero baseline.

    Returns formatted string with explanation if baseline is zero.
    """
    if lpt_val is None or ffd_val is None:
        return "N/A"

    if ffd_val == 0:
        if lpt_val == 0:
            return "0% (both zero)"
        else:
            return f"N/A (FFD baseline is zero)"

    pct_diff = ((lpt_val - ffd_val) / ffd_val) * 100
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
        f.write(f"- **Queue Policy**: {baseline_result.get('queue_policy', 'N/A')}\n")
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
                f.write(f"| {algo} | {latency if latency is not None else 'N/A'} | baseline |\n")
            else:
                diff, diff_str = calculate_difference(latency, baseline_latency)
                f.write(f"| {algo} | {latency if latency is not None else 'N/A'} | {diff_str} |\n")
        f.write("\n")

        # Execution Summary Metrics
        f.write("## Execution Summary Metrics\n\n")
        f.write("All times in seconds (virtual execution time).\n\n")

        metrics = [
            ("makespan", "Makespan", "Total virtual execution time"),
            ("average_turnaround_time", "Avg Turnaround Time", "Job submission to completion (successful jobs only)"),
            ("average_waiting_time", "Avg Waiting Time", "Time between job batches (successful jobs only)"),
            ("average_response_time", "Avg Response Time", "Initial waiting time (successful jobs only)"),
            ("job_completion_rate", "Job Completion Rate", "Throughput: successes / makespan"),
            ("average_fidelity", "Avg Fidelity", "Mean fidelity (successful jobs only)"),
        ]

        # Build table header dynamically
        header = "| Metric | " + " | ".join(algorithm_names) + " |"
        separator = "|" + "|".join(["--------"] * (len(algorithm_names) + 1)) + "|"
        f.write(header + "\n")
        f.write(separator + "\n")

        for field, label, description in metrics:
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
                        row_values.append(f"{val:.4f} ({diff_str}, {pct_str})")
                    else:
                        row_values.append(f"{val:.4f}")
                else:
                    row_values.append("N/A")

            f.write("| " + " | ".join(row_values) + " |\n")

        f.write("\n**Metric Definitions:**\n\n")
        for _, label, description in metrics:
            f.write(f"- **{label}**: {description}\n")
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

    # Define color palette for algorithms
    colors = plt.cm.tab10(np.linspace(0, 1, max(num_algos, 3)))

    # Chart 1: Key Metrics Comparison
    metrics = [
        ("makespan", "Makespan"),
        ("average_turnaround_time", "Avg Turnaround"),
        ("average_waiting_time", "Avg Waiting"),
        ("job_completion_rate", "Completion Rate"),
        ("average_fidelity", "Avg Fidelity"),
    ]

    fig, axes = plt.subplots(1, len(metrics), figsize=(16, 4))
    fig.suptitle("Algorithm Comparison: Key Metrics", fontsize=14, fontweight="bold")

    for idx, (field, label) in enumerate(metrics):
        ax = axes[idx]

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
            bars = ax.bar(labels, values, color=colors_used)
            ax.set_title(label)
            ax.set_ylabel("Value")
            ax.tick_params(axis='x', rotation=45)

            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.3f}',
                       ha='center', va='bottom', fontsize=8)
        else:
            ax.text(0.5, 0.5, "Data\nN/A", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(label)

    plt.tight_layout()
    chart_path = output_dir / "metrics_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
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
