import time
import multiprocessing
from simulator.src.main import start_gui_process


def test_gui_starts_in_own_process():
    proc = start_gui_process()
    time.sleep(1)  # Give the GUI time to start
    assert proc.is_alive(), "GUI process should be alive after starting."
    assert proc.pid != multiprocessing.current_process().pid, "GUI should run in a different process."
    proc.terminate()
    proc.join(timeout=2)
    assert not proc.is_alive(), "GUI process should terminate cleanly."
