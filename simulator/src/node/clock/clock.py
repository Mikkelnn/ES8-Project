from simulator.src.custom_types import LocalEventTypes
from simulator.src.node.Imodule import IModule
from simulator.src.node.event_local_queue import LocalEventQueue

class Clock(IModule):
    def __init__(self, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.local_event_queue = local_event_queue
        self.second_to_global_tick = second_to_global_tick
        self.joules_per_second_consumption = 1 # TODO: Set realistic value
        self.consuption_per_tick = self.joules_per_second_consumption * self.second_to_global_tick

        self.local_time: int = 0
        self.local_tick: int = 0
        
    def tick(self, current_global_tick: int) -> float:
        self.local_tick += 1 # increment local tick TODO with some drift

        if self.local_tick >= 100:
            self.local_time += 1
            self.local_tick = 0

        # Puplish tick event to local event bus
        self.local_event_queue.add_event_to_current_tick(LocalEventTypes.LOCALTIME, self.local_time)

        return self.consuption_per_tick # Power consumption for this tick
    
    def reset(self, current_global_tick: int) -> None:
        self.local_time = 0
        self.local_tick = 0