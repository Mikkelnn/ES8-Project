from enum import Enum

from medium.medium_service import MediumService
from node.Imodule import IModule
from node.battery.battery import Battery
from node.clock.clock import Clock
from node.event_local_queue import LocalEventQueue
from node.protocols.ping_pong import PingPongProtocol
from node.tranceiver.tranceiverService import TranceiverService

class State(Enum):
    DEAD = 1
    SLEEP = 2
    WAKE = 3

class AccumulatedState:
    def __init__(self):
        self.reset()
    
    def update(self, state: tuple[float, int | None]) -> None:
        (power, tick) = state
        self.power += abs(power)
        if tick is not None and (self.earliest_global_tick is None or self.earliest_global_tick > tick):
            self.earliest_global_tick = tick
        
    def reset(self):
        self.power = 0
        self.earliest_global_tick = None

class Node(IModule):
    def __init__(self, node_id: int, second_to_global_tick: float, medium_service: MediumService):
        self.node_id = node_id
        self.local_event_queue = LocalEventQueue()
        self.accumelated_state = AccumulatedState()

        self.battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=10, second_to_global_tick=second_to_global_tick)
        self.clock = Clock(self.node_id, self.local_event_queue, second_to_global_tick)
        self.tranceiver = TranceiverService(self.node_id, medium_service, self.local_event_queue, second_to_global_tick)
        self.protocol = PingPongProtocol(self.node_id, self.local_event_queue, second_to_global_tick) 
        self.state = State.DEAD

    def tick(self, current_global_tick: int):
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
        
        if self.battery.is_dead() and self.state != State.DEAD:
            # Tell all modules we just died -> they need to reset and maybe do some cleanup
            self.clock.reset(current_global_tick)
            self.tranceiver.reset(current_global_tick)
            self.protocol.reset(current_global_tick)
            self.local_event_queue.reset(current_global_tick)
            self.state = State.DEAD

        if self.state == State.DEAD and not self.battery.is_dead():
            self.state = State.WAKE # We can decide to start in sleep mode instead if we want to test that

        # Clear local event bus        
        self.local_event_queue.clear_events()

        # determine earliest next tick among modules
        # if there are internal events scheduled for next tick, this is the earliest
        return self.accumelated_state.earliest_global_tick if not self.local_event_queue.have_events() else current_global_tick + 1
