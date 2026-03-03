import math


# events = SortedDict({ 1: set(range(0, 20)) })


# events.setdefault(3, default=set()).add(3)
# events.setdefault(3, default=set()).add(3)
# events.setdefault(3, default=set()).add(4)

# events.setdefault(5, default=set())

# while len(events):
#   e = events.popitem(0)
#   print(e)
#   for i in e[1]:
#     print(i)


_second_to_global_tick = 0.001 # ms
data = [1]

__sf = 7 # Spreading factor
__bandwidth = 125000 # Bandwidth in Hz
__coding_rate = 1 # Coding rate (1 means 4/5, 2 means 4/6, etc.)
__preamble_length = 8 # Preamble length in symbols

# Calculate the effective data rate based on SF, bandwidth, and coding rate
__effective_data_rate_tick = (__bandwidth / (2 ** __sf)) * (4 / (4 + __coding_rate)) * _second_to_global_tick
# Calculate the preamble time in seconds
__preamble_time_ticks = ((__preamble_length + 4.25) * (2 ** __sf) / __bandwidth) / _second_to_global_tick

print(f"__effective_data_rate_tick {__effective_data_rate_tick} b/t, __preamble_time_ticks: {__preamble_time_ticks} t")

ticks = (len(data) * 8 / __effective_data_rate_tick) + __preamble_time_ticks
print(f"duration: {ticks} t")
ticks = int(math.ceil(ticks))
print(f"ceiled duration: {ticks} t")