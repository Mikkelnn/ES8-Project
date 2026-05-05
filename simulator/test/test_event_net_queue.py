from custom_types import EventNet, EventNetTypes, MediumTypes
from sim.device_event_queue import DeviceEventQueue


def test_init_tick_and_get_next_events():
	q = DeviceEventQueue()
	q.init_tick(5, [1, 2, 3])
	tick, nodes = q.get_next_events()
	assert tick == 5
	assert set(nodes) == {1, 2, 3}


def test_add_event_and_get_next_events():
	q = DeviceEventQueue()
	q.add_event(10, 7)
	tick, nodes = q.get_next_events()
	assert tick == 7
	assert 10 in nodes


def test_multiple_events():
	q = DeviceEventQueue()
	q.add_event(1, 2)
	q.add_event(2, 2)
	q.add_event(3, 3)
	tick1, nodes1 = q.get_next_events()
	tick2, nodes2 = q.get_next_events()
	assert tick1 == 2
	assert set(nodes1) == {1, 2}
	assert tick2 == 3
	assert set(nodes2) == {3}


def multi_event_queue():
	q = DeviceEventQueue()
	e1 = EventNet(node_id=1, time_start=0, time_end=10, data=["a"], type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
	e2 = EventNet(node_id=2, time_start=5, time_end=15, data=["b"], type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
	e3 = EventNet(node_id=3, time_start=20, time_end=30, data=["c"], type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
	e4 = EventNet(node_id=4, time_start=12, time_end=18, data=["d"], type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
	for e in [e1, e2, e3, e4]:
		q.push_event_stop(e)
	return q, [e1, e2, e3, e4]
