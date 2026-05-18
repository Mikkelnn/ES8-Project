import math
import argparse
import mmap
from pathlib import Path
from collections.abc import Iterator
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from uuid import UUID
from tqdm import tqdm

#===================Analyser classes===================
class deadnodecounter:
    """Tracks how many times each node has died.

    dict — {node_id: death_count}
    """

    AREAS = frozenset({"NODE"})

    # Marker that separates the log prefix from the node_id in death lines.
    # Format: [CRITICAL] (NODE) @ <tick>: Node <node_id> DIED, <data>
    _NODE_MARKER = ': Node '

    def __init__(self):
        self.dict = {}

    def build_dict(self, line: str) -> None:
        """Parse one log line and increment the death count for the node.

        Only processes [CRITICAL] (NODE) lines matching:
        [CRITICAL] (NODE) @ <tick>: Node <node_id> DIED

        Uses plain string operations — no regex — for maximum throughput on
        large log files where this method is called millions of times.
        """
        if not line.startswith('[CRITICAL]'):
            return

        # Area guard: only NODE lines carry death events.
        if '(NODE)' not in line:
            return

        # Locate ': Node ' which immediately precedes the node_id.
        idx = line.find(self._NODE_MARKER)
        if idx == -1:
            return

        # rest = "<node_id> DIED, <data>"
        rest = line[idx + len(self._NODE_MARKER):]

        # node_id is the first whitespace-delimited token.
        space_idx = rest.find(' ')
        if space_idx == -1:
            return

        node_str = rest[:space_idx]
        if not node_str.isdigit():
            return

        # Confirm the event type — must be followed by ' DIED'.
        if not rest[space_idx:].startswith(' DIED'):
            return

        node_id = int(node_str)
        self.dict[node_id] = self.dict.get(node_id, 0) + 1

    def deathcounter(self):
        """Return (node_ids, counts) where counts[i] is the death count for node_ids[i]."""
        node_ids = list(self.dict.keys())
        counts = list(self.dict.values())
        return node_ids, counts

    def death_distribution(self):
        """Return {death_count: num_nodes} — how many nodes share each death count.

        Iterates self.dict ({node_id: death_count}) and groups nodes by their count.
        Nodes with the same death count are merged into a single bucket.

        example output:
        {
            3: 2,   # two nodes each died 3 times
            1: 1    # one node died once
        }
        """
        distribution = {}
        for death_count in self.dict.values():
            distribution[death_count] = distribution.get(death_count, 0) + 1
        return distribution

    def report_text(self) -> str:
        """Return a human-readable plain-text summary of death events.

        Sections:
        1. Totals       — unique nodes that died and total death events
        2. Per-node     — each node ID and its death count, sorted by node ID
        3. Distribution — how many nodes share each death count, sorted by count
        """
        if not self.dict:
            return "No death events recorded.\n"

        total_nodes  = len(self.dict)
        total_deaths = sum(self.dict.values())
        distribution = self.death_distribution()

        lines = [
            "Dead Node Report",
            "================",
            f"Total nodes  : {total_nodes}",
            f"Total deaths : {total_deaths}",
            "",
            "Per-node breakdown",
            "------------------",
            f"  {'Node ID':>7}  {'Deaths':>6}",
            f"  {'-------':>7}  {'------':>6}",
        ]
        for node_id, count in sorted(self.dict.items()):
            lines.append(f"  {node_id:>7}  {count:>6}")

        lines += [
            "",
            "Distribution",
            "------------",
            f"  {'Deaths':>6}  {'Nodes':>5}",
            f"  {'------':>6}  {'-----':>5}",
        ]
        for death_count, node_count in sorted(distribution.items()):
            lines.append(f"  {death_count:>6}  {node_count:>5}")

        return "\n".join(lines) + "\n"

    def plot(self, ax=None):
        """Plot a histogram of how many nodes share each death count.

        x-axis — number of deaths per node (distinct death counts)
        y-axis — count (number of nodes with that death count)
        """
        distribution = self.death_distribution()

        if ax is None:
            fig, ax = plt.subplots()

        if not distribution:
            ax.set_title("Death Count Distribution")
            ax.text(0.5, 0.5, "No death events recorded",
                    ha='center', va='center', transform=ax.transAxes)
            return ax

        x_vals = sorted(distribution.keys())
        y_vals = [distribution[x] for x in x_vals]

        ax.bar(x_vals, y_vals, color='steelblue')
        ax.set_xlabel("Number of deaths per node")
        ax.set_ylabel("Count")
        ax.set_title("Death Count Distribution")
        # Death counts and node counts are discrete — force integer ticks on both axes.
        ax.set_xticks(x_vals)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        return ax

    def merge(self, other):
        """Merge another deadnodecounter into this one."""
        for node_id, count in other.dict.items():
            self.dict[node_id] = self.dict.get(node_id, 0) + count

