import argparse
import re

import matplotlib.pyplot as plt


# ===================Analyser classes===================
class deadnodecounter:
    """initializes the dictionary to keep a track of the Node IDs
    and the number of times 'Death' event recorded for each Node ID"""

    def __init__(self):
        self.dict = {}

    """Builds the dictionary by reading the log file and appends the nodeId
    and the death tick to the dictionary for each 'Death' event found in the log file
    Input arguments: line - a line from the log file i.e., string

    ===============
    Example of log file line:
    [CRITICAL] (NODE) @ 'int:current_global_tick': Node 'int: node_id' DIED

    Logic:
    1. Check if the line starts with '[CRITICAL]'
    2. Extract the global tick after the '@' symbol and before the ':' symbol
    3. Extract the node_id after the 'Node' keyword and

    example output:
    {
        1: [100, 200, 300],
        2: [150, 250],
        3: [50]
    }
    """

    def build_dict(self, line):
        if not line.startswith("[CRITICAL]"):
            return None
        pattern = r"\[CRITICAL\]\s+\(NODE\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+DIED"
        match = re.match(pattern, line)
        if match:
            tick = int(match.group("tick"))
            node_id = int(match.group("node_id"))
            self.dict.setdefault(node_id, []).append(tick)

    def deathcounter(self):
        """increments the count of 'Death' event for the given Node ID in the dictionary"""
        # Need count for every node ID, so we can plot the graph with node ID on x-axis and count of 'Death' events on y-axis
        count = []
        for i in self.dict:
            count.append(len(self.dict[i]))

        node_ids = list(self.dict.keys())

        return node_ids, count

    def plot(self, ax=None):
        """Plot death events per node."""

        node_ids, counts = self.deathcounter()

        if ax is None:
            fig, ax = plt.subplots()

        if not node_ids:
            ax.set_title("Events per Node")
            ax.text(0.5, 0.5, "No death events recorded", ha="center", va="center", transform=ax.transAxes)
            return ax

        ax.stem(node_ids, counts, label="Death Events")
        ax.set_xlabel("Node ID")
        ax.set_ylabel("Count")
        ax.set_title("Events per Node")
        ax.legend()

        return ax


class sync_interval_counter:
    """initializes the sets to keep a track of the syncronised and unsynchronised Node IDs
    and the maximum tick at which the last 'Sync' event recorded globally among the syncronised nodes"""

    def __init__(self):
        self.sync_node_set = set()  # Set to track synced nodes
        self.unsync_node_set = set()  # Set to track unsynced nodes
        self.max_sync_tick = 0  # Variable to track the maximum sync tick globally

    """Builds the dictionary by reading the log file (line-by-line) and appends the synced nodes and replaces the largest sync tick in the dictionary for each 'Sync' event found in the log file
    Input arguments: line - a line from the log file i.e., string

    ===============
    Example of log file line:
    begins with -> [DEBUG] (PROTOCOL) @ ['int:tick']: Node ['int:Node_id'] attempts gateway connect via WAN
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
        attempt_pattern = r"\[DEBUG\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+attempts gateway connect via WAN"
        synced_pattern = r"\[INFO\]\s+\(PROTOCOL\)\s+@\s+(?P<tick>\d+):\s+Node\s+(?P<node_id>\d+)\s+(connected to gateway via WAN|discovery complete with hop count \d+)"

        match = re.match(attempt_pattern, line)
        if match:
            node_id = int(match.group("node_id"))
            # Special case 1 & 2: ignore if already synced or already waiting
            if node_id not in self.sync_node_set and node_id not in self.unsync_node_set:
                self.unsync_node_set.add(node_id)
            return

        match = re.match(synced_pattern, line)
        if match:
            node_id = int(match.group("node_id"))
            tick = int(match.group("tick"))
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

        ax.bar(["Synced", "Unsynced"], [len(synced), len(unsynced)], color=["steelblue", "salmon"])
        ax.set_ylabel("Node count")
        ax.set_title(f"Sync state  (Time taken to complete synchronization: {tick})")

        return ax


# ===================Helper functions===================
def execute(executable_list, line):
    """Passes each log line to every analyser's build_dict method."""
    for exe in executable_list:
        exe.build_dict(line)


def post_process_and_plot(executable_list):
    """Creates one subplot per analyser in a single window and calls plot(ax) on each."""
    n = len(executable_list)
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 5))
    if n == 1:
        axes = [axes]
    for exe, ax in zip(executable_list, axes):
        exe.plot(ax)
    fig.tight_layout()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="Log_debugging\\simulation.log", help="Path to log file")
    args = parser.parse_args()

    executable_list = [deadnodecounter(), sync_interval_counter()]

    with open(args.log, "r") as file:
        for line in file:
            execute(executable_list, line)

    post_process_and_plot(executable_list)
    plt.show()


if __name__ == "__main__":
    main()
