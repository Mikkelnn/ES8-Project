import pytest
from simulator.src.simulator.logger import Logger
from simulator.src.custom_types import Severity, Area

def test_logger_singleton():
    l1 = Logger()
    l2 = Logger()
    assert l1 is l2, "Logger is not a singleton!"

def test_logger_add_and_get():
    logger = Logger()
    logger._logs.clear()  # Clear previous logs for test isolation
    logger.add(Severity.INFO, Area.SIMULATOR, "Simulation started")
    logger.add(Severity.ERROR, Area.NODE, "Node failure")
    logs = logger.get()
    assert any(log['msg'] == "Simulation started" for log in logs)
    assert any(log['msg'] == "Node failure" for log in logs)
    # Test filtering
    info_logs = logger.get(severity=Severity.INFO)
    assert all(log['severity'] == Severity.INFO.value for log in info_logs)
    node_logs = logger.get(area=Area.NODE)
    assert all(log['area'] == Area.NODE.value for log in node_logs)
    msg_logs = logger.get(msg="failure")
    assert all("failure" in log['msg'] for log in msg_logs)

def test_logger_add_wrong_severity():
    logger = Logger()
    with pytest.raises(ValueError):
        logger.add("NOT_A_SEVERITY", Area.SIMULATOR, "Bad severity")

def test_logger_add_wrong_area():
    logger = Logger()
    with pytest.raises(ValueError):
        logger.add(Severity.INFO, "NOT_AN_AREA", "Bad area")

def test_logger_get_wrong_types():
    logger = Logger()
    # Should not raise, but will not match anything
    logs = logger.get(severity=Severity.INFO, area=Area.SIMULATOR, msg="notfound")
    assert isinstance(logs, list)