class sync_interval_counter:
    """initializes the sets to keep a track of the syncronised and unsynchronised Node IDs
     and the maximum tick at which the last 'Sync' event recorded globally among the syncronised nodes"""

    AREAS = frozenset({"PROTOCOL"})

    # Markers used to locate fields within a PROTOCOL log line.
    # Format: [INFO] (PROTOCOL) @ <tick>: Node <node_id> <message>, <data>
    _AT_MARKER   = '@ '
    _NODE_MARKER = ': Node '

    def __init__(self):
        self.sync_node_set = set()    # nodes that completed gateway sync
        self.unsync_node_set = set()  # nodes that attempted but have not yet synced
        self.max_sync_tick = 0        # tick of the most recent sync completion

    """Builds the dictionary by reading the log file (line-by-line) and appends the synced nodes and replaces the largest sync tick in the dictionary for each 'Sync' event found in the log file
    Input arguments: line - a line from the log file i.e., string

    ===============
    Example of log file line:
    begins with -> [INFO] (PROTOCOL) @ ['int:tick']: Node ['int:Node_id'] attempts gateway connect via WAN
    Ends with either -> [INFO] (PROTOCOL) @ ['int:tick']: Node ['int:Node_id'] connected to gateway via WAN
        or -> [INFO] (PROTOCOL) @ ['int:tick']: Node ['int:Node_id'] discovery complete with hop count ['int:hop_count']

    Logic:
    1. Check if the line starts with the exact regex pattern for gateway connect attempt
    2. Add the node_id to the unsynced nodes list in the dictionary
    3. Check if the line ends with the exact regex pattern for successful gateway connection or discovery complete
    4. Replace the unsynced node_id with the synced node_id in the set and update the max tick to the current tick

    Special case1: If a node_id is already in the synced nodes set then we can ignore the line.
    Special case2: If a node_id is in the unsynced nodes set and we encounter another gateway connect attempt for the same node_id then we ignore the line as well.


    example output:
    sync_node_set = {1, 2, 3}
    unsync_node_set = {4, 5}
    max_sync_tick = 500
    """
    def build_dict(self, line: str) -> None:
        if not line.startswith('[INFO]'):
            return
        if '(PROTOCOL)' not in line:
            return

        tick, node_id, suffix = self._parse_line(line)
        if node_id is None:
            return

        if suffix.startswith('attempts gateway connect via WAN'):
            # Only track the first attempt — ignore if already synced or pending.
            if node_id not in self.sync_node_set and node_id not in self.unsync_node_set:
                self.unsync_node_set.add(node_id)
            return

        if suffix.startswith('connected to gateway via WAN') or \
           suffix.startswith('discovery complete with hop count'):
            self.sync_node_set.add(node_id)
            # Remove from unsync immediately so sync_counter() is always consistent.
            self.unsync_node_set.discard(node_id)
            self.max_sync_tick = tick

    def _parse_line(self, line: str) -> tuple[int, int | None, str]:
        """Extract (tick, node_id, message_suffix) from a PROTOCOL INFO line.

        Returns (0, None, '') if the line does not match the expected structure.
        suffix is the text starting after '<node_id> '.
        """
        # Tick: between '@ ' and the following ':'
        at_idx = line.find(self._AT_MARKER)
        if at_idx == -1:
            return 0, None, ''
        colon_idx = line.find(':', at_idx + 2)
        if colon_idx == -1:
            return 0, None, ''
        tick_str = line[at_idx + 2:colon_idx]
        if not tick_str.isdigit():
            return 0, None, ''

        # node_id: first token after ': Node '
        node_idx = line.find(self._NODE_MARKER, colon_idx)
        if node_idx == -1:
            return 0, None, ''
        rest = line[node_idx + len(self._NODE_MARKER):]
        space_idx = rest.find(' ')
        if space_idx == -1:
            return 0, None, ''
        node_str = rest[:space_idx]
        if not node_str.isdigit():
            return 0, None, ''

        return int(tick_str), int(node_str), rest[space_idx + 1:]

    def sync_counter(self):
        """Returns (synced_nodes, unsynced_nodes, max_tick) as sorted lists and int."""
        return sorted(self.sync_node_set), sorted(self.unsync_node_set), self.max_sync_tick

    def plot(self, ax=None):
        """Plot synced vs unsynced node counts."""
        synced, unsynced, tick = self.sync_counter()

        if ax is None:
            fig, ax = plt.subplots()

        ax.bar(['Unsynced', 'Synced'], [len(unsynced), len(synced)],
               color=['salmon', 'steelblue'])
        ax.set_ylabel("Node count")
        ax.set_title(f"Sync state  (Time taken to complete synchronization: {tick})")

        return ax

    def merge(self, other):
        """Merge another sync_interval_counter into this one."""
        # Merge sync sets first
        self.sync_node_set.update(other.sync_node_set)
        self.unsync_node_set.update(other.unsync_node_set)

        # Remove any node from unsync if it successfully synced
        self.unsync_node_set -= self.sync_node_set

        self.max_sync_tick = max(self.max_sync_tick, other.max_sync_tick)

