from medium.medium_service import MediumService
from logger.ILogger import ILogger
from logger.simple_logger import SimpleLogger
from node.node import Node
from custom_types import NodeMediumInfo, Severity, Area, SimState
from .global_time import GlobalTime
from .global_event_queue import GlobalEventQueue
import time
from multiprocessing import Value, Lock, Process, Queue
from ctypes import c_int
import threading
from collections import deque

global_time = GlobalTime()

# Constant for number of log lines to display in GUI
GUI_LOG_DISPLAY_LINES = 75

class Simulation:

    def __init__(self, log: SimpleLogger, status=None, lock=None, tps_value=None, log_queue=None, log_lines=100, current_tick_value=None):
        self.log = log
        # make N nodes that ping pong in pairs and have the other as neighbor, for testing purposes
        num_nodes = 5
        node_neighbors = {}

        self.nodes: list[Node] = []
        self.global_time = GlobalTime()
        self.event_queue = GlobalEventQueue()
        self.event_queue.init_tick(start_tick=1, node_ids=range(1, num_nodes + 1))

        for i in range(1, num_nodes + 1):
            neighbors = []
            if i % 2 == 1 and i < num_nodes:  # Odd node, add next node as neighbor
                neighbors.append(i + 1)
            elif i % 2 == 0:  # Even node, add previous node as neighbor
                neighbors.append(i - 1)
            node_neighbors[i] = NodeMediumInfo(position=(i, 0), neighbors=neighbors)

        self.medium_service = MediumService(node_neighbors=node_neighbors, event_queue=self.event_queue, log=self.log)

        for i in range(1, num_nodes + 1):
            self.nodes.append(Node(node_id=i, second_to_global_tick=0.001, medium_service=self.medium_service, log=self.log))
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
        while len(self.event_queue.events):
            # Check status frequently for pause/stop
            for _ in range(10):
                # Read status live
                if self.status is not None and self.lock is not None:
                    with self.lock:
                        sim_state = self.status.value
                else:
                    sim_state = SimState.RUNNING.value
                if sim_state == SimState.STOPPED.value:
                    return
                while sim_state == SimState.PAUSED.value:
                    time.sleep(0.05)
                    if self.status is not None and self.lock is not None:
                        with self.lock:
                            sim_state = self.status.value
                    else:
                        sim_state = SimState.RUNNING.value
                    if sim_state == SimState.STOPPED.value:
                        return
            (current_time, node_ids) = self.event_queue.get_next_events()
            self.global_time.set_time(current_time)

            # Update shared current tick value
            if self.current_tick_value is not None:
                self.current_tick_value.value = int(current_time)

            if current_time > stop_tick:
                current_time = stop_tick
                break

            # Tick all nodes, do this in parallel if needed
            node_start_time = time.time()
            for node_id in node_ids:
                next_evaluation = self.nodes[node_id - 1].tick(current_time)
                self.event_queue.add_event(node_id, next_evaluation)
            node_tick_time += time.time() - node_start_time

            propagation_start_time = time.time()
            self.medium_service.propagate_mediums(current_time)
            propagation_time += time.time() - propagation_start_time
            total_evaluated += 1

            if self.log_queue is not None:
                try:
                    lines = self.log.get()
                    if lines:  # Only send if we have logs
                        self.log_queue.put(lines[-GUI_LOG_DISPLAY_LINES:])
                except Exception:
                    pass
            self.log.flush()
            # TPS calculation every second
            now = time.time()
            if self.tps_value is not None and now - last_tps_calc > 1.0:
                self.global_time.tps_calc()
                tps = self.global_time.get_tps()
                self.tps_value.value = int(tps) if tps is not None else 0
                last_tps_calc = now
        elapsed_time = time.time() - stopwatch_start_time

        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total elapsed real time: {elapsed_time:.2f} seconds for {len(self.nodes)} nodes")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total node tick time: {node_tick_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total propagation time: {propagation_time:.2f} seconds")
        self.log.add(Severity.INFO, Area.SIMULATOR, 0, f"Total log time: {(elapsed_time - (propagation_time + node_tick_time)):.2f} seconds")
        self.log.flush(force=True)

    def run(self):
        self.run_for(float('inf'))
    # Pause, resume, stop now controlled by Engine

class Engine:
    def __init__(self, log_lines=100, log_path='profile-results.log'):
        self.log: ILogger = SimpleLogger(log_path=log_path, buffer_size=100_000)
        self.status = Value(c_int, SimState.PAUSED.value)
        self.tps_from_sim = Value(c_int, 0)
        self.current_tick = Value(c_int, 0)
        self.log_queue = Queue()
        self.lock = Lock()
        self.amount_of_processes = 1
        self.sim_process = None
        self.log_lines = log_lines
        self._run_ticks = None
        # Circular buffer to keep last N logs in memory (3x display for safety)
        self._log_buffer = deque(maxlen=GUI_LOG_DISPLAY_LINES * 3)

    def _simulation_entry(self, log, status, lock, tps_value, log_queue, log_lines, current_tick_value, run_ticks=None):
        sim = Simulation(log, status=status, lock=lock, tps_value=tps_value, log_queue=log_queue, log_lines=log_lines, current_tick_value=current_tick_value)
        if run_ticks is not None:
            sim.run_for(run_ticks)
        else:
            sim.run()

    def get_tps(self):
        return self.tps_from_sim.value

    def get_current_tick(self):
        return self.current_tick.value

    def get_log(self, lines=None):
        # Drain queue and add to circular buffer
        while not self.log_queue.empty():
            try:
                new_logs = self.log_queue.get_nowait()
                self._log_buffer.extend(new_logs)
            except Exception:
                break

        # Return last N lines from buffer
        n_lines = lines if lines is not None else self.log_lines
        return list(self._log_buffer)[-n_lines:] if self._log_buffer else []

    def start_continue(self, run_ticks=None):
        with self.lock:
            self.status.value = SimState.RUNNING.value
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine started", data=None)
        self._run_ticks = run_ticks
        if self.sim_process is None or not self.sim_process.is_alive():
            self.sim_process = Process(target=self._simulation_entry, args=(self.log, self.status, self.lock, self.tps_from_sim, self.log_queue, self.log_lines, self.current_tick, self._run_ticks))
            self.sim_process.start()

    def run_for(self, ticks):
        self.start_continue(run_ticks=ticks)

    def pause(self):
        with self.lock:
            self.status.value = SimState.PAUSED.value
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine paused", data=None)

    def stop(self):
        with self.lock:
            self.status.value = SimState.STOPPED.value
        self.log.add(Severity.INFO, Area.SIMULATOR, global_time.get_time(), "Engine stopped", data=None)
        # Non-blocking: poll for process exit
        if self.sim_process is not None:
            def poll_exit():
                self.sim_process.join()
                self.sim_process = None
            threading.Thread(target=poll_exit, daemon=True).start()

if __name__ == "__main__":
    engine = Engine()