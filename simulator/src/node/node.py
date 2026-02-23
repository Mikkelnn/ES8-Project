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

class Node(IModule):
    def __init__(self, node_id: int, second_to_global_tick: float, medium_service: MediumService):
        self.node_id = node_id
        self.local_event_queue = LocalEventQueue()

        self.battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=10, second_to_global_tick=second_to_global_tick)
        self.clock = Clock(self.node_id, self.local_event_queue, second_to_global_tick)
        self.tranceiver = TranceiverService(self.node_id, medium_service, self.local_event_queue, second_to_global_tick)
        self.protocol = PingPongProtocol(self.node_id, self.local_event_queue, second_to_global_tick) 
        self.state = State.DEAD

    def tick(self, current_global_tick: int):
        match self.state:
            case State.DEAD:
                self.battery.tick(0)
            case State.SLEEP:
                current_power_consumption = 0 # Base system usage
                current_power_consumption += self.clock.tick(current_global_tick)
                self.battery.tick(current_power_consumption)
            case State.WAKE:
                current_power_consumption = 0 # Base system usage
                current_power_consumption += self.clock.tick(current_global_tick)
                # TODO: Sensor
                current_power_consumption += self.tranceiver.tick(current_global_tick)
                current_power_consumption += self.protocol.tick(current_global_tick)
                self.battery.tick(current_power_consumption)
        
        if self.battery.is_dead() and self.state != State.DEAD:
            # Tell all modules we just died -> they need to reset and maybe do some cleanup
            self.clock.reset(current_global_tick)
            self.tranceiver.reset(current_global_tick)
            self.protocol.reset(current_global_tick)
            self.local_event_queue.reset(current_global_tick)
            self.state = State.DEAD

        if not self.battery.is_dead() and self.state == State.DEAD:
            self.state = State.WAKE # We can decide to start in sleep mode instead if we want to test that

        # Clear local event bus
        self.local_event_queue.clear_events()

        

        
