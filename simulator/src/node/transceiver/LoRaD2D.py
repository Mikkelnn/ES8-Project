import math
from typing import List

from custom_types import MediumTypes
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.transceiver.base_transceiver import BaseTransceiver
from logger.ILogger import ILogger
from Interfaces import ILength


class LoRaD2D(BaseTransceiver):
    def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
        joules_per_second_consumption_transmit = 0.396
        joules_per_second_consumption_receive = 0.03564
        joules_per_second_consumption_idle = 0.66E-6


        super().__init__(node_id, medium_service, local_event_queue, log, second_to_global_tick, MediumTypes.LORA_D2D, 
                         joules_per_second_consumption_transmit, joules_per_second_consumption_receive, joules_per_second_consumption_idle)

        self.__sf = 7 # Spreading factor
        self.__bandwidth = 125000 # Bandwidth in Hz
        self.__coding_rate = 1 / (4 / 5) # Coding rate (4/5, 4/6, etc.)
        self.__preamble_length = 8 # Preamble length in symbols

        self.__ts = (2 ** self.__sf) / self.__bandwidth # Symbol duration in seconds

        # Calculate the preamble time in seconds
        self.__preamble_time_ticks = (self.__preamble_length + 4.25) * self.__ts * (1 / self._second_to_global_tick)

    def _calculate_transmission_duration_ticks(self, data: ILength) -> int:
        # Calculate the number of symbols needed to transmit the data based on the spreading factor, coding rate, and data size
        N_symbols = math.ceil((data.length * 8 * self.__coding_rate) / self.__sf)
        # Calculate the total transmission time in ticks ceil to ensure we account for any partial symbol time
        symbol_time_ticks = math.ceil(N_symbols * self.__ts * (1 / self._second_to_global_tick))

        # Calculate the transmission time in global ticks based on the size of the data
        return int(symbol_time_ticks + self.__preamble_time_ticks)