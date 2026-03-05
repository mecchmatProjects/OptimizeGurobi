"""Improved model construction utilities.

Concise paper summary (to keep the model intent documented inline):

This module implements a canonical, "compact" construction of the tail
assignment model described in the paper "A compact optimization model for the
tail assignment problem". The model follows the compact MILP style: use
assignment variables x[i,p] together with a small set of auxiliary variables
z and y to encode maintenance activation and blocking. Compactness is
achieved by aggregating maintenance decisions by day/check type and by using
counting/inequality constraints rather than explicit pairwise flight arcs.

Key modeling highlights (mapping to code):
- x[i,p] : binary assignment of flight i to plane p
- z[i,p,d,c] : binary marker that flight i (assigned to p) triggers maintenance
    check c on day d
- y[p,d,c] : binary activation of maintenance c for plane p on day d
- equipment_turn / continuity constraints: conservative counting inequalities
    that ensure aircraft continuity at airports with a minimum turnaround time
- maint_block constraints: prevent assigning flights that overlap active
    maintenance windows (via z/y)

Practical implementation notes (kept here for developers):
- Try to keep Big-M values as tight as possible. Large M degrades LP
    relaxations and slows branch-and-bound.
- Build z only for (i,p,d,c) combinations that are feasible (e.g., flight i
    arrives at an airport that can perform check c) to avoid combinatorial blowup.
- For unit testing we intentionally provide flags to toggle equipment-turn and
    maintenance-block constraints so tests can isolate each constraint group.

This module exposes:
- build_full_model(data, min_turn=30, add_equipment_turn=True, add_maint_block=True)

The returned tuple is (model, FlightData, Days, AircraftInit).
"""
from pyomo.environ import ConstraintList
from model_builder import build_model_from_data


def add_equipment_turn_constraints(model, FlightData, min_turn, AircraftInit):
    # conservative equipment-turn / continuity constraints
    model.equipment_turn_constraints = ConstraintList()
    F_dep_k = {k: [i for i in model.F if FlightData[i]['origin'] == k] for k in model.A}
    def F_arr_t(k, t, delta):
        return [i for i in F_dep_k[k] if FlightData[i]['arrivalTime'] <= t - delta]

    for j in model.P:
        for k in model.A:
            for i in F_dep_k[k]:
                t_dep = FlightData[i]['departureTime']
                lhs_geq = sum(model.x[i1, j] for i1 in F_arr_t(k, t_dep, min_turn))
                lhs_lt = sum(model.x[i1, j] for i1 in F_dep_k[k] if FlightData[i1]['departureTime'] < t_dep)
                if k != AircraftInit.get(j, None):
                    model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j])
                else:
                    model.equipment_turn_constraints.add(lhs_geq - lhs_lt >= model.x[i, j] - 1)


