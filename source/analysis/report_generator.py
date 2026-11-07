"""Markdown report generation and batch results comparison orchestrator."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from source.analysis.chart_generator import generate_charts, parse_nested_json
from source.analysis.metrics import (
    COMPARISON_METRICS,
    calculate_difference,
    calculate_percentage_difference,
    format_value_for_display,
    safe_float,
    safe_int,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_batch_results(csv_path: Path) -> list[dict[str, Any]]:
    """Load all result rows from the batch CSV file."""
    results = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results


def check_compatibility(results: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Check if results are compatible for comparison.

    Returns:
        (is_compatible, warnings) tuple.
    """
    warnings = []

    if len(results) < 2:
        warnings.append("Less than 2 results found in CSV")
        return (False, warnings)

    # Check workload fingerprints
    fingerprints = {
        r.get("workload_fingerprint", "")
        for r in results
        if r.get("process_status") == "SUCCESS"
    }
    if len(fingerprints) > 1:
        warnings.append(f"Different workload fingerprints detected: {fingerprints}")

    # Check machine configs
    machines = {
        r.get("machine_config", "")
        for r in results
        if r.get("process_status") == "SUCCESS"
    }
    if len(machines) > 1:
        warnings.append("Different machine configurations detected")

    # Check seeds
    seeds = {r.get("seed", "") for r in results if r.get("process_status") == "SUCCESS"}
    if len(seeds) > 1:
        warnings.append(f"Different seeds used: {seeds}")

    # Check queue policies
    policies = {
        r.get("queue_policy", "")
        for r in results
        if r.get("process_status") == "SUCCESS"
    }
    if len(policies) > 1:
        warnings.append(f"Different queue policies used: {policies}")

    # Check cutting policies
    cutting_policies = {
        r.get("cutting_policy", "")
        for r in results
        if r.get("process_status") == "SUCCESS"
    }
    if len(cutting_policies) > 1:
        warnings.append(f"Different cutting policies used: {cutting_policies}")

    return (True, warnings)


