
import threading
import os
import sys

from .global_time import time_global
from ..custom_types import Severity, Area

class Logger:
	_instance = None
	_lock = threading.Lock()
	_log_file = os.path.join(os.path.dirname(__file__), '../../simulator.log')

	def __new__(cls):
		with cls._lock:
			if cls._instance is None:
				cls._instance = super().__new__(cls)
				cls._instance._logs = []
		return cls._instance

	def add(self, severity: Severity, area: Area, msg: str):
		# Use global simulation time for timestamp
		if not isinstance(severity, Severity):
			raise ValueError(f"severity must be a Severity enum, got {severity}")
		if not isinstance(area, Area):
			raise ValueError(f"area must be an Area enum, got {area}")
		sim_time = time_global().get_time()
		entry = {
			'sim_time': sim_time,
			'severity': severity.value,
			'area': area.value,
			'msg': msg
		}
		self._logs.append(entry)
		# Write to file
		with open(self._log_file, 'a', encoding='utf-8') as f:
			f.write(f"[t={sim_time}] [{severity.value}] ({area.value}): {msg}\n")

	def get(self, severity: Severity = None, area: Area = None, msg: str = None):
		results = self._logs
		if severity is not None:
			results = [log for log in results if log['severity'] == severity.value]
		if area is not None:
			results = [log for log in results if log['area'] == area.value]
		if msg is not None:
			results = [log for log in results if msg in log['msg']]
		return results
