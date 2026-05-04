import pytest

from simulator.src.custom_types import EventNet, EventNetTypes, MediumTypes, NodeMediumInfo
from simulator.src.medium.lora_d2d_medium import LoraD2DMedium
from simulator.src.simulator.device_event_queue import DeviceEventQueue
from simulator.src.logger.ILogger import ILogger


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
