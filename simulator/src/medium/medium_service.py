# type: ignore
from typing import List

from custom_types import EventNet, EventNetTypes, MediumTypes, NodeMediumInfo
from logger import ILogger
from sim.device_event_queue import DeviceEventQueue

from .lora_d2d_medium import LoraD2DMedium
from .lora_wan_medium import LoraWanMedium


class MediumService:
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: DeviceEventQueue, log: ILogger):
        mediums = [LoraD2DMedium(node_neighbors, event_queue, log), LoraWanMedium(node_neighbors, event_queue, log)]
        self._mediums_by_type = {m.type: m for m in mediums}

    def propagate_mediums(self, current_global_tick: int):
        for medium in self._mediums_by_type.values():
            medium.propagate_queue(current_global_tick)

    def transmit(self, from_node_id: int, medium_type: MediumTypes, data: List[int], time_start_global_tick: int, time_end_global_tick: int):
        event = EventNet(node_id=from_node_id, time_start=time_start_global_tick, time_end=time_end_global_tick, data=data, type=EventNetTypes.TRANSMIT, type_medium=medium_type)
        self._mediums_by_type[medium_type].add_transmission_event(event)

    def cancel_transmission(self, from_node_id: int, medium_type: MediumTypes, time_start_global_tick: int, time_end_global_tick: int):
        event = EventNet(node_id=from_node_id, time_start=time_start_global_tick, time_end=time_end_global_tick, data=[], type=EventNetTypes.CANCELED, type_medium=medium_type)
        self._mediums_by_type[medium_type].add_transmission_event(event)

    def receive(self, to_node_id: int, medium_type: MediumTypes) -> List[EventNet]:
        medium = self._mediums_by_type.get(medium_type)
        if medium is None:
            return []
        return medium.pop_received_event_for_node(to_node_id)