def generate_markdown_report(
    results: list[dict[str, Any]],
    output_path: Path,
    warnings: list[str],
) -> None:
    """Generate a Markdown report comparing algorithm results."""
    results_by_algo = {}
    for result in results:
        algo = result.get("algorithm", "Unknown")
        results_by_algo[algo] = result

    algorithm_names = list(results_by_algo.keys())
    successful_algos = [
        algo
        for algo in algorithm_names
        if results_by_algo[algo].get("process_status") == "SUCCESS"
    ]

    baseline_algo = successful_algos[0] if successful_algos else algorithm_names[0]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Quantum Scheduling Batch Results Comparison\n\n")

        if warnings:
            f.write("## ⚠️ Compatibility Warnings\n\n")
            for warning in warnings:
                f.write(f"- {warning}\n")
            f.write("\n")

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

        if len(successful_algos) < 2:
            f.write(
                f"**⚠️ Need at least 2 successful runs for comparison (found {len(successful_algos)})**\n\n"
            )
            return

        baseline_result = results_by_algo[baseline_algo]

        f.write("## Workload and Configuration\n\n")
        f.write(
            f"- **Circuits**: {baseline_result.get('num_circuits', 'N/A')} ({baseline_result.get('name_circuits', 'N/A')})\n"
        )
        f.write(f"- **Average Qubits**: {baseline_result.get('average_qubits', 'N/A')}\n")
        f.write(f"- **Machines**: {baseline_result.get('name_machines', 'N/A')}\n")
        f.write(f"- **Queue / Backfill Policy**: {baseline_result.get('queue_policy', 'N/A')}\n")
        f.write(f"- **Baseline Algorithm**: {baseline_algo}\n\n")

        f.write("### Circuit Cutting Configurations\n\n")
        f.write("| Algorithm | Mandatory Cut (Exceed) | Optional Cut (Remaining) |\n")
        f.write("|-----------|------------------------|-------------------------|\n")
        for algo in algorithm_names:
            res = results_by_algo[algo]
            if res.get("process_status") != "SUCCESS":
                continue
            exceed_p = res.get("cutting_policy") or res.get("exceed_cutting_policy") or "greedy"
            is_opt = str(res.get("optional_cutting", "False")).lower() in ("true", "1")
            opt_p = res.get("optional_cutting_policy", "")
            opt_s = f"Enabled ({opt_p})" if is_opt else "Disabled (exceed only)"
            f.write(f"| {algo} | {exceed_p} | {opt_s} |\n")
        f.write("\n")

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
                _, diff_str = calculate_difference(latency, baseline_latency)
                f.write(f"| {algo} | {format_value_for_display(latency)} | {diff_str} |\n")
        f.write("\n")

        f.write("## Execution Summary Metrics\n\n")
        f.write("All times in seconds (virtual execution time) unless specified otherwise.\n\n")

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
                    if algo != baseline_algo:
                        baseline_val = safe_float(baseline_result.get(field))
                        _, diff_str = calculate_difference(val, baseline_val)
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

        f.write("## Machine Utilization\n\n")
        all_machines_data = {}
        for algo in algorithm_names:
            result = results_by_algo[algo]
            if result.get("process_status") == "SUCCESS":
                machines_json = parse_nested_json(result.get("machines_json", ""))
                all_machines_data[algo] = machines_json

        if all_machines_data:
            all_machine_names = sorted(
                set(name for machines in all_machines_data.values() for name in machines.keys())
            )
            header_cols = (
                ["Machine"]
                + [f"{algo} Util" for algo in algorithm_names]
                + [f"{algo} Busy Time" for algo in algorithm_names]
            )
            f.write("| " + " | ".join(header_cols) + " |\n")
            f.write("|" + "|".join(["---"] * len(header_cols)) + "|\n")

            for machine_name in all_machine_names:
                row = [machine_name]
                for algo in algorithm_names:
                    machines = all_machines_data.get(algo, {})
                    machine_data = machines.get(machine_name, {})
                    util = safe_float(machine_data.get("utilization"))
                    row.append(f"{util:.4f}" if util is not None else "N/A")

                for algo in algorithm_names:
                    machines = all_machines_data.get(algo, {})
                    machine_data = machines.get(machine_name, {})
                    busy = safe_float(machine_data.get("busy_time"))
                    row.append(f"{busy:.2f}s" if busy is not None else "N/A")

                f.write("| " + " | ".join(row) + " |\n")

            f.write("\n")
            f.write("**Note**: Utilization measures logical qubit allocation over capacity * makespan.\n\n")
        else:
            f.write("No machine utilization data available.\n\n")

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

                for batch in batches[:20]:
                    batch_id = batch.get("batch_id", "?")
                    machine = batch.get("machine_name", "?")
                    jobs = batch.get("job_ids", [])
                    job_count = len(jobs) if isinstance(jobs, list) else "?"
                    shots = batch.get("shots", "?")
                    start = safe_float(batch.get("start_time"))
                    end = safe_float(batch.get("end_time"))
                    duration = (
                        f"{end - start:.2f}s"
                        if start is not None and end is not None
                        else "N/A"
                    )
                    status = batch.get("status", "?")
                    start_display = f"{start:.2f}s" if start is not None else "N/A"
                    end_display = f"{end:.2f}s" if end is not None else "N/A"

                    f.write(
                        f"| {batch_id} | {machine} | {job_count} | {shots} | {start_display} | {end_display} | {duration} | {status} |\n"
                    )

                if len(batches) > 20:
                    f.write(f"\n*Showing first 20 of {len(batches)} batches*\n")
                f.write("\n")
            else:
                f.write("No batch data available.\n\n")

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


def run_comparison(csv_path: Path | str) -> Path:
    """Run batch results comparison, generating markdown report and charts."""
    csv_file = Path(csv_path).expanduser()
    if not csv_file.is_absolute() and not csv_file.exists():
        csv_file = PROJECT_ROOT / csv_file
    csv_file = csv_file.resolve()

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    csv_stem = csv_file.stem
    analysis_dir = csv_file.parent / f"analysis_{csv_stem}"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading results from: {csv_file}")
    results = load_batch_results(csv_file)
    print(f"  Loaded {len(results)} result rows")

    _is_compatible, warnings = check_compatibility(results)
    if warnings:
        print("\nCompatibility warnings:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")

    report_path = analysis_dir / "comparison_report.md"
    print(f"\nGenerating report: {report_path}")
    generate_markdown_report(results, report_path, warnings)

    print("Generating charts...")
    chart_paths = generate_charts(results, analysis_dir)
    for chart_path in chart_paths:
        print(f"  Created: {chart_path}")

    print(f"\n✅ Analysis complete. Results in: {analysis_dir}")
    return analysis_dir
