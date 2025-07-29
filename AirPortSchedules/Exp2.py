import heapq
from collections import defaultdict

def time_str_to_minutes(time_str: str) -> int:
    """Converts HH:MM string to minutes since midnight."""
    hour, minute = map(int, time_str.split(":"))
    return hour * 60 + minute

class Scheduler:
    def __init__(self, starts, ends, day_start=0, day_end=1440):
        self.starts = starts
        self.ends = ends
        self.day_start = day_start
        self.day_end = day_end
        self.day_length = day_end - day_start

    def shifts_assign_day(self, starts, ends):
        intervals = sorted(enumerate(zip(starts, ends)), key=lambda x: x[1][0])
        heap = []
        result = {}
        next_worker_id = 0

        for index, (start, end) in intervals:
            if heap and heap[0][0] <= start:
                _, worker_id = heapq.heappop(heap)
            else:
                worker_id = next_worker_id
                next_worker_id += 1

            result[index] = worker_id
            heapq.heappush(heap, (end, worker_id))

        return result  # shift_id → bus_id

    def shifts_assign_day_with_carry(self, starts, ends, previous_bus_last_ends=None):
        """
        Assign shifts (start, end) to buses.
        If previous_bus_last_ends is given, prevent reusing a bus if it's still busy.
        """
        intervals = sorted(enumerate(zip(starts, ends)), key=lambda x: x[1][0])
        heap = []
        result = {}
        next_worker_id = 0

        if previous_bus_last_ends:
            # preload heap with busy buses from previous day
            for bus_id, end_time in previous_bus_last_ends.items():
                heapq.heappush(heap, (end_time, bus_id))

        for index, (start, end) in intervals:
            while heap and heap[0][0] <= start:
                heapq.heappop(heap)  # free up buses whose shift is finished

            # Check if any worker is now available
            available_bus_ids = [bus_id for (et, bus_id) in heap if et <= start]

            if available_bus_ids:
                bus_id = available_bus_ids[0]
                heap = [(et, bid) for (et, bid) in heap if bid != bus_id]  # remove used
            else:
                bus_id = next_worker_id
                next_worker_id += 1

            result[index] = bus_id
            heapq.heappush(heap, (end, bus_id))

        return result

    def build_multi_day_schedule_via_permutation(self):
        day1_assignments = self.shifts_assign_day(self.starts, self.ends)

        # Build bus_last_ends dict from Day 1
        bus_last_ends = {}
        for shift_id, bus_id in day1_assignments.items():
            bus_last_ends[bus_id] = max(bus_last_ends.get(bus_id, 0), self.ends[shift_id])

        print(day1_assignments)

        # Shift Day 2
        offset = self.day_length
        starts2 = [s + offset for s in self.starts]
        ends2 = [e + offset for e in self.ends]

        day2_assignments = self.shifts_assign_day_with_carry(
            starts2, ends2, previous_bus_last_ends=bus_last_ends
        )

        print(day2_assignments)

        # Create permutation π: bus_day2 = π[bus_day1]
        n_shifts = len(self.starts)
        bus_day1 = [day1_assignments[i] for i in range(n_shifts)]
        bus_day2 = [day2_assignments[i] for i in range(n_shifts)]

        max_bus_id = max(bus_day1 + bus_day2) + 1
        permutation = [None] * max_bus_id  # π[bus_id] = new_bus_id

        for b1, b2 in zip(bus_day1, bus_day2):
            permutation[b1] = b2

        # Fill identity for unused buses
        for i in range(len(permutation)):
            if permutation[i] is None:
                permutation[i] = i

        # Find permutation cycle length
        def apply_permutation(p, k):
            result = list(range(len(p)))
            for _ in range(k):
                result = [p[i] for i in result]
            return result

        seen = {}
        current = list(range(len(permutation)))
        for k in range(1, 100):  # limit to 100 just in case
            current = [permutation[i] for i in current]
            frozen = tuple(current)
            if frozen in seen:
                cycle_length = k - seen[frozen]
                break
            seen[frozen] = k
        else:
            cycle_length = 1  # fallback if cycle not found

        # Generate rotation plan using the permutation cycle
        plan = []
        current_bus_ids = bus_day1.copy()  # initial bus assignments

        for day in range(cycle_length):
            bus_to_shifts = defaultdict(list)
            for shift_id, bus_id in enumerate(current_bus_ids):
                bus_to_shifts[bus_id].append(shift_id)

            bus_shifts = []
            for bus_id, shifts in bus_to_shifts.items():
                bus_shifts.append({
                    "busId": bus_id,
                    "shifts": shifts
                })

            plan.append({
                "dayNumber": day + 1,
                "busShifts": bus_shifts
            })

            # Apply permutation to get bus assignment for next day
            current_bus_ids = [permutation[b] for b in current_bus_ids]

        return {"busRotationPlan": plan}

