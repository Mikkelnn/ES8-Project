
from typing import List
from custom_types import MediumTypes, NodeMediumInfo
from medium.base_medium import BaseMedium
from simulator.global_event_queue import GlobalEventQueue
from logger.ILogger import ILogger

class LoraD2DMedium(BaseMedium):
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: GlobalEventQueue, log: ILogger):
        super().__init__(type=MediumTypes.LORA_D2D, event_queue=event_queue, log=log)
        self.node_neighbors = node_neighbors # key: node_id, value: List[node_id]

    def _get_reception_node_ids(self, event):
        if event.node_id in self.node_neighbors:
            return self.node_neighbors[event.node_id].neighbors # TODO implement correctly currently only direct neighbors
        else:
            return []