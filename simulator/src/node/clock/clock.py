from simulator.src.node.eventBus.localEventBus import LocalEventBus

class Clock:
    def __init__(self, localeventbus: LocalEventBus, secondToGlobalTick):
        self.localeventbus = localeventbus
        self.secondToGlobalTick = secondToGlobalTick
        self.julesPerSecondConsumption = 1 # TODO: Set realistic value
        self.consuptionPerTick = self.julesPerSecondConsumption * self.secondToGlobalTick

        self.localTick = 0
        
    def tick(self):
        self.localTick += 1 # increment local tick with some drift

        # Puplish tick event to local event bus
        self.localeventbus.add_event_to_current_tick({"type": "tick", "tick": self.localTick})

        return self.consuptionPerTick # Power consumption for this tick
    