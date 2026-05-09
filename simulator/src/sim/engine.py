# type: ignore
import json
import time
from collections import deque
from ctypes import c_int
from multiprocessing import Lock, Process, Queue, Value
from pathlib import Path

from custom_types import Area, LocalEventTypes, MediumTypes, NodeMediumInfo, Severity, SimState
from gateway.gateway import Gateway
from Interfaces import IDevice
from logger.ILogger import ILogger
from logger.simple_logger import SimpleLogger
from loraWanFrameHelper import LoRaWanPHYPayload, MACPayload
from medium.medium_service import MediumService
from node.node import Node
from payload_types import MegaSync, PayloadData, PayloadHopCnt

from .device_event_queue import DeviceEventQueue
from .global_time import GlobalTime

global_time = GlobalTime()

# Constant for number of log lines to display in GUI
GUI_LOG_DISPLAY_LINES = 75


class NetworkTopologyLoader:
    """Load network topology from node_outputs.json file."""

    @staticmethod
    def from_json(json_path: str) -> dict[int, NodeMediumInfo]:
        """Load topology from JSON and return as NodeMediumInfo dict."""
        with open(json_path) as f:
            data = json.load(f)

        node_neighbors = {}
        nodes_data = data.get("nodes", {})
        gateways_data = data.get("gateways", {})
        gateway_ids = set(int(gw_id) for gw_id in gateways_data.keys())

        for node_id_str, node_info in nodes_data.items():
            node_id = int(node_id_str)
            position = tuple(node_info["point"])
            neighbors = [int(n) for n in node_info.get("neighbours", [])]
            is_gw = node_id in gateway_ids

            node_neighbors[node_id] = NodeMediumInfo(
                position=position,
                neighbors=neighbors,
                gateways_in_range=[],
                is_gateway=is_gw,
            )

        return node_neighbors

    @staticmethod
    def from_file(file_path: str | Path) -> dict[int, NodeMediumInfo]:
        """Alias for from_json."""
        return NetworkTopologyLoader.from_json(str(file_path))


