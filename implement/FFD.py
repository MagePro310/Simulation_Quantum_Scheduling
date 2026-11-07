"""Run First Fit Decreasing (FFD) quantum scheduling algorithm.

Places larger jobs first into open machine bins based on qubit footprint.
"""

from pathlib import Path
import sys
from typing import Any

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.algorithm.heuristic.FFD import FFD
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    config: Any = None,
    json_output: Path | None = None,
):
    """Run the FFD scheduling algorithm driven strictly by config."""
    return run_pipeline(
        algorithm=FFD(),
        config=config,
        json_output=json_output,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(FFD, description="Run FFD quantum scheduling algorithm")
