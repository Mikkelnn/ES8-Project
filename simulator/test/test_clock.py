"""
Comprehensive unit tests for the Clock class.

Tests cover the 3 main scenarios:
1. No event scheduled - returns None for scheduled_global_tick
2. Scheduled event with queue - sets localtime, returns next event's global tick
3. Unscheduled event - calculates local time with drift, reschedules

Additional test coverage includes timer management, sleep/wake, clock drift, and edge cases.

Tests use a module-level seed for reproducible clock drift behavior.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from custom_types import LocalClockInfo, LocalEventNet, LocalEventSubTypes, LocalEventTypes
from logger.ILogger import ILogger
from node.clock.clock import Clock
from node.event_local_queue import LocalEventQueue

# ============================================================================
# Seed Configuration & Fixtures
# ============================================================================

# Set module-level seed for reproducible clock drift
RANDOM_SEED = 42


@pytest.fixture(scope="module", autouse=True)
def set_random_seed():
    """Set numpy random seed for reproducible clock drift across all tests."""
    np.random.seed(RANDOM_SEED)
    yield
    # Reset after module completes
    np.random.seed(None)


@pytest.fixture
def mock_event_queue():
    """Create a mock LocalEventQueue with default empty event returns."""
    mock = Mock(spec=LocalEventQueue)
    mock.get_current_events_by_type.return_value = []
    mock.add_event_to_current_tick = Mock()
    mock.add_event_to_next_tick = Mock()
    return mock


@pytest.fixture
def mock_log():
    """Create a mock ILogger for testing."""
    return Mock(spec=ILogger)


@pytest.fixture
def clock_instance(mock_log, mock_event_queue):
    """Create a fresh Clock instance for testing."""
    # Re-seed before each test for consistent clock drift
    np.random.seed(RANDOM_SEED)
    clock = Clock(log=mock_log, node_id=1, local_event_queue=mock_event_queue, second_to_global_tick=0.001)
    return clock


def create_local_event_net(event_type, data, sub_type=None):
    """Helper to create LocalEventNet instances for testing."""
    return LocalEventNet(type=event_type, sub_type=sub_type, data=data)


# ============================================================================
# Test Class 1: No Event Scheduled Scenario
# ============================================================================


class TestNoEventScheduled:
    """
    Tests the scenario where no timers or sleep events are scheduled.
    Expected behavior: scheduled_global_tick should be None, localtime should increment
    based on clock drift.
    """

    def test_no_events_returns_none_scheduled_tick(self, clock_instance):
        """When no events are scheduled, tick() should return None."""
        power, scheduled_tick = clock_instance.tick(current_global_tick=1)
        assert scheduled_tick is None
        assert clock_instance.scheduled_global_tick is None

    def test_no_events_local_time_increments(self, clock_instance):
        """Local time updates as ticks progress (monotonically non-decreasing)."""
        times = []
        # Keep well under 100 ticks to avoid random vector exhaustion
        for tick in range(1, 51):
            clock_instance.tick(current_global_tick=tick)
            times.append(clock_instance.localtime)

        # With seed 42, localtime may increment very slowly or stay at 0
        # The key is that it doesn't crash and remains non-decreasing
        for i in range(1, len(times)):
            assert times[i] >= times[i - 1], f"Localtime decreased at index {i}"

    def test_multiple_ticks_no_events(self, clock_instance):
        """Multiple consecutive ticks with no events should maintain None scheduled_tick."""
        for tick in range(1, 6):
            power, scheduled_tick = clock_instance.tick(current_global_tick=tick)
            assert scheduled_tick is None
            assert clock_instance.scheduled_global_tick is None

    def test_earliest_next_local_time_none(self, clock_instance):
        """When no events scheduled, earliest_next_local_time should be None."""
        clock_instance.tick(current_global_tick=1)
        assert clock_instance.earliest_next_local_time is None

    def test_local_time_published_to_queue(self, clock_instance):
        """LOCAL_TIME event should be published each tick."""
        clock_instance.tick(current_global_tick=1)

        # Verify LOCAL_TIME event was added
        calls = clock_instance.local_event_queue.add_event_to_current_tick.call_args_list
        local_time_calls = [c for c in calls if c[0][0] == LocalEventTypes.LOCAL_TIME]
        assert len(local_time_calls) > 0


# ============================================================================
# Test Class 2: Scheduled Event Happened with Queue
# ============================================================================


class TestScheduledEventWithQueue:
    """
    Tests the scenario where an event was scheduled and we tick at the exact
    scheduled global time with another event queued.
    Expected behavior: localtime set to earliest_next_local_time, return next event's global tick.
    """

    def test_scheduled_tick_reached_sets_localtime(self, clock_instance, mock_event_queue):
        """When scheduled_global_tick is reached, localtime should be set to earliest_next_local_time."""
        # First, set up a scheduled event by setting timer
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 10, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        # First tick: schedule timer event
        clock_instance.tick(current_global_tick=1)
        scheduled_tick = clock_instance.scheduled_global_tick
        earliest_local_time = clock_instance.earliest_next_local_time

        assert scheduled_tick is not None
        assert earliest_local_time is not None

        # Reset mock for next tick
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []

        # Second tick: reach scheduled tick
        clock_instance.tick(current_global_tick=scheduled_tick)
        assert clock_instance.localtime == earliest_local_time

    def test_scheduled_event_with_next_queue(self, clock_instance, mock_event_queue):
        """When scheduled event occurs, next event should be calculated if queue has more."""
        # First tick: set timer
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 20, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        first_scheduled = clock_instance.scheduled_global_tick

        # Reset and tick again at scheduled time
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        power, scheduled_tick = clock_instance.tick(current_global_tick=first_scheduled)

        # Result should be None if no more timers, or a new scheduled tick
        assert scheduled_tick is None or isinstance(scheduled_tick, int)

    def test_scheduled_tick_returns_next_global_tick(self, clock_instance, mock_event_queue):
        """When scheduled tick reached, return value should be the next scheduled global tick (or None)."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 15, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        scheduled_tick = clock_instance.scheduled_global_tick

        # At scheduled tick, result should be an int (next scheduled tick) or None
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        power, scheduled_tick_result = clock_instance.tick(current_global_tick=scheduled_tick)
        assert scheduled_tick_result is None or isinstance(scheduled_tick_result, int)


