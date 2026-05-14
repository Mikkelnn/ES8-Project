# Metrics

Log format reference:
```
[LEVEL] (COMPONENT) @ tick: message
```
- Levels: `DEBUG`, `INFO`, `WARNING`, `CRITICAL`
- Components: `NODE`, `TRANCEIVER`, `PROTOCOL`
- `tick` is an integer (milliseconds). Float ticks in the log are a simulator logging error and are not matched.

---

## 1. Packet forwarding delay — *not implemented*
Track the time from when a packet first appears at a node to when it first appears at a gateway, using the UUID as the correlation key.

- On first UUID appearance at a node → record `(uuid object: [tick, node_id])` as a dict
- On first UUID appearance at a gateway → compute `delay = gateway_tick - node_tick` signifying a successful transmission
- Record the information in a new dictionary: {node_id: [diff:int, successful_transmission_count:int, lost:int(initialised to 0)]}
- Pop the UUID object and the tick value from the dict.
- Once the simulation log is completely parsed. I need to parse the UUID dictionary to identify the lost UUIDs and increment the count of the nodes_id in the second dictionary.
- the lost count indicated the packet loss per node, which we then need to represent in a histogram with 10 bins.

Example of Node to gateway: 
- Code: self.log.add(Severity.INFO, Area.GATEWAY, current_global_tick, f"Gateway {self.gateway_id} received data:{data}, GUID={data.mac_payload.frm_payload.guid}")
- Regex: \[INFO\]\s+\(GATEWAY\)\s+@\s+(?P<tick>\d+):\s+Gateway\s+(?P<gateway_id>\d+)\s+received
  data:.*GUID=(?P<guid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})

- Example: [INFO] (GATEWAY) @ 5000: Gateway 1 received data:LoRaWanPHYPayload(mhdr=64, mac_payload=MACPayload(dev_addr=1, fctrl_flags=<FCtrlUplink: 0>, fcnt=5, frm_payload=PayloadData(id={1, 2}, length_payload=14, time=1000.0, data=Data(sensor1=0, sensor2=0), guid=UUID('f47ac10b-58cc-4372-a567-0e02b2c3d479')), fopts=b'', fport=1), join_request=None, join_accept=None, mic=b'\x00\x00\x00\x00'), GUID=f47ac10b-58cc-4372-a567-0e02b2c3d479,

Example of Generation of Node:
- Code: self.log.add(Severity.INFO, Area.PROTOCOL, current_global_tick, f"Node {self.node_id} enqueued averaged payload: avg_s1={avg_s1}, avg_s2={avg_s2}, GUID={self.payload_data.guid}")
- Regex: \[INFO\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+enqueued averaged
  payload:\s+avg_s1=(?P<avg_s1>[\d.]+),\s+avg_s2=(?P<avg_s2>[\d.]+),\s+GUID=(?P<guid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})

- Example: [INFO] (PROTOCOL) @ 1000: Node 3 enqueued averaged payload: avg_s1=42.5, avg_s2=17.0, GUID=f47ac10b-58cc-4372-a567-0e02b2c3d479,

---

## 2. Dead node count — *implemented* (`deadnodecounter`)

**Log line matched:**
```
[CRITICAL] (NODE) @ <tick>: Node <node_id> DIED
```

**Class interface:**
- `build_dict(line)` — called per line; populates `dict: {node_id: [tick, ...]}`
- `deathcounter()` → `(node_ids, counts)` — count of death events per node
- `plot(ax)` — stem plot of death count per node; displays "No death events recorded" if dict is empty

---

## 3. Sync start-to-completion interval — *implemented* (`sync_interval_counter`)

**Log lines matched:**
```
[DEBUG] (PROTOCOL) @ <tick>: Node <node_id> attempts gateway connect via WAN
[INFO]  (PROTOCOL) @ <tick>: Node <node_id> connected to gateway via WAN
[INFO]  (PROTOCOL) @ <tick>: Node <node_id> discovery complete with hop count <n>
```

**Class interface:**
- `build_dict(line)` — called per line; maintains:
  - `sync_node_set` — nodes that completed sync
  - `unsync_node_set` — nodes that attempted but have not yet completed sync
  - `max_sync_tick` — tick at which the last sync completion was recorded
- Special case 1: a second attempt from an already-synced node is ignored
- Special case 2: a second attempt from a node already waiting is ignored
- A completion line with no prior attempt for that node is ignored
- `sync_counter()` → `(sorted synced list, sorted unsynced list, max_sync_tick)`
- `plot(ax)` — bar chart of synced vs. unsynced node counts, with `max_sync_tick` in the title

---

## 4. Packet loss — *not implemented*
Check whether each UUID that was transmitted was ultimately delivered to the gateway.

- Track all UUIDs seen at nodes
- Cross-reference against UUIDs seen at the gateway
- UUIDs present at nodes but absent at the gateway are lost packets

---

## 5. Average time drift — *not implemented*
Compute average clock drift per node over a configurable tick interval.

---

## 6. Battery capacity between sleep and wake — *not implemented*
Track battery level at each sleep event and each wake event per node; plot the delta per cycle.

1. We need 2 different histograms here.
    * The first histogram tacks the number of times the range of the battery capacity in which the sensor woke up. This would signify the amount of charge the node had...directly relates to the range in which the sensor was working in.
    * The second histogram tracks the battery capacity range in terms of difference between the capacity at wake-up and sleep. This signifies the effort it took to complete the message transmission protocol.

2. Example: data structure:
Key point to consider : total battery capacity range = 0 - 7.9 Joules

Histogram 1:
dict_op_range = {keyword=[Node_IDs] : Values=[0, 1 , 2, 4, 5]}
dict_op_range = {1 : [20, 2, 30, 40, 100],
                       2 : [2, 30, 10, 90, 1], so on...}
                       Here, the values signifies the count of times the sensor woke up have a battery capacity in that range. The range is divided into x equal sections for the histogram and is configurable.

Histogram 2:
dict_operating_range = {keyword=[Node_IDs] : Values=[0, 1 , 2, 4, 5]}
dict_operating_range = {1 : [20, 2, 30, 40, 100],
                       2 : [2, 30, 10, 90, 1], so on...}
                       Here, the values signifies the count of times the operating capacity of the sensor. The range is divided in to x incremental sections. i.e., 1.5, 1.5+1.5, 3.0+1.5, so on...

Pattern:
  Wake up log line:
  [INFO] (NODE) @ 1000: Node 3 woke up, , Battery charge 95.5,

  Regex:
  \[INFO\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+woke up,\s*,\s*Battery charge\s+(?P<battery>[\d.]+)

  Sleep log line:
  [INFO] (NODE) @ 2000: Node 3 is going to sleep, Battery charge 88.2,

  Regex:
  \[INFO\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+is going to sleep,\s+Battery charge\s+(?P<battery>[\d.]+)
---

## Optional

### 7. Reset and re-discovery after node death — *not implemented*
After a `DIED` event, track whether the node re-attempts gateway connect and successfully re-syncs. Cross-reference with metric 3.
