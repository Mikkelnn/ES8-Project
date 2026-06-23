"""BFS-based network topology analyzer for gateway reachability."""

from collections import defaultdict, deque
from math import sqrt


class BFSTopologyAnalyzer:
    """Analyze network topology using multi-source BFS from gateways."""

    LORA_WAN_RADIUS_M = 300.0

    @staticmethod
    def _dist_m(p1: tuple, p2: tuple, m_per_svg_x: float, m_per_svg_y: float) -> float:
        """Calculate distance in meters between two SVG points."""
        dx = (p1[0] - p2[0]) * m_per_svg_x
        dy = (p1[1] - p2[1]) * m_per_svg_y
        return sqrt(dx * dx + dy * dy)

    @staticmethod
    def _build_graph(nodes_data: dict) -> dict[int, list[int]]:
        """Construct node neighbor graph from JSON nodes data."""
        return {int(nid): [int(nb) for nb in n.get("neighbours", [])] for nid, n in nodes_data.items()}

    @staticmethod
    def _find_gateway_initial_nodes(
        nodes_data: dict,
        gateways_data: dict,
        m_per_svg_x: float,
        m_per_svg_y: float,
        radius_m: float,
        gw_id_offset: int,
    ) -> dict[int, list[int]]:
        """Find nodes within LORA_WAN_RADIUS of each gateway.

        Returns: {gateway_id: [node_ids_in_reach]}
        """
        positions = {int(nid): tuple(n["point"]) for nid, n in nodes_data.items()}
        gateway_initials = {}

        for gw_id_str, gw_info in sorted(gateways_data.items()):
            gw_id = gw_id_offset + int(gw_id_str)
            gw_point = tuple(gw_info["point"])

            initial_nodes = []
            for nid, pos in sorted(positions.items()):
                dist = BFSTopologyAnalyzer._dist_m(pos, gw_point, m_per_svg_x, m_per_svg_y)
                if dist <= radius_m:
                    initial_nodes.append(nid)

            if initial_nodes:
                gateway_initials[gw_id] = sorted(initial_nodes)

        return gateway_initials

    @staticmethod
    def _run_multi_source_bfs(graph: dict[int, list[int]], gateway_initials: dict[int, list[int]]) -> tuple[set[int], dict[int, int]]:
        """Execute multi-source BFS from all gateway initial nodes.

        Returns: (visited_nodes_set, node_to_gateway_map)
            - visited_nodes_set: Set of all visited node IDs
            - node_to_gateway_map: Dict mapping node_id -> gateway_id (single gateway per node)
        """
        visited = set()
        node_to_gateway = {}
        queue = deque()

        # Initialize all gateway sources
        for gw_id in sorted(gateway_initials.keys()):
            for init_node in sorted(gateway_initials[gw_id]):
                if init_node not in visited:
                    visited.add(init_node)
                    node_to_gateway[init_node] = gw_id
                    queue.append((init_node, gw_id))

        # BFS traverse
        while queue:
            node, gw_id = queue.popleft()
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    # node_to_gateway[neighbor] = gw_id
                    queue.append((neighbor, gw_id))

        return visited, node_to_gateway

    @staticmethod
    def analyze(
        nodes_data: dict,
        gateways_data: dict,
        m_per_svg_x: float,
        m_per_svg_y: float,
        radius_m: float | None = None,
        gw_id_offset: int | None = None,
    ) -> tuple[set[int], dict[int, list[int]], dict[int, int]]:
        """Run full BFS topology analysis.

        Args:
            nodes_data: Dict of nodes from JSON
            gateways_data: Dict of gateways from JSON
            m_per_svg_x: Meters per SVG unit (X axis)
            m_per_svg_y: Meters per SVG unit (Y axis)
            radius_m: LoRaWAN radius in meters (default: LORA_WAN_RADIUS_M)
            gw_id_offset: ID offset for gateway numbering (required)

        Returns:
            (visited_nodes, gateway_initials, node_to_gateway)
            - visited_nodes: Set of BFS-visited node IDs
            - gateway_initials: Dict {gateway_id: [nodes_in_range]}
            - node_to_gateway: Dict {node_id: gateway_id}
        """
        if radius_m is None:
            radius_m = BFSTopologyAnalyzer.LORA_WAN_RADIUS_M
        if gw_id_offset is None:
            raise ValueError("gw_id_offset is required")

        graph = BFSTopologyAnalyzer._build_graph(nodes_data)
        gateway_initials = BFSTopologyAnalyzer._find_gateway_initial_nodes(nodes_data, gateways_data, m_per_svg_x, m_per_svg_y, radius_m, gw_id_offset)
        visited_nodes, node_to_gateway = BFSTopologyAnalyzer._run_multi_source_bfs(graph, gateway_initials)

        return visited_nodes, gateway_initials, node_to_gateway

    @staticmethod
    def analyze_with_stats(
        nodes_data: dict,
        gateways_data: dict,
        m_per_svg_x: float,
        m_per_svg_y: float,
        radius_m: float | None = None,
        gw_id_offset: int = 0,
    ) -> dict:
        """Run BFS topology analysis with hop/count statistics (gatewayBFS format).

        Args:
            nodes_data: Dict of nodes from JSON
            gateways_data: Dict of gateways from JSON
            m_per_svg_x: Meters per SVG unit (X axis)
            m_per_svg_y: Meters per SVG unit (Y axis)
            radius_m: LoRaWAN radius in meters (default: LORA_WAN_RADIUS_M)
            gw_id_offset: ID offset for gateway numbering (default: 0)

        Returns:
            Dict with structure matching gatewayBFS output:
            {
                "gateway_radius_m": int,
                "total_nodes": int,
                "total_reached": int,
                "total_nodes_unreached": int,
                "max_hop": {"gid": int, "init_node_id": int, "max_hop": int},
                "max_count": {"gid": int, "init_node_id": int, "count": int},
                gateway_id: {"gateway_id": int, "total_nodes_reached": int, "num_initial_nodes": int},
                "visited": [node_ids...]
            }
        """
        if radius_m is None:
            radius_m = BFSTopologyAnalyzer.LORA_WAN_RADIUS_M

        graph = BFSTopologyAnalyzer._build_graph(nodes_data)
        gateway_initials = BFSTopologyAnalyzer._find_gateway_initial_nodes(nodes_data, gateways_data, m_per_svg_x, m_per_svg_y, radius_m, gw_id_offset)

        # Run BFS with stats tracking
        visited = set()
        gateway_total = defaultdict(int)
        per_init_count = defaultdict(lambda: defaultdict(int))
        per_init_max_hops = defaultdict(lambda: defaultdict(int))

        queue = deque()
        for gw_id in sorted(gateway_initials.keys()):
            for init in sorted(gateway_initials[gw_id]):
                if init not in visited:
                    visited.add(init)
                    queue.append((init, gw_id, init, 0))
                    gateway_total[gw_id] += 1
                    per_init_count[gw_id][init] += 1
                    per_init_max_hops[gw_id][init] = 0

        while queue:
            node, gw_id, owner_init, hops = queue.popleft()
            for nb in graph.get(node, []):
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, gw_id, owner_init, hops + 1))
                    gateway_total[gw_id] += 1
                    per_init_count[gw_id][owner_init] += 1
                    if hops + 1 > per_init_max_hops[gw_id][owner_init]:
                        per_init_max_hops[gw_id][owner_init] = hops + 1

        # Compute global stats
        reached_count = len(visited)
        unreached_count = len(nodes_data) - reached_count
        max_hop_gid, max_hop_init, global_max_hops = max(
            ((g, i, h) for g, d in per_init_max_hops.items() for i, h in d.items()),
            key=lambda x: x[2],
        )
        max_node_gid, max_node_init, global_max_nodes = max(
            ((g, i, c) for g, d in per_init_count.items() for i, c in d.items()),
            key=lambda x: x[2],
        )

        results = {
            "gateway_radius_m": int(radius_m),
            "total_nodes": len(nodes_data),
            "total_reached": reached_count,
            "total_nodes_unreached": unreached_count,
            "max_hop": {"gid": max_hop_gid, "init_node_id": max_hop_init, "max_hop": global_max_hops},
            "max_count": {"gid": max_node_gid, "init_node_id": max_node_init, "count": global_max_nodes},
        }

        for gw_id in gateway_initials:
            results[str(gw_id)] = {
                "gateway_id": gw_id,
                "total_nodes_reached": gateway_total[gw_id],
                "num_initial_nodes": len(gateway_initials[gw_id]),
            }

        results["visited"] = sorted(list(visited))
        return results

    @staticmethod
    def cluster_partition(node_neighbors: dict, n_clusters: int) -> dict[int, int]:
        """Partition nodes into n_clusters topologically coherent groups via BFS from geo-spread seeds.

        Returns {node_id: cluster_id} where cluster_id is in 0..n_clusters-1.
        Gateways are assigned to the cluster owning most of their served nodes.
        """
        if n_clusters <= 1:
            return {nid: 0 for nid in node_neighbors}

        regular = {nid: info for nid, info in node_neighbors.items() if not info.is_gateway}
        gateways = {nid: info for nid, info in node_neighbors.items() if info.is_gateway}

        sorted_nodes = sorted(regular.items(), key=lambda kv: kv[1].position[0] + kv[1].position[1])
        n = len(sorted_nodes)
        if n == 0:
            return {nid: 0 for nid in node_neighbors}

        step = max(1, n // n_clusters)
        seeds = [sorted_nodes[min(i * step, n - 1)][0] for i in range(n_clusters)]

        node_to_cluster: dict[int, int] = {}
        queue: deque = deque()
        for cid, seed in enumerate(seeds):
            if seed not in node_to_cluster:
                node_to_cluster[seed] = cid
                queue.append((seed, cid))

        while queue:
            nid, cid = queue.popleft()
            for nb in node_neighbors[nid].neighbors:
                if nb in node_to_cluster or nb not in regular:
                    continue
                node_to_cluster[nb] = cid
                queue.append((nb, cid))

        # Assign any disconnected regular nodes round-robin
        fallback = 0
        for nid in regular:
            if nid not in node_to_cluster:
                node_to_cluster[nid] = fallback % n_clusters
                fallback += 1

        # Assign each gateway to the cluster owning the majority of its served nodes
        for gw_id, gw_info in gateways.items():
            votes: dict[int, int] = {}
            for nb in gw_info.neighbors:
                cid = node_to_cluster.get(nb)
                if cid is not None:
                    votes[cid] = votes.get(cid, 0) + 1
            node_to_cluster[gw_id] = max(votes, key=votes.get) if votes else 0

        return node_to_cluster
