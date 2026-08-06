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

## Next execution steps
1. Compile the LaTeX draft and resolve any remaining build issues in the paper environment.
2. Consolidate the Phase-2 results into a concise summary table and interpret the practical
   performance gap between MILP and heuristics on the benchmark family.
3. Prepare a stronger exact-solver comparison on the exact-feasible subset, where MILP certification
   is more meaningful than on the larger random-grid cases.
4. Generate lower bounds or additional exact-feasible validation cases for the harder instances to
   support a quality comparison against the heuristics.
5. Conduct a sensitivity analysis on the MILP model to identify the dominant parameters that
   affect runtime and feasibility.
6. Investigate valid inequalities or reformulations that can tighten the MILP without changing the
   core modeling intent.
7. Compare the arc-based formulation against a path-based MILP formulation to assess whether the
   alternative structure delivers a meaningful performance gain.