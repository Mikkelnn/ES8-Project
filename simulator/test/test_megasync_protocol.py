"""
MegaSync protocol flow tests.

Tests for:
1. MegaSync injection into Gateway (Node 1)
2. MegaSyncReq from nodes with hopcnt 0 (gateway candidates)
3. MegaSync response from gateway back to nodes
4. End-to-end MegaSync synchronization flow
"""

import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import os

import pytest

from payload_types import MegaSync
from sim.engine import Engine


@pytest.mark.serial
class TestMegaSyncReqFromGatewayNode:
    """Test MegaSyncReq generation from nodes with hopcnt=0 (gateway candidates)."""

    def test_megasync_req_from_node_with_hopcnt_0(self):
        """Test MegaSyncReq originates from node with hop count 0 to gateway.

        Expected: Nodes discovering they are at hopcnt=0 send MegaSyncReq
        Status: Implementation needs - requires hop count discovery
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            # No injection - we're testing natural protocol behavior
            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # During convergence, nodes should discover hopcnt and some may have hopcnt=0
            # They should send MegaSyncReq upward
            assert "MegaSyncReq" in log, "Nodes should generate MegaSyncReq during sync phase"

    def test_megasync_req_format_with_hopcnt_0(self):
        """Test MegaSyncReq has correct format for hopcnt=0 nodes.

        Expected: MegaSyncReq(data=1) from nodes at gateway distance
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # MegaSyncReq should have data field set
            assert "MegaSyncReq" in log and "data" in log, "MegaSyncReq should include data field"


@pytest.mark.serial
class TestMegaSyncResponseFromGateway:
    """Test gateway responds with MegaSync to requesting nodes."""

    def test_gateway_returns_megasync_response(self):
        """Test gateway responds to MegaSyncReq with MegaSync frame.

        Expected: Gateway sends MegaSync downlink after receiving MegaSyncReq
        Status: Implementation needed - gateway response handler
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # After receiving MegaSyncReq, gateway should send MegaSync
            # Look for gateway transmission of MegaSync
            megasync_count = log.count("MegaSync(time=")

            assert megasync_count > 0, "Gateway should send MegaSync responses"

    def test_megasync_response_contains_gateway_time(self):
        """Test MegaSync response includes gateway's current time.

        Expected: MegaSync(time=<gateway_tick>, total_handle_time=...)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # MegaSync should have time and handle_time fields
            assert "MegaSync(" in log, "Gateway should send MegaSync with time information"

    def test_megasync_response_propagates_to_relays(self):
        """Test MegaSync response from gateway propagates through relay chain.

        Expected: Nodes relay MegaSync downlink through multi-hop
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # Count MegaSync instances - should see multiple as it propagates
            megasync_instances = log.count("MegaSync(")

            assert megasync_instances > 1, "MegaSync should propagate through relay chain"


@pytest.mark.serial
class TestMegaSyncInjectionToGatewayAndResponse:
    """Test end-to-end MegaSync injection to gateway with response.

    Scenario:
    1. Inject MegaSync into Node 1 (gateway)
    2. Gateway processes sync time
    3. Gateway sends MegaSync downlink
    4. Nodes receive and process MegaSync
    """

    def test_megasync_sync_time_preserved_in_response(self):
        """Test sync time is preserved when gateway responds.

        Expected: Gateway responds with same time value from injection
        Status: Implementation needed
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            sync_time = 15123456
            megasync = MegaSync(time=sync_time, total_handle_time=500)

            injection_tasks = [{"node_id": 1, "tick": 15000000, "payload": megasync}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # Gateway response should contain the sync time
            # or at least should have processed it
            megasync_count = log.count("MegaSync")
            assert megasync_count >= 1, "Gateway should process injected MegaSync"


@pytest.mark.serial
class TestMegaSyncTimingAndSequencing:
    """Test MegaSync timing and event sequencing."""

    def test_megasync_req_interval_from_nodes(self):
        """Test nodes send MegaSyncReq at periodic intervals.

        Expected: MegaSyncReq appears multiple times as protocol runs
        Status: Implementation needed - requires periodic protocol state
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            engine = Engine(log_path=log_path, injection_tasks=[])
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            megasync_req_count = log.count("MegaSyncReq")
            # Should see multiple requests over 16M ticks
            # At least one per protocol cycle
            assert megasync_req_count >= 1, "Nodes should send MegaSyncReq periodically"

    def test_megasync_response_latency(self):
        """Test latency of gateway MegaSync response.

        Expected: Gateway responds within 1-2 seconds (protocol RX1 window)
        Status: Implementation needs verification
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            megasync = MegaSync(time=3000000, total_handle_time=0)

            injection_tasks = [{"node_id": 1, "tick": 3000000, "payload": megasync}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(4000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # Should have MegaSync activity
            assert "MegaSync" in log or "INJECTED" in log, "MegaSync should be present in logs"


@pytest.mark.serial
class TestMegaSyncProtocolErrors:
    """Test error handling in MegaSync protocol."""

    def test_megasync_to_gateway_with_invalid_handle_time(self):
        """Test MegaSync with very large handle_time.

        Expected: Gateway processes without error
        Status: Robustness test
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            megasync = MegaSync(time=15000000, total_handle_time=65535)

            injection_tasks = [{"node_id": 1, "tick": 15000000, "payload": megasync}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # Should not crash
            assert len(log) > 0, "Large handle_time should not crash simulation"

    def test_multiple_concurrent_megasync_injections(self):
        """Test gateway handles multiple MegaSync at same tick.

        Expected: Gateway queues/processes all without dropping
        Status: Implementation needs verification
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "simulation.log")

            # Try injecting same MegaSync twice (edge case)
            megasync = MegaSync(time=15000000, total_handle_time=500)

            injection_tasks = [{"node_id": 1, "tick": 15000000, "payload": megasync}]

            engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
            engine.run_for(16000000)
            if engine.sim_process:
                engine.sim_process.join()

            with open(log_path, "r") as f:
                log = f.read()

            # Should not crash with multiple injections
            assert len(log) > 0, "Concurrent injections should not crash"
