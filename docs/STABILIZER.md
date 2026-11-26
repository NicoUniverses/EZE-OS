# Stabilizer simulator

`ezeos.stabilizer` simulates Clifford circuits (H, S, CX, CZ, SWAP, iSWAP, ECR and any
parameterised gate at a Clifford angle) in polynomial time with the tableau method of
S. Aaronson and D. Gottesman, *Improved simulation of stabilizer circuits*,
Phys. Rev. A 70, 052328 (2004), [arXiv:quant-ph/0406196](https://arxiv.org/abs/quant-ph/0406196).

```python
from ezeos import algorithms as A
from ezeos.stabilizer import StabilizerSimulator, is_clifford

ghz = A.ghz(1000)
assert is_clifford(ghz)
print(StabilizerSimulator(seed=1).run(ghz, shots=8).counts)   # only 000...0 and 111...1
```

```bash
ezeos stabilizer ghz:3 --stabilizers      # +XXX  +IZZ  +ZZI
ezeos run ghz:5 --backend stabilizer      # through the kernel, after transpilation
```

## How gate rules are obtained

No conjugation table is typed in by hand. For a gate `U` on `k` qubits the module computes
`U X_j U†` and `U Z_j U†` from the exact matrix in `ezeos.gates` and decomposes each image in
the Pauli basis. If every image is a single signed Pauli string the gate is Clifford and the
images become its rule; otherwise `NotCliffordError` is raised. Rules are cached per gate and
parameters.

## Representation

A tableau row is `i^r · X^x · Z^z` with `x` and `z` as integer bit masks (bit `q` = qubit `q`,
the same little-endian order as the state-vector simulator). Rows `0..n-1` are destabilizers and
rows `n..2n-1` stabilizers. Products use `X^a Z^b · X^c Z^d = (-1)^{|b∧c|} X^{a⊕c} Z^{b⊕d}`.

## Limits

- Only Clifford gates; T, CCX, arbitrary rotations need `ezeos.Simulator`.
- Each gate costs O(n) row updates and each random measurement O(n) row products, in pure Python.
- `to_statevector()` is for checking small states (up to 16 qubits).
