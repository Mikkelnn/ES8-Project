
from typing import Tuple, List, Set
import math
from custom_types import MediumTypes, NodeMediumInfo
from medium.base_medium import BaseMedium
from simulator.device_event_queue import DeviceEventQueue
from logger.ILogger import ILogger

class LoraD2DMedium(BaseMedium):
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: DeviceEventQueue, log: ILogger):
        super().__init__(type=MediumTypes.LORA_D2D, event_queue=event_queue, log=log)
        self.node_neighbors = node_neighbors # key: node_id, value: List[node_id]
        self.max_propagation_angle = 45.0 # degrees
        self.max_hop_count = 2

    def _get_reception_node_ids(self, event):

        visited: Set[int] = {event.node_id}
        results: List[Tuple[int, float]] = []

        def traverse(current_node: int, incoming_dir: Tuple[float, float] | None, hop: int):
            if hop > self.max_hop_count:
                return
            if current_node not in self.node_neighbors:
                return

            current_info = self.node_neighbors[current_node]
            for neighbor in current_info.neighbors:
                if neighbor in visited:
                    continue

                # On hop >= 2, check deviation angle from incoming direction
                if hop >= 2 and incoming_dir is not None:
                    deviation = self._calculate_deviation_angle(
                        incoming_dir,
                        self.node_neighbors[neighbor].position,
                        current_info.position
                    )
                    if deviation > self.max_propagation_angle:
                        continue

                visited.add(neighbor)
                if neighbor != event.node_id:
                    rssi = self._estimate_rssi(hop)
                    results.append((neighbor, rssi))

                # Calculate outgoing direction for next hop
                if neighbor in self.node_neighbors:
                    dx = self.node_neighbors[neighbor].position[0] - current_info.position[0]
                    dy = self.node_neighbors[neighbor].position[1] - current_info.position[1]
                    mag = math.sqrt(dx**2 + dy**2)
                    if mag > 1e-9:
                        next_dir = (dx / mag, dy / mag)
                    else:
                        next_dir = (0.0, 0.0)
                else:
                    next_dir = incoming_dir

                traverse(neighbor, next_dir, hop + 1)

        traverse(event.node_id, None, 1)
        return results

    def _calculate_deviation_angle(self, incoming_direction: Tuple[float, float], outgoing_node_pos: Tuple[int, int], current_node_pos: Tuple[int, int]) -> float:
        """Calculate deviation angle between incoming wave direction and outgoing path.

        Parameters:
        - incoming_direction: (dx, dy) normalized vector of incoming wave
        - outgoing_node_pos: position of next node
        - current_node_pos: position of current (junction) node
        
        Returns deviation angle in degrees [0, 180].
        """
        # outgoing vector
        outgoing = (outgoing_node_pos[0] - current_node_pos[0], outgoing_node_pos[1] - current_node_pos[1])
        out_mag = math.sqrt(outgoing[0]**2 + outgoing[1]**2)
        if out_mag < 1e-9:
            return 0.0
        
        # normalize outgoing
        outgoing_norm = (outgoing[0] / out_mag, outgoing[1] / out_mag)
        
        # dot product
        dot = incoming_direction[0] * outgoing_norm[0] + incoming_direction[1] * outgoing_norm[1]
        dot = max(-1.0, min(1.0, dot))
        return math.degrees(math.acos(dot))

    def _estimate_rssi(hop_count, base_rssi=-40, decay=12):
        """
        Estimate RSSI from hop count.

        Args:
            hop_count (int): Number of hops (>=1)
            base_rssi (float): Estimated RSSI at 1 hop
            decay (float): Signal degradation factor per log2 hop

        Returns:
            float: Estimated RSSI in dBm
        """
        if hop_count < 1:
            raise ValueError("hop_count must be >= 1")

        return base_rssi - decay * math.log2(hop_count)
