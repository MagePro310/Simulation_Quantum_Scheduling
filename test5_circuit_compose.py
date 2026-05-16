from qiskit import QuantumCircuit

circuit1 = QuantumCircuit(5)
circuit1.h(0)
circuit1.cx(0, 1)
circuit1.cx(0, 2)
circuit1.cx(0, 3)
circuit1.cx(0, 4)


circuit2 = QuantumCircuit(3)
circuit2.x(0)
circuit2.y(1)
circuit2.z(2)


# circuit3 = circuit1 compose circuit2
circuit3 = circuit1.tensor(circuit2)
print(circuit3)