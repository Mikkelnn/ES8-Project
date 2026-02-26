from typing import List
from custom_types import Area, LocalEventTypes, MediumTypes, Severity, TranceiverState
from medium.medium_service import MediumService
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue
from node.tranceiver.LoRaD2D import LoRaD2D
from node.tranceiver.LoRaWan import LoRaWan
from node.helpers.accumulated_state import AccumulatedState
from node.tranceiver.base_tranceiver import BaseTranceiver
from simulator.logger import Logger

# log = Logger()

class TranceiverService(IModule):
    def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.medium_service = medium_service
        self.local_event_queue = local_event_queue
        # self.second_to_global_tick = second_to_global_tick

        self.accumulated_state: AccumulatedState = AccumulatedState()
        self.tranceivers: List[BaseTranceiver] = [
            LoRaD2D(node_id, medium_service, local_event_queue, second_to_global_tick),
            # LoRaWan(node_id, medium_service, local_event_queue, second_to_global_tick)
        ]

        
    def tick(self, current_global_tick: int) -> float:
        self.accumulated_state.reset()
        tranceiver_statuses: dict[MediumTypes, TranceiverState] = {}

        for tranceiver in self.tranceivers:
            self.accumulated_state.update(tranceiver.tick(current_global_tick))
            tranceiver_statuses[tranceiver.medium_type] = tranceiver.state
            
        self.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, sub_type=None, data=tranceiver_statuses)
        # self.__log_warnings(tranceiver_statuses)

        return self.accumulated_state.get_accumulated()
    
    def reset(self, current_global_tick: int) -> None:
        for tranceiver in self.tranceivers:
            tranceiver.reset(current_global_tick=current_global_tick)
    

    def __log_warnings(self, tranceiver_statuses: dict[MediumTypes, TranceiverState]):
        if MediumTypes.LORA_D2D in tranceiver_statuses and MediumTypes.LORA_WAN in tranceiver_statuses:
            if tranceiver_statuses[MediumTypes.LORA_D2D] != TranceiverState.IDLE and tranceiver_statuses[MediumTypes.LORA_WAN] != TranceiverState.IDLE:
                message = f"Node {self.node_id} is transmitting/receiving on both LoRaD2D and LoRaWan at the same time, this should not happen!"
                # log.add(Severity.WARNING, Area.TRANCEIVER, message)