class battery_capacity_analyser:
    """Tracks battery charge at wake-up and sleep events per node.

    Builds two histograms across the 0-MAX_CHARGE (7.9 J) range,
    each divided into num_bins equal-width bins:

    dict_op_range        — {node_id: [bin_counts]} wake-up charge distribution
    dict_operating_range — {node_id: [bin_counts]} charge delta (wake - sleep) distribution

    Log lines matched:
    Wake  → [INFO]     (NODE) @ <tick>: Node <node_id> woke up, , Battery charge <charge>,
    Sleep → [INFO]     (NODE) @ <tick>: Node <node_id> is going to sleep, Battery charge <charge>,
    Death → [CRITICAL] (NODE) @ <tick>: Node <node_id> DIED,   (treated as sleep with charge=0)

    Logic:
    1. On wake  → record charge in dict_op_range and store in _pending_wake
    2. On sleep → if prior wake exists, compute delta = wake - sleep_charge, record delta
    3. On death → if prior wake exists, compute delta = wake - 0 (battery exhausted), record delta
    4. Sleep/death with no prior wake is ignored
    5. Second sleep/death before a new wake is also ignored (_pending_wake already cleared)

    Example output:
    dict_op_range        = {1: [0, 0, 0, 1, 0], 2: [0, 1, 0, 0, 0]}
    dict_operating_range = {1: [1, 0, 0, 0, 0], 2: [0, 1, 0, 0, 0]}
    """

    MAX_CHARGE = 7.9   # total battery capacity in Joules
    plot_count = 2     # signals post_process_and_plot to allocate two subplots
    AREAS = frozenset({"NODE"})

    # Markers for locating fields in NODE log lines.
    # Wake:  [INFO]     (NODE) @ <tick>: Node <id> woke up, , Battery charge <v>,
    # Sleep: [INFO]     (NODE) @ <tick>: Node <id> is going to sleep, Battery charge <v>,
    # Death: [CRITICAL] (NODE) @ <tick>: Node <id> DIED,
    _NODE_MARKER    = ': Node '
    _BATTERY_MARKER = 'Battery charge '

    def __init__(self, num_bins=5):
        self.num_bins = num_bins
        self._pending_wake = {}        # {node_id: wake_charge} — unmatched wake events
        self.dict_op_range = {}        # histogram 1: wake-up charge level
        self.dict_operating_range = {} # histogram 2: charge consumed per cycle

    def build_dict(self, line: str) -> None:
        """Parse one log line and update the appropriate histogram."""
        if not line.startswith('[INFO]') and not line.startswith('[CRITICAL]'):
            return
        if '(NODE)' not in line:
            return

        node_id, suffix = self._parse_node_line(line)
        if node_id is None:
            return

        if suffix.startswith('woke up'):
            charge = self._extract_charge(suffix)
            if charge is None:
                return
            self._pending_wake[node_id] = charge
            self._ensure_node(node_id)
            self.dict_op_range[node_id][self._charge_to_bin(charge)] += 1
            return

        if suffix.startswith('is going to sleep'):
            charge = self._extract_charge(suffix)
            if charge is None:
                return
            self._record_delta(node_id, sleep_charge=charge)
            return

        if suffix.startswith('DIED'):
            self._record_delta(node_id, sleep_charge=0.0)

    def _parse_node_line(self, line: str) -> tuple[int | None, str]:
        """Extract (node_id, message_suffix) from a NODE log line.

        Returns (None, '') if the line does not match the expected structure.
        suffix is the text starting after '<node_id> '.
        """
        idx = line.find(self._NODE_MARKER)
        if idx == -1:
            return None, ''
        rest = line[idx + len(self._NODE_MARKER):]
        space_idx = rest.find(' ')
        if space_idx == -1:
            return None, ''
        node_str = rest[:space_idx]
        if not node_str.isdigit():
            return None, ''
        return int(node_str), rest[space_idx + 1:]

    def _extract_charge(self, text: str) -> float | None:
        """Extract the float after 'Battery charge ' in text. Returns None if absent."""
        idx = text.find(self._BATTERY_MARKER)
        if idx == -1:
            return None
        rest = text[idx + len(self._BATTERY_MARKER):]
        comma_idx = rest.find(',')
        charge_str = rest[:comma_idx].strip() if comma_idx != -1 else rest.strip()
        try:
            return float(charge_str)
        except ValueError:
            return None

    def _record_delta(self, node_id, sleep_charge):
        """Record a wake-to-sleep delta if a prior wake event exists for this node."""
        if node_id in self._pending_wake:
            wake_charge = self._pending_wake.pop(node_id)
            delta = wake_charge - sleep_charge
            self._ensure_node(node_id)
            self.dict_operating_range[node_id][self._delta_to_bin(delta)] += 1

    def get_histograms(self):
        """Return (dict_op_range, dict_operating_range)."""
        return self.dict_op_range, self.dict_operating_range

    def plot(self, axes=None):
        """Plot both histograms.

        axes : list of 2 Axes, or None (creates its own figure).
        """
        if axes is None:
            _, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes = list(axes)

        self._plot_wakeup_histogram(axes[0])
        self._plot_delta_histogram(axes[1])
        return axes

    def _plot_wakeup_histogram(self, ax):
        """Histogram 1 — total wake-up events per charge bin across all nodes."""
        if not self.dict_op_range:
            ax.set_title("Battery charge at wake-up")
            ax.text(0.5, 0.5, "No wake-up events recorded",
                    ha='center', va='center', transform=ax.transAxes)
            return ax

        total_counts = self._aggregate(self.dict_op_range)
        x = list(range(self.num_bins))
        ax.bar(x, total_counts, color='steelblue')
        ax.set_xticks(x)
        ax.set_xticklabels(self._bin_labels(), rotation=45, ha='right')
        ax.set_xlabel("Battery charge (J)")
        ax.set_ylabel("Event count")
        ax.set_title("Battery charge at wake-up")
        return ax

    def _plot_delta_histogram(self, ax):
        """Histogram 2 — total charge-consumed events per delta bin across all nodes."""
        if not self.dict_operating_range:
            ax.set_title("Battery delta (wake - sleep)")
            ax.text(0.5, 0.5, "No complete sleep cycles recorded",
                    ha='center', va='center', transform=ax.transAxes)
            return ax

        total_counts = self._aggregate(self.dict_operating_range)
        x = list(range(self.num_bins))
        ax.bar(x, total_counts, color='salmon')
        ax.set_xticks(x)
        ax.set_xticklabels(self._bin_labels(), rotation=45, ha='right')
        ax.set_xlabel("Charge consumed (J)")
        ax.set_ylabel("Event count")
        ax.set_title("Battery delta (wake - sleep)")
        return ax

    def _aggregate(self, histogram_dict):
        """Sum bin counts across all nodes into a single list of per-bin totals."""
        totals = [0] * self.num_bins
        for counts in histogram_dict.values():
            for bin_idx, count in enumerate(counts):
                totals[bin_idx] += count
        return totals

    def _ensure_node(self, node_id):
        """Initialise zero-filled bin arrays for a node seen for the first time."""
        if node_id not in self.dict_op_range:
            self.dict_op_range[node_id] = [0] * self.num_bins
        if node_id not in self.dict_operating_range:
            self.dict_operating_range[node_id] = [0] * self.num_bins

    def _charge_to_bin(self, charge):
        """Map an absolute charge value (J) to its bin index."""
        bin_width = self.MAX_CHARGE / self.num_bins
        return min(int(charge / bin_width), self.num_bins - 1)

    def _delta_to_bin(self, delta):
        """Map a charge delta (J) to its bin index, clamped to valid range."""
        bin_width = self.MAX_CHARGE / self.num_bins
        return min(max(int(delta / bin_width), 0), self.num_bins - 1)

    def _bin_labels(self):
        """Generate human-readable range labels for each bin."""
        bin_width = self.MAX_CHARGE / self.num_bins
        return [
            f"{i * bin_width:.2f}-{(i + 1) * bin_width:.2f}"
            for i in range(self.num_bins)
        ]

    def merge(self, other):
        """Merge another battery_capacity_analyser into this one."""
        for node_id, bins in other.dict_op_range.items():
            if node_id not in self.dict_op_range:
                self.dict_op_range[node_id] = [0] * self.num_bins
            for i, count in enumerate(bins):
                self.dict_op_range[node_id][i] += count

        for node_id, bins in other.dict_operating_range.items():
            if node_id not in self.dict_operating_range:
                self.dict_operating_range[node_id] = [0] * self.num_bins
            for i, count in enumerate(bins):
                self.dict_operating_range[node_id][i] += count

