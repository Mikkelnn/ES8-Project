import math
from typing import List

from simulator.src.custom_types import LocalEventSubTypes
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.node.tranceiver.baseTranceiver import BaseTranceiver
from simulator.src.simulator.global_event_queue import GlobalEventQueue


class LoRaWan(BaseTranceiver):
    def __init__(self, node_id: int, globaleventbus: GlobalEventQueue, localeventbus: LocalEventQueue, secondToGlobalTick: float):
        joules_per_second_consumption_transmit = 1
        joules_per_second_consumption_receive = 0.1
        joules_per_second_consumption_idle = 0.001

        super().__init__(node_id, globaleventbus, localeventbus, secondToGlobalTick, LocalEventSubTypes.LORA_WAN, 
                         joules_per_second_consumption_transmit, joules_per_second_consumption_receive, joules_per_second_consumption_idle)
        
        self.__sf = 7 # Spreading factor
        self.__bandwidth = 125000 # Bandwidth in Hz
        self.__coding_rate = 1 # Coding rate (1 means 4/5, 2 means 4/6, etc.)
        self.__preamble_length = 8 # Preamble length in symbols

    def _calculate_transmission_duration_ticks(self, data: List[int]) -> int:
        # Calculate the effective data rate based on SF, bandwidth, and coding rate
        effective_data_rate = (self.__bandwidth / (2 ** self.__sf)) * (4 / (4 + self.__coding_rate))
        # Calculate the preamble time in seconds
        preamble_time_seconds = (self.__preamble_length + 4.25) * (2 ** self.__sf) / self.__bandwidth
        # Calculate the transmission time in seconds based on the size of the data
        transmission_time_seconds = (len(data) * 8 / effective_data_rate) + preamble_time_seconds
        # Convert the transmission time to global ticks and apply ceiling
        transmission_time_global_ticks = int(math.ceil(transmission_time_seconds * self._second_to_global_tick))
        return transmission_time_global_ticks