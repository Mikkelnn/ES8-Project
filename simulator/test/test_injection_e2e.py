# """
# End-to-end injection tests with multiple scenarios.

# Tests cover:
# - Payload injection from different nodes
# - MegaSync injection to different nodes
# - Multi-hop propagation verification
# - Different network topologies
# """

# import sys
# from pathlib import Path

# src_path = Path(__file__).parent.parent / "src"
# sys.path.insert(0, str(src_path))

# import os
# import tempfile

# import pytest

# from payload_types import MegaSync, PayloadData
# from sim.engine import Engine


# @pytest.mark.serial
# class TestPayloadInjectionLinearChain:
#     """Test payload injection in linear chain topology (1-2-3-...-10)."""

#     def _run_scenario(self, node_id: int, sensor1: int, sensor2: int, run_ticks: int = 16000000):
#         """Helper to run injection scenario."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload = PayloadData(id={node_id})
#             payload.data.sensor1 = sensor1
#             payload.data.sensor2 = sensor2
#             payload.time = 0
#             payload.length_calc()

#             injection_tasks = [{"node_id": node_id, "tick": 15000000, "payload": payload}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(run_ticks)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log_content = f.read()

#             return log_content

#     def test_payload_injection_node_10(self):
#         """Test payload injection from Node 10 (farthest from gateway)."""
#         log = self._run_scenario(node_id=10, sensor1=42, sensor2=99)

#         assert "INJECTED: PayloadData into Node 10" in log
#         assert "sensor1=42" in log
#         assert "sensor2=99" in log
#         assert "source_node_id=10" in log

#     def test_payload_injection_node_5(self):
#         """Test payload injection from Node 5 (middle node)."""
#         log = self._run_scenario(node_id=5, sensor1=11, sensor2=22)

#         assert "INJECTED: PayloadData into Node 5" in log
#         assert "sensor1=11" in log
#         assert "sensor2=22" in log
#         assert "source_node_id=5" in log

#     def test_payload_injection_node_2(self):
#         """Test payload injection from Node 2 (closest non-gateway node)."""
#         log = self._run_scenario(node_id=2, sensor1=77, sensor2=88)

#         assert "INJECTED: PayloadData into Node 2" in log
#         assert "sensor1=77" in log
#         assert "sensor2=88" in log
#         assert "source_node_id=2" in log

#     def test_payload_propagation_node_10_to_relay(self):
#         """Test payload from Node 10 propagates to intermediate nodes."""
#         log = self._run_scenario(node_id=10, sensor1=42, sensor2=99)

#         # Verify Node 10 transmitted
#         assert "Node 10 started transmitting" in log
#         assert "sensor1=42, sensor2=99" in log

#         # Verify relay nodes received (Nodes 8, 9 should be neighbors of Node 10)
#         assert "Node 8 successfully received data" in log or "Node 9 successfully received data" in log
#         assert "sensor1=42, sensor2=99" in log


# @pytest.mark.serial
# class TestMegaSyncInjectionLinearChain:
#     """Test MegaSync injection in linear chain topology."""

#     def _run_scenario(self, node_id: int, sync_time: int, handle_time: int, run_ticks: int = 16000000):
#         """Helper to run MegaSync injection scenario."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             megasync = MegaSync(time=sync_time, total_handle_time=handle_time)

#             injection_tasks = [{"node_id": node_id, "tick": 15000000, "payload": megasync}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(run_ticks)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log_content = f.read()

#             return log_content

#     def test_megasync_injection_node_2(self):
#         """Test MegaSync injection into Node 2."""
#         log = self._run_scenario(node_id=2, sync_time=15000000, handle_time=500)

#         assert "INJECTED: MegaSync into Node 2" in log
#         assert "time=15000000" in log
#         assert "total_handle_time=500" in log

#     def test_megasync_injection_node_5(self):
#         """Test MegaSync injection into Node 5."""
#         log = self._run_scenario(node_id=5, sync_time=15001000, handle_time=1000)

#         assert "INJECTED: MegaSync into Node 5" in log
#         assert "time=15001000" in log
#         assert "total_handle_time=1000" in log