def add_maint_block_and_related(
    model,
    FlightData,
    Days,
    params,
    min_turn,
    All_Check_days,
    All_Checks_Done_Days,
    All_Checks,
    All_Check_Done_hours,
    All_Check_durations_days,
    Mbig,
    mcap,
    enable_z_check=False,
    enable_maint_spacing=False,
    enable_maint_spacing2=False,
    enable_maint_cumulative=False,
    enable_maint_cumulative_start=False,
    enable_maint_block_checks=True,
    enable_maint_checks_days=True,
    enable_maint_capacity=True,
    enable_maint_link=True,
    enable_maint_hierarchy=True,
    enable_overlap_checks=False,
):
    """Add maintenance blocking and auxiliary maintenance constraints.

    This function mirrors the inlined block previously present in
    build_full_model but is extracted to keep the builder modular. It does
    not change logical behaviour; inputs and flags are forwarded as before.
    """
    # recompute helpers locally
    F_dep_k = {k: [i for i in model.F if FlightData[i]['origin'] == k] for k in model.A}
    F_arr_k = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

    def F_dep_t_t1(k, t, t1):
        return [i for i in F_dep_k[k] if FlightData[i]['departureTime'] > t and FlightData[i]['departureTime'] <= t1]

    def F_d_next(d1, d2):
        return [i for i in model.F if d1 < FlightData[i]['day_departure'] <= d2]

    # Block flights during maintenance windows using z variables
    model.maint_block_flights = ConstraintList()
    for c in model.C:
        for i in model.F:
            t_arr = FlightData[i]['arrivalTime']
            day = FlightData[i]['day_arrival']
            airport = FlightData[i]['destination']
            if airport not in model.MA:
                continue

            for j in model.P:
                for i2 in F_dep_t_t1(airport, t_arr, t_arr + 1e6):
                    model.maint_block_flights.add(model.z[i, j, day, c] + model.x[i2, j] <= 1)

    # Optional: link z/y checking and other maintenance constraints
    if enable_z_check:
        model.z_check = ConstraintList()
        for check in model.C:
            for i in model.F:
                for j in model.P:
                    for d in model.D:
                        if d < FlightData[i]["day_arrival"]:
                            model.z_check.add(model.z[i, j, d, check] == 0)
                        if d > FlightData[i]["day_arrival"]:
                            model.z_check.add(Mbig * (1 - model.z[i, j, d, check]) >=
                                              sum(model.x[i1, j] for i1 in F_d_next(FlightData[i]["day_arrival"], d + 1)))

    if enable_maint_spacing:
        model.maint_spacing = ConstraintList()
        for check in model.C:
            nd = All_Check_days.get(check, 1)
            for j in model.P:
                for start in range(0, max(1, len(Days) - nd)):
                    model.maint_spacing.add(
                        sum(model.mega_check[j, r, check] for r in Days[start:start + nd]) >= 1
                    )

    if enable_maint_spacing2:
        model.maint_spacing2 = ConstraintList()
        for check in model.C:
            for j in model.P:
                days_without_checks = int(All_Check_days.get(check, 0) - All_Checks_Done_Days.get(check, {}).get(j, 0)) if isinstance(All_Checks_Done_Days, dict) else 0
                if days_without_checks <= 0 or days_without_checks >= len(model.D):
                    continue
                model.maint_spacing2.add(sum(model.mega_check[j, r, check] for r in Days[:days_without_checks]) >= 1)

    if enable_maint_cumulative:
        model.maint_cumulative = ConstraintList()
        for check in model.C:
            for j in model.P:
                for start in range(len(Days) - 1):
                    for end in range(start + 2, min(start + All_Check_days.get(check, len(Days)), len(Days))):
                        d = Days[start]
                        d_ = Days[end]
                        t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(d, d_))
                        y_sum = sum(model.mega_check[j, r, check] for r in Days[start + 1:end])
                        model.maint_cumulative.add(
                            t_sum <= All_Check_Done_hours.get(check, 0) * 60 + Mbig * y_sum + Mbig * (2 - model.mega_check[j, d, check] - model.mega_check[j, d_, check])
                        )

    if enable_maint_cumulative_start:
        model.maint_cumulative_start = ConstraintList()
        for check in model.C:
            for j in model.P:
                for end in range(1, min(len(Days) - 1, All_Check_days.get(check, len(Days)))):
                    d = Days[0]
                    d_ = Days[end]
                    t_sum = sum(FlightData[i]['duration'] * model.x[i, j] for i in F_d_next(0, d_))
                    y_sum = sum(model.mega_check[j, r, check] for r in Days[:end - 1])
                    model.maint_cumulative_start.add(
                        t_sum <= (All_Check_Done_hours.get(check, 0) - All_Checks.get(check, {}).get(j, 0)) * 60 + Mbig * y_sum + Mbig * model.mega_check[j, d_, check]
                    )

    if enable_maint_block_checks:
        if not hasattr(model, 'maint_block_checks'):
            model.maint_block_checks = ConstraintList()
        for j in model.P:
            for d in model.D:
                model.maint_block_checks.add(sum(model.y[j, d, check] for check in model.C) <= 1)

    if enable_maint_checks_days:
        model.maint_checks_days = ConstraintList()
        for j in model.P:
            for check in model.C:
                duration_days = All_Check_durations_days.get(check, 0)
                if duration_days == 0:
                    continue
                for d_idx in range(len(Days)):
                    K = min(d_idx + duration_days, len(Days))
                    if d_idx == 0:
                        model.maint_checks_days.add(
                            sum(model.mega_check[j, Days[d1], check] for d1 in range(1, K)) + Mbig * (1 - model.mega_check[j, Days[0], check]) >= K - 1
                        )
                        continue
                    if d_idx >= K:
                        continue
                    model.maint_checks_days.add(
                        sum(model.mega_check[j, Days[d1], check] for d1 in range(d_idx + 1, K)) + Mbig * model.mega_check[j, Days[d_idx - 1], check] + Mbig * (1 - model.mega_check[j, Days[d_idx], check]) >= K - d_idx - 1
                    )

    if enable_maint_capacity:
        model.maint_capacity = ConstraintList()
        for check in model.C:
            for d in model.D:
                for m in model.MA:
                    relevant_flights = F_dep_k.get(m, [])
                    if relevant_flights:
                        cap = mcap.get((m, d), len(model.P)) if mcap else len(model.P)
                        model.maint_capacity.add(sum(model.z[i, j, d, check] for i in relevant_flights for j in model.P) <= cap)

    if enable_maint_link:
        if not hasattr(model, 'maint_link'):
            model.maint_link = ConstraintList()
        for check in model.C:
            for d in model.D:
                for j in model.P:
                    model.maint_link.add(sum(model.z[i, j, d, check] for i in model.F if FlightData[i]["destination"] in model.MA) == model.y[j, d, check])

    if enable_maint_hierarchy:
        if not hasattr(model, 'maint_hierarchy'):
            model.maint_hierarchy = ConstraintList()
        CHECK_HIERARCHY = {
            "Acheck": ["Acheck", "Bcheck", "Ccheck", "Dcheck"],
            "Bcheck": ["Bcheck", "Ccheck", "Dcheck"],
            "Ccheck": ["Ccheck", "Dcheck"],
            "Dcheck": ["Dcheck"],
        }
        for j in model.P:
            for d in model.D:
                for c in model.C:
                    model.maint_hierarchy.add(model.mega_check[j, d, c] == sum(model.y[j, d, check] for check in CHECK_HIERARCHY.get(c, [c])))

    if enable_overlap_checks:
        model.flight_overlap = ConstraintList()
        for i in model.F:
            for i1 in model.F:
                if i1 <= i:
                    continue
                if FlightData[i]["departureTime"] >= FlightData[i1]["arrivalTime"] + min_turn:
                    continue
                if FlightData[i1]["departureTime"] >= FlightData[i]["arrivalTime"] + min_turn:
                    continue
                for j in model.P:
                    model.flight_overlap.add(model.x[i, j] + model.x[i1, j] <= 1)


