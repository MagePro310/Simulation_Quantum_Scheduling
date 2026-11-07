"""Template for creating a new algorithm script.

Copy this file and modify it to add your own scheduling algorithm.

Steps to create a new algorithm:
1. Copy this file to a new name in implement/ (e.g., implement/MyAlgorithm.py)
2. Import and instantiate your algorithm class in run_algorithm()
3. Update the algorithm name in run_cli(description="...")
4. Add your algorithm to ALGORITHMS in run_batch.py (e.g. {"name": "MyAlgorithm", "module": "implement.MyAlgorithm"})
5. Run standalone: python implement/MyAlgorithm.py
   Run batch: python run_batch.py
"""

from pathlib import Path
import sys

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import your algorithm here:
# from source.algorithm.heuristic.MyAlgorithm import MyAlgorithm
from source.algorithm.heuristic.FFD import FFD  # Replace with your algorithm class
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    queue_policy: str = "strict",
    seed: int = 0,
    **kwargs,
):
    """Run the scheduling algorithm and optionally save results to JSON."""
    algorithm = FFD()  # Replace with your algorithm instance
    return run_pipeline(
        algorithm=algorithm,
        json_output=json_output,
        cutting_policy=cutting_policy,
        queue_policy=queue_policy,
        seed=seed,
        **kwargs,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(FFD, description="Run [YOUR ALGORITHM NAME] quantum scheduling algorithm")
