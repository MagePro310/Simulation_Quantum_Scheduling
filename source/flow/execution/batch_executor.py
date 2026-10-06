"""Batch executor: execute quantum batches using True Joint Execution or standard multi-programming."""

from qiskit.primitives.containers import DataBin, PrimitiveResult, PubResult
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import SamplerV2

from source.component.dataclass.execution_info import (
    BatchCounts,
    BatchExecutionRecord,
    PreparedBatch,
)
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.execution.circuit_composer import CircuitPreparation
from source.flow.execution.quantum_simulator import QuantumExecutor


class BatchExecutor:
    """Execute quantum batches on backends with True Joint Execution and count demultiplexing."""

    def __init__(
        self,
        circuit_composer: CircuitPreparation | None = None,
        quantum_runner: QuantumExecutor | None = None,
    ):
        self.circuit_composer = circuit_composer or CircuitPreparation()
        self.quantum_runner = quantum_runner or QuantumExecutor()

    def execute_batch(
        self,
        now: float,
        machine: MachineCharacteristic,
        active_jobs: list[str],
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        prepared_batch: PreparedBatch | None,
        seed: int,
        batch_id: int,
    ) -> tuple[BatchExecutionRecord, dict[str, BatchCounts] | None, str | None, PreparedBatch | None]:
        """Prepare and execute a batch on the target machine.

        Returns:
            Tuple of (batch_record, job_counts, error_message, prepared_batch_cache).
        """
        batch_record = BatchExecutionRecord(
            batch_id=batch_id,
            machine_name=machine.name,
            job_ids=tuple(active_jobs),
            shots=min(results[name].requested_shots - results[name].completed_shots for name in active_jobs),
            start_time=now,
            end_time=now,
            logical_qubits=sum(scheduler_job[name].job_information.circuit.num_qubits for name in active_jobs),
        )

        # Apply shot limit
        if max_shots := self.quantum_runner.max_shots(machine):
            batch_record.shots = min(batch_record.shots, max_shots)

        has_subexperiments = any(
            getattr(scheduler_job[name].job_information, "subexperiments", None) is not None
            for name in active_jobs
        )

        if has_subexperiments:
            return self._execute_joint_cutting_batch(
                now, machine, active_jobs, scheduler_job, results, batch_record, seed, batch_id
            )

        return self._execute_standard_batch(
            now, machine, active_jobs, scheduler_job, results, prepared_batch, batch_record, seed, batch_id
        )

    def _execute_joint_cutting_batch(
        self,
        now: float,
        machine: MachineCharacteristic,
        active_jobs: list[str],
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        batch_record: BatchExecutionRecord,
        seed: int,
        batch_id: int,
    ) -> tuple[BatchExecutionRecord, dict[str, BatchCounts] | None, str | None, PreparedBatch | None]:
        """Execute batch with True Joint Execution (subexperiments composed on backend topology)."""
        for name in active_jobs:
            if results[name].start_time is None:
                results[name].start_time = now
            results[name].status = "RUNNING"

        print(f"│ Dispatch : {machine.name:<15} → {', '.join(active_jobs)} ({batch_record.shots} shots, cut subcircuits)")

        try:
            pass_manager = generate_preset_pass_manager(
                optimization_level=1, backend=machine.quantum_machine, seed_transpiler=seed
            )
            sampler = SamplerV2(mode=machine.quantum_machine)

            jobs_dict = {name: scheduler_job[name].job_information for name in active_jobs}
            joint_circuits, reg_meta = self.circuit_composer.compose_joint_cutting_batch(jobs_dict)

            isa_composed = pass_manager.run(joint_circuits)
            total_duration = sum(
                float(c.estimate_duration(machine.quantum_machine.target, unit="s"))
                for c in isa_composed
            ) * batch_record.shots

            raw_res = sampler.run(isa_composed, shots=batch_record.shots).result()

            job_counts = {}
            for name in active_jobs:
                meta = reg_meta[name]
                info = scheduler_job[name].job_information

                if meta["type"] == "subcircuit":
                    sub_len = meta["len"]
                    pubs = []
                    for p in raw_res[:sub_len]:
                        obs_data = getattr(p.data, meta["obs"])
                        qpd_name = meta["qpd"]
                        if qpd_name and hasattr(p.data, qpd_name):
                            qpd_data = getattr(p.data, qpd_name)
                            db = DataBin(observable_measurements=obs_data, qpd_measurements=qpd_data)
                        else:
                            db = DataBin(observable_measurements=obs_data)
                        pubs.append(PubResult(db))

                    sub_res = PrimitiveResult(pubs)
                    if info.parentJob and getattr(info.parentJob, "cutting_context", None):
                        info.parentJob.cutting_context.sub_results[info.partition_label] = sub_res

                    obs_meas = getattr(getattr(sub_res[0], "data", None), "observable_measurements", None)
                    first_counts = dict(obs_meas.get_counts()) if obs_meas else {}

                    job_counts[name] = BatchCounts(
                        distribution_no_noise=first_counts,
                        distribution_with_noise=first_counts,
                    )
                else:
                    # Uncut circuit: extract noisy counts from joint topology execution
                    meas_name = meta["meas"]
                    raw_pub = raw_res[0]
                    counts_with_noise = dict(getattr(raw_pub.data, meas_name).get_counts())

                    # Ideal noiseless simulation for baseline fidelity
                    qc_ideal = info.circuit.copy()
                    if qc_ideal.num_clbits == 0:
                        qc_ideal.measure_all()
                    ideal_res = AerSimulator().run(qc_ideal, shots=batch_record.shots, seed_simulator=seed).result()
                    counts_no_noise = dict(ideal_res.get_counts())

                    job_counts[name] = BatchCounts(
                        distribution_no_noise=counts_no_noise,
                        distribution_with_noise=counts_with_noise,
                    )

            batch_record.end_time = now + max(total_duration, 0.0001)
            return batch_record, job_counts, None, None

        except Exception as e:
            return batch_record, None, f"Batch {batch_id} execution failed: {e}", None

    def _execute_standard_batch(
        self,
        now: float,
        machine: MachineCharacteristic,
        active_jobs: list[str],
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        prepared_batch: PreparedBatch | None,
        batch_record: BatchExecutionRecord,
        seed: int,
        batch_id: int,
    ) -> tuple[BatchExecutionRecord, dict[str, BatchCounts] | None, str | None, PreparedBatch | None]:
        """Execute standard multi-programming composite batch."""
        if prepared_batch is None or prepared_batch.job_ids != batch_record.job_ids:
            prepared_batch = self.circuit_composer.prepare_batch(
                machine,
                {name: scheduler_job[name].job_information for name in active_jobs},
                seed=seed,
            )

        batch_record.end_time = now + float(prepared_batch.duration_per_shot) * batch_record.shots

        for name in active_jobs:
            if results[name].start_time is None:
                results[name].start_time = now
            results[name].status = "RUNNING"

        print(f"│ Dispatch : {machine.name:<15} → {', '.join(active_jobs)} ({batch_record.shots} shots)")

        try:
            merged_counts = self.quantum_runner.execute_batch(
                machine,
                prepared_batch,
                batch_record.shots,
                seed=(seed + batch_id - 1) % 2**32,
            )
            job_counts = self.split_counts(prepared_batch, merged_counts)
            return batch_record, job_counts, None, prepared_batch
        except Exception as e:
            return batch_record, None, f"Batch {batch_id} execution failed: {e}", prepared_batch

    @staticmethod
    def split_counts(prepared_batch: PreparedBatch, merged_counts: BatchCounts) -> dict[str, BatchCounts]:
        """Split merged batch results into individual job counts."""
        job_counts = {}

        for job_id in prepared_batch.job_ids:
            bit_indices = prepared_batch.classical_bits[job_id]
            no_noise = {}
            with_noise = {}

            for bitstring, count in merged_counts.distribution_no_noise.items():
                job_bits = "".join(bitstring[-(i + 1)] for i in bit_indices)
                no_noise[job_bits] = no_noise.get(job_bits, 0) + count

            for bitstring, count in merged_counts.distribution_with_noise.items():
                job_bits = "".join(bitstring[-(i + 1)] for i in bit_indices)
                with_noise[job_bits] = with_noise.get(job_bits, 0) + count

            job_counts[job_id] = BatchCounts(
                distribution_no_noise=no_noise,
                distribution_with_noise=with_noise,
            )

        return job_counts