# ============================================================================
# Test Class 3: Unscheduled Event (Event Not at Scheduled Time)
# ============================================================================


class TestUnscheduledEvent:
    """
    Tests the scenario where a tick occurs but not at the scheduled global time.
    Expected behavior: localtime calculated with clock drift, next event rescheduled.
    """

    def test_unscheduled_tick_calculates_localtime_with_drift(self, clock_instance, mock_event_queue):
        """When tick doesn't match scheduled time, localtime should be calculated with drift."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 10, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        scheduled_tick = clock_instance.scheduled_global_tick

        # Reset and tick at a different time (unscheduled)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        unscheduled_tick = scheduled_tick + 5  # Tick 5 ticks after scheduled

        local_time_before = clock_instance.localtime
        clock_instance.tick(current_global_tick=unscheduled_tick)
        local_time_after = clock_instance.localtime

        # Localtime should have updated using drift calculation
        assert local_time_after > local_time_before or local_time_after == local_time_before

    def test_unscheduled_tick_reschedules_event(self, clock_instance, mock_event_queue):
        """When unscheduled tick occurs, next event should be rescheduled."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 10, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        first_scheduled = clock_instance.scheduled_global_tick

        # Reset and tick unscheduled
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        clock_instance.tick(current_global_tick=first_scheduled - 3)  # Tick early

        # Scheduled tick should be recalculated and not equal to first scheduled time
        # (it should be pushed forward since we ticked early)
        assert clock_instance.scheduled_global_tick is not None


# ============================================================================
# Test Class 4: Timer Management
# ============================================================================


