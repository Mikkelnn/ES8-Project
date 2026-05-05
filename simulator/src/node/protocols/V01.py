# type: ignore
from dataclasses import dataclass
from enum import Enum
from random import Random

from pyparsing import cast

from custom_types import (
	Area,
	LocalClockInfo,
	LocalEventSubTypes,
	LocalEventTypes,
	LoRaD2DFrame,
	LoRaD2DFrameType,
	MediumTypes,
	Severity,
	TransceiverState,
)
from logger.ILogger import ILogger
from loraWanFrameHelper import LoRaWanPHYPayload, make_uplink
from node.event_local_queue import LocalEventQueue
from node.Imodule import IModule


class State(Enum):
	INITIAL = 0
	SKIP_NEXT_TICK = 1  # used to skip next tick when  sleeping is scheduled, set the stae here to the one that should be executed after waking up

	TRY_CONNECT_GATEWAY = 2
	GATEWAY_TX_WAIT_COMPLETE = 3
	GATEWAY_RX = 4

	D2D_DISCOVERY = 5
	D2D_RX = 6
	D2D_TX_WAIT_COMPLETE = 7

	PACKET_FORWARDING = 8


@dataclass
class D2DNeighborInfo:
	neighbor_id: int
	hopcount_to_gateway: int
	last_seen: int  # local time when we last saw this neighbor, used to remove stale neighbors from the known_neighbors list after some time


