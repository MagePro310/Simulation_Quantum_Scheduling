from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from component.ibm_simulator.sim_machine5qubits import FakeManilaV2
from qiskit.visualization import plot_histogram

# Construct quantum circuit
circ = QuantumCircuit(3, 3)
circ.h(0)
circ.cx(0, 1)
circ.cx(1, 2)
circ.measure([0, 1, 2], [0, 1, 2])

sim_ideal = AerSimulator()

# Execute and get counts
result = sim_ideal.run(transpile(circ, sim_ideal)).result()
counts = result.get_counts(0)
plot_histogram(counts, title='Ideal counts for 3-qubit GHZ state')