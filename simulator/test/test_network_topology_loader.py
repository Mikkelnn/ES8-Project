"""Test NetworkTopologyLoader loads all maps correctly using BFSTopologyAnalyzer."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from custom_types import NodeMediumInfo
from sim.bfs_topology_analyzer import BFSTopologyAnalyzer
from sim.engine import NetworkTopologyLoader

MAPS_DIR = Path(__file__).parent.parent / "tools" / "uplinkNodeLoad"


class TestNetworkTopologyLoader:
    """Test NetworkTopologyLoader integrates BFSTopologyAnalyzer correctly."""

    @pytest.fixture
    def available_maps(self):
        """Return list of all available map paths."""
        maps = []
        for json_file in sorted(MAPS_DIR.glob("*/node_outputs.json")):
            maps.append(json_file)
        return maps

    def test_loader_finds_all_maps(self, available_maps):
        """Verify all map files can be located."""
        assert len(available_maps) >= 2, f"Expected at least 2 maps, found {len(available_maps)}"
        for map_path in available_maps:
            assert map_path.exists(), f"Map file missing: {map_path}"

    @pytest.mark.parametrize(
        "map_path",
        [MAPS_DIR / "test_line" / "node_outputs.json", MAPS_DIR / "final_selected" / "node_outputs.json"],
    )
    def test_loader_successfully_loads_all_maps(self, map_path):
        """Test that NetworkTopologyLoader.from_json() loads all maps without error."""
        assert map_path.exists(), f"Map file not found: {map_path}"

        # Load topology
        device_neighbors = NetworkTopologyLoader.from_json(str(map_path))

        # Verify output structure
        assert isinstance(device_neighbors, dict)
        assert len(device_neighbors) > 0, f"No devices loaded from {map_path}"

        # All values should be NodeMediumInfo
        for device_id, info in device_neighbors.items():
            assert isinstance(device_id, int)
            assert isinstance(info, NodeMediumInfo)
            assert isinstance(info.position, tuple)
            assert isinstance(info.neighbors, list)
            assert isinstance(info.gateways_in_range, list)
            assert isinstance(info.is_gateway, bool)

    @pytest.mark.parametrize("map_path", [MAPS_DIR / "test_line" / "node_outputs.json"])
    def test_loader_uses_bfs_topology_analyzer_correctly(self, map_path):
        """Verify NetworkTopologyLoader correctly applies BFSTopologyAnalyzer results."""
        with open(map_path) as f:
            data = json.load(f)

        nodes_data = data["nodes"]
        gateways_data = data["gateways"]
        meta = data.get("metadata", {})
        mx = meta.get("m_per_svg_x", 391.287)
        my = meta.get("m_per_svg_y", 702.570)

        # Get BFS results
        max_node_id = max(int(nid) for nid in nodes_data.keys()) if nodes_data else 0
        gw_id_offset = max_node_id + 1

        visited_nodes, gateway_initials, node_to_gateway = BFSTopologyAnalyzer.analyze(
            nodes_data=nodes_data,
            gateways_data=gateways_data,
            m_per_svg_x=mx,
            m_per_svg_y=my,
            radius_m=300,
            gw_id_offset=gw_id_offset,
        )

        # Load via NetworkTopologyLoader
        device_neighbors = NetworkTopologyLoader.from_json(str(map_path))

        # Verify visited nodes are in device_neighbors
        for node_id in visited_nodes:
            assert node_id in device_neighbors, f"Visited node {node_id} not in device_neighbors"

        # Verify unreached nodes are NOT in device_neighbors
        for node_id_str, node_info in nodes_data.items():
            node_id = int(node_id_str)
            if node_id not in visited_nodes:
                assert node_id not in device_neighbors, f"Unreached node {node_id} should not be in device_neighbors"

        # Verify all gateways are in device_neighbors
        for gw_id_str in gateways_data.keys():
            gw_id = gw_id_offset + int(gw_id_str)
            assert gw_id in device_neighbors, f"Gateway {gw_id} not in device_neighbors"
            assert device_neighbors[gw_id].is_gateway is True

    @pytest.mark.parametrize("map_path", [MAPS_DIR / "test_line" / "node_outputs.json"])
    def test_loader_filters_neighbors_to_visited_only(self, map_path):
        """Verify node neighbors are filtered to only include visited nodes."""
        with open(map_path) as f:
            data = json.load(f)

        nodes_data = data["nodes"]
        gateways_data = data["gateways"]
        meta = data.get("metadata", {})
        mx = meta.get("m_per_svg_x", 391.287)
        my = meta.get("m_per_svg_y", 702.570)

        # Get BFS results
        max_node_id = max(int(nid) for nid in nodes_data.keys()) if nodes_data else 0
        gw_id_offset = max_node_id + 1

        visited_nodes, _, _ = BFSTopologyAnalyzer.analyze(
            nodes_data=nodes_data,
            gateways_data=gateways_data,
            m_per_svg_x=mx,
            m_per_svg_y=my,
            radius_m=300,
            gw_id_offset=gw_id_offset,
        )

        # Load via NetworkTopologyLoader
        device_neighbors = NetworkTopologyLoader.from_json(str(map_path))

        # Verify node neighbors are only visited nodes
        for node_id, info in device_neighbors.items():
            if not info.is_gateway:
                for neighbor_id in info.neighbors:
                    assert neighbor_id in visited_nodes, f"Node {node_id} has neighbor {neighbor_id} that's not visited"

    @pytest.mark.parametrize("map_path", [MAPS_DIR / "test_line" / "node_outputs.json"])
    def test_loader_assigns_gateways_to_nodes(self, map_path):
        """Verify each node is assigned exactly one gateway via BFS."""
        with open(map_path) as f:
            data = json.load(f)

        nodes_data = data["nodes"]
        gateways_data = data["gateways"]
        meta = data.get("metadata", {})
        mx = meta.get("m_per_svg_x", 391.287)
        my = meta.get("m_per_svg_y", 702.570)

        # Get BFS results
        max_node_id = max(int(nid) for nid in nodes_data.keys()) if nodes_data else 0
        gw_id_offset = max_node_id + 1

        _, _, node_to_gateway = BFSTopologyAnalyzer.analyze(
            nodes_data=nodes_data,
            gateways_data=gateways_data,
            m_per_svg_x=mx,
            m_per_svg_y=my,
            radius_m=300,
            gw_id_offset=gw_id_offset,
        )

        # Load via NetworkTopologyLoader
        device_neighbors = NetworkTopologyLoader.from_json(str(map_path))

        # Verify each non-gateway node has exactly one gateway
        for node_id, info in device_neighbors.items():
            if not info.is_gateway:
                assert len(info.gateways_in_range) == 1, f"Node {node_id} should have exactly 1 gateway"
                gateway_id = info.gateways_in_range[0]
                # Verify gateway ID matches BFS assignment
                assert gateway_id == node_to_gateway[node_id], f"Node {node_id} gateway mismatch: NetworkTopologyLoader={gateway_id}, BFS={node_to_gateway[node_id]}"

    @pytest.mark.parametrize("map_path", [MAPS_DIR / "test_line" / "node_outputs.json"])
    def test_loader_gateway_neighbors_are_assigned_nodes(self, map_path):
        """Verify gateway neighbors only contain nodes assigned to that gateway."""
        with open(map_path) as f:
            data = json.load(f)

        nodes_data = data["nodes"]
        gateways_data = data["gateways"]
        meta = data.get("metadata", {})
        mx = meta.get("m_per_svg_x", 391.287)
        my = meta.get("m_per_svg_y", 702.570)

        # Get BFS results
        max_node_id = max(int(nid) for nid in nodes_data.keys()) if nodes_data else 0
        gw_id_offset = max_node_id + 1

        _, _, node_to_gateway = BFSTopologyAnalyzer.analyze(
            nodes_data=nodes_data,
            gateways_data=gateways_data,
            m_per_svg_x=mx,
            m_per_svg_y=my,
            radius_m=300,
            gw_id_offset=gw_id_offset,
        )

        # Load via NetworkTopologyLoader
        device_neighbors = NetworkTopologyLoader.from_json(str(map_path))

        # Verify gateway neighbors match BFS assignment (RAW, no sorting)
        for gw_id_str in gateways_data.keys():
            gw_id = gw_id_offset + int(gw_id_str)
            gateway_info = device_neighbors[gw_id]

            # Gateway neighbors should only be nodes assigned to this gateway (raw order)
            expected_neighbors = [nid for nid, assigned_gw in node_to_gateway.items() if assigned_gw == gw_id]
            assert gateway_info.neighbors == expected_neighbors, f"Gateway {gw_id} neighbors mismatch (RAW order):\n  Expected: {expected_neighbors}\n  Got: {gateway_info.neighbors}"
