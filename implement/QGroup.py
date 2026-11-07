"""Run QGroup quantum scheduling algorithm.

Groups quantum circuits based on compatibility and resource requirements.
"""

from pathlib import Path
import sys
from typing import Any

# Support running this script directly from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.algorithm.heuristic.QGroup import QGroup
from source.flow.runner import run_cli, run_pipeline


def run_algorithm(
    config: Any = None,
    json_output: Path | None = None,
):
    """Run the QGroup scheduling algorithm driven strictly by config."""
    return run_pipeline(
        algorithm=QGroup(),
        config=config,
        json_output=json_output,
    )


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    run_cli(QGroup, description="Run QGroup quantum scheduling algorithm")
