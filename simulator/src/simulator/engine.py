
from .logger import Logger
from custom_types import Severity, Area
import threading
from .global_time import time_global
import random
class Engine:

    def __init__(self):
        self.logger = Logger()
        self.running = False
        self.paused = False

    def _run_loop(self, stop_time=None):
        from .global_time import time_global
        import time
        timer = time_global()
        if stop_time is not None:
            self.logger.add(Severity.INFO, Area.SIMULATOR, f"Engine running from t={timer.get_time()} to t={stop_time}")
        else:
            self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine started running (infinite)")
        self.running = True
        self.paused = False
        while self.running:
            if stop_time is not None and timer.get_time() >= stop_time:
                break
            if self.paused:
                self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine paused; waiting to resume")
                while self.paused and self.running:
                    time.sleep(0.1)
                if not self.running:
                    self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine stopped during pause in run")
                    break
            #TODO change later
            # Simulate different data areas with data to export 
            current_time = timer.get_time()
            # Simulate log messages
            self.logger.add(Severity.INFO, Area.SIMULATOR, f"Status: running, time: {current_time}")
            self.logger.add(Severity.DEBUG, Area.NODE, f"Node event at t={current_time}")
            self.logger.add(Severity.WARNING, Area.GATEWAY, f"Gateway warning at t={current_time}")
            # Simulate data logs with units
            self.logger.add_data(Area.BATTERY, "level", 75 + random.uniform(-5, 5), unit="percent")
            self.logger.add_data(Area.BATTERY, "voltage", 3.7 + random.uniform(-0.1, 0.1), unit="V")
            self.logger.add_data(Area.CLOCK, "tick", 1 + random.randint(-1, 1), unit="ms")
            self.logger.add_data(Area.CLOCK, "drift", random.uniform(-0.05, 0.05), unit="ms")
            self.logger.add_data(Area.TRANCEIVER, "signal", random.uniform(0, 100), unit="dBm")
            self.logger.add_data(Area.TRANCEIVER, "snr", random.uniform(-10, 20), unit="dB")

            timer.increment_time(1)
        self.logger.add(Severity.INFO, Area.SIMULATOR, f"Engine finished running at t={timer.get_time()}")
        self.running = False

    def run(self):
        import threading
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def run_for(self, time_units: int):

        timer = time_global()
        stop_time = timer.get_time() + time_units
        t = threading.Thread(target=self._run_loop, args=(stop_time,), daemon=True)
        t.start()

    def pause(self):
        if self.running:
            self.paused = True
            self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine paused")

    def stop(self):
        if self.running:
            self.running = False
            self.paused = False
            self.logger.add(Severity.INFO, Area.SIMULATOR, "Engine stopped")


if __name__ == "__main__":
    engine = Engine()
    engine.run()
