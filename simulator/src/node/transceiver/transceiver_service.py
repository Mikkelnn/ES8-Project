from typing import List

from custom_types import Area, LocalEventTypes, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.helpers.accumulated_state import AccumulatedState
from node.Imodule import IModule
from node.transceiver.base_transceiver import BaseTransceiver
from node.transceiver.LoRaD2D import LoRaD2D
from node.transceiver.LoRaWan import LoRaWan


class TransceiverService(IModule):
	def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
		self.node_id = node_id
		self.medium_service = medium_service
		self.local_event_queue = local_event_queue
		self.log = log
		# self.second_to_global_tick = second_to_global_tick

		self.accumulated_state: AccumulatedState = AccumulatedState()
		self.transceivers: List[BaseTransceiver] = [LoRaD2D(node_id, medium_service, local_event_queue, second_to_global_tick, log), LoRaWan(node_id, medium_service, local_event_queue, second_to_global_tick, log)]

	def tick(self, current_global_tick: int) -> float:
		self.accumulated_state.reset()
		transceiver_statuses: dict[MediumTypes, TransceiverState] = {}

		for transceiver in self.transceivers:
			self.accumulated_state.update(transceiver.tick(current_global_tick))
			transceiver_statuses[transceiver.medium_type] = transceiver.state

		self.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, sub_type=None, data=transceiver_statuses)
		self.__log_warnings(transceiver_statuses)

		return self.accumulated_state.get_accumulated()

	def reset(self, current_global_tick: int) -> None:
		for transceiver in self.transceivers:
			transceiver.reset(current_global_tick=current_global_tick)

	def __log_warnings(self, transceiver_statuses: dict[MediumTypes, TransceiverState]):
		if MediumTypes.LORA_D2D in transceiver_statuses and MediumTypes.LORA_WAN in transceiver_statuses:
			if transceiver_statuses[MediumTypes.LORA_D2D] != TransceiverState.IDLE and transceiver_statuses[MediumTypes.LORA_WAN] != TransceiverState.IDLE:
				message = f"Node {self.node_id} is transmitting/receiving on both LoRaD2D and LoRaWan at the same time, this should not happen!"
				self.log.add(Severity.WARNING, Area.TRANCEIVER, message)
