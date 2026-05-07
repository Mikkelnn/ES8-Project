from unittest.mock import MagicMock

from custom_types import LocalEventTypes, MediumTypes, TransceiverState
from gateway.gateway import Gateway
from loraWanFrameHelper import FCtrlUplink, LoRaWanPHYPayload, MACPayload, MType, build_mhdr


class TestGatewayMultipleNodes:
	"""Test gateway handling multiple nodes receiving data in same tick."""

	def setup_method(self):
		"""Setup gateway with mocked dependencies."""
		self.mock_medium_service = MagicMock()
		self.mock_logger = MagicMock()
		self.gateway = Gateway(gateway_id=1, second_to_global_tick=1000, medium_service=self.mock_medium_service, log=self.mock_logger)
		# Mock transceiver tick to avoid complex setup
		self.gateway.transceiver.tick = MagicMock(return_value=(0, None))  # type: ignore

	def _create_payload(self, dev_addr: int) -> LoRaWanPHYPayload:
		"""Helper to create LoRaWAN uplink payload."""
		mac = MACPayload(dev_addr=dev_addr, fctrl_flags=FCtrlUplink(0), fcnt=0, frm_payload=b"test")
		return LoRaWanPHYPayload(mhdr=build_mhdr(MType.UNCONFIRMED_DATA_UP), mac_payload=mac)

	def test_single_node_baseline(self):
		"""Single node reception works (baseline)."""
		dev_addr = 0x12345678
		payload = self._create_payload(dev_addr)

		# Inject received data event
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		# Setup transceiver status for next tick
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})

		self.gateway.tick(100)

		# Check single node queued for response
		assert len(self.gateway.rx_to_nodes) == 1
		assert dev_addr in self.gateway.rx_to_nodes

	def test_multiple_nodes_same_tick(self):
		"""Multiple nodes receiving in same tick both queued."""
		dev_addr_1 = 0x11111111
		dev_addr_2 = 0x22222222
		payload_1 = self._create_payload(dev_addr_1)
		payload_2 = self._create_payload(dev_addr_2)

		# Inject two received data events
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload_1)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload_2)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})

		self.gateway.tick(100)

		# Check both nodes queued
		assert len(self.gateway.rx_to_nodes) == 2
		assert dev_addr_1 in self.gateway.rx_to_nodes
		assert dev_addr_2 in self.gateway.rx_to_nodes

	def test_three_nodes_same_tick(self):
		"""Three nodes receiving in same tick all queued."""
		dev_addrs = [0x11111111, 0x22222222, 0x33333333]
		payloads = [self._create_payload(addr) for addr in dev_addrs]

		for payload in payloads:
			self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})

		self.gateway.tick(100)

		assert len(self.gateway.rx_to_nodes) == 3
		for addr in dev_addrs:
			assert addr in self.gateway.rx_to_nodes

	def test_ack_sent_at_correct_time(self):
		"""ACK scheduled at correct rx1 time."""
		dev_addr = 0x12345678
		payload = self._create_payload(dev_addr)
		current_tick = 1000

		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})

		self.gateway.tick(current_tick)

		# rx1_tick = current_tick + 1 second delay
		expected_rx_tick = current_tick + 1 * (1 / self.gateway.second_to_global_tick)
		assert self.gateway.rx_to_nodes[dev_addr] == expected_rx_tick

	def test_acks_sent_when_time_reaches_response_tick(self):
		"""All pending nodes get ACK when their response tick arrives."""
		dev_addr_1 = 0x11111111
		dev_addr_2 = 0x22222222
		payload_1 = self._create_payload(dev_addr_1)
		payload_2 = self._create_payload(dev_addr_2)

		# Tick 100: receive data from two nodes
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload_1)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload_2)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(100)

		assert len(self.gateway.rx_to_nodes) == 2
		# Get response ticks to know when ACKs will be sent
		rx_tick = list(self.gateway.rx_to_nodes.values())[0]

		# Tick forward to when response is due
		tick_val = int(rx_tick) + 1  # Add 1 to ensure we're past float value
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(tick_val)

		# Both nodes should be removed from pending
		assert len(self.gateway.rx_to_nodes) == 0

	def test_multiple_nodes_same_response_time(self):
		"""Multiple nodes with same response time get ACKs together."""
		dev_addr_1 = 0x11111111
		dev_addr_2 = 0x22222222
		dev_addr_3 = 0x33333333
		payloads = [self._create_payload(dev_addr_1), self._create_payload(dev_addr_2), self._create_payload(dev_addr_3)]

		# All receive at same tick
		for payload in payloads:
			self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(500)

		assert len(self.gateway.rx_to_nodes) == 3
		# All should have same response time
		expected_tick = 500 + 1 * (1 / self.gateway.second_to_global_tick)
		for addr in [dev_addr_1, dev_addr_2, dev_addr_3]:
			assert self.gateway.rx_to_nodes[addr] == expected_tick

		# At response time, all should be cleared
		self.gateway.local_event_queue.reset()
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(int(expected_tick) + 1)

		assert len(self.gateway.rx_to_nodes) == 0

	def test_receive_formulas(self):
		"""Response time correctly calculated from receive tick."""
		dev_addr = 0x12345678
		payload = self._create_payload(dev_addr)

		tick_val = 5000
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(tick_val)

		# Response time = tick + 1 second
		expected_rx_tick = tick_val + 1 * (1 / self.gateway.second_to_global_tick)
		assert self.gateway.rx_to_nodes[dev_addr] == expected_rx_tick

	def test_accumulated_state_tracks_earliest_in_tick(self):
		"""Accumulated state within tick uses earliest pending response time."""
		dev_addr_1 = 0x11111111
		dev_addr_2 = 0x22222222
		dev_addr_3 = 0x33333333

		payload_1 = self._create_payload(dev_addr_1)
		payload_2 = self._create_payload(dev_addr_2)
		payload_3 = self._create_payload(dev_addr_3)

		# All three receive in same tick
		for payload in [payload_1, payload_2, payload_3]:
			self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})

		self.gateway.tick(100)

		# Accumulated state within this tick should have earliest response time
		expected_earliest = min(self.gateway.rx_to_nodes[dev_addr_1], self.gateway.rx_to_nodes[dev_addr_2], self.gateway.rx_to_nodes[dev_addr_3])
		assert self.gateway.accumulated_state.earliest_global_tick == expected_earliest

	def test_no_pending_responses_empty_dict(self):
		"""No pending responses when no data received."""
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(100)

		assert len(self.gateway.rx_to_nodes) == 0
		assert isinstance(self.gateway.rx_to_nodes, dict)

	def test_same_node_multiple_packets(self):
		"""Same node sending multiple packets overwrites response time."""
		dev_addr = 0x12345678
		payload = self._create_payload(dev_addr)

		# First packet at tick 100
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(100)
		rx_tick_1 = self.gateway.rx_to_nodes[dev_addr]

		# Second packet at tick 500 (same node, new response time)
		self.gateway.local_event_queue.reset()
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_RECEIVED_DATA, sub_type=MediumTypes.LORA_WAN, data=payload)
		self.gateway.local_event_queue.add_event_to_current_tick(type=LocalEventTypes.TRANCEIVER_STATUS, data={MediumTypes.LORA_WAN: TransceiverState.IDLE})
		self.gateway.tick(500)
		rx_tick_2 = self.gateway.rx_to_nodes[dev_addr]

		# Should have one entry with latest response time
		assert len(self.gateway.rx_to_nodes) == 1
		assert rx_tick_2 > rx_tick_1
