import re
import matplotlib.pyplot as plt
from collections import defaultdict

# Example:
# [INFO] (CLOCK) @ 3423771: Node 3 clock drift before correction: 225, after correction: 215,

log_file = "results\\16_05_2026_17_33\\simulation.log"

# Regex that supports negative values
pattern = re.compile(
    r'@\s*(\d+):\s*Node\s+(\d+)\s+clock drift before correction:\s*(-?\d+),\s*after correction:\s*(-?\d+)'
)

# Store data per node
node_data = defaultdict(lambda: {
    "time": [],
    "before": [],
    "after": []
})

with open(log_file, "r") as f:
    for line in f:
        match = pattern.search(line)
        if match:
            true_time = int(match.group(1)) / 3600_000
            node_id = int(match.group(2))
            before = int(match.group(3))
            after = int(match.group(4))

            node_data[node_id]["time"].append(true_time)
            node_data[node_id]["before"].append(before)
            node_data[node_id]["after"].append(after)

# Plot
plt.figure(figsize=(12, 7))

for node_id, data in sorted(node_data.items()):

    # Before correction
    # plt.plot(
    #     data["time"],
    #     data["before"],
    #     linestyle='-',
    #     marker='o',
    #     label=f'Node {node_id} Before'
    # )

    # After correction
    plt.plot(
        data["time"],
        data["after"],
        linestyle='--',
        marker='x',
        label=f'Node {node_id} After'
    )

plt.axhline(0, color='black', linewidth=1)

plt.xlabel("True Time")
plt.ylabel("Clock Drift")
plt.title("Clock Drift Before vs After Correction")
plt.grid(True)
plt.legend(ncol=2)
plt.tight_layout()

plt.show()