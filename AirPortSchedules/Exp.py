import heapq
from collections import defaultdict, OrderedDict


def time_str_to_minutes(time_str: str) -> int:
    """Converts HH:MM string to minutes since midnight."""
    hour, minute = map(int, time_str.split(":"))
    return hour * 60 + minute

class Scheduler:
    def __init__(self, starts, ends, day_start=0, day_end=1440):
        self.starts = starts
        self.ends = []
        for x,y in zip(starts, ends):
            if y < x:
                self.ends.append(y + 24 * 60)
            else:
                self.ends.append(y)
            print(x,y)

        self.day_start = day_start
        self.day_end = day_end
        self.day_length = 24 * 60

    def schedule_one_day(self) -> dict[int, int]:
        """
        Do the scheduling for the first day only
        """
        return self.shifts_assign_day(self.starts, self.ends)
    def shifts_assign_day(self, starts, ends):
        intervals = sorted(enumerate(zip(starts, ends)), key=lambda x: x[1][0])
        print(intervals)
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
            print(heap)
        #
        # for i in range(next_worker_id):
        #     for j,c in enumerate(result):
        #         if c==i:
        #             print(intervals[j][0], intervals[j][1],end=" ")
        #     print()
        print(result)

        res = []
        for i,v in sorted(result.items()):
            res.append(v)

        X = list(enumerate(zip(starts, ends)))

        for i in range(next_worker_id):
            for j,c in enumerate(res):
                if c==i:
                    print(X[j][0], X[j][1],end=" ")
            print()
        return res

    def build_multi_day_schedule0(self):
        day_offset = 24 * 60
        n = len(self.starts)

        # Day 2 starts and ends offset by 24h
        day_starts2 = [s + day_offset for s in self.starts]
        day_ends2 = [e + day_offset for e in self.ends]

        # Assign workers for day 2 only
        day_assignment = self.shifts_assign_day(day_starts2, day_ends2)

        # Assign workers for full 2-day range
        day_assignment2 = self.shifts_assign_day(self.starts + day_starts2, self.ends + day_ends2)
        print("DA2", day_assignment2)

        # Extract assignments for each shift
        first_day = day_assignment2[:n]
        second_day = day_assignment2[n:]

        print(first_day, second_day)

        # Create permutation from worker indices day 1 -> day 2
        mapping = {}
        for i in range(n):
            mapping[first_day[i]] = second_day[i]

        print(mapping)
        # Detect permutation cycle
        visited = set()
        cycles = []
        for start in mapping:
            if start not in visited:
                current = start
                cycle = []
                while current not in visited:
                    visited.add(current)
                    cycle.append(current)
                    current = mapping[current]
                cycles.append(cycle)

        print(cycles)
        # Calculate length of the permutation cycle (LCM of individual cycle lengths)
        from math import lcm
        period = 1
        for cycle in cycles:
            period = lcm(period, len(cycle))

        # Now build full schedule for required number of days
        schedule = {}
        for day in range(period):
            offset = day * day_offset
            shifted_starts = [s + offset for s in self.starts]
            shifted_ends = [e + offset for e in self.ends]
            assignment = self.shifts_assign_day(shifted_starts, shifted_ends)
            for idx, worker in enumerate(assignment):
                shift_id = idx + day * n
                schedule[shift_id] = {"day": day + 1, "worker": worker}

        print(schedule)
        return schedule


    def build_multi_day_schedule(self, period=3):
        day_offset = 24 * 60
        n = len(self.starts)

        # Day 1 and Day 2 assignments
        day_starts2 = [s + day_offset for s in self.starts]
        day_ends2 = [e + day_offset for e in self.ends]

        day_assignment = self.shifts_assign_day(self.starts, self.ends)
        day_assignment2 = self.shifts_assign_day(self.starts + day_starts2, self.ends + day_ends2)[n:]

        print(day_assignment, day_assignment2)
        # Build permutation: maps Day 1 shift index -> Day 2 shift index
        num_worker = set(day_assignment)
        m = len(num_worker)
        perm = [None] * m
        for worker1, worker in zip(day_assignment2,day_assignment):
            if perm[worker] is None:
                perm[worker] = worker1
            else:
                if perm[worker]!= worker1:
                    print("!!", worker, perm[worker],worker1)

        print(perm)
        # Extract cycles from permutation
        visited = [False] * m
        cycles = []

        for i in range(m):
            if not visited[i]:
                cycle = []
                current = i
                while not visited[current]:
                    visited[current] = True
                    cycle.append(current)
                    current = perm[current]
                cycles.append(cycle)

        print(cycles)
        # Build schedule from cycles
        result = {'bus_rotation_plan': []}

        buses = list(range(m))
        for day in range(period):

            bus_shifts_map = defaultdict(list)
            for shift_index, bus_id in enumerate(day_assignment):
                bus_shifts_map[buses[bus_id]].append(shift_index)

            # bus_shifts_map = sorted(bus_shifts_map.items())
            bus_shifts = []
            for k, v in sorted(bus_shifts_map.items()):
                bus_shifts.append({'bus_id': k, 'shifts': v})
            print(bus_shifts)

            for i in range(m):
                buses[i] = perm[buses[i]]
            print(buses)

            result['bus_rotation_plan'].append({'day_number': day + 1, 'bus_shifts': bus_shifts})

        print(result)
        return result


start_times = ["03:05", "11:20", "13:35", "20:35","22:35", "04:20", "09:20", "16:20","19:50","04:35"]
end_times =   ["09:55", "20:25", "19:30", "04:05","04:35", "13:10", "15:55", "22:20","03:05","10:55"]

starts = [60, 180, 300]
ends   = [120, 240, 360]

starts = [time_str_to_minutes(t) for t in start_times]
ends   = [time_str_to_minutes(t) for t in end_times]

scheduler = Scheduler(starts, ends, day_start=0, day_end=1440)
result1 = scheduler.schedule_one_day()
print(result1)

input()
result2 = scheduler.build_multi_day_schedule()


from pprint import pprint
print("day1:")
pprint(result1)
print()
pprint(result2)