#     def test_megasync_injection_node_10(self):
#         """Test MegaSync injection into Node 10 (leaf node)."""
#         log = self._run_scenario(node_id=10, sync_time=15002000, handle_time=750)

#         assert "INJECTED: MegaSync into Node 10" in log
#         assert "time=15002000" in log
#         assert "total_handle_time=750" in log


# @pytest.mark.serial
# class TestDualInjectionLinearChain:
#     """Test multiple injections in sequence."""

#     def test_sequential_payload_then_megasync(self):
#         """Test payload injection followed by MegaSync injection."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload = PayloadData(id={10})
#             payload.data.sensor1 = 42
#             payload.data.sensor2 = 99
#             payload.time = 0
#             payload.length_calc()

#             megasync = MegaSync(time=15001000, total_handle_time=500)

#             injection_tasks = [{"node_id": 10, "tick": 15000000, "payload": payload}, {"node_id": 2, "tick": 15001000, "payload": megasync}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             assert "INJECTED: PayloadData into Node 10" in log
#             assert "INJECTED: MegaSync into Node 2" in log

#     def test_multiple_payload_injections(self):
#         """Test multiple payload injections from different nodes."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload1 = PayloadData(id={10})
#             payload1.data.sensor1 = 42
#             payload1.data.sensor2 = 99
#             payload1.time = 0
#             payload1.length_calc()

#             payload2 = PayloadData(id={5})
#             payload2.data.sensor1 = 11
#             payload2.data.sensor2 = 22
#             payload2.time = 0
#             payload2.length_calc()

#             injection_tasks = [{"node_id": 10, "tick": 15000000, "payload": payload1}, {"node_id": 5, "tick": 15500000, "payload": payload2}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             assert "INJECTED: PayloadData into Node 10" in log
#             assert "sensor1=42, sensor2=99" in log
#             assert "INJECTED: PayloadData into Node 5" in log
#             assert "sensor1=11, sensor2=22" in log


# @pytest.mark.serial
# class TestInjectionErrorHandling:
#     """Test error handling for invalid injections."""

#     def test_injection_invalid_node(self):
#         """Test injection to non-existent node (should fail gracefully)."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload = PayloadData(id={99})
#             payload.data.sensor1 = 42
#             payload.data.sensor2 = 99
#             payload.time = 0
#             payload.length_calc()

#             injection_tasks = [{"node_id": 99, "tick": 15000000, "payload": payload}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             # Should log failure but not crash
#             assert "INJECTION FAILED" in log or len(log) > 0

#     def test_injection_invalid_packet_type(self):
#         """Test injection with unknown packet type."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             injection_tasks = [{"node_id": 5, "tick": 15000000, "payload": None}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             assert "INJECTION FAILED" in log or "Unknown packet type" in log


# @pytest.mark.serial
# class TestInjectionWithDifferentValues:
#     """Test injection with various sensor values."""

#     def test_payload_min_values(self):
#         """Test payload with minimum values."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload = PayloadData(id={10})
#             payload.data.sensor1 = 0
#             payload.data.sensor2 = 0
#             payload.time = 0
#             payload.length_calc()

#             injection_tasks = [{"node_id": 10, "tick": 15000000, "payload": payload}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             assert "sensor1=0, sensor2=0" in log

#     def test_payload_max_values(self):
#         """Test payload with maximum values (16-bit)."""
#         with tempfile.TemporaryDirectory() as tmpdir:
#             log_path = os.path.join(tmpdir, "simulation.log")

#             payload = PayloadData(id={10})
#             payload.data.sensor1 = 65535
#             payload.data.sensor2 = 65535
#             payload.time = 0
#             payload.length_calc()

#             injection_tasks = [{"node_id": 10, "tick": 15000000, "payload": payload}]

#             engine = Engine(log_path=log_path, injection_tasks=injection_tasks)
#             engine.run_for(16000000)
#             if engine.sim_process:
#                 engine.sim_process.join()

#             with open(log_path, "r") as f:
#                 log = f.read()

#             assert "sensor1=65535, sensor2=65535" in log
