# Design decisions

Format for each entry: **context → options → choice → evidence**. Newest at the bottom.

---

## D-001 — Work in a separate clone, mounted into the tool container
- **Context:** all EDA tools run inside the Docker container `iic-osic`, which originally mounted only
  `~/vlsi`. `~/vlsi` is itself a git repo, so cloning this project inside it would nest one repo in another.
- **Options:**
  1. Clone under `~/vlsi` and ignore it there.
  2. Clone to `~/projects` and add a second container mount.
- **Choice:** option 2 (user's choice). `~/projects` → `/foss/projects`. The container was recreated with
  that mount; no data was lost because all designs live on the host.
- **Evidence:** `docker exec iic-osic bash -lc 'ls /foss/projects'` lists `32bit-RTL-To-GDS`.

## D-002 — LibreLane instead of OpenLane
- **Context:** the brief says "librelane (or openlane)". The image ships LibreLane 3.1.0.dev3 and no
  `openlane`.
- **Options:**
  1. Install OpenLane 2 separately.
  2. Use LibreLane.
- **Choice:** LibreLane. It is the maintained successor of OpenLane 2, has the same configuration model,
  and is already installed. No extra installs are needed.
- **Evidence:** `results/env_check.txt`.

## D-003 — yices as the SMT solver for SymbiYosys
- **Context:** the brief asks for a solver (`z3`/`boolector`/`yices`). Only `yices-smt2` 2.7.0 is
  installed.
- **Options:**
  1. Ask to install z3 or boolector.
  2. Use yices.
- **Choice:** yices. It is one of the listed acceptable solvers and is a strong default for `smtbmc`.
  Yosys's built-in `abc pdr` engine is also available as a second engine if a proof struggles.
- **Evidence:** `results/env_check.txt`.

## D-004 — cocotb-coverage installed in a repo-local venv
- **Context:** `cocotb-coverage` was the only missing tool. The brief prefers pip inside a venv and
  forbids sudo.
- **Options:**
  1. A system pip install.
  2. A venv with `--system-site-packages`.
- **Choice:** option 2, `.venv/` in the repo (git-ignored, created inside the container), user-approved.
  It pins `cocotb-coverage==2.0`, the first release that supports cocotb 2.x (it requires `cocotb>=2.0`),
  and reuses the image's cocotb 2.0.1.
- **Evidence:** `results/env_check.txt` shows `cocotb 2.0.1` and `cocotb-coverage 2.0` from
  `.venv/bin/python`.

## D-005 — Audit claims are backed by a reproducible probe simulation
- **Context:** rule 1 forbids hand-typed results. The audit makes claims about the legacy design's
  behaviour.
- **Choice:** commit `legacy/tb_probe.v` and `scripts/legacy_probe.sh`. Every behavioural claim in
  `docs/AUDIT.md` quotes a line from `results/legacy_probe.txt`.
- **Evidence:** `scripts/legacy_probe.sh` reproduces the log.

---

## Bugs found by verification
(Phase 3 fills this in.)
