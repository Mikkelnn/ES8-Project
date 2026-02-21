from typing import List
from simulator.src.custom_types import LocalEventTypes
from simulator.src.node.Imodule import IModule
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.node.tranceiver import LoRaD2D
from simulator.src.node.tranceiver.LoRaWan import LoRaWan
from simulator.src.node.tranceiver.baseTranceiver import BaseTranceiver
from simulator.src.simulator.global_event_queue import GlobalEventQueue

class TranceiverManager(IModule):
    def __init__(self, node_id: int, global_event_queue: GlobalEventQueue, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.global_event_queue = global_event_queue
        self.local_event_queue = local_event_queue
        # self.second_to_global_tick = second_to_global_tick

        self.tranceivers: List[BaseTranceiver] = []
        self.tranceivers.append(LoRaD2D(node_id, global_event_queue, local_event_queue, second_to_global_tick))
        self.tranceivers.append(LoRaWan(node_id, global_event_queue, local_event_queue, second_to_global_tick))

    def tick(self, current_global_tick: int) -> float:
        current_power_consumed = 0
        tranceiver_statuses = {}

        for tranceiver in self.tranceivers:
            current_power_consumed += tranceiver.tick(current_global_tick=current_global_tick)
            tranceiver_statuses[tranceiver.local_event_sub_type] = tranceiver.state
            
        self.local_event_queue.push_event(type=LocalEventTypes.TRANCEIVER_STATUS, sub_type=None, data=tranceiver_statuses)

        return current_power_consumed # Power consumption for this tick
    
    def reset(self, current_global_tick: int) -> None:
        for tranceiver in self.tranceivers:
            tranceiver.reset(current_global_tick=current_global_tick)