class V01(IModule):
	"This implement simple WAN GW discovery and a simple D2D hopcount establishment."

	def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float, log: ILogger):
		self.node_id = node_id
		self.local_event_queue = local_event_queue
		self.second_to_global_tick = second_to_global_tick
		self.log = log

		self.slot_period = 60_000  # 1 minute slot period
		self.slot_duration = 100  # 100 ms slots
		self.slot_count = 5
		self.lora_wan_slot_inerleave = 60  # tx to gateway every 60 minutes when we have a connection to the gateway

		self.reset(0)
		self.random = Random(self.node_id)

	def tick(self, current_global_tick: int) -> float:
		current_local_clock_info = cast(LocalClockInfo, self.local_event_queue.get_current_events_by_type(LocalEventTypes.LOCAL_TIME)[0].data)
		current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data  # Always populated by transceiver service before this protocol is ticked, so we can be sure to have it.
		current_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA)

		match self.state:
			case State.SKIP_NEXT_TICK:
				self.state = self.next_state
				self.next_state = None

			case State.INITIAL:
				# set to sleep for 45 min to ensure battery is charged.
				# to reduce chance of first and second node of getting same hopcount
				rnd = self.random.choices([0, 1, 3, 5], k=3)
				rnd = int(sum(rnd) / 3)
				self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node: {self.node_id} cose {rnd} to add to sleep")
				self.__sleep(sleep_duration_milliseconds=(45 + rnd) * 60 * 1000, next_state=State.TRY_CONNECT_GATEWAY)

			case State.TRY_CONNECT_GATEWAY:
				# try to connect to gateway by sending a message on the LoRaWAN channel, we will not do anything with the response in this simple protocol, we just want to test that we can send and receive messages on the LoRaWAN channel and that the gateway can respond.
				lora_wan_frame = make_uplink(dev_addr=self.node_id, frame_count=0, payload=[], confirmed=True)  # The content of the message does not matter in this protocol, so we just send a list with one element.)
				self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=MediumTypes.LORA_WAN, data=lora_wan_frame)
				self.state = State.GATEWAY_TX_WAIT_COMPLETE
				self.log.add(Severity.DEBUG, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} is trying to connect to gateway by sending a message on the LoRaWAN channel...")

			case State.GATEWAY_TX_WAIT_COMPLETE:
				if current_transceiver_states[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
					# wait for 1 second after tx as per LoRaWAN specification for rx1 and add a small guard time of 10 ms to ensure we do not miss the rx window due to clock drift
					self.__sleep(sleep_duration_milliseconds=1000 - 10, next_state=State.GATEWAY_RX)

			case State.GATEWAY_RX:
				if current_transceiver_states[MediumTypes.LORA_WAN] == TransceiverState.IDLE:
					self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.RECEIVING)
					self.local_event_queue.add_event_to_next_tick(LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=1010)  # Set timer to wake up after the rx window, we set it to 1100 ms to ensure we wake up after the rx window is closed.

				timer_1 = current_local_clock_info.timer_1_remaining
				if timer_1 is not None and timer_1 <= 0:
					self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
					self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} did not receive any response from gateway, will try to connect using D2D...")
					self.state = State.D2D_DISCOVERY

				if len(current_receptions) > 0:
					reception_data = cast(LoRaWanPHYPayload, current_receptions[0].data)
					if reception_data.mac_payload.dev_addr == self.node_id and reception_data.is_ack():
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
						self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} received ACK from gateway!")
						# We did receive the ACK from the gateway, we can now set our hopcount to 0 and start doing D2D syncs to establish hopcounts to neighbors.
						self.gw_hopcount = 0

						# maybe schedule based on GPS time from gateway....
						time_to_next_minute = 60_000 - (current_local_clock_info.current_local_time % 60_000)
						self.__sleep(sleep_duration_milliseconds=time_to_next_minute, next_state=State.PACKET_FORWARDING)

			case State.D2D_DISCOVERY:
				timer_1 = current_local_clock_info.timer_1_remaining
				if timer_1 is None:  # we have not started discovery yet, so start by listening for D2D messages
					self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)
					self.local_event_queue.add_event_to_next_tick(LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.slot_period + (2 * self.slot_count * self.slot_duration))

				if len(current_receptions) > 0:
					reception_data = cast(LoRaD2DFrame, current_receptions[0].data)
					if reception_data.type == LoRaD2DFrameType.CURRENT_HOP_COUNT:
						neighbor_info = D2DNeighborInfo(neighbor_id=reception_data.source_node_id, hopcount_to_gateway=int.from_bytes(reception_data.payload, "big"), last_seen=current_local_clock_info.current_local_time)

						# update known neighbors list with new info or add new neighbor if we have not seen it before
						existing_neighbor_index = next((index for index, neighbor in enumerate(self.known_neighbors) if neighbor.neighbor_id == neighbor_info.neighbor_id), None)
						if existing_neighbor_index is not None:
							self.known_neighbors[existing_neighbor_index] = neighbor_info
						else:
							self.known_neighbors.append(neighbor_info)

						# if we have two devices with consequtive hopcounts we can set our hopcount to one more than the highest hopcount we have seen.
						hopcounts = set(neighbor.hopcount_to_gateway for neighbor in self.known_neighbors)
						for hopcount in hopcounts:
							if (hopcount + 1) in hopcounts:
								self.gw_hopcount = hopcount + 2
								self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set its hopcount to gateway to {self.gw_hopcount} based on neighbors info!")
								# TODO: we can end rx mode and sleep until next slot to start packet forwarding as we now have a connection to the gateway through our neighbors and can start forwarding packets.
								# TODO: we should handle case after death where all four nodes around us is alive, here we should set our hopcount to the missing
								break

				# end of rx, if no or only single neighbor we sleep for some time and then try again
				if timer_1 is not None and timer_1 == 0:
					self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
					# if only received single with hopcount 0 we can assume we are 1 hop away from the gateway and set our hopcount to 1
					if len(self.known_neighbors) == 1 and self.known_neighbors[0].hopcount_to_gateway == 0:
						self.gw_hopcount = 1
						self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} set its hopcount to gateway to {self.gw_hopcount} based on single neighbor with hopcount 0!")

					if self.gw_hopcount < 65535:
						self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished D2D discovery with hopcount to gateway {self.gw_hopcount}!")
						# TODO: maybe schedule based on GPS time from gateway.... Here it should be based on rx time of the messages from neighbors to ensure we are in sync with them, but for simplicity we just schedule based on our local clock.
						time_to_next_minute = 60_000 - (current_local_clock_info.current_local_time % 60_000)
						self.__sleep(sleep_duration_milliseconds=time_to_next_minute, next_state=State.PACKET_FORWARDING)
					else:
						# sleep for 25 min and try again - ensure power in battery
						self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} finished D2D discovery with NO hopcount to gateway, will try again later!")
						self.__sleep(sleep_duration_milliseconds=25 * 60 * 1000, next_state=State.D2D_DISCOVERY)

			case State.PACKET_FORWARDING:
				if len(self.d2d_packet_buffer) == 0:
					# as we dont have scheduled data we just tx current hopcount
					self.d2d_packet_buffer.append(
						LoRaD2DFrame(
							source_node_id=self.node_id,
							destination_node_id=0xFFFFFFFF,  # broadcast
							type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
							payload=self.gw_hopcount.to_bytes(2, "big"),
						)
					)

				# start or chage slot
				if current_local_clock_info.timer_1_remaining is None or current_local_clock_info.timer_1_remaining == 0:
					self.current_slot = self.current_slot + 1
					if self.current_slot < self.slot_count:
						self.local_event_queue.add_event_to_next_tick(LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_1, data=self.slot_duration)
						if self.current_slot == self.gw_hopcount % self.slot_count:  # add a guard time of 10 ms before TX
							self.local_event_queue.add_event_to_next_tick(LocalEventTypes.SET_TIMER, sub_type=LocalEventSubTypes.TIMER_2, data=10)
					else:
						# we have gone through all slots
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_WAN, data=TransceiverState.IDLE)
						self.current_slot = -1
						self.slot_period_counter = self.slot_period_counter + 1
						if self.slot_period_counter >= self.lora_wan_slot_inerleave:
							self.slot_period_counter = 0
						self.__sleep(sleep_duration_milliseconds=self.slot_period - self.slot_count * self.slot_duration, next_state=State.PACKET_FORWARDING)

					return (0, None)

				if self.current_slot == self.gw_hopcount % self.slot_count:  # tx slot
					medium = MediumTypes.LORA_D2D
					tx_buffer = self.d2d_packet_buffer

					if self.gw_hopcount == 0 and self.slot_period_counter % self.lora_wan_slot_inerleave == 0:
						medium = MediumTypes.LORA_WAN
						tx_buffer = self.wan_packet_buffer
						if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
							self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.IDLE)

					if current_transceiver_states[medium] == TransceiverState.RECEIVING:
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=medium, data=TransceiverState.IDLE)

					if (current_local_clock_info.timer_2_remaining is None or current_local_clock_info.timer_2_remaining == 0) and current_transceiver_states[medium] != TransceiverState.TRANSMITTING and len(tx_buffer) > 0:
						# TODO: ensure we have time left in window to tx next packet in buffer, if not we should wait for next slot to tx
						packet = tx_buffer.pop(0)  # send the oldest packet in the buffer
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA, sub_type=medium, data=packet)

				else:  # receive in other slots
					if current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.RECEIVING:
						self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.TRANCEIVER_SET_STATE, sub_type=MediumTypes.LORA_D2D, data=TransceiverState.RECEIVING)

					# hadle received packets
					for reception in current_receptions:
						reception_data = cast(LoRaD2DFrame, reception.data)
						# TODO: handle acks and retransmissions in a real protocol, but for simplicity we just forward the packet and hope for the best.
						# TODO: update last seen for neighbors when we receive packets from them to ensure we do not remove them from our known_neighbors list due to timeout
						if reception_data.type == LoRaD2DFrameType.DATA_TO_GW and reception_data.destination_node_id == self.node_id:
							# if we receive a packet that is destined to the gateway, we should add it to LoRaWAN queue if we have no connection to the gateway,
							# but if we have a hopcount to the gateway we can just forward it to our neighbors with lower hopcount to the gateway
							if self.gw_hopcount > 0 and self.gw_hopcount < 65535:
								# we have a connection to the gateway through our neighbors, so we can just forward the packet to our neighbors with lower hopcount to the gateway
								reception_data.destination_node_id = self.known_neighbors[0].neighbor_id
								self.d2d_packet_buffer.append(reception_data)
							elif self.gw_hopcount == 0:
								# we do have a connection to the gateway, so we can just add the packet to the LoRaWAN queue to be sent to the gateway
								self.wan_packet_buffer.append(make_uplink(dev_addr=self.node_id, frame_count=0, payload=reception_data.payload, confirmed=False))

		# return no next tick as this module will run whenever we receive a message or a timer expires.
		return (0, None)  # Power consumption for this tick

	def __sleep(self, sleep_duration_milliseconds: int, next_state: State):
		self.local_event_queue.add_event_to_next_tick(type=LocalEventTypes.NODE_SLEEP_FOR, sub_type=None, data=sleep_duration_milliseconds)
		self.next_state = next_state
		self.state = State.SKIP_NEXT_TICK

	def reset(self, current_global_tick: int) -> None:
		self.state = State.INITIAL
		self.next_state = None
		self.slot_period_counter = 0
		self.current_slot = -1  # trach the slot we are in to know when to transmit and listen

		# This is the maximum value for a uint16, we use this to indicate that we do not have a connection to the gateway yet.
		# Once we have a connection to the gateway, we will set this to 0 and start doing D2D syncs to establish hopcounts to neighbors.
		# If we do not receive an ACK from the gateway we try to connect using D2D
		self.gw_hopcount = 65535
		self.known_neighbors: list[D2DNeighborInfo] = []
		self.d2d_packet_buffer: list[LoRaD2DFrame] = []
		self.wan_packet_buffer: list[LoRaWanPHYPayload] = []
