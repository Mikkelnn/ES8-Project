from custom_types import LocalEventTypes
from node.Imodule import IModule
from node.event_local_queue import LocalEventQueue

# log = Logger()
class Clock(IModule):
    def __init__(self, node_id: int, local_event_queue: LocalEventQueue, second_to_global_tick: float):
        self.node_id = node_id
        self.local_event_queue = local_event_queue

        joules_per_second_consumption = 1E-6 # TODO: Set realistic value
        self.consuption_per_tick = joules_per_second_consumption * second_to_global_tick

        # self.local_time: int = 0
        # self.local_tick: int = 0

        self.local_time_increment_per_second = 1000
        self.global_ticks_per_local_time_increment = int(1 / second_to_global_tick / self.local_time_increment_per_second)

        self.sleep_until_local_time: int | None = None
        self.global_tick_for_wake_up: int | None = None
        
    def tick(self, current_global_tick: int) -> float | None:

        # calculate the local time from global, this is an ideal clock
        local_time = int(current_global_tick / self.global_ticks_per_local_time_increment)

        # Puplish tick event to local event bus
        self.local_event_queue.add_event_to_current_tick(LocalEventTypes.LOCAL_TIME, local_time)

        sleep_request = self.local_event_queue.get_current_events_by_type(LocalEventTypes.NODE_SLEEP_FOR)
        if len(sleep_request) > 0:
            sleep_milliseconds = sleep_request[0].data
            # We subtract 2 ticks to ensure we wake up a bit before the sleep time, this is to account for delays in the processing of events.
            self.sleep_until_local_time = local_time + sleep_milliseconds - 2 # static 2 as 1 tick corresponds to 1 ms
            self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_SLEEP)

        if self.sleep_until_local_time is not None:
            # determine next tick to evaluate.
            self.global_tick_for_wake_up = self.sleep_until_local_time * self.global_ticks_per_local_time_increment
            
            if local_time >= self.sleep_until_local_time:
                self.sleep_until_local_time = None
                self.global_tick_for_wake_up = None
                self.local_event_queue.add_event_to_current_tick(LocalEventTypes.NODE_WAKE_UP)

        return (self.consuption_per_tick, self.global_tick_for_wake_up) # Power consumption for this tick
    
    def reset(self, current_global_tick: int) -> None:
        # self.local_time = 0
        # self.local_tick = 0
        pass