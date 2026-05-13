import json
import matplotlib.pyplot as plt

# Load the JSON file
with open("maps\intersection.json", "r") as f:
    data = json.load(f)

nodes = data["nodes"]

# Extract coordinates
x_coords = []
y_coords = []
labels = []

for node_id, node_info in nodes.items():
    x, y = node_info["point"]
    x_coords.append(x)
    y_coords.append(y)
    labels.append(node_id)

# Plot nodes
plt.figure(figsize=(12, 8))
plt.scatter(x_coords, y_coords, color='blue', s=50)

# Add labels
for i, label in enumerate(labels):
    plt.text(x_coords[i]+0.1, y_coords[i]+0.1, label, fontsize=8)

# Highlight gateway(s)
# for gw_id, gw_info in data.get("gateways", {}).items():
#     gx, gy = gw_info["point"]
#     plt.scatter(gx, gy, color='orange', s=100, label=f'Gateway {gw_id}')
#     plt.text(gx+0.1, gy+0.1, f'GW {gw_id}', fontsize=10, fontweight='bold')

plt.title("Network Nodes")
plt.xlabel("X Coordinate")
plt.ylabel("Y Coordinate")
plt.grid(True)
plt.legend()
plt.show()