# Updated execution roadmap

## Completed or in progress
1. Finalize and classify the 25 benchmark instances into easy, medium, and hard categories, with
   documented reasoning and a structured Phase-1 matrix.
2. Extend the benchmark workflow so the MILP and heuristic methods are evaluated on the same
   instance family and report a consistent set of outcomes.
3. Add and validate a new bounded local-search refinement for the heuristic pipeline, then wire it
   into the batch benchmark flow.
4. Run the full Phase-2 comparison over the 25-instance suite and capture the resulting benchmark
   evidence for the paper.
5. Polish the manuscript narrative in the paper draft so the computational results are presented as
   a coherent report with the relevant tables and figures embedded in the analysis.
6. Compile the LaTeX draft and resolve overfull hbox issues; paper now builds cleanly at ~708 KB.
7. Consolidate the Phase-2 results into a full 25-instance summary table (tab:phase2_full) and
   interpret the practical performance gap: LS heuristic improves greedy by mean 12.7% on all 25
   instances; MILP blocked by solver-limit on all 25 random-grid cells.
8. Prepare exact-feasible comparison (subsec:exact_feasible_comp, tab:exact_feasible_comp) across
   9 carefully selected instances (6 constructive + 5 curated ABCD test cases). All instances solve
   to optimality via Integrated MILP (runtime 1.8–21.4s). Heuristic gaps range 0% (trivial instances)
   to 345% (tight capacity, unassigned flights). Key finding: MILP certification achieves full
   maintenance-compliant optimality; greedy heuristic lacks conflict resolution for partial assignments.
9. Generate LP relaxation lower bounds (subsec:lp_lower_bounds, tab:lp_lower_bounds) for exact-feasible
   instances and Phase-1 random-grid samples. LP bounds are computed by relaxing all binary variables
   to continuous [0,1] domain and solving the resulting continuous LP. Key findings: (a) LP relaxations
   solve instantly (<0.01s) even on 64-flight instances with 42K constraints; (b) Integrality gaps are
   small (0–13%) on exact-feasible instances; (c) Heuristic gap to LP bound quantifies solution quality
   even when MILP hits time limit; (d) Greedy on capacity-bottleneck instance is 362% above LP bound,
   while trivial instances achieve LP bound. LP bounds serve as rigorous lower bounds for heuristic
   quality assessment on larger Phase-1/2 instances.

## Next execution steps

5. Conduct a sensitivity analysis on the MILP model to identify the dominant parameters that
   affect runtime and feasibility.
   
6. Compare the arc-based formulation against a path-based MILP formulation to assess whether the
   alternative structure delivers a meaningful performance gain.
7. Investigate valid inequalities or reformulations that can tighten the MILP without changing the
   core modeling intent. For long horizons, the biggest gains are likely from reachability preprocessing + maintenance-window / interval cuts + strong trigger/start/arc linking, not from generic solver cuts alone; Al-Thani et al. explicitly propose graph reduction and valid inequalities for OAMRP solvability13, Maher et al. show that look-ahead maintenance constraints reduce future maintenance misalignment, and recent combinatorial Benders work reports that valid inequalities improve convergence and that ILP performance improves when these inequalities are embedded.


For the step 7 - check this table

   Priority Inequality / strengthening family Expected impact  Implementation complexity
1 Reachability preprocessing and arc elimination: remove infeasible flight, ground, maintenance, and maintenance-link arcs before model build Very high: directly reduces 2M variables Medium
2 Maintenance prefix / cumulative-utilization cuts by tail and check type Very high: attacks weak fractional trigger/start LPs Medium
3 Maintenance-window / interval-cover cuts using only feasible starts that can actually reset the aircraft High: stronger than simple spacing Medium
4 Trigger–start–maintenance-arc equalities and disaggregated linking High: removes weak big-M behavior Low–medium
5 No-flight-during-maintenance conflict cliques High when maintenance duration is long or multi-day Low
6 Maintenance-capacity lifted cover cuts at station-day and station-interval level High when capacity is binding Medium
7 Station/time cutset and aircraft-count cuts Medium–high: improves flow LP bound Medium
8 Look-ahead / rolling-window maintenance route cuts Medium–high for 180-day horizons Medium–high
9 Symmetry breaking for truly identical tails Medium; can be high for homogeneous subfleets Low–medium
10 Lazy combinatorial Benders / no-good feasibility cuts from infeasible maintenance substructures High in hard nodes; more engineering High