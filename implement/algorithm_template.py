"""Template for creating a new algorithm script.

Copy this file and modify it to add your own scheduling algorithm.

Steps:
1. Copy this file to a new name in implement/ (e.g., implement/MyAlgorithm.py)
2. Change the algorithm import in run_algorithm
3. Update the algorithm name in the ArgumentParser description
4. Add your algorithm to batch_config.py
5. Run: python run_batch.py
"""

import sys
import json
import argparse
from pathlib import Path

# Support running this script directly from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.component.help_function.result_serialization import serialize_result
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.flow.input.phase_input import ConcreteInputPhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase
from source.flow.execution.orchestrator import ConcreteExecutionPhase


def run_algorithm(json_output: Path | None = None):
    """Run the scheduling algorithm and optionally save results to JSON."""

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()

    # Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # TODO: Import and use your algorithm here
    # Example: from source.algorithm.heuristic.YourAlgorithm import YourAlgorithm
    # For now, using FFD as a placeholder:
    from source.algorithm.heuristic.FFD import FFD
    algorithm = FFD()  # Replace with your algorithm

    # Schedule Phase
    schedule_result = ConcreteSchedulePhase(algorithm=algorithm).execute(
        input_job, machines_set, capture_result_schedule
    )

    # Execution Phase
    results = ConcreteExecutionPhase().execute(
        machines_set, schedule_result, capture_result_schedule=capture_result_schedule
    )

    # Write JSON output if requested
    if json_output:
        result_data = serialize_result(capture_result_schedule)
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
        print(f"\nJSON output written to: {json_output}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run [YOUR ALGORITHM NAME] quantum scheduling algorithm")
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Path to write structured JSON results for batch processing"
    )
    args = parser.parse_args()

    run_algorithm(json_output=args.json_output)
