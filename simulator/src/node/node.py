# type: ignore
from enum import Enum

from custom_types import Area, LocalEventTypes, Severity
from Interfaces import IDevice
from logger import ILogger
from medium.medium_service import MediumService
from node.battery.battery import Battery
from node.clock.clock import Clock
from node.event_local_queue import LocalEventQueue
from node.helpers.accumulated_state import AccumulatedState
from node.protocols.V01 import V01
from node.transceiver.transceiver_service import TransceiverService


class State(Enum):
	DEAD = 1
	SLEEP = 2
	WAKE = 3


class Node(IDevice):
	def __init__(self, node_id: int, second_to_global_tick: float, medium_service: MediumService, log: ILogger):
		self.node_id = node_id
		self.local_event_queue = LocalEventQueue()
		self.accumulated_state = AccumulatedState()

		self.battery = Battery(capacity_joule=7.9, recharge_rate_joule_per_second=5.4, second_to_global_tick=second_to_global_tick)
		self.clock = Clock(self.node_id, self.local_event_queue, second_to_global_tick)
		self.transceiver = TransceiverService(self.node_id, medium_service, self.local_event_queue, second_to_global_tick, log)
		# self.protocol = PingPongProtocol(self.node_id, self.local_event_queue, second_to_global_tick, log)
		self.protocol = V01(self.node_id, self.local_event_queue, second_to_global_tick, log)
		self.state = State.WAKE
		self.log = log
		self.second_to_global_tick = second_to_global_tick

	def tick(self, current_global_tick: int) -> int | None:
		self.accumulated_state.reset()

		match self.state:
			case State.DEAD:
				pass
			case State.SLEEP:
				self.accumulated_state.update((150e-6 * self.second_to_global_tick, None))  # Base system usage
				self.accumulated_state.update(self.clock.tick(current_global_tick))
			case State.WAKE:
				self.accumulated_state.update((5.3e-3 * self.second_to_global_tick, None))  # Base system usage
				self.accumulated_state.update(self.clock.tick(current_global_tick))
				# TODO: Sensor
				self.accumulated_state.update(self.transceiver.tick(current_global_tick))
				self.accumulated_state.update(self.protocol.tick(current_global_tick))

		# battery is always evaluated and done last
		self.accumulated_state.update(self.battery.tick(current_global_tick, self.accumulated_state.power))

		node_sleep_events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_SLEEP)
		if len(node_sleep_events) > 0 and self.state == State.WAKE:
			self.state = State.SLEEP
			self.log.add(Severity.INFO, Area.NODE, current_global_tick, f"Node {self.node_id} is going to sleep...")

		node_wake_events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_WAKE_UP)
		if len(node_wake_events) > 0 and self.state == State.SLEEP:
			self.state = State.WAKE
			self.log.add(Severity.INFO, Area.NODE, current_global_tick, f"Node {self.node_id} woke up...")
			self.accumulated_state.update((0, current_global_tick + 1))  # tick next

		# deterimine if we died during the current tick
		if self.battery.is_dead() and self.state != State.DEAD:
			# Tell all modules we just died -> they need to reset and maybe do some cleanup
			self.clock.reset(current_global_tick)
			self.transceiver.reset(current_global_tick)
			self.protocol.reset(current_global_tick)
			self.local_event_queue.reset(current_global_tick)
			self.state = State.DEAD

		# deterrmine if we just came alive in this tick
		if self.state == State.DEAD and not self.battery.is_dead():
			self.state = State.WAKE  # We can decide to start in sleep mode instead if we want to test that
			self.accumulated_state.update((0, current_global_tick + 1))  # tick next

		# Clear local event bus
		self.local_event_queue.clear_events()

		# determine earliest next tick among modules
		# if there are internal events scheduled for next tick, this is the earliest
		return self.accumulated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
