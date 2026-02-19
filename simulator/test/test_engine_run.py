import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import time
from simulator.src.simulator.engine import Engine
from simulator.src.simulator.global_time import time_global

def test_engine_run_pause_resume_stop():
    timer = time_global()
    timer.set_time(0)
    engine = Engine()
    engine.run()
    # Wait until engine is running
    for _ in range(20):
        if engine.running:
            break
        time.sleep(0.05)
    assert engine.running is True
    # Let it run a bit
    time.sleep(0.2)
    # Pause
    engine.pause()
    paused_time = timer.get_time()
    assert engine.paused is True
    time.sleep(0.2)
    # Should not advance while paused
    assert timer.get_time() == paused_time
    # Resume
    engine.paused = False
    time.sleep(0.2)
    # Should continue running
    assert timer.get_time() > paused_time
    # Stop
    engine.stop()
    stopped_time = timer.get_time()
    time.sleep(0.2)
    # Should not advance after stop
    assert timer.get_time() == stopped_time
    assert not engine.running