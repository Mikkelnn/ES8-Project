import json

import matplotlib.pyplot as plt


def load_nodes():
    with open("../uplinkNodeLoad/final_selected/node_outputs.json") as f:
        data = json.load(f)
    return data["nodes"], data["metadata"]


if __name__ == "__main__":
    nodes, metadata = load_nodes()
    max_neighbours = max(len(node["neighbours"]) for node in nodes.values())

    neighbour_counts = [len(node["neighbours"]) for node in nodes.values()]

    from collections import Counter

    dist = Counter(neighbour_counts)

    x = sorted(dist.keys())
    y = [dist[i] for i in x]

    # Cap y value for 2 neighbours to max of others
    y_capped = y.copy()
    max_other = max(v for i, v in enumerate(y) if x[i] != 2)
    idx_2 = x.index(2)
    actual_2 = y[idx_2]
    y_capped[idx_2] = max_other

    plt.figure(figsize=(10, 6))
    plt.stem(x, y_capped, basefmt=" ")

    # Annotate 2 neighbours with actual value
    plt.text(2, max_other + max_other * 0.05, str(actual_2), ha="center", va="bottom", fontsize=11, fontweight="bold", color="red")

    plt.xlabel("Number of Neighbours")
    plt.ylabel("Count of Nodes")
    plt.title("Distribution of Neighbours per Node")
    plt.xticks(range(1, 9))
    plt.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig("nodes_neighbours_stem.png", dpi=150)
    print("Stem plot saved to nodes_neighbours_stem.png")
    print()
    print("Distribution of Neighbours:")
    print("-" * 40)
    print(f"{'Neighbours':<12} {'Count':<15}")
    print("-" * 40)
    for i in x:
        marker = " (outlier)" if i == 2 else ""
        print(f"{i:<12} {dist[i]:<15}{marker}")
    print("-" * 40)
