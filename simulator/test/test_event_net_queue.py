import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import pytest
from simulator.src.simulator.event_net_queue import event_net_queue
from simulator.src.custom_types import EventNet, EventNetTypes, MediumTypes

@pytest.fixture
def sample_event():
    return EventNet(node_id=1, time_start=10, time_end=20, data=["payload"], type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA)

@pytest.fixture
def another_event():
    return EventNet(node_id=2, time_start=15, time_end=25, data=["payload2"], type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA)

@pytest.fixture
def queue_with_events(sample_event, another_event):
    q = event_net_queue()
    q.push_event_stop(sample_event)
    q.push_event_stop(another_event)
    return q

def test_push_and_pop_event_start(sample_event):
    q = event_net_queue()
    q.push_event_start(sample_event)
    assert q.pop_event_start() == sample_event

def test_push_and_pop_event_end(sample_event):
    q = event_net_queue()
    q.push_event_stop(sample_event)
    assert q.pop_event_end() == sample_event

def test_get_events(queue_with_events, sample_event, another_event):
    events = queue_with_events.get_events()
    assert sample_event in events and another_event in events

def test_get_events_start_end(queue_with_events, sample_event, another_event):
    assert queue_with_events.get_events_start() == sample_event
    assert queue_with_events.get_events_end() == another_event

def test_get_events_as_json(queue_with_events):
    json_events = queue_with_events.get_events(as_json=True)
    assert isinstance(json_events, list)
    assert isinstance(json_events[0], dict)

def test_pop_event_start_as_json(queue_with_events):
    json_event = queue_with_events.pop_event_start(as_json=True)
    assert isinstance(json_event, dict)

def test_pop_event_end_as_json(queue_with_events):
    json_event = queue_with_events.pop_event_end(as_json=True)
    assert isinstance(json_event, dict)

def test_sort_queue_time_start(sample_event, another_event):
    q = event_net_queue()
    q.push_event_stop(another_event)
    q.push_event_stop(sample_event)
    q.sort_queue_time_start()
    assert q.get_events_start() == sample_event


# Additional tests for time_start and time_end filtering
@pytest.fixture
def multi_event_queue():
    from simulator.src.custom_types import EventNetTypes, MediumTypes
    q = event_net_queue()
    e1 = EventNet(node_id=1, time_start=0, time_end=10, data=["a"], type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA)
    e2 = EventNet(node_id=2, time_start=5, time_end=15, data=["b"], type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA)
    e3 = EventNet(node_id=3, time_start=20, time_end=30, data=["c"], type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA)
    e4 = EventNet(node_id=4, time_start=12, time_end=18, data=["d"], type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA)
    for e in [e1, e2, e3, e4]:
        q.push_event_stop(e)
    return q, [e1, e2, e3, e4]

def test_get_events_time_range_overlap(multi_event_queue):
    q, events = multi_event_queue
    # Should get e1 and e2 (overlap with 0-10)
    result = q.get_events(time_start=0, time_end=10)
    assert events[0] in result
    assert events[1] in result
    assert events[2] not in result
    assert events[3] not in result

def test_get_events_time_start_only(multi_event_queue):
    q, events = multi_event_queue
    # Should get e1 and e2 (time_start <= 5 <= time_end)
    result = q.get_events(time_start=5)
    assert events[0] in result
    assert events[1] in result
    assert events[2] not in result
    assert events[3] not in result

def test_get_events_time_end_only(multi_event_queue):
    q, events = multi_event_queue
    # Should get e2 and e4 (time_start <= 15 <= time_end)
    result = q.get_events(time_end=15)
    assert events[0] not in result
    assert events[1] in result
    assert events[2] not in result
    assert events[3] in result

def test_get_events_time_range_late(multi_event_queue):
    q, events = multi_event_queue
    # Should get only e3 (overlap with 25-29)
    result = q.get_events(time_start=25, time_end=29)
    assert events[2] in result
    assert events[0] not in result
    assert events[1] not in result
    assert events[3] not in result
