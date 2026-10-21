"""Audit uniform-policy artifacts independently and render their paper tables."""

import argparse
import csv
import hashlib
import json
import math
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_schedule(data, schedule, policy, objective):
    flights = {int(row[0]): row for row in data["Flights"]}
    assignments = {(int(flight), int(aircraft)) for flight, aircraft in schedule["assignments"]}
    events = schedule["events"]
    problems = []
    if len(assignments) != len(schedule["assignments"]):
        problems.append("duplicate assignment records")
    tolerance = 1e-5
    coverage = Counter(flight for flight, _aircraft in assignments)
    if any(coverage[flight] != 1 for flight in flights):
        problems.append("flight coverage")
    if any(flight not in flights or aircraft not in data["Aircrafts"] for flight, aircraft in assignments):
        return ["unknown flight/aircraft"]
    duration = float(data["Maintenance_Durations"]["A"])
    threshold = float(data["Maintenance_Thresholds"]["A"])
    grid = policy["time_grid_minutes"]
    defer = policy["maximum_start_deferral_minutes"]
    by_aircraft = defaultdict(list)
    starts = Counter()
    triggers = Counter()
    for event in events:
        flight, aircraft = event["flight"], event["aircraft"]
        if (flight, aircraft) not in assignments or event["check"] != "A":
            problems.append("unassigned or invalid maintenance event")
            continue
        arrival = float(flights[flight][4])
        start, end = event["start"], event["completion"]
        if abs(end - start - duration) > tolerance:
            problems.append("maintenance duration")
        if start < arrival - tolerance or start > arrival + defer + tolerance:
            problems.append("maintenance deferral")
        if abs(start / grid - round(start / grid)) > tolerance:
            problems.append("start off grid")
        day = int(start // 1440) + 1
        starts[aircraft, day] += 1
        triggers[flight, aircraft] += 1
        night = policy["night_start_minute"]
        if night is not None and abs(start - (day - 1) * 1440 - night) > tolerance:
            problems.append("night-start restriction")
        for following, tail in assignments:
            departure = float(flights[following][3])
            if tail == aircraft and arrival - tolerance <= departure < end + 30 - tolerance:
                problems.append("flight while waiting/under maintenance/turn")
        by_aircraft[aircraft].append(event)
    if any(count > 1 for count in starts.values()):
        problems.append("multiple checks per actual start day")
    if any(count > 1 for count in triggers.values()):
        problems.append("multiple events per trigger")
    for aircraft in data["Aircrafts"]:
        airport = data["AIRCRAFT_INIT_POS"][str(aircraft)]
        ready = 0.0
        accumulated = float(data.get("Initial_Checks", {}).get("A", {}).get(str(aircraft), 0))
        if not 0 <= accumulated <= threshold:
            problems.append("initial exposure")
        tail_events = sorted(by_aircraft[aircraft], key=lambda event: event["completion"])
        cursor = 0
        assigned = sorted(
            (flights[flight] for flight, tail in assignments if tail == aircraft),
            key=lambda row: (float(row[3]), row[0]),
        )
        for flight, origin, destination, departure, arrival in assigned:
            if origin != airport or departure < ready - tolerance:
                problems.append("airport continuity/overlap/turn")
            while cursor < len(tail_events) and tail_events[cursor]["completion"] <= departure + tolerance:
                accumulated = 0.0
                cursor += 1
            accumulated += arrival - departure
            if accumulated > threshold + tolerance:
                problems.append("flight-hour threshold before check")
            airport, ready = destination, arrival + 30
    for airport, capacity in data["Station_Capacity"].items():
        local = [event for event in events if flights[event["flight"]][2] == airport]
        for instant in {event["start"] for event in local}:
            occupancy = sum(event["start"] <= instant + tolerance < event["completion"] - tolerance for event in local)
            if occupancy > capacity:
                problems.append("maintenance bay capacity")
        if capacity <= 0 and local:
            problems.append("maintenance station eligibility")
    columns = {aircraft: index for index, aircraft in enumerate(data["Aircrafts"])}
    cost = sum(data["Cost_Matrix"][flight - 1][columns[aircraft]] for flight, aircraft in assignments)
    cost += len(events) * 100 * max(1, math.ceil(duration / 1440))
    if abs(cost - float(objective)) > tolerance:
        problems.append("objective reconstruction")
    return problems


def load_and_audit(path, allow_day_boundary=False):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))["runs"][-1]
    if digest(path) != metadata["result_csv_sha256"]:
        raise ValueError(f"Changed result CSV: {path}")
    schedules_path = path.with_suffix(".schedules.json")
    if digest(schedules_path) != metadata["schedule_sha256"]:
        raise ValueError(f"Changed schedules: {path}")
    snapshot = path.with_name(metadata["source_snapshot"])
    if digest(snapshot) != metadata["source_snapshot_sha256"]:
        raise ValueError(f"Changed source snapshot: {path}")
    with zipfile.ZipFile(snapshot) as archive:
        for relative, expected in metadata["sources"].items():
            observed = hashlib.sha256(archive.read(relative.replace("\\", "/"))).hexdigest()
            if observed != expected:
                raise ValueError(f"Source snapshot mismatch: {relative}")
    inputs = {}
    for relative, record in metadata["inputs"].items():
        source = ROOT / relative
        if digest(source) != record["sha256"]:
            raise ValueError(f"Changed input: {relative}")
        inputs[source.stem] = json.loads(source.read_text(encoding="utf-8"))
        if record["effective_enabled_checks"] != ["A"]:
            raise ValueError("Uniform study is not A-only")
    observed = [(row["case"], row["formulation"]) for row in rows]
    expected = {
        (case, method) for case in inputs
        for method in metadata["configuration"]["methods"]
    }
    if set(observed) != expected or len(observed) != len(expected):
        raise ValueError("Incomplete or duplicated method/input grid")
    schedules = {
        (item["case"], item["formulation"]): item
        for item in json.loads(schedules_path.read_text(encoding="utf-8"))
    }
    policies = metadata["configuration"]["policies"]
    for row in rows:
        if row["formulation"] not in policies and not allow_day_boundary:
            raise ValueError("Uniform study contains a nonuniform method")
        if row["status"] == "ERROR" or row["error"]:
            raise ValueError(f"Failed solver run: {row}")
        if allow_day_boundary and row["lp_relaxation"] == "True":
            if row["status"] != "optimal":
                raise ValueError("Repaired LP ablation contains a non-optimal objective")
            continue
        if row["has_solution"] == "True":
            key = row["case"], row["formulation"]
            if key not in schedules or row["replay_status"] != "pass":
                raise ValueError(f"Missing accepted incumbent: {key}")
            if allow_day_boundary:
                data = inputs[row["case"]]
                schedule = schedules[key]
                flight_data = {flight[0]: flight for flight in data["Flights"]}
                checked = {(event["legacy_index"][1], event["legacy_index"][2]) for event in schedule["events"]}
                problems = []
                for aircraft in data["Aircrafts"]:
                    exposure = data.get("Initial_Checks", {}).get("A", {}).get(str(aircraft), 0)
                    by_day = defaultdict(list)
                    for flight, tail in schedule["assignments"]:
                        if tail == aircraft:
                            by_day[int(flight_data[flight][3] // 1440) + 1].append(flight_data[flight])
                    days = set(by_day) | {day for tail, day in checked if tail == aircraft}
                    for day in sorted(days):
                        for flight in sorted(by_day[day], key=lambda item: item[3]):
                            exposure += flight[4] - flight[3]
                            if exposure > data["Maintenance_Thresholds"]["A"] + 1e-5:
                                problems.append("day-boundary flight-hour limit")
                        if (aircraft, day) in checked:
                            exposure = 0
            else:
                problems = audit_schedule(inputs[row["case"]], schedules[key], policies[row["formulation"]], row["objective"])
            if problems:
                raise ValueError(f"Independent artifact replay failed: {key}: {problems}")
        elif row["status"] == "optimal":
            raise ValueError("Optimal row without a loaded solution")
    for case in {row["case"] for row in rows}:
        by_method = {row["formulation"]: row for row in rows if row["case"] == case}
        for timing in ("flexible", "night"):
            pair = [by_method.get(f"uniform_{timing}_{encoding}") for encoding in ("day", "event")]
            if all(item and item["status"] == "optimal" for item in pair):
                if abs(float(pair[0]["objective"]) - float(pair[1]["objective"])) > 1e-6:
                    raise ValueError(f"Encoding mismatch: {case}/{timing}")
    return rows


def plot_main(rows, output_dir):
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    methods = ("uniform_flexible_day", "uniform_flexible_event")
    labels = ("Day-indexed", "Event-indexed")
    colors = ("#166534", "#b45309")
    horizon_rows = [row for row in rows if int(row["H"]) == 30]
    common = {
        case for case in {row["case"] for row in horizon_rows}
        if {row["formulation"] for row in horizon_rows if row["case"] == case and row["status"] == "optimal"} == set(methods)
    }
    for metric, label, filename in (
        ("vars", "Active scalar variables", "uniform_variables_h30_20261021.png"),
        ("wall_s", "Solve wall time (s)", "uniform_wall_h30_20261021.png"),
    ):
        figure, axis = plt.subplots(figsize=(7, 4.2), constrained_layout=True)
        for method, legend, color in zip(methods, labels, colors):
            series = sorted(
                (row for row in horizon_rows if row["formulation"] == method
                 and (metric != "wall_s" or row["case"] in common)),
                key=lambda row: int(row["P"]),
            )
            axis.plot([int(row["P"]) for row in series], [float(row[metric]) for row in series],
                      marker="o" if method.endswith("_day") else "s", color=color, label=legend)
        axis.set_xlabel("Number of aircraft")
        axis.set_ylabel(label)
        axis.legend(frameon=False)
        axis.grid(alpha=0.25)
        figure.savefig(output_dir / filename, dpi=220)
        plt.close(figure)


def render(main_rows, night_rows, multiseed_rows, prefix_lp_rows=(), prefix_mip_rows=()):
    output = [
        r"\subsection{Uniform Flexible-Start Study}",
        r"\label{subsec:uniform_results}",
        r"The new comparison uses the common policy in \Cref{subsec:uniform_flexible}.",
        r"Both encodings use CPLEX 12.6.0.0, one thread, presolve on, and a 180-second limit.",
        r"They share the hour engine; the comparison measures maintenance encoding, not independent physical models.",
        r"All loaded incumbents, including time-limited ones, are checked by chronological replay.",
        r"An additional audit reconstructs cost, hours, timing, routes, actual start-day counts and bay occupancy",
        r"directly from the saved decisions and input JSON, without the model's state values.",
        r"\begin{table}[t]\centering\scriptsize",
        r"\caption{Uniform flexible-start encodings. Wall time is measured around the solver call.",
        r"Status is the interface termination code; a time-limited incumbent is not an optimum.}",
        r"\label{tab:uniform_flexible}\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{rrl lrrrrl}\toprule",
        r"$|P|$ & $H$ & Encoding & Status & Objective & Wall (s) & Vars & Rows & Replay \\\midrule",
    ]
    for row in sorted(main_rows, key=lambda row: (int(row["P"]), int(row["H"]), row["formulation"])):
        encoding = "Day" if row["formulation"].endswith("_day") else "Event"
        objective = f"{float(row['objective']):.0f}" if row["has_solution"] == "True" else "--"
        output.append(f"{row['P']} & {row['H']} & {encoding} & {row['status']} & {objective} & {float(row['wall_s']):.2f} & {row['vars']} & {row['constraints']} & {row['replay_status'].upper()} " + r"\\")
    output.extend([r"\bottomrule\end{tabular}}\end{table}"])
    optimal = sum(row["status"] == "optimal" for row in main_rows)
    loaded = sum(row["has_solution"] == "True" for row in main_rows)
    output.append(f"Of {len(main_rows)} runs, {optimal} terminate optimally and {loaded} return loaded incumbents; all {loaded} pass both replay checks.")
    output.append(r"Unavailable solver bounds and node counts are left blank in raw data, not inferred from incumbent values.")
    output.append(r"The timings are descriptive workstation measurements, not isolated repeated-runtime trials or evidence of general speedup.")
    if prefix_lp_rows and prefix_mip_rows:
        output.extend([
            r"\begin{table}[t]\centering\scriptsize",
            r"\caption{Repaired day-boundary ablation, including the first-day opening row. This is not the arbitrary flexible-start model.}",
            r"\label{tab:repaired_prefix}\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{rr rrr r ll}\toprule",
            r"$|P|$ & $H$ & State LP & Interval LP & Prefix LP & Common MIP & Interval vars/rows & Prefix vars/rows \\\midrule",
        ])
        for case in sorted({row["case"] for row in prefix_lp_rows}):
            lp = {row["formulation"]: row for row in prefix_lp_rows if row["case"] == case}
            mip = {row["formulation"]: row for row in prefix_mip_rows if row["case"] == case}
            state = lp["legacy_corrected_strengthened"]
            interval = lp["legacy_strict_interval"]
            prefix = lp["legacy_hour_prefix"]
            objectives = [float(row["objective"]) for row in mip.values()]
            if any(row["status"] != "optimal" for row in mip.values()) or max(objectives) - min(objectives) > 1e-5:
                raise ValueError("Repaired integer ablation is non-optimal or mismatched")
            if abs(float(interval["objective"]) - float(prefix["objective"])) > 1e-5:
                raise ValueError("Repaired interval and prefix LP bounds differ")
            interval_mip, prefix_mip = mip["legacy_strict_interval"], mip["legacy_hour_prefix"]
            output.append(
                f"{state['P']} & {state['H']} & {float(state['objective']):.2f} & {float(interval['objective']):.2f} & "
                f"{float(prefix['objective']):.2f} & {objectives[0]:.0f} & {interval_mip['vars']}/{interval_mip['constraints']} & "
                f"{prefix_mip['vars']}/{prefix_mip['constraints']} " + r"\\"
            )
        output.extend([
            r"\bottomrule\end{tabular}}\end{table}",
            r"All 12 repaired LP and all 12 integer runs terminate optimally. Saved integer schedules pass the day-boundary hour replay.",
            r"The interval/prefix LP equality follows from telescoping with identical bounds and opening domains; equality to the stronger reset-state LP is not claimed.",
            r"The raw snapshots are \path{repaired_hour_prefix_lp_20261021.csv} and \path{repaired_hour_prefix_milp_20261021.csv}.",
        ])
    output.extend([
        r"\begin{figure}[t]\centering",
        r"\includegraphics[width=0.86\linewidth]{figures/uniform_variables_h30_20261021.png}",
        r"\caption{Uniform flexible model size at observed $H=30$, including the P=15 models.}",
        r"\end{figure}",
        r"\begin{figure}[t]\centering",
        r"\includegraphics[width=0.86\linewidth]{figures/uniform_wall_h30_20261021.png}",
        r"\caption{Uniform flexible solve time at $H=30$ on common optimal cells only (P=5 and P=10).}",
        r"\end{figure}",
    ])
    if night_rows:
        output.extend([
            r"\begin{table}[t]\centering\scriptsize",
            r"\caption{Fixed 22:00 restriction on the four P=5/10 cases, with the same 180-second limit.}",
            r"\label{tab:uniform_night}\begin{tabular}{rrllrrl}\toprule",
            r"$|P|$ & $H$ & Encoding & Status & Objective & Wall (s) & Replay \\\midrule",
        ])
        for row in sorted(night_rows, key=lambda row: (int(row["P"]), int(row["H"]), row["formulation"])):
            encoding = "Day" if row["formulation"].endswith("_day") else "Event"
            objective = f"{float(row['objective']):.0f}" if row["has_solution"] == "True" else "--"
            output.append(f"{row['P']} & {row['H']} & {encoding} & {row['status']} & {objective} & {float(row['wall_s']):.2f} & {row['replay_status'].upper()} " + r"\\")
        output.extend([r"\bottomrule\end{tabular}\end{table}", r"The nightly model is a restricted flexible model, not Khaled's daily-quota/calendar-spacing model."])
        for night in night_rows:
            flexible = next(row for row in main_rows if row["case"] == night["case"] and row["formulation"] == night["formulation"].replace("_night_", "_flexible_"))
            if night["status"] == flexible["status"] == "optimal" and float(night["objective"]) < float(flexible["objective"]) - 1e-6:
                raise ValueError("Night restriction improves a certified flexible optimum")
    if multiseed_rows:
        output.extend([
            r"\begin{table}[t]\centering\scriptsize",
            r"\caption{Uniform flexible three-seed subset: wall time as mean $\pm$ sample standard deviation, optimal runs only.}",
            r"\label{tab:uniform_seeds}\begin{tabular}{rrllr}\toprule",
            r"$|P|$ & $H$ & Encoding & Optimal / runs & Wall (s) \\\midrule",
        ])
        groups = defaultdict(list)
        for row in multiseed_rows:
            groups[row["P"], row["H"], row["formulation"]].append(row)
        for (fleet, horizon, method), rows in sorted(groups.items(), key=lambda item: (int(item[0][0]), int(item[0][1]), item[0][2])):
            times = [float(row["wall_s"]) for row in rows if row["status"] == "optimal"]
            summary = f"${statistics.mean(times):.3f}\\pm{statistics.stdev(times):.3f}$" if len(times) > 1 else "--"
            output.append(f"{fleet} & {horizon} & {'Day' if method.endswith('_day') else 'Event'} & {len(times)}/{len(rows)} & {summary} " + r"\\")
        output.extend([r"\bottomrule\end{tabular}\end{table}", r"Three seeds test limited instance variation; seed zero overlaps the six-case study and is not an additional independent sample."])
    output.extend([
        r"Raw new results use the \path{uniform_flexible_main_20261021.csv},",
        r"\path{uniform_night_subset_20261021.csv} and \path{uniform_flexible_multiseed_20261021.csv}",
        r"snapshots in \path{results/tables/}, each with saved schedules, source archive and hashed metadata.",
        r"The following 2026-10-20 tables are historical snapshots with different policies; their values are not results for these uniform encodings.",
    ])
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, default=ROOT / "results/tables/uniform_flexible_main_20261021.csv")
    parser.add_argument("--night", type=Path)
    parser.add_argument("--multiseed", type=Path)
    parser.add_argument("--prefix-lp", type=Path, default=ROOT / "results/tables/repaired_hour_prefix_lp_20261021.csv")
    parser.add_argument("--prefix-mip", type=Path, default=ROOT / "results/tables/repaired_hour_prefix_milp_20261021.csv")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main_rows = load_and_audit(args.main)
    night_rows = load_and_audit(args.night) if args.night else []
    seeds = load_and_audit(args.multiseed) if args.multiseed else []
    prefix_lp = load_and_audit(args.prefix_lp, allow_day_boundary=True)
    prefix_mip = load_and_audit(args.prefix_mip, allow_day_boundary=True)
    text = render(main_rows, night_rows, seeds, prefix_lp, prefix_mip)
    if args.output:
        args.output.write_text(text, encoding="ascii")
        plot_main(main_rows, ROOT / "results/figures/uniform_20261021")
        plot_main(main_rows, ROOT / "paper/figures")
    print(f"UNIFORM/PREFIX ARTIFACT AUDIT PASSED: {len(main_rows) + len(night_rows) + len(seeds) + len(prefix_lp) + len(prefix_mip)} rows")


if __name__ == "__main__":
    main()