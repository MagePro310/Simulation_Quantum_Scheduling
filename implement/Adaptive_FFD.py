"""Run Adaptive First Fit Decreasing (Adaptive_FFD) quantum scheduling algorithm.

Dynamically adapts packing strategy based on machine load and circuit characteristics.
"""

from pathlib import Path
import sys
from typing import Any

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.algorithm.heuristic.Adaptive_FFD import Adaptive_FFD
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    config: Any = None,
    json_output: Path | None = None,
):
    """Run the Adaptive_FFD scheduling algorithm driven strictly by config."""
    return run_pipeline(
        algorithm=Adaptive_FFD(),
        config=config,
        json_output=json_output,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(Adaptive_FFD, description="Run Adaptive_FFD quantum scheduling algorithm")
