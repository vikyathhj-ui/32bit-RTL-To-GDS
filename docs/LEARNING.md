# Learning notes

Concepts you must understand to own this project. Each one is explained simply, with pointers into
the code. Filled in phase by phase.

## Phase 0
- **Why the old ALU was wrong** (`docs/AUDIT.md`). The output mux used the opcode from the *current*
  cycle to pick a result computed in the *previous* cycle. **Rule:** every control signal must travel
  down the pipeline together with the data it controls.
- **Non-blocking assignment (`<=`) reads old values.** `zero <= (result == 0)` in the same clocked block
  as `result <= ...` sees last cycle's `result`. Compute flags from the same expression that feeds `y`.
- **Ripple carry vs. lookahead.** A loop `C[i] = G[i-1] | P[i-1] & C[i-1]` is a chain of 32 dependent
  stages, so its delay grows as O(n). Lookahead/prefix adders compute carries in parallel trees with
  O(log n) depth. Phase 2 implements both.

## Phase 1+
(to be added)
