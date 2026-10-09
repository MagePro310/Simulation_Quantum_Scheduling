"""Circuit preparation: compose quantum circuits for multi-programming and circuit cutting.

Provides two distinct circuit composition strategies:
1. Standard Multi-programming (prepare_batch):
   Composes independent, uncut circuits onto disjoint qubit/clbit registers on a single QPU.
2. True Joint Execution (compose_joint_cutting_batch):
   Composes cut subcircuits (with QPD subexperiments and observable classical registers)
   alongside uncut circuits, aligning multi-variant runs onto unified quantum registers.
"""

from typing import Any
from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.compiler import transpile

from source.component.dataclass.execution_info import PreparedBatch
from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


class CircuitPreparation:
    """Compose individual circuits and transpile for quantum backend."""

    # =========================================================================
    # Strategy 1: Standard Multi-Programming (Uncut Circuits)
    # =========================================================================

    def prepare_batch(
        self,
        machine: MachineCharacteristic,
        jobs: dict[str, JobInfo],
        *,
        seed: int,
    ) -> PreparedBatch:
        """Compose independent circuits onto disjoint qubit ranges and transpile for backend.

        Args:
            machine: Quantum machine specification with target backend.
            jobs: Dictionary of uncut JobInfo objects to pack together.
            seed: Random seed for transpiler reproducibility.

        Returns:
            PreparedBatch container with merged circuit, transpiled circuit, and bit mappings.
        """
        total_qubits = sum(job.circuit.num_qubits for job in jobs.values())
        total_clbits = sum(job.circuit.num_clbits for job in jobs.values())
        merged_circuit, classical_bits = self._compose_circuits(jobs, total_qubits, total_clbits)

        # Transpile composite circuit for target backend
        transpiled_circuit = transpile(
            merged_circuit,
            backend=machine.quantum_machine,
            scheduling_method="alap",
            optimization_level=1,
            seed_transpiler=seed,
        )
        duration_per_shot = float(
            transpiled_circuit.estimate_duration(machine.quantum_machine.target, unit="s")
        )

        return PreparedBatch(
            job_ids=tuple(jobs),
            merged_circuit=merged_circuit,
            transpiled_circuit=transpiled_circuit,
            classical_bits=classical_bits,
            logical_qubits=total_qubits,
            duration_per_shot=duration_per_shot,
        )

    @staticmethod
    def _compose_circuits(
        jobs: dict[str, JobInfo],
        total_qubits: int,
        total_clbits: int,
    ) -> tuple[QuantumCircuit, dict[str, tuple[int, ...]]]:
        """Place jobs onto disjoint qubit and classical bit ranges."""
        merged_circuit = QuantumCircuit(
            QuantumRegister(total_qubits, "q"),
            ClassicalRegister(total_clbits, "meas"),
        )
        classical_bits = {}
        qubit_offset = clbit_offset = 0

        for job_id, job in jobs.items():
            bit_indices = tuple(range(clbit_offset, clbit_offset + job.circuit.num_clbits))
            merged_circuit.compose(
                job.circuit,
                qubits=range(qubit_offset, qubit_offset + job.circuit.num_qubits),
                clbits=bit_indices,
                inplace=True,
            )
            classical_bits[job_id] = bit_indices
            qubit_offset += job.circuit.num_qubits
            clbit_offset += job.circuit.num_clbits

        return merged_circuit, classical_bits

    # =========================================================================
    # Strategy 2: True Joint Execution (Subcircuits + Uncut Circuits)
    # =========================================================================

    @staticmethod
    def compose_joint_cutting_batch(
        jobs: dict[str, JobInfo],
    ) -> tuple[list[QuantumCircuit], dict[str, dict[str, Any]]]:
        """Compose cut subcircuits and uncut circuits into a list of joint quantum circuits.

        Handles heterogeneous batches where some jobs are cut subexperiments (with QPD & obs registers)
        and other jobs are regular uncut circuits (meas registers).

        Args:
            jobs: Dictionary of jobs to run in this batch.

        Returns:
            Tuple of:
            - joint_circuits: List of composed QuantumCircuit objects ready for transpilation.
            - reg_meta: Mapping from job_name to register metadata for result demultiplexing:
                - for subcircuit: {'type': 'subcircuit', 'obs': obs_reg_name, 'qpd': qpd_reg_name, 'len': n_subexpts}
                - for uncut: {'type': 'uncut', 'meas': meas_reg_name}
        """
        # Separate subexperiments from regular uncut circuits
        sub_jobs = {k: v for k, v in jobs.items() if getattr(v, "subexperiments", None) is not None}
        uncut_jobs = {k: v for k, v in jobs.items() if getattr(v, "subexperiments", None) is None}

        # Subexperiments may have varying counts; align them across the maximum length
        max_sub_len = max((len(v.subexperiments) for v in sub_jobs.values()), default=1)

        joint_circuits = []
        reg_meta = {}

        for i in range(max_sub_len):
            joint_qc = QuantumCircuit()
            q_offset = 0

            # 1. Compose subcircuits for variant index i
            for name, job in sub_jobs.items():
                sub_qc = job.subexperiments[i % len(job.subexperiments)]
                qr = QuantumRegister(sub_qc.num_qubits, f"q_{name}")
                joint_qc.add_register(qr)

                # Identify observable and QPD measurement registers
                obs_cr = next((cr for cr in sub_qc.cregs if "obs" in cr.name), sub_qc.cregs[0])
                qpd_cr = next((cr for cr in sub_qc.cregs if "qpd" in cr.name), sub_qc.cregs[1] if len(sub_qc.cregs) > 1 else None)

                joint_obs = ClassicalRegister(obs_cr.size, f"obs_{name}")
                joint_qc.add_register(joint_obs)
                clbits_to_map = list(joint_obs)

                if qpd_cr:
                    joint_qpd = ClassicalRegister(qpd_cr.size, f"qpd_{name}")
                    joint_qc.add_register(joint_qpd)
                    clbits_to_map += list(joint_qpd)
                    reg_meta[name] = {
                        "type": "subcircuit",
                        "obs": f"obs_{name}",
                        "qpd": f"qpd_{name}",
                        "len": len(job.subexperiments),
                    }
                else:
                    reg_meta[name] = {
                        "type": "subcircuit",
                        "obs": f"obs_{name}",
                        "qpd": None,
                        "len": len(job.subexperiments),
                    }

                qubits_to_map = list(range(q_offset, q_offset + sub_qc.num_qubits))
                joint_qc.compose(sub_qc, qubits=qubits_to_map, clbits=clbits_to_map, inplace=True)
                q_offset += sub_qc.num_qubits

            # 2. Compose uncut circuits (repeated alongside each subexperiment variant)
            for name, job in uncut_jobs.items():
                uncut_qc = job.circuit
                qr = QuantumRegister(uncut_qc.num_qubits, f"q_{name}")
                joint_qc.add_register(qr)

                num_clbits = uncut_qc.num_clbits if uncut_qc.num_clbits > 0 else uncut_qc.num_qubits
                meas_cr = ClassicalRegister(num_clbits, f"meas_{name}")
                joint_qc.add_register(meas_cr)
                reg_meta[name] = {"type": "uncut", "meas": f"meas_{name}"}

                qubits_to_map = list(range(q_offset, q_offset + uncut_qc.num_qubits))
                if uncut_qc.num_clbits > 0:
                    joint_qc.compose(uncut_qc, qubits=qubits_to_map, clbits=list(meas_cr), inplace=True)
                else:
                    joint_qc.compose(uncut_qc, qubits=qubits_to_map, inplace=True)
                    joint_qc.measure(qubits_to_map, list(meas_cr))
                q_offset += uncut_qc.num_qubits

            joint_circuits.append(joint_qc)

        return joint_circuits, reg_meta