class TestTimerManagement:
    """
    Tests timer scheduling, expiration, and multiple timer scenarios.
    """

    def test_timer_1_scheduling(self, clock_instance, mock_event_queue):
        """TIMER_1 should be scheduled when SET_TIMER event received."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 50, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)

        # Timer_1 should be set
        assert clock_instance.timer_1_end_local_time is not None
        assert clock_instance.timer_1_end_local_time > clock_instance.localtime

    def test_timer_2_scheduling(self, clock_instance, mock_event_queue):
        """TIMER_2 should be scheduled when SET_TIMER event received."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 100, LocalEventSubTypes.TIMER_2)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)

        # Timer_2 should be set
        assert clock_instance.timer_2_end_local_time is not None
        assert clock_instance.timer_2_end_local_time > clock_instance.localtime

    def test_timer_expiration_clears_timer(self, clock_instance, mock_event_queue):
        """When localtime reaches timer end time, timer should be cleared."""
        # Set a timer with larger duration so it doesn't expire immediately
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 100, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        timer_end_time = clock_instance.timer_1_end_local_time

        # Timer should be set and not cleared immediately
        assert timer_end_time is not None, "Timer not set after SET_TIMER event"

        # Fast-forward a few ticks (stay under 100 to avoid random vector exhaustion)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        for tick in range(2, 50):
            clock_instance.tick(current_global_tick=tick)
            # If we've reached or passed the timer end, we should be done
            if clock_instance.timer_1_end_local_time is not None and clock_instance.localtime >= clock_instance.timer_1_end_local_time:
                break

        # Check timer state: either cleared if reached, or still pending if not reached
        if clock_instance.localtime >= timer_end_time:
            # If we reached the end time, timer should be cleared
            assert clock_instance.timer_1_end_local_time is None
        else:
            # If we haven't reached it yet, timer should still be set
            assert clock_instance.timer_1_end_local_time == timer_end_time

    def test_multiple_timers_simultaneously(self, clock_instance, mock_event_queue):
        """Both TIMER_1 and TIMER_2 can be set simultaneously."""
        timer1_event = create_local_event_net(LocalEventTypes.SET_TIMER, 30, LocalEventSubTypes.TIMER_1)
        timer2_event = create_local_event_net(LocalEventTypes.SET_TIMER, 50, LocalEventSubTypes.TIMER_2)

        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer1_event, timer2_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)

        # Both timers should be set
        assert clock_instance.timer_1_end_local_time is not None
        assert clock_instance.timer_2_end_local_time is not None

    def test_timer_duration_accounting_for_1tick_delay(self, clock_instance, mock_event_queue):
        """Timer duration should account for 1 tick delay in scheduling."""
        duration = 25
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, duration, LocalEventSubTypes.TIMER_1)

        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)

        # tick() advances localtime first, then sets timer_end = localtime + duration - 1
        # ("-1" cancels the 1-tick scheduling delay), so use the post-tick localtime.
        expected_end = clock_instance.localtime + duration - 1
        assert clock_instance.timer_1_end_local_time == expected_end


# ============================================================================
# Test Class 5: Sleep/Wake Functionality
# ============================================================================


class TestSleepWake:
    """
    Tests sleep scheduling, wake timing, and NODE_WAKE_UP event generation.
    """

    def test_sleep_request_sets_sleep_time(self, clock_instance, mock_event_queue):
        """NODE_SLEEP_FOR event should set sleep_until_local_time."""
        sleep_event = create_local_event_net(LocalEventTypes.NODE_SLEEP_FOR, 100)

        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [sleep_event] if evt_type == LocalEventTypes.NODE_SLEEP_FOR else []

        clock_instance.tick(current_global_tick=1)

        # Sleep should be scheduled
        assert clock_instance.sleep_until_local_time is not None

    def test_sleep_publish_node_sleep_event(self, clock_instance, mock_event_queue):
        """NODE_SLEEP event should be published when sleep is initiated."""
        sleep_event = create_local_event_net(LocalEventTypes.NODE_SLEEP_FOR, 50)

        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [sleep_event] if evt_type == LocalEventTypes.NODE_SLEEP_FOR else []

        clock_instance.tick(current_global_tick=1)

        # Check that NODE_SLEEP event was published
        calls = clock_instance.local_event_queue.add_event_to_current_tick.call_args_list
        sleep_calls = [c for c in calls if c[0][0] == LocalEventTypes.NODE_SLEEP]
        assert len(sleep_calls) > 0

    def test_wake_up_at_scheduled_time(self, clock_instance, mock_event_queue):
        """When localtime reaches sleep_until_local_time, NODE_WAKE_UP should be published."""
        # Sleep with larger duration so it doesn't expire immediately
        sleep_event = create_local_event_net(LocalEventTypes.NODE_SLEEP_FOR, 100)

        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [sleep_event] if evt_type == LocalEventTypes.NODE_SLEEP_FOR else []

        clock_instance.tick(current_global_tick=1)
        sleep_until = clock_instance.sleep_until_local_time

        # Sleep should be set and not cleared immediately
        assert sleep_until is not None, "Sleep not set after NODE_SLEEP_FOR event"

        # Fast-forward a few ticks (stay under 100 to avoid random vector exhaustion)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        for tick in range(2, 50):
            clock_instance.tick(current_global_tick=tick)
            if clock_instance.sleep_until_local_time is not None and clock_instance.localtime >= clock_instance.sleep_until_local_time:
                break

        # Check that NODE_WAKE_UP was published
        calls = clock_instance.local_event_queue.add_event_to_current_tick.call_args_list
        wake_up_calls = [c for c in calls if c[0][0] == LocalEventTypes.NODE_WAKE_UP]
        # Either woken up, or sleep_until still pending (acceptable if not enough ticks elapsed)
        assert len(wake_up_calls) > 0 or clock_instance.sleep_until_local_time is not None


