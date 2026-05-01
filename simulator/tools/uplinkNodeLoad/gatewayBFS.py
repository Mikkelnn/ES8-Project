import json
from math import sqrt
from collections import deque, defaultdict


# -----------------------------
# CONFIG
# -----------------------------
INPUT_FILE = "node_outputs.json"
RADIUS_M = 300


# -----------------------------
# LOAD + CONVERT (clean pattern)
# -----------------------------
with open(INPUT_FILE) as f:
    data = json.load(f)

nodes_raw = data["nodes"]
gateways = data["gateways"]

# direct int conversion
graph = {
    int(nid): [int(nb) for nb in n["neighbours"]]
    for nid, n in nodes_raw.items()
}

positions = {
    int(nid): tuple(n["point"])
    for nid, n in nodes_raw.items()
}

total_nodes = len(graph)

mx = data["metadata"]["m_per_svg_x"]
my = data["metadata"]["m_per_svg_y"]


# -----------------------------
# DISTANCE
# -----------------------------
def dist_m(p1, p2):
    dx = (p1[0] - p2[0]) * mx
    dy = (p1[1] - p2[1]) * my
    return sqrt(dx * dx + dy * dy)


# -----------------------------
# FIND INITIAL NODES
# -----------------------------
def find_initial_nodes(g_point, radius_m):
    result = []
    for nid, p in positions.items():
        if dist_m(p, g_point) <= radius_m:
            result.append(nid)
    return sorted(result)  # deterministic


# -----------------------------
# GLOBAL MULTI-SOURCE BFS (streaming stats)
# -----------------------------
def global_bfs(graph, gateway_initials):
    visited = set()
    queue = deque()

    # stats
    gateway_total = defaultdict(int)
    per_init_count = defaultdict(lambda: defaultdict(int))
    per_init_max_hops = defaultdict(lambda: defaultdict(int))

    # init all sources
    for gid in sorted(gateway_initials.keys()):
        for init in sorted(gateway_initials[gid]):
            if init in visited: 
                gateway_initials[gid].remove(init)  # remove duplicate initial node for stats
                print(f"Warning: Initial node {init} for gateway {gid} already visited by another gateway, skipping duplicate.")
            else:
                # ensure node only added once if multiple gateways have same initial node
                visited.add(init)
                queue.append((init, gid, init, 0))

                gateway_total[gid] += 1
                per_init_count[gid][init] += 1
                per_init_max_hops[gid][init] = 0

    # BFS
    while queue:
        node, gid, owner_init, hops = queue.popleft()

        for nb in graph.get(node, []):
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, gid, owner_init, hops + 1))

                gateway_total[gid] += 1
                per_init_count[gid][owner_init] += 1

                if hops + 1 > per_init_max_hops[gid][owner_init]:
                    per_init_max_hops[gid][owner_init] = hops + 1

    return visited, gateway_total, per_init_count, per_init_max_hops


# -----------------------------
# MAIN
# -----------------------------
def main():
    # 1. find initial nodes per gateway
    gateway_initials = {}

    for gid_str, g in gateways.items():
        gid = int(gid_str)
        g_point = tuple(g["point"])

        initial_nodes = find_initial_nodes(g_point, RADIUS_M)

        if initial_nodes:
            gateway_initials[gid] = initial_nodes

    # 2. run global BFS
    visited, gateway_total, per_init_count, per_init_max_hops = global_bfs(
        graph, gateway_initials
    )

    # 3. compute unreached
    reached_count = len(visited)
    unreached_count = total_nodes - reached_count

    # 4. build result
    max_hop_gid, max_hop_init, global_max_hops = max(((g,i,h) for g,d in per_init_max_hops.items() for i,h in d.items()), key=lambda x: x[2])
    max_node_gid, max_node_init, global_max_nodes = max(((g,i,c) for g,d in per_init_count.items() for i,c in d.items()), key=lambda x: x[2])
    results = {
        "gateway_radius_m": RADIUS_M,
        "total_nodes": total_nodes,
        "total_reached": reached_count,
        "total_nodes_unreached": unreached_count,

        "max_hop": {
            "gid": max_hop_gid,
            "init_node_id": max_hop_init,
            "max_hop": global_max_hops
        },
        "max_count": {
            "gid": max_node_gid,
            "init_node_id": max_node_init,
            "count": global_max_nodes
        }
    }

    for gid in gateway_initials:
        results[gid] = {
            "gateway_id": gid,
            "total_nodes_reached": gateway_total[gid],            
            "num_initial_nodes": len(gateway_initials[gid]),
            # "initial_nodes": {
            #     init: {
            #         "node_count": per_init_count[gid][init],
            #         "max_hops": per_init_max_hops[gid][init],
            #     }
            #     for init in gateway_initials[gid]
            # },
        }

    results["visited"] = list(visited)

    return results


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    results = main()

    # for gid, r in results.items():
    #     print(f"\nGateway {gid}")
    #     print(f"  Reached:   {r['total_nodes_reached']}")
    #     print(f"  Unreached: {r['total_nodes_unreached']}")
    #     print(f"  Initial nodes: {r['num_initial_nodes']}")

    #     for nid, stats in r["initial_nodes"].items():
    #         print(
    #             f"    Init {nid}: nodes={stats['node_count']}, "
    #             f"max_hops={stats['max_hops']}"
    #         )

    # save
    with open("gateway_results.json", "w") as f:
        json.dump(results, f, indent=2)