================================================================================
  AIRCRAFT SCHEDULE OPTIMIZER — README
  Main script: heu180h.py
================================================================================

This document explains how to set up Python, install the required packages,
and run the program — both from the command line and from PyCharm.

--------------------------------------------------------------------------------
CONTENTS
--------------------------------------------------------------------------------
  1. Requirements
  2. Command-Line Setup (Windows)
     2a. Check Python installation
     2b. Navigate to the project folder
     2c. Create a virtual environment
     2d. Activate the virtual environment
     2e. Install required packages
     2f. Install a solver
     2g. Run the program
     2h. Deactivate the virtual environment
  3. PyCharm Setup
     3a. Open the project
     3b. Configure the Python interpreter
     3c. Install packages in PyCharm
     3d. Create a run configuration
     3e. Run the program
  4. Command Reference (all options)
  5. Notes on Solvers


================================================================================
1. REQUIREMENTS
================================================================================

  - Python 3.8 or newer
      Download from: https://www.python.org/downloads/
      During installation, check "Add Python to PATH".

  - Third-party Python packages (installed in the steps below):
      matplotlib   — for Gantt chart plots
      pandas       — for tabular output
      pyomo        — mathematical optimisation framework

  - An optimisation solver (see Section 5 for options):
      glpk    — free, open-source, recommended for beginners
      cbc     — free, open-source, alternative
      cplex   — commercial (IBM), high performance


================================================================================
2. COMMAND-LINE SETUP (WINDOWS)
================================================================================

Open a Command Prompt (cmd.exe) or PowerShell window.

------------------------------------------------------------------------
2a. Check Python installation
------------------------------------------------------------------------

Type the following and press Enter:

    py -3 --version

You should see something like:  Python 3.11.4
If you get an error, download and install Python from python.org first.

------------------------------------------------------------------------
2b. Navigate to the project folder
------------------------------------------------------------------------

    cd D:\Heuristics

(Replace the path above if you copied the project to a different location.)

------------------------------------------------------------------------
2c. Create a virtual environment
------------------------------------------------------------------------

A virtual environment keeps the packages for this project separate from
the rest of your system.

    py -3 -m venv venv

This creates a folder called "venv" inside the project directory.
You only need to do this ONCE.

------------------------------------------------------------------------
2d. Activate the virtual environment
------------------------------------------------------------------------

  Command Prompt (cmd.exe):
    venv\Scripts\activate.bat

  PowerShell:
    venv\Scripts\Activate.ps1

  (If PowerShell blocks the script, run first:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   and confirm with "Y".)

After activation you will see "(venv)" at the start of your prompt:
  (venv) f:\...\Heuristics>

------------------------------------------------------------------------
2e. Install required packages
------------------------------------------------------------------------

With the venv active, run:

    pip install matplotlib pandas pyomo

This downloads and installs all three libraries. It may take a minute.

------------------------------------------------------------------------
2f. Install a solver
------------------------------------------------------------------------

The program needs an external solver to solve MILP (integer programming)
problems.  The easiest free option is GLPK.

  Option A — GLPK via conda (if you have Anaconda/Miniconda):
    conda install -c conda-forge glpk

  Option B — GLPK pre-built binary for Windows:
    1. Download from: https://sourceforge.net/projects/winglpk/
    2. Extract the archive (e.g. to C:\glpk\).
    3. Add the folder that contains "glpsol.exe" to your PATH.
       (Search Windows for "Edit the system environment variables",
        open "Environment Variables", edit "Path", add the folder.)
    4. Restart your Command Prompt / PowerShell.
    5. Verify: glpsol --version

  Option C — CBC solver (install via conda):
    conda install -c conda-forge coincbc

  Option D — IBM CPLEX (commercial, requires a licence):
    Install CPLEX separately, then:
      pip install cplex

After installing a solver, verify it works with Pyomo:
    py -3 -c "from pyomo.opt import SolverFactory; s=SolverFactory('glpk'); print(s.available())"
Should print: True

------------------------------------------------------------------------
2g. Run the program
------------------------------------------------------------------------

Make sure the virtual environment is still active (you see "(venv)").
Make sure you are in the project folder.

-- Heuristic mode (fast, no solver needed) --

  Run on the default test file:
    py -3 heu180h.py --data DataCplex_density=1_p=10_h=7_test_0.json

  Suppress the pop-up Gantt chart:
    py -3 heu180h.py --data DataCplex_density=1_p=10_h=7_test_0.json --no-show

  Save output to a specific CSV file:
    py -3 heu180h.py --data DataCplex_density=1_p=10_h=7_test_0.json --out my_result.csv

-- MILP mode (exact optimisation, requires a solver) --

  Using GLPK:
    py -3 heu180h.py --mode milp --data DataCplex_density=1_p=10_h=7_test_0.json --solver glpk

  Using GLPK with verbose solver output:
    py -3 heu180h.py --mode milp --data DataCplex_density=1_p=10_h=7_test_0.json --solver glpk --tee

  Using CPLEX:
    py -3 heu180h.py --mode milp --data DataCplex_density=1_p=10_h=7_test_0.json --solver cplex --tee

  Test files in the inputsABCD subfolder:
    py -3 heu180h.py --mode milp --data inputsABCD\ABCD_all_checks_test.json --solver glpk --tee

-- Batch mode (run all JSON files in a folder) --

  Heuristic on all files in the Inputs folder:
    py -3 heu180h.py --mode batch --input-dir Inputs --output-dir Outputs

  Both heuristic and MILP, using GLPK:
    py -3 heu180h.py --mode batch --batch-mode both --solver glpk --input-dir Inputs --output-dir Outputs

