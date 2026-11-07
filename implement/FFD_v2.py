"""Run First Fit Decreasing Version 2 (FFD_v2) quantum scheduling algorithm.

Pre-sorts and cuts eligible circuits using Circuit Cutting Helper before bin packing.
"""

from pathlib import Path
import sys

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.algorithm.heuristic.FFD_v2 import FFD_v2
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    queue_policy: str = "strict",
    seed: int = 0,
    **kwargs,
):
    """Run the FFD_v2 scheduling algorithm and optionally save results to JSON."""
    return run_pipeline(
        algorithm=FFD_v2(),
        json_output=json_output,
        cutting_policy=cutting_policy,
        queue_policy=queue_policy,
        seed=seed,
        **kwargs,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(FFD_v2, description="Run FFD_v2 quantum scheduling algorithm")
