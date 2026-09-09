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


def test_concrete_flow(json_output: Path | None = None):

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()
    # Create input circuit, and quantum machine (notchanged))
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # Schedule Phase (change algorithm here)
    from source.algorithm.heuristic.LPT import LPT
    schedule_result = ConcreteSchedulePhase(algorithm=LPT()).execute(input_job, machines_set, capture_result_schedule)
    results = ConcreteExecutionPhase().execute(machines_set, schedule_result, capture_result_schedule=capture_result_schedule)

    # Write JSON output if requested
    if json_output:
        result_data = serialize_result(capture_result_schedule)
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
        print(f"\nJSON output written to: {json_output}")

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LPT quantum scheduling algorithm")
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Path to write structured JSON results for batch processing"
    )
    args = parser.parse_args()

    test_concrete_flow(json_output=args.json_output)
