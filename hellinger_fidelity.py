from qiskit.quantum_info import hellinger_fidelity

# Kết quả đếm (counts dict) từ 2 lần chạy hoặc mô phỏng khác nhau
counts_ideal = {'00': 500, '11': 500}
counts_noisy = {'00': 480, '11': 470, '01': 30, '10': 20}

# Tính Hellinger fidelity
h_fidelity = hellinger_fidelity(counts_ideal, counts_noisy)
print(f"Hellinger Fidelity: {h_fidelity}")
