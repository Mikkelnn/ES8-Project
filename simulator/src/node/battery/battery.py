
from simulator.src.node.Imodule import IModule


class Battery(IModule):
    def __init__(self, capacity_joule, recharge_rate_jule_per_second: int, second_to_global_tick: float):
        self.capacity = capacity_joule
        self.current_charge = capacity_joule

        self.recharge_rate = recharge_rate_jule_per_second * second_to_global_tick # jules charged per global tick
    
    """ Returns False if battery is empty, True otherwise. """
    def tick(self, current_consumption_joule) -> bool:
        # Simulate gradual discharge over time (e.g., 1 unit per 100 steps)
        self.__recharge(self.recharge_rate)
        self.__consume(current_consumption_joule)

        if self.__is_empty():
            return False # Battery is empty
        return True # Battery still has charge


    def __consume(self, amount):
        self.current_charge -= amount
        if self.current_charge < 0:
            self.current_charge = 0

    def __recharge(self, amount):
        self.current_charge += amount
        if self.current_charge > self.capacity:
            self.current_charge = self.capacity

    def __is_empty(self):
        return self.current_charge <= 0