class Scheduler2:
    def __init__(self, starts, ends, day_start=0, day_end=1440):
        self.starts = starts
        self.ends = ends
        self.day_start = day_start
        self.day_end = day_end
        self.day_length = day_end - day_start

    def shifts_assign_day_with_blocking(self, starts, ends, previous_bus_last_ends=None):
        intervals = sorted(enumerate(zip(starts, ends)), key=lambda x: x[1][0])
        heap = []  # stores (end_time, bus_id)
        result = {}
        next_worker_id = 0

        busy_until = dict(previous_bus_last_ends) if previous_bus_last_ends else {}

        for index, (start, end) in intervals:
            # Free up buses that finished before this shift starts
            reusable = [
                bus_id for bus_id, until in busy_until.items() if until <= start
            ]

            if reusable:
                bus_id = reusable[0]
            else:
                bus_id = next_worker_id
                next_worker_id += 1

            result[index] = bus_id
            busy_until[bus_id] = end

        return result, busy_until

    def build_multi_day_schedule_via_permutation(self):
        n_shifts = len(self.starts)

        # Day 1 assignment
        shift_to_bus_day1, bus_ends_day1 = self.shifts_assign_day_with_blocking(
            self.starts, self.ends
        )
        bus_day1 = [shift_to_bus_day1[i] for i in range(n_shifts)]

        # Day 2 assignment — shifted in time, block reuse of Day 1 buses still working
        starts2 = [s + self.day_length for s in self.starts]
        ends2 = [e + self.day_length for e in self.ends]
        shift_to_bus_day2, _ = self.shifts_assign_day_with_blocking(
            starts2, ends2, previous_bus_last_ends=bus_ends_day1
        )
        bus_day2 = [shift_to_bus_day2[i] for i in range(n_shifts)]

        # Normalize bus ids to match shift positions
        # We want: π[bus_day1[i]] == bus_day2[i]
        max_bus_id = max(bus_day1 + bus_day2) + 1
        permutation = [None] * max_bus_id

        for b1, b2 in zip(bus_day1, bus_day2):
            permutation[b1] = b2

        # Fill in identity for unused
        for i in range(max_bus_id):
            if permutation[i] is None:
                permutation[i] = i

        # Detect permutation cycle length
        def apply_perm(p, x):
            return [p[i] for i in x]

        seen = {}
        current = list(range(max_bus_id))
        for k in range(1, 100):  # cap at 100
            current = apply_perm(permutation, current)
            frozen = tuple(current)
            if frozen in seen:
                cycle_length = k - seen[frozen]
                break
            seen[frozen] = k
        else:
            cycle_length = 1

        # Build the rotation plan for cycle_length days
        plan = []
        current_bus_ids = bus_day1.copy()

        for day in range(cycle_length):
            bus_to_shifts = defaultdict(list)
            for shift_id, bus_id in enumerate(current_bus_ids):
                bus_to_shifts[bus_id].append(shift_id)

            day_entry = {
                "dayNumber": day + 1,
                "busShifts": [
                    {"busId": bus_id, "shifts": shift_ids}
                    for bus_id, shift_ids in sorted(bus_to_shifts.items())
                ]
            }
            plan.append(day_entry)

            # Advance to next day by applying the permutation
            current_bus_ids = [permutation[b] for b in current_bus_ids]

        return {"busRotationPlan": plan}



import itertools

