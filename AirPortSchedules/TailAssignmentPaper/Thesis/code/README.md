# Tail Assignment Thesis Package (Portable)

This folder is a clean, portable package of the code and thesis sources used for thesis creation.

## 1) What is included

- `src/`: Core Tail Assignment implementation (MILP + heuristics) in Pyomo.
- `experiments/`: Reproducibility and analysis scripts used for thesis tables/figures.
- `tests/`: Validation test suite.
- `data/` and `data_test/`: Input instances used by experiments and sanity checks.
- `results/reference/`: Baseline reference table(s) for comparison.
- `results/tables/`: Generated and validated table outputs used in analysis.
- `results/figures/`: Generated figures from computational experiments.
- `Thesis/`: Thesis LaTeX source (`main.tex`, sections, bibliography).
- `paper/figures/`: Figure assets referenced from thesis chapters.
- `docs/`: Mathematical derivations and reproducibility notes.
- `requirements.txt`: Python dependencies.

## 2) What this package can do

- Run heuristic aircraft-tail assignment with or without ferry legs.
- Run MILP optimization with maintenance constraints and model switches.
- Run batch experiments over instance folders.
- Reproduce key computational outputs used in thesis chapters.
- Validate behavior with automated tests.
- Compile thesis LaTeX to PDF.

## 3) Minimum requirements on another device

- Python 3.10+ (3.12 recommended)
- A MILP solver for exact mode:
  - Preferred: CPLEX (full license)
  - Alternatives for many workflows: HiGHS (`highspy`), CBC, GLPK
- TeX distribution for thesis PDF build:
  - TeX Live or MiKTeX
  - `latexmk` recommended

## 4) Setup on a new device

### Windows PowerShell

1. Open PowerShell in this `Thesis/code` folder.
2. Create and activate virtual environment:

   `py -3 -m venv .venv`

   `.\.venv\Scripts\Activate.ps1`

3. Install dependencies:

   `python -m pip install --upgrade pip`

   `python -m pip install -r requirements.txt`

### macOS/Linux

1. Open terminal in this `Thesis/code` folder.
2. Create and activate virtual environment:

   `python3 -m venv .venv`

   `source .venv/bin/activate`

3. Install dependencies:

   `python -m pip install --upgrade pip`

   `python -m pip install -r requirements.txt`

## 5) Run the application

### A) Heuristic mode (no MILP solver required)

`python src/model.py --mode heuristic --data data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json --out Outputs/heuristic_schedule.csv --no-show`

Expected:
- A complete or partial schedule CSV
- Event report text output
- Console summary with objective/cost information

### B) MILP mode (solver required)

`python src/model.py --mode milp --data data/instances/DataCplex_density=0.5_p=10_h=7_test_0.json --solver cplex --time-limit 60 --out Outputs/milp_summary.txt --no-show`

If CPLEX preview/restricted license is installed, large instances may fail with size-limit errors. In that case:
- Use smaller instances for smoke checks, or
- Switch solver for supported workflows (for example `--solver highs` where applicable), or
- Use full CPLEX license for full-scale thesis replication.

### C) Batch mode

`python experiments/run_batch.py --mode both --solver cplex --time-limit 300 --input-dir data/instances --output-dir results/tables --label portable_run`

## 6) Validation

Run all tests:

`python -m pytest tests -v --tb=short`

## 7) Reproduce thesis-related outputs

Examples:

- Reproduce reference tables subset:

  `python experiments/reproduce_tables.py --table 5 --quick --solver cplex`

- Generate strengthening figures required by Chapter 6:

  `python experiments/plot_step7_strengthening.py`

This script writes Chapter 6 figure files into `Thesis/figures/`.

## 8) Compile Thesis LaTeX to PDF

The thesis source entry point is:
- `Thesis/main.tex`

### Recommended build (latexmk)

From `Thesis/code`:

`cd Thesis`

`latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`

Output:
- `Thesis/main.pdf`

### Manual build sequence (fallback)

From `Thesis/code/Thesis`:

1. `pdflatex -interaction=nonstopmode main.tex`
2. `bibtex main`
3. `pdflatex -interaction=nonstopmode main.tex`
4. `pdflatex -interaction=nonstopmode main.tex`

## 9) Notes on figures and paths

- Chapter 6 uses `Thesis/figures/strength_*.png`.
  - If missing, run `python experiments/plot_step7_strengthening.py` from `Thesis/code`.
- Chapter 8 references assets under `paper/figures/`.
  - This package already includes `paper/figures` for those references.

## 10) Recommended run order on a fresh machine

1. Install Python dependencies.
2. Run `python -m pytest tests -v --tb=short`.
3. Run heuristic smoke check.
4. Run MILP smoke check on small instance.
5. Generate chapter-specific figures if needed.
6. Compile thesis PDF.

## 11) Folder intent

This `Thesis/code` folder is intended to be copied as-is to another machine and used independently from the original repository root.