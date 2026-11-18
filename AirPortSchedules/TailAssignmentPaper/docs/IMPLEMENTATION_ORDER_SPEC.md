# A-Only Paper Implementation Specification

## Status

Frozen baseline for branch `dev_thesis_paper_mix` on 2026-11-18.

This document is the executable task contract for the A-only paper variant. It separates the faithful Khaled profile, the historical endpoint-split profile, the corrected A-only formulation, the two executable-maintenance options, and the event formulation. Do not pool results across these profiles unless the experiment metadata records the shared assumptions and the comparison is explicitly labelled as a controlled ablation.

Implementation checkpoint completed on 2026-11-18:

- independent certificate replay covers routes, duration, release timing, daily and simultaneous capacity, and strict A-hour exposure;
- `KhaledPrintedC13Scheduler`, `EndpointSplitC13Scheduler`, `CorrectedAOnlyScheduler`, `OptionAExecutableScheduler`, and `OptionBProtectedScheduler` are implemented;
- Option B certification returns `unsupported` before model construction;
- the historical event model is recovered as `event_historical_unverified` and rejects the fixed known-bad A-hour schedule, but remains unverified for broader equivalence;
- the profile runner writes CSV, schedules, source hashes, input hashes, metadata and a source archive;
- the root and `Thesis/code` Python mirrors are synchronized;
- the full root suite has 87 passing tests, mirrored focused tests pass, and the manuscript has a validated one-instance control plus a paired timing study on 40 certified inputs (10 seeds in each of four fleet/horizon cells) under CPLEX 12.9.

The paired timing study is small-scale and descriptive; legacy Khaled/split schedules that fail strict replay are not feasible-quality baselines. This checkpoint does not claim scale performance, solver-independent rankings, full event-model equivalence, or a reproduction of Khaled's real-data grid.

## Baseline

- Baseline commit: `e59c4186bcf917920051a6e4f34e302e51b621d1`.
- Branch: `dev_thesis_paper_mix`.
- Python: 3.12.0.
- Pyomo: 6.10.1.
- Tests: 75 passed before implementation work resumed.
- Available local CPLEX: IBM ILOG CPLEX Interactive Optimizer 12.9.0.0.
- Local Gurobi: not required for stages 1--7; Gurobi provenance belongs in a separately identified rerun.

## Canonical Units And Time Semantics

- Flight, check, service-window, buffer, turn, threshold, and exposure times are absolute or elapsed **minutes**.
- Calendar day `d` is one-based: `d = floor(t / 1440) + 1`.
- A flight `i` has departure day `d_i`, arrival day `bar d_i`, departure time `t_i^down`, arrival time `t_i^up`, and strictly positive duration `p_i = t_i^up - t_i^down`.
- A selected trigger is attached to an assigned flight, its maintenance-capable arrival airport, and its arrival day unless a profile explicitly declares otherwise.
- A night labelled `d` starts after the selected arrival on day `d`; an hour reset occurs at check completion, not at trigger arrival.
- The existing basic route rows require continuity and turn time. Overlap rows are mandatory for the corrected profiles.
- Half-open ground intervals `[S,C)` are used for maintenance and occupancy; departure exactly at completion plus release buffer is allowed when no turn-time incompatibility remains.

## Khaled Primary-Source Findings

The locally archived Khaled et al. PDF is `References/FA45_A compact optimization model for the tail assignment problem.pdf`.

- Printed equation (13) uses the pair range `2 <= d' - d <= d_max - 1` and `d < n_d`.
- The prose on p. 556 instead states `1 <= d' - d <= d_max - 1`.
- The faithful published-profile implementation follows the displayed equation, and the prose discrepancy is reported explicitly rather than silently resolved.
- The printed flight window is `F_{d+1,d'}`, equivalently the current notation `(d,d']`.
- The published maintenance policy is nightly, trigger-linked maintenance at the last flight's arrival airport, with per-airport daily capacity and both maximum calendar spacing and cumulative flight-time requirements.

