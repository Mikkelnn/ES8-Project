# known_neighbors = [0, 1]
# slot_count = 3
# own_slot = 2

# used_slots = {n for n in known_neighbors if n > -1}
# used_slots.add(own_slot)
# usable = set(range(slot_count))

# available = usable.difference(used_slots)
# if not available:
#     print("shit")

# print(available)
# print(available[0] if available else 0)

_slot_count = 17
_own_tx_slot: int = 3
_observed_slots: dict[int, int] = {

}

def get_slot(node):
    used = set(_observed_slots.values()) | {_own_tx_slot}
    start = (_own_tx_slot % (_slot_count - 1)) + 1
    for i in range(_slot_count - 1):
        slot = (start - 1 + i) % (_slot_count - 1) + 1
        if slot not in used:
            return slot

    print(f"slot exhaustion")
    return 0


for n in range(16):
    s = get_slot(n)
    _observed_slots[n] = s
    print(f"Node {n}, {s}")