class Simulation:
    def __init__(self, log_path: str, status=None, lock=None, tps_value=None, log_queue=None, log_lines=100, current_tick_value=None, injection_tasks=None, node_neighbors=None):
        self.log = SimpleLogger(log_path=log_path, buffer_size=100_000)
        self.nodes: list[IDevice] = []
        self.global_time = GlobalTime()
        self.injection_tasks = injection_tasks or []
        self.completed_injections = set()

        if node_neighbors is None:
            node_neighbors = NetworkTopologyLoader.from_file("tools/uplinkNodeLoad/final_selected/node_outputs.json")

        num_nodes = len(node_neighbors)
        self.event_queue = DeviceEventQueue()
        self.event_queue.init_tick(start_tick=1, node_ids=range(1, num_nodes + 1))

        self.medium_service = MediumService(node_neighbors=node_neighbors, event_queue=self.event_queue, log=self.log)
        self._build_nodes(node_neighbors)

        self.status = status
        self.lock = lock
        self.tps_value = tps_value
        self.log_queue = log_queue
        self.log_lines = log_lines
        self.current_tick_value = current_tick_value

    def _build_nodes(self, node_neighbors: dict[int, NodeMediumInfo]) -> None:
        for node_id in sorted(node_neighbors.keys()):
            node_info = node_neighbors[node_id]
            if node_info.is_gateway:
                self.nodes.append(Gateway(gateway_id=node_id, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
            else:
                self.nodes.append(Node(node_id=node_id, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))

    def _inject_data(self, node_id: int, current_time: int, payload_data):

        node = self.nodes[node_id - 1]
        if not hasattr(node, "protocol"):
            self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION FAILED: Node {node_id} protocol not available")
            return

        # Check if node is awake (can receive)
        if hasattr(node, "state"):
            from node.node import State

            if node.state == State.SLEEP:
                self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION SKIPPED: Node {node_id} is sleeping")
                return

        if isinstance(payload_data, PayloadData):
            # PayloadData generated locally by APP layer
            if hasattr(node.protocol, "app"):
                node.protocol.app.enqueue_payload(payload_data)
                self.log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: PayloadData into Node {node_id}, payload_id={payload_data.id}, sensor1={payload_data.data.sensor1}, sensor2={payload_data.data.sensor2}")
            else:
                self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION FAILED: Node {node_id} app not available")
        elif isinstance(payload_data, MegaSync):
            # MegaSync received via WAN transceiver (from gateway)
            if hasattr(node, "local_event_queue"):
                wan_frame = LoRaWanPHYPayload(mhdr=96, mac_payload=MACPayload(dev_addr=node_id, fctrl_flags=0, fcnt=0, frm_payload=payload_data))
                node.local_event_queue.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, wan_frame, sub_type=MediumTypes.LORA_WAN)
                self.log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: MegaSync into Node {node_id} (via WAN), time={payload_data.time}, total_handle_time={payload_data.total_handle_time}")
            else:
                self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION FAILED: Node {node_id} event queue not available")
        elif isinstance(payload_data, PayloadHopCnt):
            # PayloadHopCnt received via D2D
            if hasattr(node.protocol, "d2d"):
                node.protocol.d2d.enqueue_payload(payload_data)
                self.log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: PayloadHopCnt into Node {node_id}, cnt={payload_data.cnt}")
            else:
                self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION FAILED: Node {node_id} d2d not available")
        else:
            self.log.add(Severity.WARNING, Area.SIMULATOR, current_time, f"INJECTION FAILED: Unknown payload type '{type(payload_data).__name__}'")

    def run_for(self, stop_tick):
        stopwatch_start_time = time.time()
        propagation_time = 0
        node_tick_time = 0
        current_time = 0
        total_evaluated = 0
        last_tps_calc = time.time()
        log_push_counter = 0
        LOG_PUSH_INTERVAL = 100

        try:
            while len(self.event_queue.events):
                sim_state = self.status.value  # c_int read is atomic, no lock needed

                if sim_state == SimState.PAUSED.value:
                    self.log.flush(force=True)

                while sim_state == SimState.PAUSED.value:
                    time.sleep(0.05)
                    sim_state = self.status.value

                if sim_state == SimState.STOPPED.value:
                    break

                (current_time, node_ids) = self.event_queue.get_next_events()

                if current_time > stop_tick:
                    if self.current_tick_value is not None:
                        self.current_tick_value.value = int(stop_tick)
                    break

                self.global_time.set_time(current_time)

                if self.current_tick_value is not None:
                    self.current_tick_value.value = int(current_time)

                node_start_time = time.time()
                for node_id in node_ids:
                    next_evaluation = self.nodes[node_id - 1].tick(current_time)
                    self.event_queue.add_event(node_id, next_evaluation)
                node_tick_time += time.time() - node_start_time

                for idx, task in enumerate(self.injection_tasks):
                    if idx not in self.completed_injections and current_time >= task["tick"]:
                        self._inject_data(task["node_id"], current_time, task["payload"])
                        self.completed_injections.add(idx)

                propagation_start_time = time.time()
                self.medium_service.propagate_mediums(current_time)
                propagation_time += time.time() - propagation_start_time
                total_evaluated += 1

                self.log.flush()
                log_push_counter += 1
                if log_push_counter >= LOG_PUSH_INTERVAL and self.log_queue is not None:
                    log_push_counter = 0
                    try:
                        lines = self.log.get()
                        if lines:
                            self.log_queue.put_nowait(lines[-GUI_LOG_DISPLAY_LINES:])
                    except Exception:
                        pass  # queue full — drop batch, GUI will get next one

                now = time.time()
                if self.tps_value is not None and now - last_tps_calc > 0.1:
                    self.global_time.tps_calc()
                    tps = self.global_time.get_tps()
                    self.tps_value.value = int(tps) if tps is not None else 0
                    last_tps_calc = now
        except Exception as e:
            print(f"Simulation error: {e}")
            self.log.add(Severity.ERROR, Area.SIMULATOR, self.global_time.get_time(), f"Simulation error: {e}", data=None)

        elapsed_time = time.time() - stopwatch_start_time

        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total elapsed real time: {elapsed_time:.2f} seconds for {len(self.nodes)} nodes")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total node tick time: {node_tick_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total propagation time: {propagation_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total log time: {(elapsed_time - (propagation_time + node_tick_time)):.2f} seconds")
        self.log.flush(force=True)

    def run(self):
        self.run_for(float("inf"))

    # Pause, resume, stop now controlled by Engine


