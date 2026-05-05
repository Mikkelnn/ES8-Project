import pytest

from custom_types import EventNet, EventNetTypes, MediumTypes, NodeMediumInfo
from logger.ILogger import ILogger
from medium.lora_d2d_medium import LoraD2DMedium
from sim.device_event_queue import DeviceEventQueue


class DummyLogger(ILogger):
	def __init__(self):
		self.messages = []

	def add(self, severity, area, global_time, msg, data=None):
		self.messages.append((severity, area, global_time, msg, data))

	def get(self):
		return self.messages

	def flush(self, force: bool = False):
		return False


def test_get_reception_node_ids_respects_max_hop_count_and_rssi():
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[2], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[1, 3, 4], gateways_in_range=[]),
		3: NodeMediumInfo(position=(2, 0), neighbors=[2], gateways_in_range=[]),
		4: NodeMediumInfo(position=(1, 1), neighbors=[2], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=1,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	assert set(reception_map) == {2, 3}
	assert reception_map[2] == pytest.approx(-40.0)
	assert reception_map[3] == pytest.approx(-52.0)
	assert 4 not in reception_map


def test_estimate_rssi_requires_hop_count_at_least_one():
	assert LoraD2DMedium._estimate_rssi(1) == pytest.approx(-40.0)
	assert LoraD2DMedium._estimate_rssi(2) == pytest.approx(-52.0)
	assert LoraD2DMedium._estimate_rssi(4) == pytest.approx(-64.0)

	with pytest.raises(ValueError, match="hop_count must be >= 1"):
		LoraD2DMedium._estimate_rssi(0)


def test_get_reception_node_ids_respects_max_hop_count_and_rssi_45_angle():
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[2], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[1, 3], gateways_in_range=[]),
		3: NodeMediumInfo(position=(6, 1), neighbors=[2, 4], gateways_in_range=[]),
		4: NodeMediumInfo(position=(8, 2), neighbors=[3], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=1,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	assert set(reception_map) == {2, 3}
	assert reception_map[2] == pytest.approx(-40.0)
	assert reception_map[3] == pytest.approx(-52.0)
	assert 4 not in reception_map


def test_9_node_star_network_angle_dependency_center_node_out():
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[5], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[5], gateways_in_range=[]),
		3: NodeMediumInfo(position=(2, 0), neighbors=[5], gateways_in_range=[]),
		4: NodeMediumInfo(position=(0, 1), neighbors=[5], gateways_in_range=[]),
		5: NodeMediumInfo(position=(1, 1), neighbors=[1, 2, 3, 4, 6, 7, 8, 9], gateways_in_range=[]),
		6: NodeMediumInfo(position=(2, 1), neighbors=[5], gateways_in_range=[]),
		7: NodeMediumInfo(position=(0, 2), neighbors=[5], gateways_in_range=[]),
		8: NodeMediumInfo(position=(1, 2), neighbors=[5], gateways_in_range=[]),
		9: NodeMediumInfo(position=(2, 2), neighbors=[5], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=5,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	# All 8 surrounding nodes should receive at hop 1 with same RSSI
	assert set(reception_map) == {1, 2, 3, 4, 6, 7, 8, 9}
	for node_id in reception_map:
		assert reception_map[node_id] == pytest.approx(-40.0)  # All are 1 hop away


def test_9_node_star_network_angle_dependency_vertical_node_in():
	# Node 2 (top center) → 5 (center) → 8 (bottom center): vertical straight line, should work
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[5], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[5], gateways_in_range=[]),
		3: NodeMediumInfo(position=(2, 0), neighbors=[5], gateways_in_range=[]),
		4: NodeMediumInfo(position=(0, 1), neighbors=[5], gateways_in_range=[]),
		5: NodeMediumInfo(position=(1, 1), neighbors=[1, 2, 3, 4, 6, 7, 8, 9], gateways_in_range=[]),
		6: NodeMediumInfo(position=(2, 1), neighbors=[5], gateways_in_range=[]),
		7: NodeMediumInfo(position=(0, 2), neighbors=[5], gateways_in_range=[]),
		8: NodeMediumInfo(position=(1, 2), neighbors=[5], gateways_in_range=[]),
		9: NodeMediumInfo(position=(2, 2), neighbors=[5], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=2,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	# Node 2 → 5 (hop 1), then 5 → 8 (hop 2, vertical continuation)
	# Node 5 should receive at hop 1, node 8 should receive at hop 2 (0° deviation)
	assert 5 in reception_map
	assert reception_map[5] == pytest.approx(-40.0)  # hop 1
	assert 8 in reception_map
	assert reception_map[8] == pytest.approx(-52.0)  # hop 2


def test_9_node_star_network_angle_dependency_horizontal_node_in():
	# Node 2 (top center) → 5 (center) → 4 (left): 90° turn, exceeds 45° limit, should not receive
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[5], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[5], gateways_in_range=[]),
		3: NodeMediumInfo(position=(2, 0), neighbors=[5], gateways_in_range=[]),
		4: NodeMediumInfo(position=(0, 1), neighbors=[5], gateways_in_range=[]),
		5: NodeMediumInfo(position=(1, 1), neighbors=[1, 2, 3, 4, 6, 7, 8, 9], gateways_in_range=[]),
		6: NodeMediumInfo(position=(2, 1), neighbors=[5], gateways_in_range=[]),
		7: NodeMediumInfo(position=(0, 2), neighbors=[5], gateways_in_range=[]),
		8: NodeMediumInfo(position=(1, 2), neighbors=[5], gateways_in_range=[]),
		9: NodeMediumInfo(position=(2, 2), neighbors=[5], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=2,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	# Node 2 → 5 (hop 1, receives)
	# Node 5 → 4: 90° deviation, exceeds 45° max, should NOT receive
	assert 5 in reception_map
	assert reception_map[5] == pytest.approx(-40.0)
	assert 4 not in reception_map


def test_9_node_star_network_angle_dependency_45_degree_node_in():
	# Node 6 (right) → 5 (center) → 4 (left): straight continuation through center
	# Incoming direction (6 to 5): (-1, 0), path (5 to 4): (-1, 0)
	# Angle: 0° deviation, well within 45° limit
	node_neighbors = {
		1: NodeMediumInfo(position=(0, 0), neighbors=[5], gateways_in_range=[]),
		2: NodeMediumInfo(position=(1, 0), neighbors=[5], gateways_in_range=[]),
		3: NodeMediumInfo(position=(2, 0), neighbors=[5], gateways_in_range=[]),
		4: NodeMediumInfo(position=(0, 1), neighbors=[5], gateways_in_range=[]),
		5: NodeMediumInfo(position=(1, 1), neighbors=[1, 2, 3, 4, 6, 7, 8, 9], gateways_in_range=[]),
		6: NodeMediumInfo(position=(2, 1), neighbors=[5], gateways_in_range=[]),
		7: NodeMediumInfo(position=(0, 2), neighbors=[5], gateways_in_range=[]),
		8: NodeMediumInfo(position=(1, 2), neighbors=[5], gateways_in_range=[]),
		9: NodeMediumInfo(position=(2, 2), neighbors=[5], gateways_in_range=[]),
	}

	medium = LoraD2DMedium(node_neighbors=node_neighbors, event_queue=DeviceEventQueue(), log=DummyLogger())
	event = EventNet(
		node_id=6,
		time_start=0,
		time_end=10,
		type=EventNetTypes.TRANSMIT,
		type_medium=MediumTypes.LORA_D2D,
		data=[],
	)

	receptions = medium._get_reception_node_ids(event)
	reception_map = {node_id: rssi for node_id, rssi in receptions}

	# Node 6 → 5 (hop 1, receives)
	# Node 5 → 4: 0° deviation (straight continuation horizontally), well within 45° limit
	assert 5 in reception_map
	assert reception_map[5] == pytest.approx(-40.0)
	assert 4 in reception_map
	assert reception_map[4] == pytest.approx(-52.0)  # hop 2
