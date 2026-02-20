import threading
import os
from .global_time import time_global
from custom_types import Severity, Area

LOG_PATH = os.path.join(os.path.dirname(__file__), '../../simulator.log')

class Logger:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._logs = {}  # key: tuple, value: log dict
        self._log_file = LOG_PATH
        self._lock = threading.Lock()
        self._initialized = True

    def set_log_file(self, log_file):
        self._log_file = log_file

    def _make_log_key(self, entry):
        # Use all fields as a tuple for uniqueness
        return tuple(sorted(entry.items()))

    def add(self, severity: Severity, area: Area, msg: str):
        if not isinstance(severity, Severity) or not isinstance(area, Area):
            raise TypeError("Logger.add requires Severity and Area enums for severity and area arguments.")
        sim_time = time_global().get_time()
        entry = {
            'sim_time': sim_time,
            'severity': severity.value,
            'area': area.value,
            'msg': msg
        }
        key = self._make_log_key(entry)
        with self._lock:
            self._logs[key] = entry

    def add_data(self, area: Area, label: str, data: float, unit: str = None):
        if not isinstance(area, Area):
            raise TypeError("Logger.add_data requires Area enum for area argument.")
        sim_time = time_global().get_time()
        entry = {
            'sim_time': sim_time,
            'area': area.value,
            'label': label,
            'data': data,
            'unit': unit
        }
        key = self._make_log_key(entry)
        with self._lock:
            self._logs[key] = entry

    def get(self, severity: Severity = None, area: Area = None, msg: str = None):
        with self._lock:
            results = list(self._logs.values())
        if severity is not None:
            if not isinstance(severity, Severity):
                raise TypeError("Logger.get requires Severity enum for severity argument.")
            results = [log for log in results if log.get('severity') == severity.value]
        if area is not None:
            if not isinstance(area, Area):
                raise TypeError("Logger.get requires Area enum for area argument.")
            results = [log for log in results if log.get('area') == area.value]
        if msg is not None:
            results = [log for log in results if 'msg' in log and msg in log['msg']]
        return results

    def get_data(self, label: str = None):
        with self._lock:
            data_logs = [log for log in self._logs.values() if 'label' in log and 'data' in log]
        if label is not None:
            data_logs = [log for log in data_logs if log['label'] == label]
        return data_logs

    def save_to_file(self, path=None):
        """Write all logs to the given file (or default log file), sorted by simulation time."""
        log_path = path or self._log_file
        with self._lock:
            logs = sorted(self._logs.values(), key=lambda log: log.get('sim_time', 0))
        with open(log_path, 'w', encoding='utf-8') as f:
            for log in logs:
                if 'severity' in log:
                    f.write(f"[t={log['sim_time']}] [{log['severity']}] ({log['area']}): {log['msg']}\n")
                elif 'label' in log and 'data' in log:
                    unit = log.get('unit', None)
                    if unit:
                        f.write(f"[t={log['sim_time']}] [DATA] ({log['area']}) [{log['label']}]: {log['data']} {unit}\n")
                    else:
                        f.write(f"[t={log['sim_time']}] [DATA] ({log['area']}) [{log['label']}]: {log['data']}\n")
