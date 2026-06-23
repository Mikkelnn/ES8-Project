import math
from typing import List, Set, Tuple

from custom_types import MediumTypes, NodeMediumInfo
from logger.ILogger import ILogger
from medium.base_medium import BaseMedium
from sim.device_event_queue import DeviceEventQueue


class LoraD2DMedium(BaseMedium):
    def __init__(self, node_neighbors: dict[int, NodeMediumInfo], event_queue: DeviceEventQueue, log: ILogger):
        super().__init__(type=MediumTypes.LORA_D2D, event_queue=event_queue, log=log)
        self.node_neighbors = node_neighbors  # key: node_id, value: List[node_id]
        FIX_PRECISION_FACTOR = 1 / (10**9)
        self.max_propagation_angle = 45.0 + FIX_PRECISION_FACTOR  # degrees
        self.max_hop_count = 2
        self._reach_map: dict[int, list[tuple[int, float]]] | None = None

    def set_reach_map(self, reach_map: dict[int, list[tuple[int, float]]]) -> None:
        self._reach_map = reach_map

    @staticmethod
    def build_reach_map(node_neighbors: dict, max_hop_count: int = 2, max_angle: float = 45.0) -> dict[int, list[tuple[int, float]]]:
        """Pre-compute D2D receiver lists for all regular nodes. O(N) startup, O(1) per transmission."""
        FIX_PRECISION_FACTOR = 1 / (10**9)
        angle = max_angle + FIX_PRECISION_FACTOR
        return {
            nid: LoraD2DMedium._compute_receivers(nid, node_neighbors, max_hop_count, angle)
            for nid, info in node_neighbors.items()
            if not info.is_gateway
        }

    @staticmethod
    def _compute_receivers(node_id: int, node_neighbors: dict, max_hop_count: int, max_propagation_angle: float) -> list[tuple[int, float]]:
        """Traverse up to max_hop_count hops from node_id and return [(receiver_id, rssi)]."""
        visited: Set[int] = {node_id}
        results: List[Tuple[int, float]] = []

        def traverse(current_node: int, incoming_dir: Tuple[float, float] | None, hop: int):
            if hop > max_hop_count:
                return
            if current_node not in node_neighbors:
                return
            current_info = node_neighbors[current_node]
            for neighbor in current_info.neighbors:
                if neighbor in visited:
                    continue
                if hop >= 2 and incoming_dir is not None:
                    outgoing = (
                        node_neighbors[neighbor].position[0] - current_info.position[0],
                        node_neighbors[neighbor].position[1] - current_info.position[1],
                    )
                    out_mag = math.sqrt(outgoing[0] ** 2 + outgoing[1] ** 2)
                    if out_mag >= 1e-9:
                        on = (outgoing[0] / out_mag, outgoing[1] / out_mag)
                        dot = max(-1.0, min(1.0, incoming_dir[0] * on[0] + incoming_dir[1] * on[1]))
                        if math.degrees(math.acos(dot)) >= max_propagation_angle:
                            continue
                visited.add(neighbor)
                if neighbor != node_id:
                    results.append((neighbor, LoraD2DMedium._estimate_rssi(hop)))
                if neighbor in node_neighbors:
                    dx = node_neighbors[neighbor].position[0] - current_info.position[0]
                    dy = node_neighbors[neighbor].position[1] - current_info.position[1]
                    mag = math.sqrt(dx ** 2 + dy ** 2)
                    next_dir = (dx / mag, dy / mag) if mag > 1e-9 else (0.0, 0.0)
                else:
                    next_dir = incoming_dir
                traverse(neighbor, next_dir, hop + 1)

        traverse(node_id, None, 1)
        return results

    def _get_reception_node_ids(self, event):
        if self._reach_map is not None and event.node_id in self._reach_map:
            return self._reach_map[event.node_id]
        return LoraD2DMedium._compute_receivers(event.node_id, self.node_neighbors, self.max_hop_count, self.max_propagation_angle)

    @staticmethod
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