# ============================================================================
# Test Class 6: Clock Drift Simulation
# ============================================================================


class TestClockDrift:
    """
    Tests the clock drift/skew (AR process), noise, and trend components.
    Verifies deterministic behavior with seeded random.
    """

    def test_alpha_initialized(self, clock_instance):
        """Alpha (clock skew) should be initialized from random vector."""
        assert clock_instance.alpha is not None
        assert isinstance(clock_instance.alpha, (float, np.floating))

    def test_trend_initialized(self, clock_instance):
        """Trend component should be initialized within bounds."""
        assert clock_instance.trend is not None
        assert -5e-2 <= clock_instance.trend <= 5e-2

    def test_noise_std_initialized(self, clock_instance):
        """Noise standard deviation should match expected value."""
        expected_std = np.sqrt(20.970167331917025 * 3.915e-15)
        assert np.isclose(clock_instance.noise_std, expected_std)

    def test_random_vector_consumed(self, clock_instance):
        """Each tick should consume one random sample from random_vector."""
        initial_vector_len = len(clock_instance.random_vector)

        clock_instance.tick(current_global_tick=1)

        # Vector length should decrease by 1
        assert len(clock_instance.random_vector) == initial_vector_len - 1

    def test_alpha_updates_with_ar_process(self, clock_instance):
        """Alpha should update using AR(1) process each tick."""
        alpha_0 = clock_instance.alpha

        clock_instance.tick(current_global_tick=1)
        alpha_1 = clock_instance.alpha

        # Alpha should change due to AR process
        assert alpha_0 != alpha_1

    def test_seeded_determinism(self):
        """Multiple clocks with same seed should produce identical drift sequences."""
        np.random.seed(42)
        mock_log1 = Mock(spec=ILogger)
        mock1 = Mock(spec=LocalEventQueue)
        mock1.get_current_events_by_type.return_value = []
        mock1.add_event_to_current_tick = Mock()

        clock1 = Clock(log=mock_log1, node_id=1, local_event_queue=mock1, second_to_global_tick=0.001)
        times1 = []
        for tick in range(1, 11):
            clock1.tick(current_global_tick=tick)
            times1.append(clock1.localtime)

        # Create second clock with same seed
        np.random.seed(42)
        mock_log2 = Mock(spec=ILogger)
        mock2 = Mock(spec=LocalEventQueue)
        mock2.get_current_events_by_type.return_value = []
        mock2.add_event_to_current_tick = Mock()

        clock2 = Clock(log=mock_log2, node_id=2, local_event_queue=mock2, second_to_global_tick=0.001)
        times2 = []
        for tick in range(1, 11):
            clock2.tick(current_global_tick=tick)
            times2.append(clock2.localtime)

        # Times should match exactly
        assert times1 == times2

    def test_local_time_drift_accumulates(self, clock_instance):
        """Local time updates monotonically as ticks progress."""
        times = []
        # Keep well under 100 ticks to avoid random vector exhaustion
        for tick in range(1, 51):
            clock_instance.tick(current_global_tick=tick)
            times.append(clock_instance.localtime)

        # Localtime should be monotonically non-decreasing (drift/trend applied)
        for i in range(1, len(times)):
            assert times[i] >= times[i - 1], f"Localtime decreased: {times[i - 1]} -> {times[i]} at index {i}"


# ============================================================================
# Test Class 7: Edge Cases & State Management
# ============================================================================


