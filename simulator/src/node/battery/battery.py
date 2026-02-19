
class Battery:
    def __init__(self, capacityJule, rechargeRateJulePerSecond, secondToGlobalTick):
        self.capacity = capacityJule
        self.current_charge = capacityJule

        self.recharge_rate = rechargeRateJulePerSecond * secondToGlobalTick # jules charged per global tick
        self.secondToGlobalTick = secondToGlobalTick
    
    """ Returns False if battery is empty, True otherwise. """
    def tick(self, currentConsumptionJule):
        # Simulate gradual discharge over time (e.g., 1 unit per 100 steps)
        self.__recharge(self.recharge_rate)
        self.__consume(currentConsumptionJule)

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