class packet_forwarding_delay:
    """Tracks packet forwarding delay and packet loss per node.

    Two-phase processing:

    Phase 1 — build_dict (called per log line):
      Node enqueue  → _node_origin[UUID] = [tick, node_id]
      Gateway recv  → pop UUID, compute delay, update _stats[node_id]

    Phase 2 — finalize (called once after all lines are read):
      Any UUID still in _node_origin never reached the gateway → lost.
      Increments _stats[node_id][2] (lost count) for each orphaned UUID.

    _stats layout: {node_id: [diff:int, successful_count:int, lost:int]}
      diff             — accumulated sum of all delivery delays for this node
      successful_count — number of packets delivered to the gateway
      lost             — number of packets never delivered (populated by finalize)

    Average delay per node = diff / successful_count (computed at plot time).

    Plot 1 (stem):      node_id vs. average forwarding delay
    Plot 2 (histogram): distribution of per-node lost-packet counts (10 bins)

    Log lines matched:
    Node enqueue → [INFO] (PROTOCOL) @ <tick>: Node <node_id> enqueued averaged
                   payload: avg_s1=<v>, avg_s2=<v>, GUID=<uuid>
    Gateway recv → [INFO] (GATEWAY) @ <tick>: Gateway <gw_id> received data:...,
                   GUID=<uuid>
    """

    plot_count = 2  # one stem + one histogram
    AREAS = frozenset({"PROTOCOL", "GATEWAY"})

    # Markers for locating fields in PROTOCOL and GATEWAY log lines.
    # Enqueue: [INFO] (PROTOCOL) @ <tick>: Node <id> enqueued averaged payload: ..., GUID=<uuid>,
    # Gateway: [INFO] (GATEWAY)  @ <tick>: Gateway <id> received data: ..., GUID=<uuid>,
    _AT_MARKER       = '@ '
    _NODE_MARKER     = ': Node '
    _ENQUEUE_SUFFIX  = 'enqueued averaged payload:'
    _RECEIVED_MARKER = 'received data:'
    _GUID_MARKER     = 'GUID='
    _GUID_LENGTH     = 36   # length of a UUID string: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    def __init__(self):
        self._node_origin = {}         # {UUID: [tick, node_id]} — first enqueue per UUID
        self._delivered_uuids = set()  # UUIDs successfully delivered to a gateway
        self._orphan_uuids = set()     # UUIDs received at gateway with no node origin
        self._stats = {}               # {node_id: [diff, successful_count, lost]}
        self._finalized = False

    @property
    def orphan_gateway_count(self):
        """Count of unique UUIDs received at the gateway with no prior node enqueue."""
        return len(self._orphan_uuids)

    def build_dict(self, line: str) -> None:
        """Parse one log line; record node origin or compute delivery stats."""
        if not line.startswith('[INFO]'):
            return
        if '(PROTOCOL)' in line:
            self._handle_protocol_line(line)
        elif '(GATEWAY)' in line:
            self._handle_gateway_line(line)

    def _handle_protocol_line(self, line: str) -> None:
        """Process a PROTOCOL enqueue line — store UUID origin if not already seen."""
        node_idx = line.find(self._NODE_MARKER)
        if node_idx == -1:
            return
        rest = line[node_idx + len(self._NODE_MARKER):]
        space_idx = rest.find(' ')
        if space_idx == -1:
            return
        node_str = rest[:space_idx]
        if not node_str.isdigit():
            return
        if not rest[space_idx + 1:].startswith(self._ENQUEUE_SUFFIX):
            return

        tick = self._extract_tick(line)
        guid = self._extract_guid(line)
        if tick is None or guid is None:
            return

        if guid not in self._node_origin:
            self._node_origin[guid] = [tick, int(node_str)]

    def _handle_gateway_line(self, line: str) -> None:
        """Process a GATEWAY receipt line — match UUID to origin and compute delay."""
        if self._RECEIVED_MARKER not in line:
            return

        tick = self._extract_tick(line)
        guid = self._extract_guid(line)
        if tick is None or guid is None:
            return

        if guid not in self._node_origin:
            # Count unique UUIDs that arrive at the gateway with no node origin.
            # Skip UUIDs that were already delivered (popped from _node_origin earlier)
            # so that duplicate gateway receipts of a delivered packet are not orphans.
            if guid not in self._delivered_uuids:
                self._orphan_uuids.add(guid)
            return

        enqueue_tick, node_id = self._node_origin.pop(guid)
        self._delivered_uuids.add(guid)
        diff = tick - enqueue_tick
        self._ensure_node(node_id)
        self._stats[node_id][0] += diff   # accumulate total delay
        self._stats[node_id][1] += 1      # increment successful count

    def _extract_tick(self, line: str) -> int | None:
        """Extract the tick integer from '@ <tick>:' in line."""
        at_idx = line.find(self._AT_MARKER)
        if at_idx == -1:
            return None
        colon_idx = line.find(':', at_idx + 2)
        if colon_idx == -1:
            return None
        tick_str = line[at_idx + 2:colon_idx]
        return int(tick_str) if tick_str.isdigit() else None

    def _extract_guid(self, line: str) -> UUID | None:
        """Extract a UUID from 'GUID=<uuid>' in line. Returns None if absent or malformed."""
        idx = line.find(self._GUID_MARKER)
        if idx == -1:
            return None
        guid_str = line[idx + len(self._GUID_MARKER):idx + len(self._GUID_MARKER) + self._GUID_LENGTH]
        try:
            return UUID(guid_str)
        except ValueError:
            return None

    def finalize(self):
        """Mark all undelivered UUIDs as lost. Idempotent after first call."""
        if self._finalized:
            return
        for entry in self._node_origin.values():
            node_id = entry[1]
            self._ensure_node(node_id)
            self._stats[node_id][2] += 1
        self._finalized = True

    def get_stats(self):
        """Return _stats after finalization. {node_id: [diff, successful_count, lost]}"""
        self.finalize()
        return self._stats

    def delay_distribution(self) -> dict[int, int]:
        """Return {rounded_avg_delay: node_count} for nodes with at least one delivery.

        Average delay per node = diff / successful_count, rounded to the nearest integer.
        Nodes that only have lost packets (successful_count == 0) are excluded.

        example output:
        {
            500: 3,   # three nodes each averaged 500 ticks
            100: 1    # one node averaged 100 ticks
        }
        """
        self.finalize()
        distribution: dict[int, int] = {}
        for diff, successful_count, _ in self._stats.values():
            if successful_count > 0:
                avg = round(diff / successful_count)
                distribution[avg] = distribution.get(avg, 0) + 1
        return distribution

    def _binned_delay_distribution(self, max_bins: int = 10) -> dict[int, int]:
        """Return delay_distribution() merged into at most max_bins equal-width buckets.

        If distinct avg-delay values ≤ max_bins the raw distribution is returned unchanged.
        Otherwise the range [min_delay, max_delay] is divided into equal-width bins and
        each node's avg delay is mapped to its bin's lower bound (an integer).
        The total node count across all bins is always preserved.
        """
        distribution = self.delay_distribution()
        if len(distribution) <= max_bins:
            return distribution

        delays = sorted(distribution.keys())
        min_delay = delays[0]
        max_delay = delays[-1]
        # +1 ensures max_delay always falls inside the last bin, not into an extra one.
        bin_width = math.ceil((max_delay - min_delay + 1) / max_bins)

        binned: dict[int, int] = {}
        for delay, count in distribution.items():
            bin_start = min_delay + ((delay - min_delay) // bin_width) * bin_width
            binned[bin_start] = binned.get(bin_start, 0) + count
        return binned

    def plot(self, axes=None):
        """Delay distribution histogram and loss histogram.

        axes : list of 2 Axes, or None (creates its own figure).
        """
        self.finalize()
        if axes is None:
            _, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes = list(axes)
        self._plot_delay_histogram(axes[0])
        self._plot_loss_histogram(axes[1])
        return axes

    def _plot_delay_histogram(self, ax):
        """Histogram of average forwarding delay distribution across nodes.

        x-axis — average delay (ticks), merged into at most 10 bins
        y-axis — count (number of nodes with that average delay)
        """
        distribution = self._binned_delay_distribution()
        if not distribution:
            ax.set_title("Packet Forwarding Delay Distribution")
            ax.text(0.5, 0.5, "No delivered packets recorded",
                    ha='center', va='center', transform=ax.transAxes)
            return ax
        x_vals = sorted(distribution.keys())
        y_vals = [distribution[x] for x in x_vals]
        ax.bar(x_vals, y_vals, color='steelblue')
        ax.set_xlabel("Average delay (ticks)")
        ax.set_ylabel("Count")
        ax.set_title("Packet Forwarding Delay Distribution")
        ax.set_xticks(x_vals)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        return ax

    def _plot_loss_histogram(self, ax):
        """Histogram of per-node lost-packet counts (10 bins)."""
        lost_counts = [s[2] for s in self._stats.values() if s[2] > 0]
        if not lost_counts:
            ax.set_title("Packet Loss Distribution")
            ax.text(0.5, 0.5, "No packet loss recorded",
                    ha='center', va='center', transform=ax.transAxes)
            return ax
        ax.hist(lost_counts, bins=10, color='salmon')
        ax.set_xlabel("Lost packets per node")
        ax.set_ylabel("Number of nodes")
        ax.set_title("Packet Loss Distribution")
        return ax

    def _ensure_node(self, node_id):
        """Initialise a zeroed stats entry for a node seen for the first time."""
        if node_id not in self._stats:
            self._stats[node_id] = [0, 0, 0]  # [diff, successful_count, lost]

    def merge(self, other):
        """Merge another packet_forwarding_delay. Reconcile UUIDs across chunks."""
        # Remove UUIDs from other's unmatched that are in this analyzer's delivered set
        for uuid in list(other._node_origin.keys()):
            if uuid in self._delivered_uuids:
                del other._node_origin[uuid]

        # Remove UUIDs from this analyzer's delivered that are in other's unmatched
        for uuid in list(other._delivered_uuids):
            if uuid in self._node_origin:
                del self._node_origin[uuid]

        # Merge stats
        for node_id, stats in other._stats.items():
            self._ensure_node(node_id)
            self._stats[node_id][0] += stats[0]  # diff
            self._stats[node_id][1] += stats[1]  # successful_count
            self._stats[node_id][2] += stats[2]  # lost

        self._delivered_uuids.update(other._delivered_uuids)
        self._node_origin.update(other._node_origin)
        self._orphan_uuids.update(other._orphan_uuids)
        self._finalized = self._finalized or other._finalized


#===================Helper functions===================
def count_lines(path: str | Path) -> int:
    """Return the number of lines in the file at path."""
    with open(path, 'r') as f:
        return sum(1 for _ in f)


def read_in_batches(path: str | Path, batch_size: int = 1000) -> Iterator[list[str]]:
    """Yield successive batches of lines read from the file at path using mmap.

    Each batch is a list of at most batch_size lines (strings including newlines).
    The last batch may be smaller if the file does not divide evenly.
    Reads mmap in 100MB chunks for faster I/O amortization.
    """
    chunk_size = 100 * 1024 * 1024  # 100MB chunks

    with open(path, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
            batch = []
            remainder = b''
            pos = 0
            file_size = len(mmapped)

            while pos < file_size:
                # Read next chunk, but not past file end
                end_pos = min(pos + chunk_size, file_size)
                chunk = remainder + mmapped[pos:end_pos]
                pos = end_pos

                # Find last newline to avoid splitting lines mid-chunk
                last_newline = chunk.rfind(b'\n')
                if last_newline == -1:
                    # No newline in chunk; if more file remains, defer this chunk
                    if pos < file_size:
                        remainder = chunk
                        continue
                    # At EOF with no newline; process entire chunk
                    to_process = chunk
                    remainder = b''
                else:
                    # Process up to last newline, save rest for next iteration
                    to_process = chunk[:last_newline + 1]
                    remainder = chunk[last_newline + 1:]

                # Decode and split this batch of complete lines
                text = to_process.decode('utf-8')
                lines = text.splitlines(keepends=True)

                for line in lines:
                    batch.append(line)
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

            # Yield any remaining lines
            if batch:
                yield batch


def save_report(text: str, folder: str | Path, filename: str) -> Path:
    """Write text to <folder>/<filename>, creating the folder tree if needed.

    Returns the path to the written file.
    Any analyser that implements report_text() can use this helper for its output.
    """
    out_dir = Path(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / filename
    report_path.write_text(text, encoding="utf-8")
    return report_path


def extract_area_fast(line: str) -> str | None:
    """Extract area tag. Log format: [SEVERITY] (AREA) @ tick: message"""
    paren_idx = line.find('(')
    if paren_idx < 0:
        return None
    close_idx = line.find(')', paren_idx)
    if close_idx < 0:
        return None
    return line[paren_idx + 1:close_idx]


def execute(executable_list, line):
    """Route line to analyzers whose AREAS match."""
    area = extract_area_fast(line)
    for exe in executable_list:
        areas = getattr(exe, 'AREAS', None)
        if areas is None or (area and area in areas):
            exe.build_dict(line)


def post_process_and_plot(executable_list):
    """Opens a separate figure window for each analyser.

    Calls finalize() on any analyser that exposes it before plotting.
    Analysers with plot_count > 1 get side-by-side subplots within their own figure.
    """
    for exe in executable_list:
        if hasattr(exe, 'finalize'):
            exe.finalize()

    for exe in executable_list:
        n = getattr(exe, 'plot_count', 1)
        # squeeze=False keeps axes as a 2-D array regardless of subplot count.
        fig, axes = plt.subplots(1, n, figsize=(6 * n, 5), squeeze=False)
        flat_axes = axes.flatten().tolist()
        if n == 1:
            exe.plot(flat_axes[0])
        else:
            exe.plot(flat_axes)
        fig.tight_layout()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log',    default='Log_debugging\\simulation.log', help='Path to log file')
    parser.add_argument('--bins',   type=int, default=5,  help='Number of histogram bins for battery metric')
    parser.add_argument('--output', default=None,         help='Folder to write text reports (skipped if omitted)')
    args = parser.parse_args()

    analyzers = [
        deadnodecounter(),
        sync_interval_counter(),
        battery_capacity_analyser(num_bins=args.bins),
        packet_forwarding_delay(),
    ]

    file_size = Path(args.log).stat().st_size
    chunk_size = 100 * 1024 * 1024  # read 100 MB at a time

    with open(args.log, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            with tqdm(total=file_size, desc="Processing", unit='B', unit_scale=True, ncols=80) as pbar:
                pos = 0
                remainder = b''

                while pos < file_size:
                    end = min(pos + chunk_size, file_size)
                    chunk = remainder + mm[pos:end]
                    pos = end

                    # Avoid splitting a line across chunks — keep the tail for next iteration.
                    last_nl = chunk.rfind(b'\n')
                    if last_nl == -1:
                        if pos < file_size:
                            remainder = chunk
                            continue
                        to_process = chunk
                        remainder = b''
                    else:
                        to_process = chunk[:last_nl + 1]
                        remainder = chunk[last_nl + 1:]

                    for line in to_process.decode('utf-8').splitlines(keepends=True):
                        execute(analyzers, line)

                    pbar.update(len(to_process))

    if args.output:
        for exe in analyzers:
            report_fn = getattr(exe, 'report_text', None)
            if callable(report_fn):
                save_report(report_fn(), args.output, f"{type(exe).__name__}_report.txt")

    post_process_and_plot(analyzers)
    plt.show()


if __name__ == "__main__":
    main()
