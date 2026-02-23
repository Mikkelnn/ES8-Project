
from typing import List
from medium.medium_service import MediumService
from node.Imodule import IModule
from node.node import Node
from .logger import Logger
from custom_types import NodeMediumInfo, Severity, Area
import threading
from .global_time import time_global
import random
from .global_time import time_global
import time

class Engine:
    def __init__(self):
        self.logger = Logger()
        self.running = False
        self.paused = False
        self.nodes: List[IModule] = []  # This will hold references to all nodes in the simulation, this will be initialized in initialize_nodes()
        self.medium_service: MediumService = None  # This will be initialized in initialize_nodes()

    def _run_loop(self, stop_time=None):
        self.running = True
        self.paused = False
        timer = time_global()
        stopwatch_start_time = time.time()
        propagation_time = 0
        node_tick_time = 0

        while self.running:
            if stop_time is not None and timer.get_time() >= stop_time:
                self.running = False
                break
            if self.paused:
                self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine paused; waiting to resume")
                while self.paused and self.running:
                    time.sleep(0.1)
                if not self.running:
                    self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine stopped during pause in run")
                    break

            self.logger.add(Severity.DEBUG, Area.SIMULATOR, f"Global tick: {timer.get_time()}")  # Log the current global tick at the start of each loop iteration for debugging purposes
            # Tick all nodes, do this in parallel if needed
            node_start_time = time.time()
            current_time = timer.get_time()
            for node in self.nodes:
                node.tick(current_time)
            
            node_tick_time += time.time() - node_start_time

            propagation_start_time = time.time()
            self.medium_service.propagate_mediums(current_time) # propagate all new transmissions in the mediums and handle receptions
            propagation_time += time.time() - propagation_start_time

            #TODO change later
            # Simulate different data areas with data to export 
            # Simulate log messages
            # self.logger.add(Severity.INFO, Area.SIMULATOR, f"Status: running, time: {current_time}")
            # self.logger.add(Severity.DEBUG, Area.NODE, f"Node event at t={current_time}")
            # self.logger.add(Severity.WARNING, Area.GATEWAY, f"Gateway warning at t={current_time}")
            # # Simulate data logs with units
            # self.logger.add_data(Area.BATTERY, "level", 75 + random.uniform(-5, 5), unit="percent")
            # self.logger.add_data(Area.BATTERY, "voltage", 3.7 + random.uniform(-0.1, 0.1), unit="V")
            # self.logger.add_data(Area.CLOCK, "tick", 1 + random.randint(-1, 1), unit="ms")
            # self.logger.add_data(Area.CLOCK, "drift", random.uniform(-0.05, 0.05), unit="ms")
            # self.logger.add_data(Area.TRANCEIVER, "signal", random.uniform(0, 100), unit="dBm")
            # self.logger.add_data(Area.TRANCEIVER, "snr", random.uniform(-10, 20), unit="dB")

            timer.increment_time(1)

        elapsed_time = time.time() - stopwatch_start_time
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Engine finished running at t={timer.get_time()}")
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Total elapsed real time: {elapsed_time:.2f} seconds for {len(self.nodes)} nodes")
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Total node tick time: {node_tick_time:.2f} seconds")
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Total propagation time: {propagation_time:.2f} seconds")
                        
    def run(self):
        self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine will run indefinitely")
        import threading
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def run_for(self, time_units: int):
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Engine will run for {time_units} time units")
        timer = time_global()
        if timer.get_time() == 0:
            self.initialize_nodes()

        stop_time = timer.get_time() + time_units
        t = threading.Thread(target=self._run_loop, args=(stop_time,), daemon=True)
        t.start()

    def pause(self):
        if self.running:
            self.paused = True
            self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine paused")

    def stop(self):
        if self.running:
            self.running = False
            self.paused = False
            self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine stopped")

    def initialize_nodes(self):
        # self.medium_service = MediumService(node_neighbors={
        #     1: NodeMediumInfo(position=(0, 0), neighbors=[2]),  # Node 1 is at (0, 0) and has Node 2 as a neighbor
        #     2: NodeMediumInfo(position=(10, 0), neighbors=[1]), # Node 2 is at (10, 0) and has Node 1 as a neighbor
        # })

        # self.nodes = [
        #     Node(node_id=1, second_to_global_tick=0.01, medium_service=self.medium_service),
        #     Node(node_id=2, second_to_global_tick=0.01, medium_service=self.medium_service),
        #     # Add more nodes as needed
        # ]

        # make N nodes that ping pong in pairs and have the other as neighbor, for testing purposes
        num_nodes = 1000
        self.nodes = []
        node_neighbors = {}
        for i in range(1, num_nodes + 1):
            neighbors = []
            if i % 2 == 1 and i < num_nodes:  # Odd node, add next node as neighbor
                neighbors.append(i + 1)
            elif i % 2 == 0:  # Even node, add previous node as neighbor
                neighbors.append(i - 1)
            node_neighbors[i] = NodeMediumInfo(position=(i, 0), neighbors=neighbors)
        self.medium_service = MediumService(node_neighbors=node_neighbors)
        
        for i in range(1, num_nodes + 1):
            self.nodes.append(Node(node_id=i, second_to_global_tick=0.01, medium_service=self.medium_service))



if __name__ == "__main__":
    pass
    # engine = Engine()
    # engine.initialize_nodes()
    # engine.run_for(1000)
    # engine.logger.save_to_file()
