import json
import sys

import matplotlib.patches as patches
import matplotlib.pyplot as plt

# Get map filename from args or use default
map_file = sys.argv[1] if len(sys.argv) > 1 else "maps/intersection.json"
plot_gateways = "--no-gateways" not in sys.argv

# Load the JSON file
with open(map_file, "r") as f:
    data = json.load(f)

nodes = data["nodes"]

# Create figure
fig, ax = plt.subplots(figsize=(12, 8))

# Draw neighbor connections first (so they appear behind nodes)
for node_id, node_info in nodes.items():
    x1, y1 = node_info["point"]
    for neighbor_id in node_info.get("neighbours", []):
        neighbor_id_str = str(neighbor_id)
        if neighbor_id_str in nodes:
            x2, y2 = nodes[neighbor_id_str]["point"]
            ax.plot([x1, x2], [y1, y2], color="red", alpha=0.5, linewidth=1, zorder=1)

# Extract node coordinates for plotting
x_coords = []
y_coords = []
labels = []

for node_id, node_info in nodes.items():
    x, y = node_info["point"]
    x_coords.append(x)
    y_coords.append(y)
    labels.append(node_id)

# Plot nodes
ax.scatter(x_coords, y_coords, color="blue", s=100, zorder=3, label="Nodes")

# Add labels
for i, label in enumerate(labels):
    ax.text(x_coords[i] + 0.1, y_coords[i] + 0.1, label, fontsize=8)

# Highlight gateways
if plot_gateways:
    gateways = data.get("gateways", {})
    if gateways:
        for gw_id, gw_info in gateways.items():
            gx, gy = gw_info["point"]
            ax.scatter(gx, gy, color="orange", s=150, marker="s", zorder=3, label=f"Gateway {gw_id}")
            ax.text(gx + 0.1, gy + 0.1, f"GW {gw_id}", fontsize=9, fontweight="bold")
            # Draw 300-unit radius dashed circle
            circle = patches.Circle((gx, gy), 300, fill=False, edgecolor="orange", linestyle="--", linewidth=1.5, alpha=0.6, zorder=2)
            ax.add_patch(circle)

title = data.get("metadata", {}).get("description", "Network Topology")
ax.set_title(title)
ax.set_xlabel("X Coordinate")
ax.set_ylabel("Y Coordinate")
ax.grid(True, alpha=0.3)
ax.legend()
plt.tight_layout()
plt.show()
