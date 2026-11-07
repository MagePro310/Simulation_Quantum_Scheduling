#!/usr/bin/env python3
"""CLI for comparing quantum scheduling batch simulation results.

Reads a timestamped CSV from run_batch.py and generates a comprehensive
Markdown report with PNG comparison charts.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.analysis.report_generator import run_comparison


def main() -> int:
    """Main CLI entry point for result comparison."""
    parser = argparse.ArgumentParser(
        description="Compare quantum scheduling batch results and generate reports/charts"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to batch results CSV file",
    )
    args = parser.parse_args()

    try:
        run_comparison(args.csv_file)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
