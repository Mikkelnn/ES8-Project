from simulator.src.simulator.global_time import time_global
import pytest

def test_singleton_behavior():
    t1 = time_global()
    t2 = time_global()
    assert t1 is t2, "time_global is not a singleton!"


def test_time_set_get_increment_decrement():
    t = time_global()
    t.set_time(10)
    assert t.get_time() == 10
    t.increment_time(5)
    assert t.get_time() == 15
    t.decrement_time(3)
    assert t.get_time() == 12
    t.set_time(0)
    assert t.get_time() == 0


def test_singleton_shared_state():
    t1 = time_global()
    t2 = time_global()
    t1.set_time(42)
    assert t2.get_time() == 42
    t2.increment_time(8)
    assert t1.get_time() == 50
