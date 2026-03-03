from enum import Enum

from medium.medium_service import MediumService
from node.battery.battery import Battery
from node.clock.clock import Clock
from node.event_local_queue import LocalEventQueue
from node.protocols.ping_pong import PingPongProtocol
from node.tranceiver.tranceiver_service import TranceiverService
from node.helpers.accumulated_state import AccumulatedState
from logger import ILogger

class State(Enum):
    DEAD = 1
    SLEEP = 2
    WAKE = 3

class Node:
    def __init__(self, node_id: int, second_to_global_tick: float, medium_service: MediumService, log: ILogger):
        self.node_id = node_id
        self.local_event_queue = LocalEventQueue()
        self.accumelated_state = AccumulatedState()

        self.battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=10, second_to_global_tick=second_to_global_tick)
        self.clock = Clock(self.node_id, self.local_event_queue, second_to_global_tick)
        self.tranceiver = TranceiverService(self.node_id, medium_service, self.local_event_queue, second_to_global_tick, log)
        self.protocol = PingPongProtocol(self.node_id, self.local_event_queue, second_to_global_tick, log) 
        self.state = State.WAKE

    def tick(self, current_global_tick: int) -> int | None:
        self.accumelated_state.reset()

        match self.state:
            case State.DEAD:
                pass
            case State.SLEEP:
                self.accumelated_state.update((0, None)) # Base system usage
                self.accumelated_state.update(self.clock.tick(current_global_tick))
            case State.WAKE:
                self.accumelated_state.update((0, None)) # Base system usage
                self.accumelated_state.update(self.clock.tick(current_global_tick))
                # TODO: Sensor
                self.accumelated_state.update(self.tranceiver.tick(current_global_tick))
                self.accumelated_state.update(self.protocol.tick(current_global_tick))

        # battery is always evaluated and done last
        self.accumelated_state.update(self.battery.tick(current_global_tick, self.accumelated_state.power))

        # deterimine if we died during the current tick        
        if self.battery.is_dead() and self.state != State.DEAD:
            # Tell all modules we just died -> they need to reset and maybe do some cleanup
            self.clock.reset(current_global_tick)
            self.tranceiver.reset(current_global_tick)
            self.protocol.reset(current_global_tick)
            self.local_event_queue.reset(current_global_tick)
            self.state = State.DEAD

        # deterrmine if we just came alive in this tick
        if self.state == State.DEAD and not self.battery.is_dead():
            self.state = State.WAKE # We can decide to start in sleep mode instead if we want to test that

        # Clear local event bus
        self.local_event_queue.clear_events()

        # determine earliest next tick among modules
        # if there are internal events scheduled for next tick, this is the earliest
        return self.accumelated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
