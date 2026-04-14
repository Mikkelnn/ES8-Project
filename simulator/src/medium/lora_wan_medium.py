
from custom_types import MediumTypes, NodeMediumInfo
from medium.base_medium import BaseMedium
from simulator.device_event_queue import DeviceEventQueue
from logger.ILogger import ILogger

class LoraWanMedium(BaseMedium):
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: DeviceEventQueue, log: ILogger):
        super().__init__(type=MediumTypes.LORA_WAN, event_queue=event_queue, log=log)
        self.node_neighbors = node_neighbors

    def _get_reception_node_ids(self, event):
        if event.node_id in self.node_neighbors:
            node_medium_info = self.node_neighbors[event.node_id]
            return node_medium_info.neighbors if node_medium_info.is_gateway else node_medium_info.gateways_in_range
        else:
            return []
