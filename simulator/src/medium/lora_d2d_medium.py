
from typing import List
from custom_types import MediumTypes, NodeMediumInfo
from medium.base_medium import BaseMedium


class LoraD2DMedium(BaseMedium):
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo]):
        super().__init__(type=MediumTypes.LORA_D2D)
        self.node_neighbors = node_neighbors # key: node_id, value: List[node_id]

    def _get_reception_node_ids(self, event):
        if event.node_id in self.node_neighbors:
            return self.node_neighbors[event.node_id].neighbors # TODO implement correctly currently only direct neighbors
        else:
            return []