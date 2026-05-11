# type: ignore
import numpy as np
from numpy import random as rnd

from custom_types import LocalClockInfo, LocalEventSubTypes, LocalEventTypes
from node.event_local_queue import LocalEventQueue
from node.Imodule import IModule


# log = Logger()
class Clock(IModule):
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.local_event_queue = local_event_queue

        self.local_time_increment_per_second = 1000
        self.global_ticks_per_local_time_increment = int(1 / second_to_global_tick / self.local_time_increment_per_second)

        self.sleep_until_local_time: int | None = None
        self.timer_1_end_local_time: int | None = None
        self.timer_2_end_local_time: int | None = None

        self.global_time_last: int = 0
        self.localtime: int = 0
        self.scheduled_global_tick: int | None = None
        self.earliest_next_local_time: int | None = None

        self.trend: float = rnd.uniform(-5e-2, 5e-2)
        self.noise_std: float = np.sqrt(20.970167331917025 * 3.915e-9)
        self.ar_constant: float = 0.9087642375247008
        self.random_vector: np.ndarray = rnd.normal(loc=0, scale=self.noise_std, size=100)
        self.alpha: float = self.random_vector[0]
        self.random_vector = self.random_vector[1:]

    def tick(self, current_global_tick: int) -> tuple[float, int | None]:

        # Check for external time sync (MegaSync)
        sync_events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.SYNC_LOCAL_TIME)

        if sync_events:
            correction = int(sync_events[0].data)
            self.local_time += correction  # +1 Because this time was scheduled 1 tick before
            if self.sleep_until_local_time is not None:
                self.sleep_until_local_time += correction
            if self.timer_1_end_local_time is not None:
                self.timer_1_end_local_time += correction
            if self.timer_2_end_local_time is not None:
                self.timer_2_end_local_time += correction

        elif self.scheduled_global_tick is not None and current_global_tick == self.scheduled_global_tick:
            # if we have reached the schedule global tick, use the ccalculatyed tieme to avoid rounding error
            self.localtime = self.earliest_next_local_time
        else:
            self.localtime = int((1 + self.alpha + self.trend) * (current_global_tick - self.global_time_last) + self.localtime)
        self.global_time_last = current_global_tick

        # calculate next clock skew
        self.alpha = self.ar_constant * self.alpha + self.random_vector[0]
        if self.random_vector.size == 1:
            self.random_vector = rnd.normal(loc=0, scale=self.noise_std, size=100)
        else:
            self.random_vector = self.random_vector[1:]

        # update timers
        set_timers = self.local_event_queue.get_current_events_by_type(LocalEventTypes.SET_TIMER)
        for set_timer in set_timers:
            timer_type = set_timer.sub_type
            timer_duration = set_timer.data
            match timer_type:
                case LocalEventSubTypes.TIMER_1:
                    self.timer_1_end_local_time = self.localtime + timer_duration - 1  # account for the 1tick delay from request
                case LocalEventSubTypes.TIMER_2:
                    self.timer_2_end_local_time = self.localtime + timer_duration - 1

        # Puplish tick event to local event bus
        local_clock_info = LocalClockInfo(
            current_local_time=self.localtime, timer_1_remaining=max(0, self.timer_1_end_local_time - self.localtime) if self.timer_1_end_local_time is not None else None, timer_2_remaining=max(0, self.timer_2_end_local_time - self.localtime) if self.timer_2_end_local_time is not None else None
        )
        self.local_event_queue.add_event_to_current_tick(LocalEventTypes.LOCAL_TIME, local_clock_info)

        sleep_request = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_SLEEP_FOR)
        if len(sleep_request) > 0:
            sleep_milliseconds = sleep_request[0].data
            # We subtract 2 ticks to ensure we wake up a bit before the sleep time, this is to account for delays in the processing of events.
            self.sleep_until_local_time = self.localtime + sleep_milliseconds - 2  # static 2 as 1 tick corresponds to 1 ms
            self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_SLEEP, None)

        if self.sleep_until_local_time is not None:
            if self.localtime >= self.sleep_until_local_time:
                self.sleep_until_local_time = None
                self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_WAKE_UP, None)

        # determine next global_tick for times if present
        if self.timer_1_end_local_time is not None:
            if self.localtime >= self.timer_1_end_local_time:
                self.timer_1_end_local_time = None

        if self.timer_2_end_local_time is not None:
            if self.localtime >= self.timer_2_end_local_time:
                self.timer_2_end_local_time = None

        self.earliest_next_local_time = None
        if self.earliest_next_local_time is None or (self.sleep_until_local_time is not None and self.sleep_until_local_time < self.earliest_next_local_time):
            self.earliest_next_local_time = self.sleep_until_local_time

        if self.earliest_next_local_time is None or (self.timer_1_end_local_time is not None and self.timer_1_end_local_time < self.earliest_next_local_time):
            self.earliest_next_local_time = self.timer_1_end_local_time

        if self.earliest_next_local_time is None or (self.timer_2_end_local_time is not None and self.timer_2_end_local_time < self.earliest_next_local_time):
            self.earliest_next_local_time = self.timer_2_end_local_time

        # get global time for: self.earliest_next_local_time
        if self.earliest_next_local_time is None:
            self.scheduled_global_tick = None
        else:
            deltaLocal = self.earliest_next_local_time - self.localtime
            self.scheduled_global_tick = int(current_global_tick + deltaLocal / (1 + self.alpha + self.trend))

        return (0, self.scheduled_global_tick)

    def reset(self, current_global_tick: int) -> None:
        self.timer_1_end_local_time = None
        self.timer_2_end_local_time = None
