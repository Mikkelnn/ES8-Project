
class time_global:
    _instance = None

    def __new__(cls): #Singlton so that no duplicates are possible, ie multiple time tracks
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._time = 0
        return cls._instance

    def get_time(self) -> int:
        return self._time

    def set_time(self, value: int):
        self._time = int(value)

    def increment_time(self, value: int = 1):
        self._time += int(value)
    
    def decrement_time(self, value: int = 1):
        self._time -= int(value)