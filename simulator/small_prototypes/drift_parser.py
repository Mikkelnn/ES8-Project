import re
import matplotlib.pyplot as plt
from collections import defaultdict

# Example:
# [INFO] (CLOCK) @ 3423771: Node 3 clock drift before correction: 225, after correction: 215,

# log_file = "results/18_05_2026_09_23/simulation.log"
# log_file = "results\\18_05_2026_15_55\\simulation.log"
log_file = "results\\18_05_2026_22_00\\simulation.log"

# Regex that supports negative values
pattern = re.compile(
    r'@\s*(\d+):\s*Node\s+(\d+)\s+clock drift before correction:\s*(-?\d+),\s*after correction:\s*(-?\d+),\s*after with trend estimate:\s*(-?\d+)'
)

# Store data per node
node_data = defaultdict(lambda: {
    "time": [],
    "before": [],
    "after": [],
    "diff": [],
    "trend": []
})

with open(log_file, "r") as f:
    for line in f:
        match = pattern.search(line)
        if match:
            true_time = int(match.group(1)) / 3600_000
            node_id = int(match.group(2))
            before = int(match.group(3))
            after = int(match.group(4))
            trend = int(match.group(5))

            node_data[node_id]["time"].append(true_time)
            node_data[node_id]["before"].append(before)
            node_data[node_id]["after"].append(after)
            node_data[node_id]["diff"].append(before - after)
            node_data[node_id]["trend"].append(trend)

# Plot
fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

# Use consistent colors for each node
colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

for idx, (node_id, data) in enumerate(sorted(node_data.items())):
    color = colors[idx % len(colors)]

    # -------- BEFORE --------
    axes[0].plot(
        data["time"],
        data["diff"],
        linestyle='-',
        marker='o',
        color=color,
        label=f'Node {node_id}'
    )

    # -------- AFTER --------
    axes[1].plot(
        data["time"],
        data["after"],
        linestyle='--',
        marker='x',
        color=color,
        label=f'Node {node_id}'
    )

    # -------- TREND --------
    axes[2].plot(
        data["time"],
        data["trend"],
        linestyle='--',
        marker='x',
        color=color,
        label=f'Node {node_id}'
    )

# Formatting
for ax in axes:
    ax.axhline(0, color='black', linewidth=1)
    ax.set_ylabel("Clock Drift")
    ax.grid(True)
    ax.legend(ncol=2)

axes[0].set_title("Correction")
axes[1].set_title("After Correction")
axes[2].set_title("With trend adjust")
axes[-1].set_xlabel("True Time")

plt.tight_layout()
plt.show()