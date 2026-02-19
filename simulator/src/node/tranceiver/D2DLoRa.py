from simulator.src.node.eventBus.localEventBus import LocalEventBus


class D2DLoRa:
    def __init__(self, node_id, globaleventbus, localeventbus: LocalEventBus, secondToGlobalTick):
        self.node_id = node_id
        self.globaleventbus = globaleventbus
        self.localeventbus = localeventbus
        self.secondToGlobalTick = secondToGlobalTick
        
    def tick(self, currentGlobalStep):

        return 0 # Power consumption for this tick