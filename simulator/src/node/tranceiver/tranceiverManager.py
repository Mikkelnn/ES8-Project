from simulator.src.node.Imodule import IModule
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.simulator import event_net_queue

class TranceiverManager(IModule):
    def __init__(self, node_id: int, global_event_queue: event_net_queue, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.global_event_queue = global_event_queue
        self.local_event_queue = local_event_queue
        # self.second_to_global_tick = second_to_global_tick

    def tick(self) -> float:
        return 0 # Power consumption for this tick
    
    def reset(self):
        return
    




        