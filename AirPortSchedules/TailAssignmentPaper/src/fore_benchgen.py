"""Application-facing API for the certified synthetic TAP benchmark generator.

The implementation remains in ``Thesis.fore_benchgenv2`` during the staged
migration. New application, test, and experiment code must import this module
so the implementation can be relocated without changing public callers.
"""

from fore_benchgen_impl import (
    Config,
    PRESETS,
    benchmark,
    compute_metrics,
    export,
    generate,
    main,
    perturb,
    plant_optimum,
    preset,
    solution_pool,
    validate,
)

__all__ = [
    "Config",
    "PRESETS",
    "benchmark",
    "compute_metrics",
    "export",
    "generate",
    "main",
    "perturb",
    "plant_optimum",
    "preset",
    "solution_pool",
    "validate",
]


if __name__ == "__main__":
    raise SystemExit(main())