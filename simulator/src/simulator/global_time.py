import time
import math

class GlobalTime:
    instance = None
    
    def __init__(self):
        self.tick = 0
        self.time_start = time.time()
        self.tick_checkpoint = 0
        self.time_checkpoint = 0
        self.tps = 0
        self.tick_pr_time_unit = 0.001 # 1 milliseconds

    def __new__(cls): #Singlton so that no duplicates are possible, ie multiple time tracks
        if cls.instance is None:
            cls.instance = super().__new__(cls)
            cls.instance.__init__()
        return cls.instance

    def get_time(self) -> int:
        return self.tick

    def set_time(self, value: int):
        self.tick = int(value)

    def increment_time(self, value: int = 1):
        self.tick += int(value)
    
    def decrement_time(self, value: int = 1):
        self.tick -= int(value)

    def tps_calc(self):
        time_current = time.time()
        time_spent = time_current - self.time_checkpoint

        tick_spent = self.tick - self.tick_checkpoint

        self.tps = int(math.ceil(tick_spent / time_spent))

        #update checkpoints
        self.time_checkpoint = time_current
        self.tick_checkpoint = self.tick

    def get_tps(self) -> int:
        return self.tps