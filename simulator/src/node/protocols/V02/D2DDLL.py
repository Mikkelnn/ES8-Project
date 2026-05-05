from dataclasses import dataclass
from typing import List

from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, LoRaD2DFrame, LoRaD2DFrameType, MediumTypes, Severity, TransceiverState
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue


@dataclass
class D2DNeighborInfo:
	neighbor_id: int
	hopcount_to_gateway: int
	last_seen: int


class D2DDLL:
	DISCOVERY_TIMEOUT_MS = 60_000 + 10 * 1000

    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, log: ILogger,
        slot_duration: int = 100, slot_count: int = 5):

        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log
        self.slot_duration = slot_duration
        self.slot_count = slot_count
        self.current_slot = -1
        self.current_tx_slot = -1
        self.reset(0)

    @property
    def link_established(self) -> bool:
        return self.hopcount_to_gateway < 65535

    def reset(self, current_global_tick: int) -> None:
        self.hopcount_to_gateway = 65535
        self.known_neighbors: List[D2DNeighborInfo] = []
        self.discovery_started = False
        self.packet_buffer: List[LoRaD2DFrame] = []
        self.current_slot = -1
        self.current_tx_slot = -1

	def enqueue_payload(self, payload: bytes) -> None:
		self.packet_buffer.append(
			LoRaD2DFrame(
				source_node_id=self.node_id,
				destination_node_id=0xFFFFFFFF,
				type=LoRaD2DFrameType.DATA_TO_GW,
				payload=payload,
			)
		)

    def tick(self, current_global_tick: int, current_local_clock_info: LocalClockInfo) -> bool:

        current_transceiver_states = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_STATUS)[0].data
        current_receptions = self.local_event_queue.get_current_events_by_type(LocalEventTypes.TRANCEIVER_RECEIVED_DATA, MediumTypes.LORA_D2D)

        self._run_discovery(current_global_tick, current_local_clock_info, current_receptions)
        period_finished = self._advance_slot(current_local_clock_info)

        if self.current_slot >= 0:
            self._run_slot(current_global_tick, current_local_clock_info, current_transceiver_states)

        return period_finished

	def _run_discovery(self, current_global_tick: int, current_local_clock_info: LocalClockInfo, current_receptions: list) -> None:
		if self.hopcount_to_gateway < 65535:
			return

		if not self.discovery_started:
			self.local_event_queue.add_event_to_next_tick(
				type=LocalEventTypes.TRANCEIVER_SET_STATE,
				sub_type=MediumTypes.LORA_D2D,
				data=TransceiverState.RECEIVING,
			)
			self.local_event_queue.add_event_to_next_tick(
				type=LocalEventTypes.SET_TIMER,
				sub_type=LocalEventSubTypes.TIMER_1,
				data=self.DISCOVERY_TIMEOUT_MS,
			)
			self.discovery_started = True
			self.log.add(
				Severity.INFO,
				Area.PROTOCOL,
				current_global_clock if (current_global_clock := current_global_tick) else current_global_tick,
				f"Node {self.node_id} started D2D discovery",
			)

		if len(current_receptions) > 0:
			for reception in current_receptions:
				reception_data = reception.data
				if reception_data.type != LoRaD2DFrameType.CURRENT_HOP_COUNT:
					continue
				neighbor_info = D2DNeighborInfo(
					neighbor_id=reception_data.source_node_id,
					hopcount_to_gateway=int.from_bytes(reception_data.payload, "big"),
					last_seen=current_local_clock_info.current_local_time,
				)
				existing = next((n for n in self.known_neighbors if n.neighbor_id == neighbor_info.neighbor_id), None)
				if existing is None:
					self.known_neighbors.append(neighbor_info)
				else:
					existing.hopcount_to_gateway = neighbor_info.hopcount_to_gateway
					existing.last_seen = neighbor_info.last_seen

			hopcounts = {neighbor.hopcount_to_gateway for neighbor in self.known_neighbors}
			if len(hopcounts) >= 2:
				for hopcount in hopcounts:
					if (hopcount + 1) in hopcounts:
						self.hopcount_to_gateway = hopcount + 2
						self.log.add(
							Severity.INFO,
							Area.PROTOCOL,
							current_global_tick,
							f"Node {self.node_id} set hopcount to gateway {self.hopcount_to_gateway} from neighbors",
						)
						break

		timer_1 = current_local_clock_info.timer_1_remaining
		if timer_1 is not None and timer_1 <= 0 and self.hopcount_to_gateway == 65535:
			if len(self.known_neighbors) == 1 and self.known_neighbors[0].hopcount_to_gateway == 0:
				self.hopcount_to_gateway = 1
				self.log.add(
					Severity.INFO,
					Area.PROTOCOL,
					current_global_tick,
					f"Node {self.node_id} set hopcount to gateway 1 based on single neighbor",
				)
			self.discovery_started = False

    def _advance_slot(self, current_local_clock_info: LocalClockInfo) -> bool:
        if self.hopcount_to_gateway == 65535:
            return False

        timer_1 = current_local_clock_info.timer_1_remaining
        if self.current_slot == -1:
            if timer_1 is None or timer_1 == 0:
                self.current_slot = 0
                self.current_tx_slot = self._tx_slot_index()
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.SET_TIMER,
                    sub_type=LocalEventSubTypes.TIMER_1,
                    data=self.slot_duration,
                )
                if self.current_slot == self.current_tx_slot:
                    self.local_event_queue.add_event_to_next_tick(
                        type=LocalEventTypes.SET_TIMER,
                        sub_type=LocalEventSubTypes.TIMER_2,
                        data=10,
                    )
            return False

        if timer_1 is None or timer_1 == 0:
            self.current_slot += 1
            if self.current_slot < self.slot_count:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.SET_TIMER,
                    sub_type=LocalEventSubTypes.TIMER_1,
                    data=self.slot_duration,
                )
                if self.current_slot == self.current_tx_slot:
                    self.local_event_queue.add_event_to_next_tick(
                        type=LocalEventTypes.SET_TIMER,
                        sub_type=LocalEventSubTypes.TIMER_2,
                        data=10,
                    )
                return False

            self.current_slot = -1
            self.current_tx_slot = -1
            self.local_event_queue.add_event_to_next_tick(
                type=LocalEventTypes.TRANCEIVER_SET_STATE,
                sub_type=MediumTypes.LORA_D2D,
                data=TransceiverState.IDLE,
            )
            return True

        return False

    def _run_slot(
        self,
        current_global_tick: int,
        current_local_clock_info: LocalClockInfo,
        current_transceiver_states: dict,
    ) -> None:
        is_tx_slot = self.current_slot == self.current_tx_slot

        if is_tx_slot:
            if current_transceiver_states[MediumTypes.LORA_D2D] == TransceiverState.RECEIVING:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_SET_STATE,
                    sub_type=MediumTypes.LORA_D2D,
                    data=TransceiverState.IDLE,
                )

			if len(self.packet_buffer) == 0 and self.hopcount_to_gateway < 65535:
				self.packet_buffer.append(
					LoRaD2DFrame(
						source_node_id=self.node_id,
						destination_node_id=0xFFFFFFFF,
						type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
						payload=self.hopcount_to_gateway.to_bytes(2, "big"),
					)
				)

            if len(self.packet_buffer) > 0 and current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.TRANSMITTING:
                packet = self.packet_buffer.pop(0)
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_TRANSMIT_DATA,
                    sub_type=MediumTypes.LORA_D2D,
                    data=packet,
                )
        else:
            if current_transceiver_states[MediumTypes.LORA_D2D] != TransceiverState.RECEIVING:
                self.local_event_queue.add_event_to_next_tick(
                    type=LocalEventTypes.TRANCEIVER_SET_STATE,
                    sub_type=MediumTypes.LORA_D2D,
                    data=TransceiverState.RECEIVING,
                )

    def _tx_slot_index(self) -> int:
        return self._effective_hopcount() % self.slot_count if self._effective_hopcount() < 65535 else 0
