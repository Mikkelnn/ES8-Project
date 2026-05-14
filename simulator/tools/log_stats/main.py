import re
import math
import argparse
from pathlib import Path
from itertools import islice
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

    _PATTERN = re.compile(
        r'\[CRITICAL\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+DIED'
    )

    def __init__(self):
        self.dict = {}

    def build_dict(self, line):
        """Parse one log line and increment the death count for the node.

        Only processes [CRITICAL] (NODE) lines matching:
        [CRITICAL] (NODE) @ <tick>: Node <node_id> DIED

        example output:
        {
            1: 3,
            2: 2,
            3: 1
        }
        """
        if not line.startswith('[CRITICAL]'):
            return None
        match = self._PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
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

class sync_interval_counter:
    """initializes the sets to keep a track of the syncronised and unsynchronised Node IDs
     and the maximum tick at which the last 'Sync' event recorded globally among the syncronised nodes"""

    AREAS = frozenset({"PROTOCOL"})

    _ATTEMPT_PATTERN = re.compile(
        r'\[INFO\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)'
        r'\s+attempts gateway connect via WAN'
    )
    _SYNCED_PATTERN = re.compile(
        r'\[INFO\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)'
        r'\s+(connected to gateway via WAN|discovery complete with hop count \d+)'
    )

    def __init__(self):
        self.sync_node_set = set()  # Set to track synced nodes
        self.unsync_node_set = set()  # Set to track unsynced nodes
        self.max_sync_tick = 0  # Variable to track the maximum sync tick globally

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
    def build_dict(self, line):
        match = self._ATTEMPT_PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
            # Special case 1 & 2: ignore if already synced or already waiting
            if node_id not in self.sync_node_set and node_id not in self.unsync_node_set:
                self.unsync_node_set.add(node_id)
            return

        match = self._SYNCED_PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
            tick    = int(match.group('tick'))
            if node_id in self.unsync_node_set:
                self.unsync_node_set.discard(node_id)
                self.sync_node_set.add(node_id)
                self.max_sync_tick = tick

    def sync_counter(self):
        """Returns (synced_nodes, unsynced_nodes, max_tick) as sorted lists and int."""
        return sorted(self.sync_node_set), sorted(self.unsync_node_set), self.max_sync_tick

    def plot(self, ax=None):
        """Plot synced vs unsynced node counts."""
        synced, unsynced, tick = self.sync_counter()

        if ax is None:
            fig, ax = plt.subplots()

        ax.bar(['Synced', 'Unsynced'], [len(synced), len(unsynced)],
               color=['steelblue', 'salmon'])
        ax.set_ylabel("Node count")
        ax.set_title(f"Sync state  (Time taken to complete synchronization: {tick})")

        return ax

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

    _WAKE_PATTERN = re.compile(
        r'\[INFO\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)'
        r'\s+woke up,\s*,\s*Battery charge\s+(?P<battery>[\d.]+)'
    )
    _SLEEP_PATTERN = re.compile(
        r'\[INFO\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)'
        r'\s+is going to sleep,\s+Battery charge\s+(?P<battery>[\d.]+)'
    )
    # Death is treated as sleep with charge=0 — the battery was fully drained
    _DEATH_PATTERN = re.compile(
        r'\[CRITICAL\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+DIED'
    )

    def __init__(self, num_bins=5):
        self.num_bins = num_bins
        self._pending_wake = {}        # {node_id: wake_charge} — unmatched wake events
        self.dict_op_range = {}        # histogram 1: wake-up charge level
        self.dict_operating_range = {} # histogram 2: charge consumed per cycle

    def build_dict(self, line):
        """Parse one log line and update the appropriate histogram."""
        match = self._WAKE_PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
            charge  = float(match.group('battery'))
            self._pending_wake[node_id] = charge
            self._ensure_node(node_id)
            self.dict_op_range[node_id][self._charge_to_bin(charge)] += 1
            return

        match = self._SLEEP_PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
            charge  = float(match.group('battery'))
            self._record_delta(node_id, sleep_charge=charge)
            return

        match = self._DEATH_PATTERN.match(line)
        if match:
            node_id = int(match.group('node_id'))
            self._record_delta(node_id, sleep_charge=0.0)

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

    _NODE_PATTERN = re.compile(
        r'\[INFO\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)'
        r'\s+enqueued averaged payload:\s+avg_s1=[\d.]+,\s+avg_s2=[\d.]+,'
        r'\s+GUID=(?P<guid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})'
    )
    _GATEWAY_PATTERN = re.compile(
        r'\[INFO\]\s+\(GATEWAY\)\s+@\s+(?P<tick>\d+):\s+Gateway\s+(?P<gateway_id>\d+)'
        r'\s+received\s+data:.*GUID=(?P<guid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})'
    )

    def __init__(self):
        self._node_origin = {}    # {UUID: [tick, node_id]} — first enqueue per UUID
        self._delivered_uuids = set()  # UUIDs successfully delivered to a gateway
        self._orphan_uuids = set()     # UUIDs received at gateway with no node origin
        self._stats = {}          # {node_id: [diff, successful_count, lost]}
        self._finalized = False

    @property
    def orphan_gateway_count(self):
        """Count of unique UUIDs received at the gateway with no prior node enqueue."""
        return len(self._orphan_uuids)

    def build_dict(self, line):
        """Parse one log line; record node origin or compute delivery stats."""
        match = self._NODE_PATTERN.match(line)
        if match:
            guid = UUID(match.group('guid'))
            if guid not in self._node_origin:
                self._node_origin[guid] = [int(match.group('tick')), int(match.group('node_id'))]
            return

        match = self._GATEWAY_PATTERN.match(line)
        if match:
            guid = UUID(match.group('guid'))
            if guid not in self._node_origin:
                # Count unique UUIDs that arrive at the gateway with no node origin.
                # Skip UUIDs that were already delivered (popped from _node_origin earlier)
                # so that duplicate gateway receipts of a delivered packet are not orphans.
                if guid not in self._delivered_uuids:
                    self._orphan_uuids.add(guid)
                return
            tick, node_id = self._node_origin.pop(guid)
            self._delivered_uuids.add(guid)
            diff = int(match.group('tick')) - tick
            self._ensure_node(node_id)
            self._stats[node_id][0] += diff   # accumulate total delay
            self._stats[node_id][1] += 1       # increment successful count

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


