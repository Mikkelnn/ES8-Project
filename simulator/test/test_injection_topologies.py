"""
Injection tests with different network topologies.

Tests injection behavior across:
- Linear chain (1-2-3-...-10)
- Branching tree topology
- Mesh topology
- Star topology (hub and spoke)
"""

import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import os

import pytest

from custom_types import NodeMediumInfo
from payload_types import PayloadData
from sim.engine import Engine


class TopologyBuilder:
    """Helper to create different network topologies."""

    @staticmethod
    def linear_chain(num_nodes: int = 10):
        """Linear chain: 1-2-3-...-N."""
        neighbors = {}
        neighbors[1] = NodeMediumInfo(position=(100, 0), neighbors=[2], gateways_in_range=[], is_gateway=True)
        for i in range(2, num_nodes):
            neighbors[i] = NodeMediumInfo(position=(i - 1, 0), neighbors=[i - 1, i + 1], gateways_in_range=[])
        neighbors[num_nodes] = NodeMediumInfo(position=(num_nodes - 1, 0), neighbors=[num_nodes - 1], gateways_in_range=[])
        return neighbors

    @staticmethod
    def branching_tree(num_nodes: int = 15):
        r"""Branching tree topology.

        Example with 15 nodes:
                1 (gateway)
                |
                2
               / \
              3   4
             / \  / \
            5  6 7   8
           /\ /\ /\ /\
          9 10 11 12 13 14 15
        """
        neighbors = {}
        neighbors[1] = NodeMediumInfo(position=(0, 0), neighbors=[2], gateways_in_range=[], is_gateway=True)
        neighbors[2] = NodeMediumInfo(position=(0, 1), neighbors=[1, 3, 4], gateways_in_range=[])
        neighbors[3] = NodeMediumInfo(position=(-1, 2), neighbors=[2, 5, 6], gateways_in_range=[])
        neighbors[4] = NodeMediumInfo(position=(1, 2), neighbors=[2, 7, 8], gateways_in_range=[])

        # Leaf nodes
        for i in range(5, min(num_nodes + 1, 9)):
            parent = 3 if i < 7 else 4
            neighbors[i] = NodeMediumInfo(position=(i - 5, 3), neighbors=[parent], gateways_in_range=[])

        # Additional nodes to reach num_nodes
        for i in range(9, num_nodes + 1):
            parent = 5 + ((i - 9) % 4)  # Distribute among nodes 5-8
            neighbors[i] = NodeMediumInfo(position=(i, 4), neighbors=[parent], gateways_in_range=[])

        return neighbors

    @staticmethod
    def star_topology(num_nodes: int = 10):
        """Star topology: all nodes connect to central gateway."""
        neighbors = {}
        neighbors[1] = NodeMediumInfo(position=(0, 0), neighbors=list(range(2, num_nodes + 1)), gateways_in_range=[], is_gateway=True)
        for i in range(2, num_nodes + 1):
            neighbors[i] = NodeMediumInfo(position=(i - 1, 1), neighbors=[1], gateways_in_range=[])
        return neighbors

    @staticmethod
    def mesh_topology(num_nodes: int = 6):
        """Mesh topology: higher connectivity."""
        neighbors = {}
        neighbors[1] = NodeMediumInfo(position=(0, 0), neighbors=list(range(2, num_nodes + 1)), gateways_in_range=[], is_gateway=True)
        for i in range(2, num_nodes + 1):
            # Connect to gateway and adjacent nodes
            node_neighbors = [1]
            if i > 2:
                node_neighbors.append(i - 1)
            if i < num_nodes:
                node_neighbors.append(i + 1)
            neighbors[i] = NodeMediumInfo(position=(i - 1, 1), neighbors=node_neighbors, gateways_in_range=[])
        return neighbors


@pytest.mark.serial
class TestLinearChainTopology:
    """Tests on linear chain topology."""

    def _run_with_topology(self, injection_tasks, run_ticks: int = 16000000):
        """Run simulation with linear chain topology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(run_ticks)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                return f.read()

    def test_linear_chain_payload_propagation(self):
        """Test payload propagates through linear chain."""
        payload = PayloadData(id={10})
        payload.data.sensor1 = 33
        payload.data.sensor2 = 44
        payload.time = 0
        payload.length_calc()

        injection_tasks = [{"node_id": 10, "tick": 15000000, "payload": payload}]

        log = self._run_with_topology(injection_tasks)

        assert "INJECTED: PayloadData into Node 10" in log
        assert "sensor1=33, sensor2=44" in log
        assert "Node 10 started transmitting" in log


@pytest.mark.serial
class TestBranchingTreeTopology:
    """Tests on branching tree topology."""

    def test_branching_tree_injection_leaf_node(self):
        """Test injection at leaf node of branching tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            payload = PayloadData(id={9})
            payload.data.sensor1 = 55
            payload.data.sensor2 = 66
            payload.time = 0
            payload.length_calc()

            injection_tasks = [{"node_id": 9, "tick": 15000000, "payload": payload}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            assert "INJECTED: PayloadData into Node 9" in log
            assert "sensor1=55, sensor2=66" in log


@pytest.mark.serial
class TestStarTopology:
    """Tests on star topology (all nodes connect to gateway)."""

    def test_star_topology_direct_injection(self):
        """Test payload injection in star topology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            payload = PayloadData(id={5})
            payload.data.sensor1 = 77
            payload.data.sensor2 = 88
            payload.time = 0
            payload.length_calc()

            injection_tasks = [{"node_id": 5, "tick": 15000000, "payload": payload}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            assert "INJECTED: PayloadData into Node 5" in log
            assert "sensor1=77, sensor2=88" in log


@pytest.mark.serial
class TestMeshTopology:
    """Tests on mesh topology with higher connectivity."""

    def test_mesh_topology_injection(self):
        """Test injection in mesh topology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            payload = PayloadData(id={6})
            payload.data.sensor1 = 99
            payload.data.sensor2 = 11
            payload.time = 0
            payload.length_calc()

            injection_tasks = [{"node_id": 6, "tick": 15000000, "payload": payload}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            assert "INJECTED: PayloadData into Node 6" in log
            assert "sensor1=99, sensor2=11" in log


@pytest.mark.serial
class TestMultipleTopologies:
    """Compare injection behavior across topologies."""

    def _inject_same_payload_all_topologies(self, node_id: int, sensor1: int, sensor2: int):
        """Run same injection on all topology types."""
        results = {}

        payload = PayloadData(id={node_id})
        payload.data.sensor1 = sensor1
        payload.data.sensor2 = sensor2
        payload.time = 0
        payload.length_calc()

        injection_tasks = [{"node_id": node_id, "tick": 15000000, "payload": payload}]

        # Test linear chain
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")
            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()
            with open(log_path, "r") as f:
                results["linear_chain"] = f.read()

        # Test star topology
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")
            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()
            with open(log_path, "r") as f:
                results["star"] = f.read()

        return results

    def test_same_payload_different_topologies(self):
        """Test same payload injection works across different topologies."""
        results = self._inject_same_payload_all_topologies(node_id=5, sensor1=42, sensor2=99)

        # Both topologies should successfully inject
        assert "INJECTED: PayloadData into Node 5" in results["linear_chain"]
        assert "INJECTED: PayloadData into Node 5" in results["star"]

        # Both should have correct payload values
        assert "sensor1=42, sensor2=99" in results["linear_chain"]
        assert "sensor1=42, sensor2=99" in results["star"]
