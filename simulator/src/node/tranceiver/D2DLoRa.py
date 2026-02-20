import math
from typing import List

from simulator.src.custom_types import LocalEventSubTypes
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.node.tranceiver.baseTranceiver import BaseTranceiver
from simulator.src.simulator import event_net_queue


class D2DLoRa(BaseTranceiver):
    def __init__(self, node_id: int, globaleventbus: event_net_queue, localeventbus: LocalEventQueue, secondToGlobalTick: float):
        self.__consuption_per_tick_idle = 0.001 * secondToGlobalTick # TODO: Set realistic value
        self.__consuption_per_tick_transmit = 0.01 * secondToGlobalTick # TODO: Set realistic value
        self.__consuption_per_tick_receive = 0.01 * secondToGlobalTick

        super().__init__(node_id, globaleventbus, localeventbus, secondToGlobalTick, LocalEventSubTypes.D2D_LORA, 
                         self.__consuption_per_tick_transmit, self.__consuption_per_tick_receive, self.__consuption_per_tick_idle)
        
        self.__sf = 7 # Spreading factor
        self.__bandwidth = 125000 # Bandwidth in Hz
        self.__coding_rate = 1 # Coding rate (1 means 4/5, 2 means 4/6, etc.)

    def _calculate_transmission_duration_ticks(self, data: List[int]) -> int:
        # Calculate the effective data rate based on SF, bandwidth, and coding rate
        effective_data_rate = (self.__bandwidth / (2 ** self.__sf)) * (4 / (4 + self.__coding_rate))
        # Calculate the transmission time in seconds based on the size of the data
        transmission_time_seconds = len(data) * 8 / effective_data_rate
        # Convert the transmission time to global ticks and apply ceiling
        transmission_time_global_ticks = int(math.ceil(transmission_time_seconds * self._second_to_global_tick))
        return transmission_time_global_ticks