import math

class LoRaTxDurationCalculator:
    """Reusable LoRa transmission duration calculator."""

    def __init__(self, second_to_global_tick: float, spreading_factor: int = 7, bandwidth: int = 125000, coding_rate: float | None = None, preamble_length: int = 8):
        self._second_to_global_tick = second_to_global_tick
        self._sf = spreading_factor
        self._bandwidth = bandwidth
        self._coding_rate = 1 / (4 / 5) if coding_rate is None else coding_rate
        self._preamble_length = preamble_length

        self._ts = (2 ** self._sf) / self._bandwidth
        self._preamble_time_ticks = ((self._preamble_length + 4.25) * self._ts * (1 / self._second_to_global_tick))

    def get_duration(self, payload_length_bytes: int) -> int:
        """Return the LoRa transmission duration in global ticks for payload length."""
        if payload_length_bytes < 0:
            raise ValueError("payload_length_bytes must be >= 0")

        n_symbols = math.ceil((payload_length_bytes * 8 * self._coding_rate) / self._sf)
        symbol_time_ticks = math.ceil(n_symbols * self._ts * (1 / self._second_to_global_tick))

        return int(symbol_time_ticks + self._preamble_time_ticks)


if __name__ == "__main__":
    bytes = 11 + 4
    ms = LoRaTxDurationCalculator(second_to_global_tick=0.001).get_duration(bytes)
    print(f"bytes: {bytes} takes {ms} ms")
