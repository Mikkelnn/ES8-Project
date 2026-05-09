import math
from typing import List

from custom_types import EventNet, EventNetTypes, MediumTypes
from Interfaces import ILength
from logger.ILogger import ILogger
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.transceiver.base_transceiver import BaseTransceiver
from node.transceiver.lora_tx_duration_calculator import LoRaTxDurationCalculator


class LoRaWan(BaseTransceiver):
    def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
        joules_per_second_consumption_transmit = 0.396
        joules_per_second_consumption_receive = 0.03564
        joules_per_second_consumption_idle = 0  # 0.66E-6 moved new estimate into WAKE in node.py

        super().__init__(node_id, medium_service, local_event_queue, log, second_to_global_tick, MediumTypes.LORA_WAN, joules_per_second_consumption_transmit, joules_per_second_consumption_receive, joules_per_second_consumption_idle)

        self.__sf = 7  # Spreading factor
        self.__bandwidth = 125000  # Bandwidth in Hz
        self.__coding_rate = 1 / (4 / 5)  # Coding rate (4/5, 4/6, etc.)
        self.__preamble_length = 8  # Preamble length in symbols

        self.__calculator = LoRaTxDurationCalculator(second_to_global_tick, self.__sf, self.__bandwidth, self.__coding_rate, self.__preamble_length)
        
    def _calculate_transmission_duration_ticks(self, data: ILength) -> int:
        return self.__calculator.get_duration(data.length)

    def _get_successful_receptions(self, current_global_tick: int) -> List[EventNet]:
        successful_receptions: List[EventNet] = []

        if self._current_reception_start_global_tick is None:
            return successful_receptions

        cancellations = [e for e in self._receive_queue if e.type == EventNetTypes.CANCELED]
        canc_by_node: dict[int, List[EventNet]] = {}
        for c in cancellations:
            canc_by_node.setdefault(c.node_id, []).append(c)

        for event in self._receive_queue:
            if event.type == EventNetTypes.CANCELED:
                continue

            if event.time_end >= current_global_tick:
                continue

            if self._current_reception_start_global_tick is not None and self._current_reception_start_global_tick > event.time_start:
                continue

            if event.node_id in canc_by_node:
                continue

            for other in self._receive_queue:
                if other is event:
                    continue
                if other.type == EventNetTypes.CANCELED:
                    continue
                if other.time_start > current_global_tick:
                    continue

                other_effective_end = other.time_end
                for c in canc_by_node.get(other.node_id, []):
                    if c.time_end > event.time_start:
                        other_effective_end = min(other_effective_end, c.time_start)

            successful_receptions.append(event)

        max_time_end = 0
        for event in successful_receptions:
            max_time_end = max(max_time_end, event.time_end)

        self._receive_queue = [e for e in self._receive_queue if e.time_start > max_time_end]

        return successful_receptions
