"""Run Longest Processing Time (LPT) quantum scheduling algorithm.

Prioritizes longer quantum circuits first to minimize overall makespan.
"""

from pathlib import Path
import sys
from typing import Any

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.algorithm.heuristic.LPT import LPT
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    config: Any = None,
    json_output: Path | None = None,
):
    """Run the LPT scheduling algorithm driven strictly by config."""
    return run_pipeline(
        algorithm=LPT(),
        config=config,
        json_output=json_output,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(LPT, description="Run LPT quantum scheduling algorithm")
