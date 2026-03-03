from simulator.src.simulator.global_time import GlobalTime
import time

def test_singleton_behavior():
    t1 = GlobalTime()
    t2 = GlobalTime()
    assert t1 is t2, "GlobalTime is not a singleton!"


def test_time_set_get_increment_decrement():
    t = GlobalTime()
    t.set_time(10)
    assert t.get_time() == 10
    t.increment_time(5)
    assert t.get_time() == 15
    t.decrement_time(3)
    assert t.get_time() == 12
    t.set_time(0)
    assert t.get_time() == 0


def test_singleton_shared_state():
    t1 = GlobalTime()
    t2 = GlobalTime()
    t1.set_time(42)
    assert t2.get_time() == 42
    t2.increment_time(8)
    assert t1.get_time() == 50

def test_tps_calc_and_get_tps():
    t = GlobalTime()
    t.set_time(0)
    t.tick_checkpoint = 0
    t.time_checkpoint = time.time()
    # Simulate ticks over a short period
    for i in range(100):
        t.increment_time(1)
        time.sleep(0.005)  # 5 ms per tick, should vary a little
    t.tps_calc()
    tps = t.get_tps()
    assert tps > 0

    # Try with a different tick rate
    t.tick_checkpoint = t.get_time()
    t.time_checkpoint = time.time()
    for i in range(50):
        t.increment_time(1)
        time.sleep(0.01)  # 10 ms per tick

def test_tps_over_10_seconds():
    t = GlobalTime()
    t.set_time(0)
    t.tick_checkpoint = 0
    t.time_checkpoint = time.time()

    for i in range(0, 5):
        t.increment_time()

        time.sleep(1)

        t.tps_calc()
        print(f"TPS: {t.get_tps()}")
        assert t.get_tps() == 1

    # test not updating

    t.tps_calc()
    print(f"TPS no update tick: {t.get_tps()}")
    assert t.get_tps() == 0