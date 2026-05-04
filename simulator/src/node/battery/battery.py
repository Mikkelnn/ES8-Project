
from node.Imodule import IModule


class Battery(IModule):
    def __init__(self, capacity_joule: float, recharge_rate_joule_per_second: float, second_to_global_tick: float):
        self.capacity = capacity_joule
        self.current_charge = capacity_joule

        self.recharge_rate = recharge_rate_joule_per_second * second_to_global_tick # jules charged per global tick
        self.prev_net_change_joule: float = 0 # the consumption during warp
        self.last_global_tick_evaluated = None

    def tick(self, current_global_tick: int, current_consumption_joule: float) -> tuple[float, int | None]:
        warped_ticks = self.__ticks_pased_since_last(current_global_tick)

        # consumption during warp, excluding current tick
        self.current_charge += self.prev_net_change_joule * warped_ticks

        # current consuption until next warp end, same as current tick consumption
        net_change = self.recharge_rate - current_consumption_joule
        self.current_charge += net_change

        # clamp current chage
        if self.current_charge < 0:
            self.current_charge = 0        
        if self.current_charge > self.capacity:
            self.current_charge = self.capacity

        # determine if we will die and if so when -> this would be the next event time
        next_event_global_tick = None
        if self.is_dead():
            next_event_global_tick = current_global_tick + 1 # TODO: maybe add threashhold for when we wake i.e at 10%
        elif net_change < 0:
            next_event_global_tick = current_global_tick + int(self.current_charge / abs(net_change))

        # save for next time
        self.prev_net_change_joule = net_change

        return (0, next_event_global_tick) # The interface specifies consumption, and since battery is not consuming power but rather providing it, we return 0 here.

    def reset(self, current_global_tick: int) -> None:
        pass

    def is_dead(self) -> bool:
        return self.current_charge <= 0
    
    # returns tics passed excluding current tick
    def __ticks_pased_since_last(self, current_global_tick: int) -> int:
        ticks_passed = 0
        if self.last_global_tick_evaluated is not None:
            ticks_passed = current_global_tick - self.last_global_tick_evaluated - 1

        self.last_global_tick_evaluated = current_global_tick
        return ticks_passed