------------------------------------------------------------------------
2h. Deactivate the virtual environment
------------------------------------------------------------------------

When you are finished, type:

    deactivate

The "(venv)" prefix disappears and you are back to the system Python.


================================================================================
3. PYCHARM SETUP
================================================================================

------------------------------------------------------------------------
3a. Open the project
------------------------------------------------------------------------

  1. Start PyCharm.
  2. On the Welcome screen click "Open".
  3. Navigate to:
       f:\Lectures\Facultative\Optimizers\Tasks\AirPortSchedules\Heuristics
  4. Click OK / Open.

------------------------------------------------------------------------
3b. Configure the Python interpreter
------------------------------------------------------------------------

  1. Go to:  File → Settings  (or  PyCharm → Preferences  on Mac)
  2. Navigate to:  Project: Heuristics → Python Interpreter
  3. Click the gear icon (top-right of the interpreter drop-down) → Add...
  4. Choose "Virtualenv Environment" → "New environment".
  5. Location: leave as the default (it will be inside the project folder).
  6. Base interpreter: select Python 3.x from the drop-down.
  7. Click OK.

PyCharm will create the venv automatically.

------------------------------------------------------------------------
3c. Install packages in PyCharm
------------------------------------------------------------------------

  Method A — using the Packages panel:
    1. In the Python Interpreter settings (from 3b), click the "+" button.
    2. Search for "matplotlib" → click "Install Package".
    3. Repeat for "pandas" and "pyomo".

  Method B — using the built-in terminal:
    1. Open the Terminal panel (View → Tool Windows → Terminal).
    2. The venv should activate automatically (you see "(venv)" in the prompt).
    3. Run:
         pip install matplotlib pandas pyomo

  For the solver, follow the same steps as Section 2f above using the
  PyCharm terminal.

------------------------------------------------------------------------
3d. Create a run configuration
------------------------------------------------------------------------

  1. Go to:  Run → Edit Configurations...
  2. Click "+" → Python.
  3. Fill in:
       Name:             heu180h heuristic
       Script path:      f:\...\Heuristics\heu180h.py
       Parameters:       --data DataCplex_density=1_p=10_h=7_test_0.json --no-show
       Working directory: f:\...\Heuristics
       Python interpreter: the venv you created in 3b
  4. Click OK.

  Create additional configurations for MILP mode by changing Parameters to:
    --mode milp --data DataCplex_density=1_p=10_h=7_test_0.json --solver glpk --tee

------------------------------------------------------------------------
3e. Run the program
------------------------------------------------------------------------

  Select the configuration from the drop-down at the top and click the
  green "Run" triangle (or press Shift+F10).

  Output appears in the "Run" panel at the bottom.
  If --no-show is not set, a Gantt chart window will pop up.


================================================================================
4. COMMAND REFERENCE (ALL OPTIONS)
================================================================================

  py -3 heu180h.py [OPTIONS]

  --mode MODE
      heuristic  (default) — fast greedy scheduler, no solver needed
      milp                 — exact integer program, requires a solver
      batch                — run all JSON files in --input-dir

  --data FILE
      Path to the JSON input file (default: data18h.json)
      Used in heuristic and milp modes.

  --input-dir DIR
      Folder containing JSON input files for batch mode (default: Inputs)

  --output-dir DIR
      Folder where batch results are written (default: Outputs)

  --batch-mode MODE
      heuristic  — only heuristic in batch
      milp       — only MILP in batch
      both       (default) — run both and compare

  --solver NAME
      cplex (default), glpk, cbc
      Only used in milp and batch modes.

  --time-limit SECONDS
      Solver time limit for MILP (default: 300)

  --tee
      Print solver log to the console (useful for debugging MILP runs)

  --out FILE
      Save output to this file (CSV for heuristic, TXT for MILP)

  --gantt FILE
      Save the Gantt chart as a PNG image to this path

  --no-show
      Do not open an interactive Gantt chart window

  --no-ferry
      Remove routing (ferry flight) constraints from the MILP

  --no-maintenance
      Remove all maintenance constraints (pure flight assignment)

  --no-overlap
      Remove pairwise time-overlap constraints from the MILP

  --no-warm-start
      Do not initialise the MILP with the heuristic solution

  --no-check-hierarchy
      Remove check hierarchy constraints from the MILP


================================================================================
5. NOTES ON SOLVERS
================================================================================

  GLPK (recommended for beginners)
    Free and open-source.
    Handles small-to-medium problems well.
    Install: see Section 2f Option A or B.
    Use with:  --solver glpk

  CBC
    Free and open-source (COIN-OR project).
    Often faster than GLPK for larger problems.
    Install: conda install -c conda-forge coincbc
    Use with:  --solver cbc

  CPLEX (IBM)
    Commercial solver — requires a paid licence or an academic licence.
    IBM offers a free academic licence via the IBM Academic Initiative.
    Very fast; recommended if you need to solve large instances.
    After installing the IBM CPLEX software, also run:
      pip install cplex
    Use with:  --solver cplex

  Checking whether a solver is found by Pyomo:
    py -3 -c "from pyomo.opt import SolverFactory; s=SolverFactory('glpk'); print('available:', s.available())"

  NOTE: The heuristic mode (--mode heuristic) does NOT need any solver.
        A solver is required only for --mode milp and --mode batch.

================================================================================
END OF README
================================================================================
