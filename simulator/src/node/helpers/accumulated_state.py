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
    
    def get_accumulated(self) -> tuple[float, int | None]:
        return (self.power, self.earliest_global_tick)