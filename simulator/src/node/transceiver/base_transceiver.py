# type: ignore
from abc import abstractmethod
from typing import List

from custom_types import (
	Area,
	EventNet,
	LocalEventTypes,
	MediumTypes,
	Severity,
	TransceiverState,
)
from Interfaces import ILength
from logger.ILogger import ILogger
from medium.medium_service import MediumService
from node.event_local_queue import LocalEventQueue
from node.Imodule import IModule


class BaseTransceiver(IModule):
	def __init__(self, node_id: int, medium_service: MediumService, local_event_queue: LocalEventQueue, log: ILogger, second_to_global_tick: float, medium_type: MediumTypes, joules_per_second_consumption_transmit: float, joules_per_second_consumption_receive: float, joules_per_second_consumption_idle: float):

		self.state = TransceiverState.IDLE
		self.medium_type = medium_type
		self._second_to_global_tick = second_to_global_tick

		self._node_id = node_id
		self._medium_service = medium_service
		self._local_event_queue = local_event_queue
		self.log = log

		self._current_transmission_end_global_tick = 0
		self._current_reception_start_global_tick: int | None = None
		self._receive_queue: List[EventNet] = []

		self._consuption_per_tick_transmit = joules_per_second_consumption_transmit * second_to_global_tick
		self._consuption_per_tick_receive = joules_per_second_consumption_receive * second_to_global_tick
		self._consuption_per_tick_idle = joules_per_second_consumption_idle * second_to_global_tick

	def tick(self, current_global_tick) -> tuple[float, int | None]:
		self._housekeep_receive_queue(current_global_tick)
		self._receive_queue.extend(self._medium_service.receive(self._node_id, self.medium_type))

		state_change = self._local_event_queue.get_current_events_by_type(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=self.medium_type)
		transmit_data_events = self._local_event_queue.get_current_events_by_type(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=self.medium_type)

		if state_change:
			next_state = state_change[0].data
			if next_state != self.state:
				self._cancel_transmission(current_global_tick)  # If we are changing state, we should not have any ongoing transmission. Just to be sure, cancel any transmission if it exists.
				self._cancel_reception(current_global_tick)  # If we are changing state, we should not have any
				self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} changing state of {self.medium_type} from {self.state} to {next_state}")
				self.state = next_state

		if self.state == TransceiverState.IDLE:
			if transmit_data_events:
				# For simplicity, we assume that if multiple transmit events are triggered in the same tick, we only handle one and ignore the rest.
				# In a more complex implementation, we might want to queue these or handle them in some other way.
				event = transmit_data_events[0]
				transmission_duration_ticks = self._calculate_transmission_duration_ticks(event.data)
				self._current_transmission_end_global_tick = current_global_tick + transmission_duration_ticks
				self._medium_service.transmit(self._node_id, self.medium_type, event.data, current_global_tick, self._current_transmission_end_global_tick)
				self.state = TransceiverState.TRANSMITTING
				self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} started transmitting on {self.medium_type} with data {event.data} for a duration of {transmission_duration_ticks} ticks (until global tick {self._current_transmission_end_global_tick})")

		if self.state == TransceiverState.TRANSMITTING:
			# Check if we have finished transmitting
			if current_global_tick >= self._current_transmission_end_global_tick:
				self._current_transmission_end_global_tick = 0
				self.state = TransceiverState.IDLE
				self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} finished transmitting on {self.medium_type}")

		if self.state == TransceiverState.RECEIVING:
			# just changed to receiving state, set the reception start global tick if not already set
			if self._current_reception_start_global_tick is None:
				self._current_reception_start_global_tick = current_global_tick

			received_events = self._get_successful_receptions(current_global_tick)
			for event in received_events:
				self._local_event_queue.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, event.data, sub_type=self.medium_type)
				self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} successfully received data {event.data} on {self.medium_type} from node {event.node_id}")

		self.log.add(Severity.DEBUG, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} transceiver {self.medium_type} state: {self.state}, current reception queue: {[{'from_node': e.node_id, 'time_start': e.time_start, 'time_end': e.time_end, 'type': e.type} for e in self._receive_queue]}")

		match self.state:
			case TransceiverState.IDLE:
				return (self._consuption_per_tick_idle, None)
			case TransceiverState.TRANSMITTING:
				return (self._consuption_per_tick_transmit, self._current_transmission_end_global_tick)
			case TransceiverState.RECEIVING:
				return (self._consuption_per_tick_receive, None)

	def reset(self, current_global_tick) -> None:
		self._cancel_transmission(current_global_tick)  # Cancel any ongoing transmission
		self._cancel_reception(current_global_tick)  # Cancel any ongoing reception

	@abstractmethod
	def _calculate_transmission_duration_ticks(self, data: ILength) -> int:
		pass

	def _cancel_transmission(self, current_global_tick):
		# Logic to determine if a transmission can be cancelled (e.g., if the node dies during transmission)
		if self._current_transmission_end_global_tick == 0:
			return

		self._medium_service.cancel_transmission(self._node_id, self.medium_type, current_global_tick, self._current_transmission_end_global_tick)
		self._current_transmission_end_global_tick = 0
		self.state = TransceiverState.IDLE
		self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} cancelled transmission on {self.medium_type}")

	def _cancel_reception(self, current_global_tick: int):
		if self._current_reception_start_global_tick is None:
			return

		self._current_reception_start_global_tick = None
		self.state = TransceiverState.IDLE
		self.log.add(Severity.INFO, Area.TRANCEIVER, current_global_tick, f"Node {self._node_id} cancelled reception on {self.medium_type}")

	def _housekeep_receive_queue(self, current_global_tick):
		# If the event is still ongoing, we keep it in the receive queue.
		# If it has ended and we are not currently receiving, we remove it from the receive queue.
		for event in reversed(self._receive_queue):  # Iterate in reverse to safely remove items from the list while iterating
			if event.time_end <= current_global_tick and self._current_reception_start_global_tick is None:
				self._receive_queue.remove(event)

	@abstractmethod
	def _get_successful_receptions(self, current_global_tick) -> List[EventNet]:
		pass
