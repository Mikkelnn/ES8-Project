# type: ignore
from custom_types import Area, LocalClockInfo, LocalEventSubTypes, LocalEventTypes, Severity
from logger.ILogger import ILogger
from node.event_local_queue import LocalEventQueue
from node.helpers.accumulated_state import AccumulatedState
from node.Imodule import IModule


# log = Logger()
class Clock(IModule):
    def __init__(self, log: ILogger, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.local_event_queue = local_event_queue
        self.log = log

        joules_per_second_consumption = 1e-6  # TODO: Set realistic value
        self.consuption_per_tick = joules_per_second_consumption * second_to_global_tick

        self.accumulated_state = AccumulatedState()

        self.local_time_increment_per_second = 1000
        self.global_ticks_per_local_time_increment = int(1 / second_to_global_tick / self.local_time_increment_per_second)

        self.sleep_until_local_time: int | None = None
        self.global_tick_for_wake_up: int | None = None

        self.timer_1_end_local_time: int | None = None
        self.timer_2_end_local_time: int | None = None

        self.total_correction = 0

    def tick(self, current_global_tick: int) -> tuple[float, int | None]:
        self.accumulated_state.reset()

        local_time = current_global_tick

        # local_time = int(current_global_tick / self.global_ticks_per_local_time_increment) + self.total_correction

        # # print(f"clock local time {local_time}")

        # # Check for external time sync (MegaSync)
        sync_events = self.local_event_queue.get_current_events_by_type(LocalEventTypes.SYNC_LOCAL_TIME)
        if sync_events:
            self.log.add(Severity.INFO, Area.CLOCK, current_global_tick, f"Node id {self.node_id} clock correction: {int(sync_events[0].data)}")
        #     drift_before_correction = local_time - current_global_tick

        #     correction = int(sync_events[0].data)
        #     self.total_correction += correction
        #     local_time += correction  # +1 Because this time was scheduled 1 tick before
        #     if self.sleep_until_local_time is not None:
        #         self.sleep_until_local_time += correction
        #     if self.timer_1_end_local_time is not None:
        #         self.timer_1_end_local_time += correction
        #     if self.timer_2_end_local_time is not None:
        #         self.timer_2_end_local_time += correction

        #     self.log.add(Severity.INFO, Area.CLOCK, current_global_tick, f"Node id {self.node_id} clock drift before correction: {drift_before_correction}, after correction: {local_time - current_global_tick}")

        # update timers
        set_timers = self.local_event_queue.get_current_events_by_type(LocalEventTypes.SET_TIMER)
        for set_timer in set_timers:
            timer_type = set_timer.sub_type
            timer_duration = set_timer.data
            match timer_type:
                case LocalEventSubTypes.TIMER_1:
                    self.timer_1_end_local_time = local_time + timer_duration - 1  # account for the 1tick delay from request
                case LocalEventSubTypes.TIMER_2:
                    self.timer_2_end_local_time = local_time + timer_duration - 1

        # Puplish tick event to local event bus
        local_clock_info = LocalClockInfo(current_local_time=local_time, timer_1_remaining=max(0, self.timer_1_end_local_time - local_time) if self.timer_1_end_local_time is not None else None, timer_2_remaining=max(0, self.timer_2_end_local_time - local_time) if self.timer_2_end_local_time is not None else None)
        self.local_event_queue.add_event_to_current_tick(LocalEventTypes.LOCAL_TIME, local_clock_info)

        sleep_request = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_SLEEP_FOR)
        if len(sleep_request) > 0:
            sleep_milliseconds = sleep_request[0].data
            # We subtract 2 ticks to ensure we wake up a bit before the sleep time, this is to account for delays in the processing of events.
            self.sleep_until_local_time = local_time + sleep_milliseconds - 2  # static 2 as 1 tick corresponds to 1 ms
            self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_SLEEP, None)

        if self.sleep_until_local_time is not None:
            # determine next tick to evaluate.
            self.global_tick_for_wake_up = self.sleep_until_local_time * self.global_ticks_per_local_time_increment  # TODO: chyange from ideal linear

            if local_time >= self.sleep_until_local_time:
                self.sleep_until_local_time = None
                self.global_tick_for_wake_up = None
                self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_WAKE_UP, None)
            else:
                self.accumulated_state.update((0, self.global_tick_for_wake_up))

        # determine next global_tick for times if present
        if self.timer_1_end_local_time is not None:
            global_tick_for_timer_1 = self.timer_1_end_local_time * self.global_ticks_per_local_time_increment  # TODO: change from ideal linear
            if local_time >= self.timer_1_end_local_time:
                self.timer_1_end_local_time = None
            else:
                self.accumulated_state.update((0, global_tick_for_timer_1))

        if self.timer_2_end_local_time is not None:
            global_tick_for_timer_2 = self.timer_2_end_local_time * self.global_ticks_per_local_time_increment  # TODO: change from ideal linear
            if local_time >= self.timer_2_end_local_time:
                self.timer_2_end_local_time = None
            else:
                self.accumulated_state.update((0, global_tick_for_timer_2))

        return self.accumulated_state.get_accumulated()  # Power consumption for this tick

    def reset(self, current_global_tick: int) -> None:
        self.timer_1_end_local_time = None
        self.timer_2_end_local_time = None
