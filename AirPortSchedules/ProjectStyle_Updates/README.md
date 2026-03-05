# Tail Assignment model (compact) — notes

This repository contains a compact MILP for the tail assignment problem.

Key developer-facing items
- `improved_model.build_full_model(data, ..., params=...)` builds the canonical model.
- `params` may be a `model_params.Params` instance, a dict with matching keys, or omitted.

Important toggles (boolean flags accepted by `build_full_model`):
- `add_equipment_turn` — enable conservative equipment-turn (continuity) constraints.
- `add_maint_block` — enable blocking of flights during maintenance windows.
- `enable_z_check` — add z->day checks for z variables (sanity constraints).
- `enable_maint_spacing` / `enable_maint_spacing2` — enforce spacing of mega_check windows.
- `enable_maint_cumulative` / `enable_maint_cumulative_start` — flying-hours cumulative constraints.
- `enable_maint_block_checks` — ensure at most one check per plane per day.
- `enable_maint_checks_days` — multi-day check duration enforcement.
- `enable_maint_capacity` — per-facility/day capacity limits (uses `params.mcap`).
- `enable_maint_link` — link z -> y activation constraints.
- `enable_maint_hierarchy` — hierarchical aggregation of checks.
- `enable_overlap_checks` — prevent overlapping flights on same plane.

Parameters (in `model_params.Params`):
- `All_Check_List` (list[str]) — names of checks, e.g. ["Acheck","Bcheck",...]
- `All_Check_days` (dict) — days threshold per check
- `All_Check_Done_hours` (dict) — flying-hour thresholds per check
- `All_Check_durations` / `All_Check_durations_days` — durations in minutes and days
- `All_Checks_Done_Days` — previously elapsed days per check (dict)
- `mcap` (optional dict[(m,d)] -> int) — maintenance capacity per airport/day

Use the `normalize_params(raw, data)` helper to construct a `Params` instance from a dict/object or from parsed data.