#===================Helper functions===================
def count_lines(path: str | Path) -> int:
    """Return the number of lines in the file at path."""
    with open(path, 'r') as f:
        return sum(1 for _ in f)


def read_in_batches(path: str | Path, batch_size: int = 1000) -> Iterator[list[str]]:
    """Yield successive batches of lines read from the file at path.

    Each batch is a list of at most batch_size lines (strings including newlines).
    The last batch may be smaller if the file does not divide evenly.
    Reading in batches amortises per-call I/O overhead compared to iterating
    line-by-line, which is the main source of parsing latency on large logs.
    """
    with open(path, 'r') as f:
        while True:
            batch = list(islice(f, batch_size))
            if not batch:
                break
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


def extract_area(line: str) -> str | None:
    """Extract the area tag from a log line, e.g. 'NODE', 'PROTOCOL', 'GATEWAY'.

    Log format: [SEVERITY] (AREA) @ tick: message
    Returns None if the line does not contain a recognisable area tag.
    """
    try:
        parts = line.split('(', 1)[1].split(')', 1)
        return parts[0] if len(parts) == 2 else None
    except IndexError:
        return None


def execute(executable_list, line):
    """Pass each log line only to analysers whose declared AREAS include the line's area.

    Analysers without an AREAS attribute receive every line (backwards-compatible).
    """
    area = extract_area(line)
    for exe in executable_list:
        areas = getattr(exe, 'AREAS', None)
        if areas is None or area in areas:
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
    parser.add_argument('--bins',   type=int, default=5, help='Number of histogram bins for battery metric')
    parser.add_argument('--output', default=None,        help='Folder to write text reports (skipped if omitted)')
    args = parser.parse_args()

    executable_list = [
        deadnodecounter(),
        sync_interval_counter(),
        battery_capacity_analyser(num_bins=args.bins),
        packet_forwarding_delay(),
    ]

    with tqdm(desc="Parsing log", unit="lines") as progress:
        for batch in read_in_batches(args.log):
            for line in batch:
                execute(executable_list, line)
            progress.update(len(batch))

    if args.output:
        for exe in executable_list:
            report_fn = getattr(exe, 'report_text', None)
            if callable(report_fn):
                filename = f"{type(exe).__name__}_report.txt"
                save_report(report_fn(), args.output, filename)

    post_process_and_plot(executable_list)
    plt.show()


if __name__ == "__main__":
    main()
