import math
from typing import List

from custom_types import MediumTypes
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.transceiver.base_transceiver import BaseTransceiver
from logger.ILogger import ILogger


class LoRaD2D(BaseTransceiver):
    def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
        joules_per_second_consumption_transmit = 1
        joules_per_second_consumption_receive = 0.1
        joules_per_second_consumption_idle = 0.001

        super().__init__(node_id, medium_service, local_event_queue, log, second_to_global_tick, MediumTypes.LORA_D2D, 
                         joules_per_second_consumption_transmit, joules_per_second_consumption_receive, joules_per_second_consumption_idle)
        
        __sf = 7 # Spreading factor
        __bandwidth = 125000 # Bandwidth in Hz
        __coding_rate = 1 # Coding rate (1 means 4/5, 2 means 4/6, etc.)
        __preamble_length = 8 # Preamble length in symbols
        
        # Calculate the effective data rate based on SF, bandwidth, and coding rate
        self.__effective_data_rate_tick = (__bandwidth / (2 ** __sf)) * (4 / (4 + __coding_rate)) * self._second_to_global_tick
        # Calculate the preamble time in seconds
        self.__preamble_time_ticks = ((__preamble_length + 4.25) * (2 ** __sf) / __bandwidth) / self._second_to_global_tick

    def _calculate_transmission_duration_ticks(self, data: List[int]) -> int:
        # Calculate the transmission time in global ticks based on the size of the data
        return int(math.ceil((len(data) * 8 / self.__effective_data_rate_tick) + self.__preamble_time_ticks))