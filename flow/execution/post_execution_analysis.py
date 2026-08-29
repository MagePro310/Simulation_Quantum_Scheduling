from platform import machine
import sys
sys.path.append('./')
from types import SimpleNamespace
from typing import Any, Dict, List

from component.dataclass.job_info import ExecutionResult, MachineExecutionResult
from component.visualize.gantt_chart import GanttChart
from qiskit.quantum_info.analysis import hellinger_fidelity
from qiskit.result import marginal_counts

from flow.execution.main_execution_quantum import MainExecutionResult


class PostExecution:
    @staticmethod
    def _job_result_width(job_info: Any) -> int | None:
        """Return the number of classical result bits owned by a job."""
        circuit = getattr(job_info, "circuit", None)
        if circuit is None:
            return None

        num_clbits = int(getattr(circuit, "num_clbits", 0) or 0)
        if num_clbits:
            return num_clbits

        # This fallback supports circuit-like test doubles that only expose
        # their qubit count. Executed Qiskit circuits normally have clbits.
        num_qubits = int(getattr(circuit, "num_qubits", 0) or 0)
        return num_qubits or None

    def _job_distributions(
        self,
        merged_result: "MainExecutionResult",
    ) -> list[tuple[Any, dict[str, int] | None, dict[str, int] | None]]:
        """Marginalize a merged count distribution back to each input job."""
        jobs = list(merged_result.job_info or [])
        widths = [self._job_result_width(job_info) for job_info in jobs]

        # Keep compatibility for incomplete result objects where the original
        # circuit layout is unavailable and therefore cannot be marginalized.
        if any(width is None for width in widths):
            return [
                (
                    job_info,
                    merged_result.distribution_no_noise,
                    merged_result.distribution_with_noise,
                )
                for job_info in jobs
            ]

        job_distributions = []
        bit_offset = 0
        for job_info, width in zip(jobs, widths):
            bit_indices = list(range(bit_offset, bit_offset + width))
            distribution_no_noise = (
                dict(marginal_counts(merged_result.distribution_no_noise, bit_indices))
                if merged_result.distribution_no_noise is not None
                else None
            )
            distribution_with_noise = (
                dict(marginal_counts(merged_result.distribution_with_noise, bit_indices))
                if merged_result.distribution_with_noise is not None
                else None
            )
            job_distributions.append(
                (job_info, distribution_no_noise, distribution_with_noise)
            )
            bit_offset += width

        return job_distributions

    def update_job_info_with_results(
        self,
        scheduler_job_simulation: Dict[str, List["MainExecutionResult"]],
    ) -> dict[str, ExecutionResult]:
        """Update the job info with execution results."""
        updated_job_info: dict[str, ExecutionResult] = {}
        for machine_name, execution_results in scheduler_job_simulation.items():
            current_machine_time = 0.0
            for merged_result in execution_results:
                execution_time = float(merged_result.execution_time or 0.0)
                start_time = current_machine_time
                end_time = start_time + execution_time
                current_machine_time = end_time

                for (
                    job_info,
                    distribution_no_noise,
                    distribution_with_noise,
                ) in self._job_distributions(merged_result):
                    fidelity = None
                    if (
                        distribution_no_noise is not None
                        and distribution_with_noise is not None
                    ):
                        fidelity = hellinger_fidelity(
                            distribution_no_noise,
                            distribution_with_noise,
                        )

                    execution_result = ExecutionResult(
                        job_info=job_info,
                        assigned_machine=machine_name,
                        distribution_no_noise=distribution_no_noise,
                        distribution_with_noise=distribution_with_noise,
                        fidelity=fidelity,
                        start_time=start_time,
                        end_time=end_time,
                        execution_time=execution_time,
                    )
                    updated_job_info[job_info.job_name] = execution_result
        return updated_job_info

    def _draw_gantt_chart(
        self,
        execution_results: dict[str, ExecutionResult],
        machines: Dict[str, Any] | None = None,
        output_path: str = "execution_gantt_chart.png",
    ) -> None:
        """Draw a Gantt chart for final execution results."""
        if machines is None:
            machine_names = {
                result.assigned_machine
                for result in execution_results.values()
                if result.assigned_machine is not None
            }
            machines = {
                machine_name: SimpleNamespace(name=machine_name)
                for machine_name in sorted(machine_names)
            }

        gantt_input = {
            job_name: SimpleNamespace(
                assigned_machine=result.assigned_machine,
                scheduled_start_time=result.start_time,
                scheduled_end_time=result.end_time,
                num_qubits=getattr(getattr(result.job_info, "circuit", None), "num_qubits", None),
                shots=getattr(result.job_info, "shots", None),
            )
            for job_name, result in execution_results.items()
        }

        chart = GanttChart(
            title="Quantum Execution (Transpiled)",
            x_axis_label="Time",
            y_axis_label="Machines",
        )
        chart.display(gantt_input, machines, output_path=output_path)

    def update_machine_info_with_results(
        self,
        machines: Dict[str, Any],
        scheduler_job_simulation: Dict[str, List["MainExecutionResult"]],
    ) -> dict[str, MachineExecutionResult]:
        """Calculate qubit-time utilization for every machine.

        Utilization is the fraction of a machine's qubit-time capacity that
        was actually consumed by scheduled jobs:

            utilization = sum(group_qubits * group.execution_time)
                          / (machine.num_qubits * sum(group.execution_time))

        Iterating over ``machines`` (not ``scheduler_job_simulation``) ensures
        idle machines with no scheduled work still appear in the result with
        utilization 0.0, and machines with zero total execution time avoid a
        ZeroDivisionError (also reported as 0.0).
        """
        machine_utilization: dict[str, MachineExecutionResult] = {}
        for machine_name, machine in machines.items():
            num_qubits = int(getattr(machine, "num_qubits", 0) or 0)
            if num_qubits <= 0:
                raise ValueError(
                    f"Machine '{machine_name}' must have a positive num_qubits "
                    "value to compute utilization."
                )

            execution_results = scheduler_job_simulation.get(machine_name, [])
            total_execution_time = 0.0
            total_qubit_time = 0.0
            for group in execution_results:
                execution_time = float(group.execution_time or 0.0)
                group_qubits = 0
                for job in group.job_info:
                    circuit = getattr(job, "circuit", None)
                    job_num_qubits = getattr(circuit, "num_qubits", None)
                    if job_num_qubits is None:
                        raise ValueError(
                            f"Job '{getattr(job, 'job_name', job)}' on machine "
                            f"'{machine_name}' is missing circuit.num_qubits "
                            "information."
                        )
                    group_qubits += int(job_num_qubits)
                total_qubit_time += group_qubits * execution_time
                total_execution_time += execution_time

            denominator = num_qubits * total_execution_time
            utilization = (total_qubit_time / denominator) if denominator else 0.0

            machine_utilization[machine_name] = MachineExecutionResult(
                machine_name=machine_name,
                utilization=utilization,
            )

        return machine_utilization

    def execute(
        self,
        machines: Dict[str, Any],
        scheduler_job_simulation: Dict[str, List["MainExecutionResult"]],
    ) -> dict[str, ExecutionResult]:
        print("PostExecution: Analyzing execution results")
        result = self.update_job_info_with_results(scheduler_job_simulation)
        machine_ultilization = self.update_machine_info_with_results(machines, scheduler_job_simulation)
        print(result)
        self._draw_gantt_chart(result, machines, output_path="execution_gantt_chart.png")

        return result
