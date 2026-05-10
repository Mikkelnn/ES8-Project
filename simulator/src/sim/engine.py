# type: ignore
import json
import os
import time
from collections import defaultdict, deque
from ctypes import c_int
from multiprocessing import Lock, Pipe, Process, Queue, Value
from multiprocessing.connection import wait as mp_wait
from pathlib import Path

from custom_types import Area, LocalEventTypes, MediumTypes, NodeMediumInfo, Severity, SimState
from gateway.gateway import Gateway
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

_SECOND_TO_GLOBAL_TICK = 0.001


# ── Worker-side proxy classes ──────────────────────────────────────────────────


class CollectingMediumService:
    """Proxy MediumService used inside worker processes.
    Collects transmit/cancel calls as plain tuples; serves pre-loaded incoming
    EventNet objects so node.transceiver.tick() can read them normally.
    """

    def __init__(self):
        self._incoming: dict = defaultdict(list)  # node_id → List[EventNet]
        self._transmissions: list = []
        self._cancellations: list = []

    def set_incoming(self, node_id: int, events: list) -> None:
        self._incoming[node_id].extend(events)

    # Called by TransceiverService inside node.tick()
    def transmit(self, from_node_id: int, medium_type, data, time_start: int, time_end: int) -> None:
        self._transmissions.append((from_node_id, medium_type, data, time_start, time_end))

    def cancel_transmission(self, from_node_id: int, medium_type, time_start: int, time_end: int) -> None:
        self._cancellations.append((from_node_id, medium_type, time_start, time_end))

    def receive(self, to_node_id: int, medium_type) -> list:
        node_events = self._incoming.get(to_node_id, [])
        matching = [e for e in node_events if e.type_medium == medium_type]
        remaining = [e for e in node_events if e.type_medium != medium_type]
        if remaining:
            self._incoming[to_node_id] = remaining
        else:
            self._incoming.pop(to_node_id, None)
        return matching

    def drain_transmissions(self) -> list:
        out = self._transmissions[:]
        self._transmissions.clear()
        return out

    def drain_cancellations(self) -> list:
        out = self._cancellations[:]
        self._cancellations.clear()
        return out


class CollectingLogger:
    """Proxy ILogger for worker processes — accumulates formatted strings."""

    def __init__(self):
        self._entries: list = []

    def add(self, severity, area, global_time: int, info: str, data=None) -> None:
        self._entries.append(f"[{severity.value}] ({area.value}) @ {global_time}: {info}, {data if data else ''}\n")

    def flush(self, force: bool = False) -> bool:
        return False

    def get(self) -> list:
        return self._entries[:]

    def drain_entries(self) -> list:
        out = self._entries[:]
        self._entries.clear()
        return out


# ── Worker process entry point ─────────────────────────────────────────────────

_WORKER_STOP = "STOP"


def _worker_run_loop(node_ids: list, node_neighbors: dict, conn) -> None:
    """Runs inside each worker Process.
    Initialises a node subset with proxy medium/logger, then loops:
      receive task → tick active nodes → send results.
    """
    # Local imports so this function works with both fork and spawn.

    medium = CollectingMediumService()
    log = CollectingLogger()
    nodes: dict = {}

    for nid in node_ids:
        info = node_neighbors[nid]
        if info.is_gateway:
            nodes[nid] = Gateway(gateway_id=nid, second_to_global_tick=_SECOND_TO_GLOBAL_TICK, medium_service=medium, log=log)
        else:
            nodes[nid] = Node(node_id=nid, second_to_global_tick=_SECOND_TO_GLOBAL_TICK, medium_service=medium, log=log)

    while True:
        task = conn.recv()
        if task == _WORKER_STOP:
            break

        current_time, active_ids, incoming, injection_tasks = task

        # Pre-load incoming media events so transceiver.tick() can pop them
        for nid, events in incoming:
            medium.set_incoming(nid, events)

        # Apply injection tasks directly to node-local state
        for inj in injection_tasks:
            nid = inj["node_id"]
            payload = inj["payload"]
            node = nodes.get(nid)
            if node is None:
                continue
            if isinstance(payload, PayloadData) and hasattr(node, "protocol") and hasattr(node.protocol, "app"):
                node.protocol.app.enqueue_payload(payload)
                log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: PayloadData into Node {nid}")
            elif isinstance(payload, MegaSync) and hasattr(node, "local_event_queue"):
                wan_frame = LoRaWanPHYPayload(mhdr=96, mac_payload=MACPayload(dev_addr=nid, fctrl_flags=0, fcnt=0, frm_payload=payload))
                node.local_event_queue.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, wan_frame, sub_type=MediumTypes.LORA_WAN)
                log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: MegaSync into Node {nid}")
            elif isinstance(payload, PayloadHopCnt) and hasattr(node, "protocol") and hasattr(node.protocol, "d2d"):
                node.protocol.d2d.enqueue_payload(payload)
                log.add(Severity.INFO, Area.SIMULATOR, current_time, f"INJECTED: PayloadHopCnt into Node {nid}")

        # Tick each active node
        next_ticks = []
        for nid in active_ids:
            node = nodes.get(nid)
            if node is not None:
                next_ticks.append((nid, node.tick(current_time)))

        conn.send((next_ticks, medium.drain_transmissions(), medium.drain_cancellations(), log.drain_entries()))


