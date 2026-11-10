"""Batch executor: execute quantum batches using True Joint Execution or standard multi-programming.

Features:
- Extensible layout strategy hook (defaults to Qiskit's native SabreLayout/VF2Layout).
- Clean separation between subcircuit PubResult extraction and uncut circuit baseline fidelity calculation.
- Clean presentation delegation via TimelineReporter.
"""

from typing import Any
from qiskit.primitives.containers import DataBin, PrimitiveResult, PubResult
from qiskit_aer.primitives import SamplerV2 as AerSamplerV2

from source.models.execution import (
    BatchCounts,
    BatchExecutionRecord,
    PreparedBatch,
)
from source.models.job import ExecutionResult, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.flow.execution.circuit_composer import CircuitPreparation, build_pass_manager
from source.flow.execution.crosstalk import apply_crosstalk, noisy_simulator
from source.flow.execution.interfaces import DefaultLayoutStrategy, LayoutStrategy
from source.flow.execution.quantum_simulator import QuantumExecutor
from source.utils.seeding import derive_seed
from source.utils.timing import shots_duration
from source.utils.ideal_distribution import ideal_counts


class BatchExecutor:
    """Execute quantum batches on backends with True Joint Execution and count demultiplexing."""

    def __init__(
        self,
        circuit_composer: CircuitPreparation | None = None,
        quantum_runner: QuantumExecutor | None = None,
        layout_strategy: LayoutStrategy | None = None,
        reporter: Any | None = None,
    ):
        self.circuit_composer = circuit_composer or CircuitPreparation()
        self.quantum_runner = quantum_runner or QuantumExecutor()
        self.layout_strategy = layout_strategy or DefaultLayoutStrategy()
        self.reporter = reporter

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

        # Apply backend shot limit
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

    # =========================================================================
    # Branch A: True Joint Execution (with Subcircuits)
    # =========================================================================

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

        if self.reporter:
            self.reporter.print_dispatch(machine.name, batch_record.job_ids, batch_record.shots, is_cut=True)
        else:
            print(f"│ Dispatch : {machine.name:<15} → {', '.join(active_jobs)} ({batch_record.shots} shots, cut subcircuits)")

        try:
            jobs_dict = {name: scheduler_job[name].job_information for name in active_jobs}

            # Layout strategy hook: None means Qiskit Pass Manager runs native heuristic
            initial_layout = self.layout_strategy.get_initial_layout(machine.quantum_machine, jobs_dict)
            pass_manager = build_pass_manager(machine, seed=seed, initial_layout=initial_layout)
            batch_seed = derive_seed(seed, batch_id)
            # Aer's sampler, not qiskit-ibm-runtime's: the runtime one rejects the
            # crosstalk noise channels as non-ISA instructions
            sampler = AerSamplerV2.from_backend(noisy_simulator(machine.quantum_machine), seed=batch_seed)

            joint_circuits, reg_meta = self.circuit_composer.compose_joint_cutting_batch(jobs_dict)
            isa_composed = pass_manager.run(joint_circuits)

            # Joint circuits run one after another; each keeps only its own qubits busy
            durations = [
                shots_duration(
                    c.estimate_duration(machine.quantum_machine.target, unit="s"),
                    batch_record.shots,
                    machine.rep_delay,
                )
                for c in isa_composed
            ]
            total_duration = sum(durations)
            qubit_time = sum(qc.num_qubits * d for qc, d in zip(joint_circuits, durations))

            noisy_circuits = []
            for circuit in isa_composed:
                noisy, exposed, two_qubit = apply_crosstalk(
                    circuit, machine.quantum_machine, machine.crosstalk_factor
                )
                noisy_circuits.append(noisy)
                batch_record.crosstalk_exposed_gates += exposed
                batch_record.two_qubit_gates += two_qubit

            raw_res = sampler.run(noisy_circuits, shots=batch_record.shots).result()

            # Demultiplex results for each active job
            job_counts = {}
            for name in active_jobs:
                meta = reg_meta[name]
                info = scheduler_job[name].job_information

                if meta["type"] == "subcircuit":
                    job_counts[name] = self._extract_subcircuit_results(raw_res, meta, info)
                else:
                    job_counts[name] = self._extract_uncut_results(raw_res, meta, info, batch_record.shots, batch_seed)

            batch_record.end_time = now + max(total_duration, 0.0001)
            elapsed = batch_record.end_time - now
            # Keep qubit-time consistent with the minimum duration a batch is given
            batch_record.qubit_time = (
                qubit_time * elapsed / total_duration if total_duration > 0
                else batch_record.logical_qubits * elapsed
            )
            return batch_record, job_counts, None, None

        except Exception as e:
            return batch_record, None, f"Batch {batch_id} execution failed: {e}", None

    @staticmethod
    def _extract_subcircuit_results(raw_res, meta: dict[str, Any], info: Any) -> BatchCounts:
        """Extract measurement results and wrap DataBin / PubResult for cut subcircuits.

        The QPD result is returned in BatchCounts.sub_result rather than written to the
        cutting context: a subcircuit can run over several batches or several shot
        shards, and ReconstructionHandler merges those before reconstruction.
        """
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

        obs_meas = getattr(getattr(sub_res[0], "data", None), "observable_measurements", None)
        first_counts = dict(obs_meas.get_counts()) if obs_meas else {}

        return BatchCounts(
            distribution_no_noise=first_counts,
            distribution_with_noise=first_counts,
            sub_result=sub_res,
        )

    @staticmethod
    def _extract_uncut_results(raw_res, meta: dict[str, Any], info: Any, shots: int, seed: int) -> BatchCounts:
        """Extract noisy counts and attach the exact ideal reference for an uncut circuit.

        `seed` is the batch's own seed; it is used only if the ideal reference has to
        fall back to sampling (see utils/ideal_distribution.py).
        """
        meas_name = meta["meas"]
        raw_pub = raw_res[0]
        counts_with_noise = dict(getattr(raw_pub.data, meas_name).get_counts())

        return BatchCounts(
            distribution_no_noise=ideal_counts(info.circuit, shots, seed=seed),
            distribution_with_noise=counts_with_noise,
        )

    # =========================================================================
    # Branch B: Standard Multi-Programming Composite Batch
    # =========================================================================

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
            try:
                jobs_dict = {name: scheduler_job[name].job_information for name in active_jobs}
                prepared_batch = self.circuit_composer.prepare_batch(
                    machine,
                    jobs_dict,
                    seed=seed,
                    initial_layout=self.layout_strategy.get_initial_layout(machine.quantum_machine, jobs_dict),
                )
            except Exception as e:
                return batch_record, None, f"Batch {batch_id} preparation failed: {e}", None

        batch_record.end_time = now + shots_duration(
            prepared_batch.duration_per_shot, batch_record.shots, machine.rep_delay
        )

        for name in active_jobs:
            if results[name].start_time is None:
                results[name].start_time = now
            results[name].status = "RUNNING"

        if self.reporter:
            self.reporter.print_dispatch(machine.name, batch_record.job_ids, batch_record.shots, is_cut=False)
        else:
            print(f"│ Dispatch : {machine.name:<15} → {', '.join(active_jobs)} ({batch_record.shots} shots)")

        try:
            merged_counts = self.quantum_runner.execute_batch(
                machine,
                prepared_batch,
                batch_record.shots,
                seed=derive_seed(seed, batch_id),
            )
            batch_record.crosstalk_exposed_gates = merged_counts.crosstalk_exposed_gates
            batch_record.two_qubit_gates = merged_counts.two_qubit_gates
            job_counts = self.split_counts(prepared_batch, merged_counts)
            for name, counts in job_counts.items():
                counts.distribution_no_noise = ideal_counts(
                    scheduler_job[name].job_information.circuit,
                    batch_record.shots,
                    seed=derive_seed(seed, batch_id, name),
                )
            return batch_record, job_counts, None, prepared_batch
        except Exception as e:
            return batch_record, None, f"Batch {batch_id} execution failed: {e}", prepared_batch

    @staticmethod
    def split_counts(prepared_batch: PreparedBatch, merged_counts: BatchCounts) -> dict[str, BatchCounts]:
        """Split merged batch results into individual job counts.

        Each job's keys follow Qiskit's convention over its own classical bits (its
        clbit 0 rightmost), the same as the joint path and the exact ideal reference,
        so counts from batches on either path add up correctly.
        """
        job_counts = {}

        for job_id in prepared_batch.job_ids:
            bit_indices = tuple(reversed(prepared_batch.classical_bits[job_id]))
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