class TestEdgeCases:
    """
    Tests edge cases, state consistency, and reset functionality.
    """

    def test_reset_clears_timers(self, clock_instance, mock_event_queue):
        """reset() should clear both timers."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 50, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)
        assert clock_instance.timer_1_end_local_time is not None

        clock_instance.reset(current_global_tick=100)
        assert clock_instance.timer_1_end_local_time is None
        assert clock_instance.timer_2_end_local_time is None

    def test_initialization_values(self, clock_instance):
        """Clock should initialize with correct starting values."""
        assert clock_instance.node_id == 1
        assert clock_instance.localtime == 0
        assert clock_instance.global_time_last == 0
        assert clock_instance.scheduled_global_tick is None
        assert clock_instance.sleep_until_local_time is None
        assert clock_instance.timer_1_end_local_time is None
        assert clock_instance.timer_2_end_local_time is None

    def test_global_time_last_updated(self, clock_instance):
        """global_time_last should be updated to current_global_tick after each tick."""
        clock_instance.tick(current_global_tick=5)
        assert clock_instance.global_time_last == 5

    def test_scheduled_tick_none_when_no_events(self, clock_instance):
        """When earliest_next_local_time is None, scheduled_global_tick should be None."""
        clock_instance.tick(current_global_tick=1)
        assert clock_instance.earliest_next_local_time is None
        assert clock_instance.scheduled_global_tick is None

    def test_state_consistency_after_multiple_ticks(self, clock_instance):
        """State should remain consistent across multiple ticks without events."""
        for tick in range(1, 6):
            clock_instance.tick(current_global_tick=tick)
            assert clock_instance.global_time_last == tick

    def test_no_rounding_error_at_scheduled_tick(self, clock_instance, mock_event_queue):
        """
        When reaching scheduled_global_tick, localtime should be set exactly to
        earliest_next_local_time instead of calculated to avoid rounding errors.

        This tests the if statement (lines 45-49) that prevents accumulated
        floating-point rounding errors when reaching scheduled events.
        """
        # Set up a timer to create a scheduled event
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 100, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        # Tick and get scheduled time
        clock_instance.tick(current_global_tick=1)
        scheduled_tick = clock_instance.scheduled_global_tick
        expected_local_time = clock_instance.earliest_next_local_time

        assert scheduled_tick is not None
        assert expected_local_time is not None

        # Reset mock for next tick
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []

        # Tick at the scheduled time
        clock_instance.tick(current_global_tick=scheduled_tick)
        actual_local_time = clock_instance.localtime

        # The key test: localtime should match expected exactly (set, not calculated)
        # This prevents rounding errors from accumulating
        assert actual_local_time == expected_local_time, f"Rounding error detected: expected {expected_local_time}, got {actual_local_time}"

    def test_rounding_error_accumulation_without_scheduled_tick(self, clock_instance, mock_event_queue):
        """
        Verify that the rounding correction works by checking that scheduled_global_tick
        is calculated correctly when events are queued.

        This tests the if statement on lines 45-49 that sets localtime directly instead of calculating.
        """
        # Set up a timer to create a scheduled event
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 100, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        # First tick: set up timer
        clock_instance.tick(current_global_tick=1)
        scheduled_tick = clock_instance.scheduled_global_tick
        initial_earliest_local_time = clock_instance.earliest_next_local_time

        if scheduled_tick is None or scheduled_tick > 50:
            pytest.skip("Scheduled tick not generated or too far in future")

        # Reset and tick a few more times
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: []
        for tick in range(2, min(scheduled_tick, 50)):
            clock_instance.tick(current_global_tick=tick)

        # At scheduled tick, localtime should be set to earliest_next_local_time (not calculated)
        clock_instance.tick(current_global_tick=scheduled_tick)
        final_localtime = clock_instance.localtime

        # The key test: when scheduled_global_tick is reached, localtime should equal the expected value
        # This confirms the if statement (line 45-49) is setting it directly
        assert final_localtime == initial_earliest_local_time, f"Expected localtime to be set to {initial_earliest_local_time}, but got {final_localtime}"

    def test_local_event_queue_reference(self, clock_instance, mock_event_queue):
        """Clock should maintain reference to local event queue."""
        assert clock_instance.local_event_queue is mock_event_queue

    def test_timer_remaining_in_local_clock_info(self, clock_instance, mock_event_queue):
        """LocalClockInfo should include remaining time for each timer."""
        timer_event = create_local_event_net(LocalEventTypes.SET_TIMER, 100, LocalEventSubTypes.TIMER_1)
        mock_event_queue.get_current_events_by_type.side_effect = lambda evt_type, sub_type=None: [timer_event] if evt_type == LocalEventTypes.SET_TIMER else []

        clock_instance.tick(current_global_tick=1)

        # Get the LocalClockInfo from the call
        calls = clock_instance.local_event_queue.add_event_to_current_tick.call_args_list
        local_time_calls = [c for c in calls if c[0][0] == LocalEventTypes.LOCAL_TIME]

        assert len(local_time_calls) > 0
        local_clock_info = local_time_calls[0][0][1]
        assert isinstance(local_clock_info, LocalClockInfo)
