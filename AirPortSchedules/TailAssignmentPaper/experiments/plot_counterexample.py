import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Setup matplotlib style
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']

# Data
days = [1, 2, 3, 4]
v_jd = [0, 10, 0, 10]
h_jd = [0, 10, 10, 20]

# Create figure
fig, ax = plt.subplots(figsize=(6.5, 4.0), constrained_layout=True)

# 1. Bar plot for daily flight time v_jd
# Using a slate color (#64748b) for the daily flight time
bars = ax.bar(days, v_jd, width=0.4, color='#64748b', alpha=0.7, edgecolor='#475569', label=r'Daily flight time $v_{jd}$')

# 2. Line plot with markers for exact cumulative state h_jd
# Using a nice dark teal (#155e75) for the cumulative state
line = ax.plot(days, h_jd, color='#155e75', marker='o', markersize=8, linewidth=2, label=r'Cumulative state $h_{jd}$')

# 3. Horizontal dashed threshold line T_max = 10
ax.axhline(10, color='#dc2626', linestyle='--', linewidth=1.5, label=r'Threshold $T_{\max} = 10$')

# 4. Maintenance-night markers at days 1 and 4
ax.axvline(1, color='#16a34a', linestyle=':', linewidth=2, label='Maintenance night')
ax.axvline(4, color='#16a34a', linestyle=':', linewidth=2)

# Styling and labels
ax.set_xlabel('Day', fontsize=11, labelpad=8)
ax.set_ylabel('Hours', fontsize=11, labelpad=8)
ax.set_xticks(days)
ax.set_yticks(range(0, 25, 5))
ax.set_ylim(-1, 23)

ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(frameon=False, loc='upper left', fontsize=10)
ax.set_title('Four-day counterexample timeline', fontsize=12, fontweight='bold', pad=12)

# Save figure
output_path = Path('paper/figures/c11_counterexample_timeline.png')
output_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(output_path, dpi=220)
plt.close(fig)

print(f"Successfully generated counterexample plot at {output_path.resolve()}")
