"""Chart and visualization generation for quantum scheduling comparative analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from source.analysis.metrics import (
    COMPARISON_METRICS,
    format_value_for_display,
    safe_float,
    safe_int,
)


def parse_nested_json(value: str) -> Any:
    """Parse JSON string field, returning empty dict/list if invalid."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


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
    """Generate comprehensive comparison charts as PNG files."""
    chart_paths = []

    results_by_algo = {}
    for result in results:
        algo = result.get("algorithm", "")
        if result.get("process_status") == "SUCCESS":
            results_by_algo[algo] = result

    if len(results_by_algo) < 2:
        return chart_paths

    algorithm_names = list(results_by_algo.keys())
    num_algos = len(algorithm_names)
    colors = [plt.cm.tab10(i % 10) for i in range(num_algos)]

    # 1. Individual Metric Charts
    for metric_info in COMPARISON_METRICS:
        single_chart_path = generate_individual_metric_chart(
            metric_info=metric_info,
            results_by_algo=results_by_algo,
            algorithm_names=algorithm_names,
            colors=colors,
            output_dir=output_dir,
        )
        chart_paths.append(single_chart_path)

    # 2. All Metrics Comparison Grid
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

    for j in range(num_metrics, len(axes_flat)):
        fig.delaxes(axes_flat[j])

    plt.tight_layout()
    chart_path = output_dir / "metrics_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    chart_paths.append(chart_path)

    # 3. Job Outcomes Comparison
    if num_algos <= 4:
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
        ax.bar(
            x,
            blocked_data,
            width,
            bottom=np.array(succeeded_data) + np.array(failed_data),
            label="Blocked",
            color="#95a5a6",
        )

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

    # 4. Machine Utilization
    all_machines_data = {}
    for algo in algorithm_names:
        result = results_by_algo[algo]
        machines_json = parse_nested_json(result.get("machines_json", ""))
        all_machines_data[algo] = machines_json

    if all_machines_data and any(all_machines_data.values()):
        all_machine_names = sorted(
            set(name for machines in all_machines_data.values() for name in machines.keys())
        )

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
