from enum import Enum
from unittest import case

from simulator.src.node.battery.battery import Battery
from simulator.src.node.clock.clock import Clock
from simulator.src.node.eventBus.localEventBus import LocalEventBus
from simulator.src.node.tranceiver.D2DLoRa import D2DLoRa

class State(Enum):
    JUST_DIED = 0
    DEAD = 1
    SLEEP = 2
    WAKE = 3

class Node:
    def __init__(self, node_id, secondToGlobalTick, globaleventbus):
        self.node_id = node_id
        
        self.globaleventbus = globaleventbus
        self.localeventbus = LocalEventBus()

        self.battery = Battery(capacityJule=1000, rechargeRateJulePerSecond=10, secondToGlobalTick=secondToGlobalTick) #TODO: Make these parameters configurable
        self.clock = Clock(self.localeventbus, secondToGlobalTick)

        self.tranceiver = D2DLoRa(self.node_id, self.globaleventbus, self.localeventbus, secondToGlobalTick)
        self.state = State.DEAD #TODO: Change to sleep when we have a battery model

    def tick(self, currentGlobalStep):
        match self.state:
            case State.DEAD:
                currentPowerConsumption = 0
                havePower = self.battery.tick(currentPowerConsumption)
                if havePower:
                    self.state = State.SLEEP
            case State.SLEEP:
                currentPowerConsumption = 0 # Base system usage
                currentPowerConsumption += self.clock.tick()
                havePower = self.battery.tick(currentPowerConsumption)
                if not havePower:
                    self.state = State.JUST_DIED
            case State.WAKE:
                currentPowerConsumption = 0 # Base system usage
                currentPowerConsumption += self.clock.tick()
                # Sensor
                currentPowerConsumption += self.tranceiver.loop(currentGlobalStep)
                # Protocol
                havePower = self.battery.tick(currentPowerConsumption)
                if not havePower:
                    self.state = State.JUST_DIED
        
        if self.state == State.JUST_DIED:
            # Clear local event bus
            # TODO: Tell all modules we just died -> they need to reset and maybe do some cleanup
            self.state = State.DEAD

        # Clear local event bus
        self.localeventbus.clear_events()



        

        
