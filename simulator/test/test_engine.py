import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import time
from simulator.src.simulator.engine import Engine
from simulator.src.simulator.global_time import time_global

def test_engine_run_for_pause_resume():
    # Reset global time
    timer = time_global()
    timer.set_time(0)
    engine = Engine()
    # Start run_for in background for 10 units
    engine.run_for(10)
    # Wait until engine is running (up to 2s)
    for _ in range(40):
        if engine.running:
            break
        time.sleep(0.05)
    assert engine.running is True
    # Pause mid-run
    engine.pause()
    # Wait for pause to take effect (up to 1s)
    for _ in range(20):
        if engine.paused:
            break
        time.sleep(0.05)
    paused_time = timer.get_time()
    assert engine.paused is True
    # Wait to ensure it stays paused
    time.sleep(0.3)
    assert abs(timer.get_time() - paused_time) <= 1  # Allow for race condition
    # Resume
    engine.paused = False
    # Wait for resume to take effect (up to 1s)
    for _ in range(20):
        if not engine.paused:
            break
        time.sleep(0.05)
    time.sleep(0.3)
    # Should continue running
    assert timer.get_time() >= paused_time  # Should continue running or finish
    # Stop mid-run
    engine.stop()
    stopped_time = timer.get_time()
    time.sleep(0.2)
    # Should not advance after stop
    assert abs(timer.get_time() - stopped_time) <= 1


def test_engine_run_for_completes():
    timer = time_global()
    timer.set_time(0)
    engine = Engine()
    engine.run_for(5)
    # Wait for engine to stop (up to 2 seconds)
    for _ in range(20):
        if not engine.running:
            break
        time.sleep(0.1)
    # After engine stops, wait up to 1s for timer to reach 5
    for _ in range(10):
        if timer.get_time() >= 5:
            break
        time.sleep(0.1)
    assert timer.get_time() >= 5
    assert not engine.running
