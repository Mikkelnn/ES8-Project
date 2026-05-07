# type: ignore
import time
from collections import deque
from ctypes import c_int
from multiprocessing import Lock, Process, Queue, Value

from custom_types import Area, NodeMediumInfo, Severity, SimState
from gateway.gateway import Gateway
from Interfaces import IDevice
from logger.ILogger import ILogger
from logger.simple_logger import SimpleLogger
from medium.medium_service import MediumService
from node.node import Node

from .device_event_queue import DeviceEventQueue
from .global_time import GlobalTime

global_time = GlobalTime()

# Constant for number of log lines to display in GUI
GUI_LOG_DISPLAY_LINES = 75


class Simulation:
    def __init__(self, log_path: str, status=None, lock=None, tps_value=None, log_queue=None, log_lines=100, current_tick_value=None):
        self.log = SimpleLogger(log_path=log_path, buffer_size=100_000)
        # make N nodes that ping pong in pairs and have the other as neighbor, for testing purposes
        num_nodes = 5
        node_neighbors = {}

        self.nodes: list[IDevice] = []
        self.global_time = GlobalTime()
        self.event_queue = DeviceEventQueue()
        self.event_queue.init_tick(start_tick=1, node_ids=range(1, num_nodes + 1))

        # for i in range(1, num_nodes + 1):
        #     neighbors = []
        #     if i % 2 == 1 and i < num_nodes:  # Odd node, add next node as neighbor
        #         neighbors.append(i + 1)
        #     elif i % 2 == 0:  # Even node, add previous node as neighbor
        #         neighbors.append(i - 1)
        #     node_neighbors[i] = NodeMediumInfo(position=(i, 0), neighbors=neighbors)
        node_neighbors[1] = NodeMediumInfo(position=(100, 0), neighbors=[2], gateways_in_range=[], is_gateway=True)
        node_neighbors[2] = NodeMediumInfo(position=(1, 0), neighbors=[3], gateways_in_range=[1])
        node_neighbors[3] = NodeMediumInfo(position=(2, 0), neighbors=[2, 4], gateways_in_range=[])
        node_neighbors[4] = NodeMediumInfo(position=(3, 0), neighbors=[3, 5], gateways_in_range=[])
        node_neighbors[5] = NodeMediumInfo(position=(4, 0), neighbors=[4], gateways_in_range=[])

        # node_neighbors[5] = NodeMediumInfo(position=(4, 0), neighbors=[3,4,6,7], gateways_in_range=[])
        # node_neighbors[6] = NodeMediumInfo(position=(5, 0), neighbors=[4,5,7,8], gateways_in_range=[])
        # node_neighbors[7] = NodeMediumInfo(position=(6, 0), neighbors=[5,6,8,9], gateways_in_range=[])
        # node_neighbors[8] = NodeMediumInfo(position=(7, 0), neighbors=[6,7,9,10], gateways_in_range=[])
        # node_neighbors[9] = NodeMediumInfo(position=(8, 0), neighbors=[7,8,10], gateways_in_range=[])
        # node_neighbors[10] = NodeMediumInfo(position=(9, 0), neighbors=[8,9], gateways_in_range=[])

        self.medium_service = MediumService(node_neighbors=node_neighbors, event_queue=self.event_queue, log=self.log)

        # for i in range(1, num_nodes + 1):
        #     self.nodes.append(Node(node_id=i, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        self.nodes.append(Gateway(gateway_id=1, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        self.nodes.append(Node(node_id=2, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        self.nodes.append(Node(node_id=3, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        self.nodes.append(Node(node_id=4, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        self.nodes.append(Node(node_id=5, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))

        # self.nodes.append(Node(node_id=6, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        # self.nodes.append(Node(node_id=7, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        # self.nodes.append(Node(node_id=8, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        # self.nodes.append(Node(node_id=9, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
        # self.nodes.append(Node(node_id=10, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))

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
    def __init__(self, log_lines=100, log_path="profile-results.log"):
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
        # Circular buffer to keep last N logs in memory (3x display for safety)
        self._log_buffer = deque(maxlen=GUI_LOG_DISPLAY_LINES * 3)
        self.log_path = log_path

    def _simulation_entry(self, log_path: str, status, lock, tps_value, log_queue, log_lines, current_tick_value, run_ticks=None):
        sim = Simulation(log_path=log_path, status=status, lock=lock, tps_value=tps_value, log_queue=log_queue, log_lines=log_lines, current_tick_value=current_tick_value)
        if run_ticks is not None:
            sim.run_for(run_ticks)
        else:
            sim.run()

    def get_tps(self):
        return self.tps_from_sim.value

    def get_current_tick(self):
        return self.current_tick.value

    def get_log(self, lines=None):
        # Drain entire queue but only keep the latest batch for display
        # so GUI always shows fresh logs instead of processing stale backlog
        latest_batch = None
        while not self.log_queue.empty():
            try:
                latest_batch = self.log_queue.get_nowait()
            except Exception:
                break

        if latest_batch:
            self._log_buffer.extend(latest_batch)

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
            self.sim_process = Process(target=self._simulation_entry, args=(self.log_path, self.status, self.lock, self.tps_from_sim, self.log_queue, self.log_lines, self.current_tick, self._run_ticks))
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