class NetworkTopologyLoader:
    """Load network topology from node_outputs.json file."""

    LORA_WAN_RADIUS_M = 300.0

    @staticmethod
    def from_json(json_path: str) -> dict[int, NodeMediumInfo]:
        """Load topology from JSON and return as NodeMediumInfo dict."""
        with open(json_path) as f:
            data = json.load(f)

        node_neighbors = {}
        nodes_data = data.get("nodes", {})
        gateways_data = data.get("gateways", {})
        gateway_ids = set(int(gw_id) for gw_id in gateways_data.keys())

        meta = data.get("metadata", {})
        m_per_svg_x = meta.get("m_per_svg_x", 391.287)
        m_per_svg_y = meta.get("m_per_svg_y", 702.570)
        radius_m = NetworkTopologyLoader.LORA_WAN_RADIUS_M

        gw_positions = {int(gw_id): tuple(gw["point"]) for gw_id, gw in gateways_data.items()}

        for node_id_str, node_info in nodes_data.items():
            node_id = int(node_id_str)
            position = tuple(node_info["point"])
            neighbors = [int(n) for n in node_info.get("neighbours", [])]
            is_gw = node_id in gateway_ids

            gateways_in_range = []
            if not is_gw:
                px, py = position
                for gw_id, (gx, gy) in gw_positions.items():
                    dx = (px - gx) * m_per_svg_x
                    dy = (py - gy) * m_per_svg_y
                    if (dx * dx + dy * dy) ** 0.5 <= radius_m:
                        gateways_in_range.append(gw_id)

            node_neighbors[node_id] = NodeMediumInfo(
                position=position,
                neighbors=neighbors,
                gateways_in_range=gateways_in_range,
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
        self.global_time = GlobalTime()
        self.injection_tasks = injection_tasks or []
        self.completed_injections = set()

        if node_neighbors is None:
            node_neighbors = NetworkTopologyLoader.from_file("tools/uplinkNodeLoad/final_selected/node_outputs.json")

        num_nodes = len(node_neighbors)
        self.event_queue = DeviceEventQueue()
        self.event_queue.init_tick(start_tick=1, node_ids=range(1, num_nodes + 1))

        self.medium_service = MediumService(node_neighbors=node_neighbors, event_queue=self.event_queue, log=self.log)

        # Cap workers to physical cores — hyperthreads don't help CPU-bound Python
        logical_cpus = os.cpu_count() or 4
        phys_cores = max(1, logical_cpus // 2)
        n_workers = max(1, min(phys_cores, num_nodes))

        sorted_ids = sorted(node_neighbors.keys())
        partitions: list[list[int]] = [[] for _ in range(n_workers)]
        self._node_to_worker: dict[int, int] = {}
        for i, nid in enumerate(sorted_ids):
            w = i % n_workers
            partitions[w].append(nid)
            self._node_to_worker[nid] = w

        # Start one persistent Process per partition, connected via duplex Pipe
        self._workers: list[tuple] = []  # (parent_conn, Process)
        for w_ids in partitions:
            parent_conn, child_conn = Pipe(duplex=True)
            p = Process(target=_worker_run_loop, args=(w_ids, node_neighbors, child_conn), daemon=True)
            p.start()
            child_conn.close()  # Only the child needs its end
            self._workers.append((parent_conn, p))

        # Pending incoming EventNets for nodes that haven't woken yet
        self._pending_incoming: dict[int, list] = defaultdict(list)

        self.status = status
        self.lock = lock
        self.tps_value = tps_value
        self.log_queue = log_queue
        self.log_lines = log_lines
        self.current_tick_value = current_tick_value

    def run_for(self, stop_tick):
        stopwatch_start_time = time.time()
        propagation_time = 0
        node_tick_time = 0
        current_time = 0
        total_evaluated = 0
        last_tps_calc = time.time()

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

                # Build per-worker batches: active nodes + pending incoming for active nodes
                n_w = len(self._workers)
                w_active: list[list] = [[] for _ in range(n_w)]
                w_incoming: list[list] = [[] for _ in range(n_w)]
                w_injections: list[list] = [[] for _ in range(n_w)]
                dispatched: set[int] = set()

                for nid in node_ids:
                    w = self._node_to_worker.get(nid)
                    if w is not None:
                        w_active[w].append(nid)
                        dispatched.add(w)
                        # Include pending incoming only when the node is being ticked
                        if nid in self._pending_incoming:
                            w_incoming[w].append((nid, self._pending_incoming.pop(nid)))

                # Route injection tasks to the owning worker
                for idx, task in enumerate(self.injection_tasks):
                    if idx not in self.completed_injections and current_time >= task["tick"]:
                        w = self._node_to_worker.get(task["node_id"])
                        if w is not None:
                            w_injections[w].append(task)
                            dispatched.add(w)
                        self.completed_injections.add(idx)

                # Dispatch tasks only to workers that have work this tick
                conn_to_worker: dict = {}
                for w in dispatched:
                    conn = self._workers[w][0]
                    conn.send((current_time, w_active[w], w_incoming[w], w_injections[w]))
                    conn_to_worker[conn] = w

                # Collect results as they arrive — overlaps with remaining worker runtime
                pending = list(conn_to_worker.keys())
                while pending:
                    ready = mp_wait(pending, timeout=60)
                    if not ready:
                        raise TimeoutError("Worker timed out after 60s")
                    for conn in ready:
                        next_ticks, transmissions, cancellations, logs = conn.recv()
                        for nid, nt in next_ticks:
                            self.event_queue.add_event(nid, nt)
                        for tx in transmissions:
                            self.medium_service.transmit(*tx)
                        for cx in cancellations:
                            self.medium_service.cancel_transmission(*cx)
                        self.log._buffer.extend(logs)
                        pending.remove(conn)

                node_tick_time += time.time() - node_start_time

                propagation_start_time = time.time()
                self.medium_service.propagate_mediums(current_time)
                propagation_time += time.time() - propagation_start_time

                # Store media deliveries so receiving nodes get them on their next wakeup
                for medium_obj in self.medium_service._mediums_by_type.values():
                    for nid, events in medium_obj.node_receptions.items():
                        self._pending_incoming[nid].extend(events)
                    medium_obj.node_receptions.clear()
                total_evaluated += 1

                if self.log_queue is not None:
                    try:
                        lines = self.log.get()
                        if lines:
                            self.log_queue.put_nowait(lines[-GUI_LOG_DISPLAY_LINES:])
                    except Exception:
                        pass  # queue full — drop batch, GUI will get next one
                self.log.flush()

                now = time.time()
                if self.tps_value is not None and now - last_tps_calc > 0.1:
                    self.global_time.tps_calc()
                    tps = self.global_time.get_tps()
                    self.tps_value.value = int(tps) if tps is not None else 0
                    last_tps_calc = now
        except Exception as e:
            import traceback

            print(f"Simulation error: {e}\n{traceback.format_exc()}")
            self.log.add(Severity.ERROR, Area.SIMULATOR, self.global_time.get_time(), f"Simulation error: {e}", data=None)
        finally:
            self._stop_workers()

        elapsed_time = time.time() - stopwatch_start_time
        num_nodes = len(self._node_to_worker)
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total elapsed real time: {elapsed_time:.2f} seconds for {num_nodes} nodes")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total node tick time: {node_tick_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total propagation time: {propagation_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total log time: {(elapsed_time - (propagation_time + node_tick_time)):.2f} seconds")
        self.log.flush(force=True)

    def _stop_workers(self) -> None:
        for conn, _ in self._workers:
            try:
                conn.send(_WORKER_STOP)
            except Exception:
                pass
        for conn, p in self._workers:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()
            try:
                conn.close()
            except Exception:
                pass

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
