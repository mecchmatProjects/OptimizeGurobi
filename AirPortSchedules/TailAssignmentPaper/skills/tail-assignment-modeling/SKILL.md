# Skill: Tail Assignment Modeling

## Description
Implement, debug, validate, and extend MILP models and heuristics for the
**Aircraft Tail Assignment Problem** (TAP). This skill covers:
- The compact multi-commodity flow MILP (Khaled et al. 2018)
- Full A/B/C/D maintenance-check hierarchy
- Greedy/insertion heuristic with ferry repositioning
- Data generation, batch experimentation, and LaTeX paper writing

Use this skill when asked to:
- Implement or modify a TAP MILP constraint
- Debug infeasibility in the aircraft scheduling model
- Generate test instances or run batch experiments
- Write mathematical derivations or paper sections about the TAP
- Validate results against the Khaled et al. (2018) paper

## Project Location
`f:\Lectures\Facultative\Optimizers\Tasks\AirPortSchedules\TailAssignmentPaper\`

## Key Files

| File | Role |
|------|------|
| `src/model.py` | Main MILP (`MILP_Sheduler`) + heuristic (`Scheduler`) |
| `src/generate_instances.py` | Deterministic instance generator |
| `src/diagnostics.py` | IIS finder + constraint-group deactivation |
| `src/convert_data.py` | DAT ↔ JSON converter |
| `experiments/reproduce_tables.py` | Reproduce Khaled et al. Tables 5,6,10,11 |
| `experiments/run_batch.py` | Parameterised batch runner |
| `docs/model_math.tex` | Full formal MILP derivation |
| `docs/heuristic_math.tex` | Heuristic formal analysis |
| `paper/main.tex` | LaTeX paper master file |
| `AGENTS.md` | Full project brief and conventions |

## Core MILP Variables

```python
m.x[i, j]         # Binary: flight i assigned to aircraft j
m.z[i, j, d, c]   # Binary: check c triggered after flight i for aircraft j on day d
m.y[j, d, c]      # Binary: aircraft j undergoes check c on day d
m.mega[j, d, c]   # Binary: aircraft j has check ≥ c on day d (hierarchy indicator)
```

## Model Build API

```python
from src.model import MILP_Sheduler

sch = MILP_Sheduler('data/instances/DataCplex_density=1_p=10_h=7_test_0.json')
model = sch.build_model(
    use_maintenance=True,      # Include maintenance constraints (8–15)
    use_day_spacing=True,      # C12: calendar-day spacing for C/D checks
    use_existing_hrs=True,     # C13b: pre-horizon accumulated hours
    use_check_hierarchy=True,  # Check hierarchy D→C→B→A resets
    use_ferry=True,            # Allow repositioning (ferry) flights
    use_overlap=True,          # Non-overlapping flight constraint
    use_paper_c13=False,       # False = use CORRECTED constraint (13) [recommended]
)
result = sch.solve(solver_name='cplex', time_limit=300, tee=False)
```

## Constraint (13) — The Key Correction

The original Khaled et al. (2018) constraint (13) has an error:

**Original** (incorrect — big-M too loose when neither endpoint has a check):
```
Σ_{i∈F_{d,d'}} x_{ij} t_i  ≤  T_max + M(2 - y_{jd} - y_{jd'}) + M·Σ y_{jr}
```

**Corrected** (two split constraints, each anchored at one endpoint):
```
Σ x_{ij} t_i  ≤  T_max + M·Σy_{jr} + M·y[j,d]    # anchored at start day d
Σ x_{ij} t_i  ≤  T_max + M·Σy_{jr} + M·y[j,d']   # anchored at end day d'
```

Implementation toggle: `use_paper_c13=False` uses the corrected version (default).

## Maintenance Check Types

| Check | Threshold | Reset type | Duration |
|-------|-----------|-----------|----------|
| A | Tmax flight-hours | Hours-based | ~6 h |
| B | Tmax flight-hours (larger) | Hours-based | ~2 days |
| C | dmax calendar days | Days-based | ~1 day |
| D | dmax calendar days (larger) | Days-based | ~2 days |

**Hierarchy**: Performing check X resets all lighter checks (D resets D,C,B,A;
C resets C,B,A; B resets B,A; A resets A only).

## Infeasibility Debugging

```python
# Quick constraint-group scan
python src/diagnostics.py --data data/instances/<file>.json --mode scan

# IIS via CPLEX
python src/diagnostics.py --data data/instances/<file>.json --mode iis --out-lp debug.lp
```

Common causes of infeasibility:
1. `c12b` (initial-days) + `c12` (spacing): aircraft already at threshold on day 0.
2. `c10` (capacity): maintenance airport capacity = 0 for all airports.
3. `c13` (hrs): tight Tmax with many long flights and few maintenance airports.
4. `c15` (no-fly during maintenance) + `c1` (coverage): no feasible slot.

## Data Format (JSON Instance)

```json
{
  "Aircrafts": [0, 1, ..., p-1],
  "AIRCRAFT_INIT_POS": {"0": "A", "1": "B", ...},
  "Flights": [[fid, origin, dest, dep_min, arr_min], ...],
  "Maintenance_Thresholds": {"A": 1200, "B": 3600, "C": 10, "D": 14},
  "Maintenance_Durations":  {"A": 360,  "B": 2880, "C": 1440, "D": 2880},
  "Station_Capacity": {"A": 1, "B": 0, "C": 4, ...},
  "Initial_Checks": {"A": {"0": 1000, ...}, "B": {...}, "C_Days": {...}, "D_Days": {...}},
  "Cost_Matrix": [[c_f1_a0, c_f1_a1, ...], ...]
}
```

Times in minutes from midnight. `9999` in Cost_Matrix = forbidden assignment.

## Paper Section Map

Write with `write-paper.prompt.md`. Section order:
1. Introduction (motivation, planning pipeline)
2. Literature review (3 formulation families + comparison)
3. Basic MILP (C1–C4, compactness proof)
4. Maintenance model (C8–C15, **correction of C13**)
5. Hierarchy extension (A/B/C/D, C13b, C14b)
6. Heuristic (greedy/insertion, complexity, gap)
7. Computational study (Tables 5,6,10,11 + correction impact)
8. Conclusion

## Solver Configuration (CPLEX via Pyomo)

```python
solver = SolverFactory('cplex')
solver.options['timelimit'] = 3600          # 1 hour max
solver.options['mip limits cutpasses'] = 0  # disable cut generation (matches paper)
solver.options['preprocessing presolve'] = 1  # 1=on (with presolve), 0=off
```
