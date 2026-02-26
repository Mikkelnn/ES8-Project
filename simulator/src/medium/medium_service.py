
from typing import List
from custom_types import EventNet, EventNetTypes, MediumTypes, NodeMediumInfo
from simulator.global_event_queue import GlobalEventQueue
from .lora_d2d_medium import LoraD2DMedium


class MediumService:
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: GlobalEventQueue):
        # Add medums to the service
        self.mediums = [
            LoraD2DMedium(node_neighbors, event_queue)
            # LoRaWanMedium()
        ]

    def propagate_mediums(self, current_global_tick: int):
        for medium in self.mediums:
            medium.propagate_queue(current_global_tick)
    
    def transmit(self, from_node_id: int, medium_type: MediumTypes, data: List[int], time_start_global_tick: int, time_end_global_tick: int):
        event = EventNet(node_id=from_node_id, time_start=time_start_global_tick, time_end=time_end_global_tick, data=data, type=EventNetTypes.TRANSMIT, type_medium=medium_type)
        for medium in self.mediums:
            if medium.type == medium_type:
                medium.add_transmission_event(event)
                break
    
    def cancel_transmission(self, from_node_id: int, medium_type: MediumTypes, time_start_global_tick: int, time_end_global_tick: int):
          event = EventNet(node_id=from_node_id, time_start=time_start_global_tick, time_end=time_end_global_tick, data=[], type=EventNetTypes.CANCELED, type_medium=medium_type)
          for medium in self.mediums:
            if medium.type == medium_type:
                medium.add_transmission_event(event)
                break
    
    def receive(self, to_node_id: int, medium_type: MediumTypes) -> List[EventNet]:
        for medium in self.mediums:
            if medium.type == medium_type:
                return medium.pop_received_event_for_node(to_node_id)
        return [] # Return an empty list if no medium of the specified type is found or no events are received for the node
    
