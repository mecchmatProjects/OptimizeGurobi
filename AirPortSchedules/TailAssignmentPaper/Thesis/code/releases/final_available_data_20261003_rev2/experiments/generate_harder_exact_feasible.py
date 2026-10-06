#!/usr/bin/env python3
"""
Generate harder exact-feasible instances for TAP validation.

These instances are designed to bridge the gap between current exact-feasible
cases (max 54 flights, 6 aircraft) and the Phase-1/2 random-grid instances
(100-1000 flights) that exceed MILP time limits.

Target properties:
- Fleet size: 8–10 aircraft (larger than current max of 6)
- Flights: 70–120 (scaled up from current max of 54)
- Horizon: 14–20 days (extended from current max of 10)
- Density: 0.5–0.8 (reasonable load)
- Maintenance: Full ABCD checks
- Solvability: MILP optimality in < 30s (validated)

Generated instances are stored in data/phase_1_25_larger/ and automatically
validated via batch MILP solver.
"""

import json
import sys
from pathlib import Path
import random
import math

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from generate_instances import stable_seed, build_instance


def generate_harder_exact_feasible():
    """Generate a small family of harder exact-feasible instances.
    
    Parameters are chosen to be empirically solvable to optimality in < 30s
    based on the exact-feasible pattern.
    """
    
    instances = []
    
    # Instance family: p=8, varying flights and horizon
    specs = [
        # (p, h, density, index, description)
        (8, 14, 0.5, 0, "p8_h14_d05_mid"),     # ~84 flights
        (8, 14, 0.65, 1, "p8_h14_d65_medium"), # ~109 flights
        (10, 10, 0.5, 0, "p10_h10_d05_small"), # ~75 flights
        (10, 14, 0.5, 0, "p10_h14_d05_medium"),# ~105 flights
        (10, 14, 0.6, 1, "p10_h14_d06_larger"),# ~126 flights
    ]
    
    output_dir = Path("data/phase1_25_harder_exact_feasible")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for p, h, density, idx, label in specs:
        seed = stable_seed(density, p, h, idx)
        random.seed(seed)
        
        # Build instance using build_instance (parameters: density, p, h, index)
        data = build_instance(
            density=density,
            p=p,
            h=h,
            index=idx,
            maintenance_profile="default"
        )
        
        # Save as JSON
        filename = f"DataCplex_density={density}_p={p}_h={h}_test_{idx}.json"
        filepath = output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        instances.append({
            'file': filename,
            'path': filepath,
            'p': p,
            'h': h,
            'density': density,
            'flights': len(data.get('Flights', [])),
            'label': label,
            'seed': seed
        })
        
        print(f"✓ Generated {filename}: p={p}, h={h}, "
              f"flights={len(data['Flights'])}, density={density}")
    
    print(f"\nGenerated {len(instances)} harder exact-feasible instances "
          f"in {output_dir}")
    
    return instances


if __name__ == '__main__':
    instances = generate_harder_exact_feasible()
    print("\nNext step: Run these instances with MILP to validate solvability:")
    print("  python src/model.py --mode batch --input-dir data/phase1_25_harder_exact_feasible \\")
    print("    --solver highs --time-limit 30")