def build_full_model(
    data,
    min_turn=30,
    add_equipment_turn=True,
    add_maint_block=True,
    params=None,
    enable_z_check=False,
    enable_maint_spacing=False,
    enable_maint_spacing2=False,
    enable_maint_cumulative=False,
    enable_maint_cumulative_start=False,
    enable_maint_block_checks=True,
    enable_maint_checks_days=True,
    enable_maint_capacity=True,
    enable_maint_link=True,
    enable_maint_hierarchy=True,
    enable_overlap_checks=False,
):
    """Build an enriched model from parsed data.

    Parameters
    - data: parsed dictionary from data_io.parse_airline_data
    - min_turn: minimum turnaround in minutes

    Returns: (model, FlightData, Days, AircraftInit)
    """
    model, FlightData, Days, AircraftInit = build_model_from_data(data)

    # helper maps
    F_dep_k = {k: [i for i in model.F if FlightData[i]['origin'] == k] for k in model.A}
    F_arr_k = {k: [i for i in model.F if FlightData[i]['destination'] == k] for k in model.A}

    def F_arr_t(k, t, delta):
        return [i for i in F_arr_k[k] if FlightData[i]['arrivalTime'] <= t - delta]

    def F_dep_t_t1(k, t, t1):
        return [i for i in F_dep_k[k] if FlightData[i]['departureTime'] > t and FlightData[i]['departureTime'] <= t1]

    # day-based helpers used by some maintenance constraints
    F_d = {d: [i for i in model.F if FlightData[i]['day_departure'] == d] for d in model.D}
    F_d_next = lambda d1, d2: [i for i in model.F if d1 < FlightData[i]['day_departure'] <= d2]

    F_d_t = lambda d, t: [i for i in model.F if FlightData[i]['day_departure'] == d and FlightData[i]['departureTime'] > t ]

    # Equipment-turn / continuity constraints (a conservative form)
    if add_equipment_turn:
        add_equipment_turn_constraints(model, FlightData, min_turn, AircraftInit)

    # Consolidate parameters into a single Params object (normalize from dict/object/data)
    try:
        from model_params import normalize_params
    except Exception:
        # defensive: if import fails, fall back to previous inline defaults
        normalize_params = None

    if normalize_params:
        params = normalize_params(params, data)
        All_Check_List = params.All_Check_List
        All_Checks = params.All_Checks or {c: {} for c in All_Check_List}
        All_Check_days = params.All_Check_days
        All_Check_Done_hours = params.All_Check_Done_hours
        All_Check_durations = params.All_Check_durations
        All_Check_durations_days = params.All_Check_durations_days
        All_Checks_Done_Days = params.All_Checks_Done_Days or {c: 0 for c in All_Check_List}
        Mbig = params.Mbig
        mcap = params.mcap
    else:
        # sensible defaults if nothing provided
        All_Check_List = ["Acheck", "Bcheck", "Ccheck", "Dcheck"]
        All_Checks = {c: {} for c in All_Check_List}
        All_Check_days = {"Acheck": 50, "Bcheck": 180, "Ccheck": 540, "Dcheck": 1825}
        All_Check_Done_hours = {"Acheck": 48, "Bcheck": 1440, "Ccheck": 4320, "Dcheck": 14600}
        All_Check_durations = {"Acheck": 8*60, "Bcheck": 48*60, "Ccheck": 5*24*60, "Dcheck": 10*24*60}
        All_Check_durations_days = {"Acheck": 1, "Bcheck": 2, "Ccheck": 5, "Dcheck": 10}
        All_Checks_Done_Days = {c: 0 for c in All_Check_List}
        Mbig = 10**6
        mcap = None

    # Block flights and add maintenance-related helper constraints
    if add_maint_block:
        add_maint_block_and_related(
            model,
            FlightData,
            Days,
            params,
            min_turn,
            All_Check_days,
            All_Checks_Done_Days,
            All_Checks,
            All_Check_Done_hours,
            All_Check_durations_days,
            Mbig,
            mcap,
            enable_z_check=enable_z_check,
            enable_maint_spacing=enable_maint_spacing,
            enable_maint_spacing2=enable_maint_spacing2,
            enable_maint_cumulative=enable_maint_cumulative,
            enable_maint_cumulative_start=enable_maint_cumulative_start,
            enable_maint_block_checks=enable_maint_block_checks,
            enable_maint_checks_days=enable_maint_checks_days,
            enable_maint_capacity=enable_maint_capacity,
            enable_maint_link=enable_maint_link,
            enable_maint_hierarchy=enable_maint_hierarchy,
            enable_overlap_checks=enable_overlap_checks,
        )

    return model, FlightData, Days, AircraftInit

