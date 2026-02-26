import numpy as np
from custom_types import Area, LocalEventTypes, Severity
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue
from simulator.logger import Logger

# log = Logger()
class Clock(IModule):
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.local_event_queue = local_event_queue

        joules_per_second_consumption = 1 # TODO: Set realistic value
        self.consuption_per_tick = joules_per_second_consumption * second_to_global_tick

        # self.local_time: int = 0
        # self.local_tick: int = 0

        self.local_time_increment_per_second = 1
        self.global_ticks_per_local_time_increment = int(1 / second_to_global_tick / self.local_time_increment_per_second)
        
    def tick(self, current_global_tick: int) -> float | None:
        # self.local_tick += 1 # np.random.choice([0, 1, 2], p=[0.2, 0.6, 0.2]) # increment local tick with some drift

        # if self.local_tick >= self.global_ticks_per_local_time_increment:
        #     self.local_time += 1
        #     self.local_tick = 0

        # calculate the local time from global, this is an ideal clock
        local_time = int(current_global_tick / self.global_ticks_per_local_time_increment)

        # Puplish tick event to local event bus
        self.local_event_queue.add_event_to_current_tick(LocalEventTypes.LOCAL_TIME, local_time)

        # ideal_local_time = int(current_global_tick / self.global_ticks_per_local_time_increment)
        # log.add_data(Area.CLOCK, "clock_drift", self.local_time - ideal_local_time, "local_time_steps")
        # log.add(Severity.DEBUG, Area.CLOCK, f"Node {self.node_id} local time: {self.local_time}, local time drift: {self.local_time - ideal_local_time}")

        return (self.consuption_per_tick, None) # Power consumption for this tick
    
    def reset(self, current_global_tick: int) -> None:
        # self.local_time = 0
        # self.local_tick = 0
        pass