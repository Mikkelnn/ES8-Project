# from unittest.mock import Mock

# import pytest

# from custom_types import EventNet, EventNetTypes, MediumTypes
# from node.transceiver.LoRaD2D import LoRaD2D
# from node.transceiver.LoRaWan import LoRaWan


# def create_mock_data(length: int):
#     data = Mock()
#     data.length = length
#     return data


# @pytest.fixture
# def mock_medium_service():
#     return Mock()


# @pytest.fixture
# def mock_event_queue():
#     mock = Mock()
#     mock.get_current_events_by_type.return_value = []
#     mock.add_event_to_current_tick = Mock()
#     return mock


# @pytest.fixture
# def mock_logger():
#     return Mock()


# @pytest.fixture
# def lora_d2d_transceiver(mock_medium_service, mock_event_queue, mock_logger):
#     return LoRaD2D(node_id=1, medium_service=mock_medium_service, local_event_queue=mock_event_queue, second_to_global_tick=1.0, log=mock_logger)


# @pytest.fixture
# def lora_wan_transceiver(mock_medium_service, mock_event_queue, mock_logger):
#     return LoRaWan(node_id=1, medium_service=mock_medium_service, local_event_queue=mock_event_queue, second_to_global_tick=1.0, log=mock_logger)


# class TestGetSuccessfulReceptions:
#     """Test __get_successful_receptions method behavior"""

#     def test_empty_receive_queue(self, lora_d2d_transceiver):
#         """No events in queue should return empty list"""
#         lora_d2d_transceiver._receive_queue = []
#         lora_d2d_transceiver._current_reception_start_global_tick = 100

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_reception_not_started(self, lora_d2d_transceiver):
#         """No events successful if reception not started"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event]
#         lora_d2d_transceiver._current_reception_start_global_tick = None

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_simple_successful_reception(self, lora_d2d_transceiver):
#         """Single event that finished before current tick and after reception start"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert len(result) == 1
#         assert result[0] == event

#     def test_event_not_finished(self, lora_d2d_transceiver):
#         """Event still ongoing should not be successful"""
#         event = EventNet(node_id=2, time_start=100, time_end=200, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(150)
#         assert result == []

#     def test_reception_start_after_event_start(self, lora_d2d_transceiver):
#         """Reception started after event started should not be successful"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event]
#         lora_d2d_transceiver._current_reception_start_global_tick = 120

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_event_cancelled(self, lora_d2d_transceiver):
#         """Event with matching cancellation should not be successful"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         cancellation = EventNet(node_id=2, time_start=120, time_end=140, data=create_mock_data(0), type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event, cancellation]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_overlapping_events_both_fail(self, lora_d2d_transceiver):
#         """Two overlapping events should both fail"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=3, time_start=120, time_end=160, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_sequential_events_both_succeed(self, lora_d2d_transceiver):
#         """Two non-overlapping sequential events from same node should both succeed"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=2, time_start=200, time_end=250, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(175)
#         assert len(result) == 1
#         assert event1 in result

#         result = lora_d2d_transceiver._get_successful_receptions(300)
#         assert len(result) == 1
#         assert event2 in result

#     def test_cancellation_reduces_overlap_window(self, lora_d2d_transceiver):
#         """Cancellation can reduce effective end time of overlapping event"""
#         # event1: 100-150
#         # event2: 120-180 (overlaps with event1)
#         # event2 has cancellation at 140, so effective end becomes 140
#         # This means event2's effective window is 120-140, still overlaps with event1
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=3, time_start=120, time_end=180, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         cancellation = EventNet(node_id=3, time_start=140, time_end=200, data=create_mock_data(0), type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2, cancellation]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         # Both should fail due to overlap (even with cancellation reducing event2's window)
#         result = lora_d2d_transceiver._get_successful_receptions(250)
#         assert result == []

#     def test_receive_queue_cleanup_after_successful_receptions(self, lora_d2d_transceiver):
#         """Receive queue should be cleaned up after selecting successful receptions"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=2, time_start=200, time_end=250, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event3 = EventNet(node_id=2, time_start=300, time_end=350, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2, event3]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(400)
#         assert len(result) == 3
#         # After processing, queue should only contain events with start_time > max successful end_time
#         # max_time_end = 350, so queue should be empty (all events have start_time <= 350)
#         assert lora_d2d_transceiver._receive_queue == []

#     def test_multiple_cancellations_same_node(self, lora_d2d_transceiver):
#         """Multiple cancellations for same node should all prevent success"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         cancel1 = EventNet(node_id=2, time_start=110, time_end=120, data=create_mock_data(0), type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
#         cancel2 = EventNet(node_id=2, time_start=130, time_end=140, data=create_mock_data(0), type=EventNetTypes.CANCELED, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event, cancel1, cancel2]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_lora_wan_successful_reception(self, lora_wan_transceiver):
#         """Single event reception succeeds"""
#         event = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_WAN)
#         lora_wan_transceiver._receive_queue = [event]
#         lora_wan_transceiver._current_reception_start_global_tick = 50

#         result = lora_wan_transceiver._get_successful_receptions(200)
#         assert len(result) == 1
#         assert result[0] == event

#     def test_lora_wan_overlapping_events_both_succeed(self, lora_wan_transceiver):
#         """LoRaWan accepts overlapping events from different nodes (no collision detection)"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_WAN)
#         event2 = EventNet(node_id=3, time_start=120, time_end=160, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_WAN)
#         lora_wan_transceiver._receive_queue = [event1, event2]
#         lora_wan_transceiver._current_reception_start_global_tick = 50

#         result = lora_wan_transceiver._get_successful_receptions(200)
#         assert len(result) == 2
#         assert event1 in result
#         assert event2 in result

#     def test_overlap_one_start_inside(self, lora_d2d_transceiver):
#         """Event2 start inside event1, end outside - should fail"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=3, time_start=140, time_end=200, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event2, event1]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(250)
#         assert result == []

#     def test_overlap_one_end_inside(self, lora_d2d_transceiver):
#         """Event2 start outside, end inside event1 - should fail"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=3, time_start=80, time_end=120, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []

#     def test_overlap_one_completely_contained(self, lora_d2d_transceiver):
#         """Event2 completely inside event1 - should fail"""
#         event1 = EventNet(node_id=2, time_start=100, time_end=150, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         event2 = EventNet(node_id=3, time_start=110, time_end=140, data=create_mock_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D)
#         lora_d2d_transceiver._receive_queue = [event1, event2]
#         lora_d2d_transceiver._current_reception_start_global_tick = 50

#         result = lora_d2d_transceiver._get_successful_receptions(200)
#         assert result == []
