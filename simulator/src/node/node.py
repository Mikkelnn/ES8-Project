from enum import Enum

from simulator.src.node.Imodule import IModule
from simulator.src.node.battery.battery import Battery
from simulator.src.node.clock.clock import Clock
from simulator.src.node.event_local_queue import LocalEventQueue
from simulator.src.node.tranceiver.tranceiverManager import TranceiverManager
from simulator.src.simulator.global_event_queue import GlobalEventQueue

class State(Enum):
    JUST_DIED = 0
    DEAD = 1
    SLEEP = 2
    WAKE = 3

class Node(IModule):
    def __init__(self, node_id: int, second_to_global_tick: float, global_event_queue: GlobalEventQueue):
        self.node_id = node_id
        
        self.global_event_queue = global_event_queue
        self.local_event_queue = LocalEventQueue()

        self.battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=10, second_to_global_tick=second_to_global_tick) #TODO: Make these parameters configurable
        self.clock = Clock(self.local_event_queue, second_to_global_tick)

        self.tranceiver = TranceiverManager(self.node_id, self.global_event_queue, self.local_event_queue, second_to_global_tick)
        self.state = State.DEAD

    def tick(self, current_global_tick: int):
        match self.state:
            case State.DEAD:
                havePower = self.battery.tick(current_power_consumption=0)
                if havePower:
                    self.state = State.SLEEP
            case State.SLEEP:
                current_power_consumption = 0 # Base system usage
                current_power_consumption += self.clock.tick()
                havePower = self.battery.tick(current_power_consumption)
                if not havePower:
                    self.state = State.JUST_DIED
            case State.WAKE:
                current_power_consumption = 0 # Base system usage
                current_power_consumption += self.clock.tick()
                # Sensor
                current_power_consumption += self.tranceiver.tick(current_global_tick)
                # Protocol
                havePower = self.battery.tick(current_power_consumption)
                if not havePower:
                    self.state = State.JUST_DIED
        
        if self.state == State.JUST_DIED:
            # TODO: Tell all modules we just died -> they need to reset and maybe do some cleanup
            self.clock.reset(current_global_tick)
            self.tranceiver.reset(current_global_tick)
            self.local_event_queue.reset(current_global_tick)
            self.state = State.DEAD
            return

        # Clear local event bus
        self.local_event_queue.clear_events()



        

        
