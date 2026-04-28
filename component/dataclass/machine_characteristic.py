from dataclasses import dataclass, field
from typing import Dict, Any
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')
from component.ibm_simulator import sim_backend

@dataclass
class MachineCharacteristic:
    """
    Dataclass to represent the characteristics of a quantum machine.
    """
    name: str
    quantum_machine: Any
    topology: Dict[int, bool] = field(default_factory=dict)
    
    def __post_init__(self):
        """Automatically initialize topology after instance creation."""
        self.initialize_topology()
    
    def initialize_topology(self):
        """Initialize topology with all qubits as not active (False)."""
        for qubit in range(self.quantum_machine.num_qubits):
            self.topology[qubit] = False
            
    

# Example usage
if __name__ == "__main__":
    # Create simulated machine instance
    quantum_machine = sim_backend.sim_machine5qubits.FakeBelemV2()
    
    # Create MachineCharacteristic instance
    machine_char = MachineCharacteristic(
        name=quantum_machine.name,
        quantum_machine=quantum_machine
    )
    
    print(f"Machine Name: {machine_char.name}")
    print(f"Number of Qubits: {machine_char.quantum_machine.num_qubits}")
    print(f"Topology: {machine_char.topology}")