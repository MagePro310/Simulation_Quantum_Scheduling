#!/usr/bin/env python3
"""CLI entry point for running a single quantum scheduling algorithm simulation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.algorithm.registry import list_algorithms
from source.flow.runner import run_pipeline


def main() -> int:
    """Run a single quantum scheduling algorithm simulation."""
    available_algos = list_algorithms()
    parser = argparse.ArgumentParser(
        description="Run a single quantum scheduling algorithm simulation"
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all registered scheduling algorithms and exit",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        type=str,
        default="FFD",
        help=f"Algorithm to run. Available: {', '.join(available_algos)} (default: FFD)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to YAML/JSON simulation config file (default: configs/default_batch.yaml)",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path to write structured JSON results",
    )
    parser.add_argument(
        "--gantt-output",
        type=Path,
        default=None,
        help="Optional custom path to export Gantt chart image",
    )
    args = parser.parse_args()

    if args.list:
        print("Registered scheduling algorithms:")
        for name in available_algos:
            print(f"  - {name}")
        return 0

    try:
        run_pipeline(
            algorithm=args.algorithm,
            config=args.config,
            json_output=args.json_output,
            gantt_output_path=args.gantt_output,
        )
        return 0
    except Exception as e:
        print(f"\nExecution error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
