

import threading
import os
from .global_time import time_global
from custom_types import Severity, Area

LOG_PATH = os.path.join(os.path.dirname(__file__), '../../simulator.log')

class Logger:

	@classmethod
	def set_log_file(cls, log_file):
		# Ensure the log file exists
		log_path = os.path.abspath(log_file)
		os.makedirs(os.path.dirname(log_path), exist_ok=True)
		if not os.path.exists(log_path):
			with open(log_path, 'w', encoding='utf-8') as f:
				pass
		with cls._lock:
			if cls._instance is not None:
				cls._instance._log_file = log_path
			else:
				cls._log_file = log_path

	_instance = None
	_lock = threading.Lock()
	_log_file = LOG_PATH


	def __new__(cls, log_file=None):
		with cls._lock:
			if cls._instance is None:
				cls._instance = super().__new__(cls)
				cls._instance._logs = []
			if log_file is not None:
				cls._instance._log_file = log_file
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
