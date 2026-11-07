"""Comparative analysis, metric calculation, and reporting modules."""

from source.analysis.chart_generator import generate_charts
from source.analysis.metrics import (
    COMPARISON_METRICS,
    calculate_difference,
    calculate_percentage_difference,
    format_value_for_display,
    safe_float,
    safe_int,
)
from source.analysis.report_generator import (
    check_compatibility,
    generate_markdown_report,
    load_batch_results,
    run_comparison,
)

__all__ = [
    "COMPARISON_METRICS",
    "safe_float",
    "safe_int",
    "format_value_for_display",
    "calculate_difference",
    "calculate_percentage_difference",
    "load_batch_results",
    "check_compatibility",
    "generate_markdown_report",
    "generate_charts",
    "run_comparison",
]