class Engine:
    def __init__(self, log_lines=100, log_path="profile-results.log", injection_tasks=None, node_neighbors=None, topology_json_path=None):
        self.log: ILogger = SimpleLogger(log_path=log_path, buffer_size=100_000)
        self.status = Value(c_int, SimState.PAUSED.value)
        self.tps_from_sim = Value(c_int, 0)
        self.current_tick = Value(c_int, 0)
        self.log_queue = Queue(maxsize=2)
        self.lock = Lock()
        self.amount_of_processes = 1
        self.sim_process = None
        self.log_lines = log_lines
        self._run_ticks = None
        self.injection_tasks = injection_tasks or []

        # Load topology from JSON if provided, otherwise use node_neighbors
        if topology_json_path:
            self.node_neighbors = NetworkTopologyLoader.from_file(topology_json_path)
        else:
            self.node_neighbors = node_neighbors

        # Circular buffer to keep last N logs in memory (3x display for safety)
        self._log_buffer = deque(maxlen=GUI_LOG_DISPLAY_LINES * 3)
        self.log_path = log_path

    def _simulation_entry(self, log_path: str, status, lock, tps_value, log_queue, log_lines, current_tick_value, run_ticks=None, injection_tasks=None, node_neighbors=None):
        sim = Simulation(log_path=log_path, status=status, lock=lock, tps_value=tps_value, log_queue=log_queue, log_lines=log_lines, current_tick_value=current_tick_value, injection_tasks=injection_tasks, node_neighbors=node_neighbors)
        if run_ticks is not None:
            sim.run_for(run_ticks)
        else:
            sim.run()

    def get_tps(self):
        return self.tps_from_sim.value

    def get_current_tick(self):
        return self.current_tick.value

    def get_log(self, lines=None):
        # Drain entire queue and accumulate all batches
        while not self.log_queue.empty():
            try:
                batch = self.log_queue.get_nowait()
                if batch:
                    self._log_buffer.extend(batch)
            except Exception:
                break

        n_lines = lines if lines is not None else self.log_lines
        return list(self._log_buffer)[-n_lines:] if self._log_buffer else []

    def _clear_log_queue(self):
        """Clear any pending logs from the queue to make pause/stop feel instant."""
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except Exception:
                break

    def start_continue(self, run_ticks=None):
        with self.lock:
            self.status.value = SimState.RUNNING.value
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine started", data=None)
        self._run_ticks = run_ticks
        if self.sim_process is None or not self.sim_process.is_alive():
            self.sim_process = Process(target=self._simulation_entry, args=(self.log_path, self.status, self.lock, self.tps_from_sim, self.log_queue, self.log_lines, self.current_tick, self._run_ticks, self.injection_tasks, self.node_neighbors))
            self.sim_process.start()

    def run_for(self, ticks):
        self.start_continue(run_ticks=ticks)

    def pause(self):
        with self.lock:
            self.status.value = SimState.PAUSED.value
        self.tps_from_sim.value = 0
        self._clear_log_queue()  # Clear pending logs to make pause feel instant
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine paused", data=None)

    def stop(self):
        with self.lock:
            self.status.value = SimState.STOPPED.value
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine stopped", data=None)
        self._clear_log_queue()
        if self.sim_process is not None:
            self.sim_process.terminate()
            self.sim_process.join(timeout=3)
            if self.sim_process.is_alive():
                self.sim_process.kill()
                self.sim_process.join()
            self.sim_process = None


if __name__ == "__main__":
    engine = Engine()