def assign_workers(starts, ends):
    n = len(starts)
    intervals = []

    for i in range(n):
        start = starts[i]
        end = ends[i]
        if end <= start:  # overnight shift
            end += 1440
        intervals.append((start, end, i))

    intervals.sort()  # sort by start time

    workers = []  # list of lists of shift indices

    for start, end, idx in intervals:
        placed = False
        for worker in workers:
            # Check if last assigned shift of this worker does not overlap
            last_idx = worker[-1]
            last_start, last_end = starts[last_idx], ends[last_idx]
            if last_end <= last_start:
                last_end += 1440
            if last_end <= start or end <= last_start:
                worker.append(idx)
                placed = True
                break
        if not placed:
            workers.append([idx])

    # Create result dictionary
    result = {}
    for i, shifts in enumerate(workers, start=1):
        result[i] = shifts

    return result


def build_multi_day_schedule(starts, ends, day_start=0, day_end=1440):
    # Normalize overnight shifts
    for i in range(len(starts)):
        if ends[i] <= starts[i]:
            ends[i] += 1440  # overnight shift

    day_minutes = day_end - day_start

    # Assign Day 1 workers
    assignments_day1 = assign_workers(starts, ends)
    print(assignments_day1)
    day1_shift_to_worker = {i: a[2] for i, a in enumerate(assignments_day1)}
    print(day1_shift_to_worker)

    # Shift everything to Day 2
    starts_day2 = [s + day_minutes for s in starts]
    ends_day2 = [e + day_minutes for e in ends]
    assignments_day2 = assign_workers(starts_day2, ends_day2)
    day2_shift_to_worker = {i: a[2] for i, a in enumerate(assignments_day2)}

    print(day2_shift_to_worker)

    # Build permutation from day1 to day2
    n = len(starts)
    perm = [day2_shift_to_worker[i] for i in range(n)]

    print(perm)
    #
    # # Cycle detection
    # seen = {}
    # cycles = []
    # for i, val in enumerate(perm):
    #     if i not in seen:
    #         cycle = []
    #         j = i
    #         while j not in seen:
    #             seen[j] = True
    #             cycle.append(j)
    #             j = perm[j] - 1  # minus 1 to use 0-based indexing
    #         if cycle:
    #             cycles.append(cycle)
    #
    # # Build schedule based on permutation cycle
    # bus_rotation_plan = []
    # for day_index in range(len(cycles[0])):  # smallest cycle length
    #     day_shifts = defaultdict(list)
    #     for i, (_, _, w) in enumerate(assignments_day1):
    #         shift_id = i + 1
    #         worker = cycles[0][(cycles[0].index(i) + day_index) % len(cycles[0])] + 1
    #         day_shifts[worker].append(shift_id)
    #     day_plan = {
    #         "dayNumber": day_index + 1,
    #         "busShifts": [{"busId": w, "shifts": sorted(s)} for w, s in day_shifts.items()]
    #     }
    #     bus_rotation_plan.append(day_plan)
    #
    # return {"busRotationPlan": bus_rotation_plan}


starts = [60, 180, 300]
ends   = [120, 240, 360]


start_times = ["03:05", "11:20", "13:35", "20:35","22:35", "04:20", "09:20", "16:20","19:50","04:35"]
end_times =   ["09:55", "20:25", "19:30", "04:05","04:35", "13:10", "15:55", "22:20","03:05","10:55"]

starts = [60, 180, 300]
ends   = [120, 240, 360]

starts = [time_str_to_minutes(t) for t in start_times]
ends   = [time_str_to_minutes(t) for t in end_times]


scheduler = Scheduler2(starts, ends, day_start=0, day_end=1440)
result = scheduler.build_multi_day_schedule_via_permutation()

from pprint import pprint
pprint(result)



start_times = ["03:05", "11:20", "13:35", "20:35","22:35", "04:20", "09:20", "16:20","19:50","04:35"]
end_times   = ["09:55", "20:25", "19:30", "04:05","04:35", "13:10", "15:55", "22:20","03:05","10:55"]

def time_str_to_minutes(s):
    h, m = map(int, s.split(":"))
    return h * 60 + m

starts = [time_str_to_minutes(t) for t in start_times]
ends   = [time_str_to_minutes(t) for t in end_times]

schedule = build_multi_day_schedule(starts, ends)