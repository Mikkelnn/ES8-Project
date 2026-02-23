from typing import List
from custom_types import LocalEventTypes, MediumTypes, TranceiverState
from medium.medium_service import MediumService
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue
from node.tranceiver.LoRaD2D import LoRaD2D
from node.tranceiver.LoRaWan import LoRaWan
from node.tranceiver.baseTranceiver import BaseTranceiver


class TranceiverService(IModule):
    def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.medium_service = medium_service
        self.local_event_queue = local_event_queue
        # self.second_to_global_tick = second_to_global_tick

        self.tranceivers: List[BaseTranceiver] = [
            LoRaD2D(node_id, medium_service, local_event_queue, second_to_global_tick),
            # LoRaWan(node_id, medium_service, local_event_queue, second_to_global_tick)
        ]
        
    def tick(self, current_global_tick: int) -> float:
        current_power_consumed = 0
        tranceiver_statuses: dict[MediumTypes, TranceiverState] = {}

        for tranceiver in self.tranceivers:
            current_power_consumed += tranceiver.tick(current_global_tick)
            tranceiver_statuses[tranceiver.medium_type] = tranceiver.state
            
        self.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, sub_type=None, data=tranceiver_statuses)

        return current_power_consumed # Power consumption for this tick
    
    def reset(self, current_global_tick: int) -> None:
        for tranceiver in self.tranceivers:
            tranceiver.reset(current_global_tick=current_global_tick)
    
