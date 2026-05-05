from copy import replace
from dataclasses import dataclass
from typing import List


@dataclass
class EventNet:
	data: List[int]
	rssi: int | None = None


if __name__ == "__main__":
	event1 = EventNet(data=[1, 2, 3], rssi=-80)
	event2 = replace(event1, rssi=-70)

	print(event1)
	print(event2)

	event1.data.append(4)

	print(event1)
	print(event2)
