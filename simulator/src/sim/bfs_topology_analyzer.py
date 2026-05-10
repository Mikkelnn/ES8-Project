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
    def _run_multi_source_bfs(
        graph: dict[int, list[int]], gateway_initials: dict[int, list[int]]
    ) -> tuple[set[int], dict[int, int]]:
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
                    node_to_gateway[neighbor] = gw_id
                    queue.append((neighbor, gw_id))

        return visited, node_to_gateway

    @staticmethod
    def analyze(
        nodes_data: dict,
        gateways_data: dict,
        m_per_svg_x: float,
        m_per_svg_y: float,
        radius_m: float = None,
        gw_id_offset: int = None,
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
        gateway_initials = BFSTopologyAnalyzer._find_gateway_initial_nodes(
            nodes_data, gateways_data, m_per_svg_x, m_per_svg_y, radius_m, gw_id_offset
        )
        visited_nodes, node_to_gateway = BFSTopologyAnalyzer._run_multi_source_bfs(graph, gateway_initials)

        return visited_nodes, gateway_initials, node_to_gateway