## Profile Contract

### `khaled_printed`

Faithful controlled reproduction of the displayed paper row family.

- Original single C13 row.
- Printed pair range: `2 <= d' - d <= d_max - 1`, `d < n_d`.
- Published A-policy calendar spacing remains active.
- Historical nightly placement and capacity assumptions are retained.
- Legacy opening-row behavior must be selected and named separately; it is not implied by displayed equation (13).
- Known correctness gaps are preserved for diagnostic comparison, not described as fixes.

### `endpoint_split`

Historical two-row endpoint relaxation used for comparison.

- Same placement, index range, calendar policy, units, and opening-row selection as `khaled_printed`.
- Replaces the single original row by the two endpoint-indicator rows.
- It is a distinct diagnostic profile and must not be described as an exact correction.

### `corrected_a_interval`

Shared corrected A-only profile.

- Arrival-day trigger eligibility only.
- Binary assignment, routing continuity, turn time, and overlap constraints.
- All day pairs `1 <= d < d' <= n_d`.
- Strict interval row relaxes only on an interior reset.
- Opening prefix is imposed for every day, including day 1, and relaxes only on checks strictly before its end day.
- Opening big-M includes initial accumulated hours.
- Calendar spacing is enabled or disabled explicitly by policy ID; results never rely on an implicit default.

### `option_a`

Corrected A-only placement plus explicit overnight executability.

- Required instance data include check duration, preparation/release buffers, service windows, capacity interpretation, and optional terminal release deadline.
- Selected triggers outside a service window are fixed out.
- Conflict rows block every assigned departure from trigger arrival until release.
- Missing required timing data raises a configuration error before solving.

### `option_b`

Corrected A-only placement certified under protected-night assumptions.

- Same candidate placement and hour model as Option A.
- A pre-solve certification verifies same-day flights, protected period containment, duration/buffer fit, staffing/capacity, and terminal release.
- Failed certification returns `unsupported`; it is not a proof of infeasibility.
- Option A and B are compared only on a common input set that passes Option B certification.

### `event_historical_unverified`

Recovered historical event model for audit only.

- Disabled from paper result tables until it passes the same route, capacity, timing, initial-hour, and known-bad-schedule checks as the day models.
- No equivalence or performance claim is allowed from model construction alone.

## Shared Replay Contract

A valid result certificate contains, at minimum:

- Flight-to-aircraft assignment.
- Maintenance events with aircraft, check type, station, start, end, trigger flight when representable, and selected model day.
- Objective, solver, solver version, termination status, time limit, bounds, and model dimensions.
- Source revision/hash, input hash, profile ID, all profile settings, and build/solve timestamps.

Independent replay checks:

1. every flight covered exactly once;
2. airport continuity;
3. no overlap and turn-time compliance;
4. trigger assignment, arrival-airport eligibility, and arrival-day eligibility;
5. same-day/overnight blocking and release timing for the selected option;
6. station capacity with the declared simultaneous-versus-daily semantics;
7. accumulated type-A flight minutes including pre-horizon exposure and check completion resets;
8. calendar spacing only when the profile enables it;
9. objective reconstruction from the certificate, independently of model state variables.

## Implementation Order

1. Freeze this specification and the baseline.
2. Create independent fixtures and replay.
3. Implement named Khaled and split profiles.
4. Implement the shared corrected A-only model.
5. Implement Option A, then Option B and Option B certification.
6. Recover and audit the event model.
7. Run reproducible controlled comparisons and faithful published-profile controls.
8. Integrate tested mirrors and paper results only after validated matched runs exist.

## Publication Gate

The computational section remains evidence-free until the selected profile, independent replay, source hashes, input hashes, solver settings, bounds, timings, and certificates exist in one complete run bundle. Unsupported Option B inputs and failed event-model audits must remain labelled as `unsupported` or `unverified`, never as infeasible or inferior.
