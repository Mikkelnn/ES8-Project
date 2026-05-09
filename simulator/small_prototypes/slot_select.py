known_neighbors = [0,1]
slot_count = 3
own_slot = 2

used_slots = {n for n in known_neighbors if n > -1}
used_slots.add(own_slot)
usable = set(range(slot_count))

available = usable.difference(used_slots)
if not available:
    print("shit")

print(available)
# print(available[0] if available else 0)

