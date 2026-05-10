import matplotlib
matplotlib.use('Agg')  # non-interactive backend — must be set before importing pyplot

import pytest
import matplotlib.pyplot as plt
from pathlib import Path

from main import deadnodecounter, execute, post_process_and_plot, sync_interval_counter

LOG_PATH = Path(__file__).parent / 'test_simulation.log'

# Ground truth derived from test_simulation.log
SYNC_EXPECTED_SYNCED   = [1, 2, 4, 5]
SYNC_EXPECTED_UNSYNCED = [3, 6]
SYNC_EXPECTED_TICK     = 140


@pytest.fixture(scope='session')
def log_lines():
    with open(LOG_PATH) as f:
        return f.readlines()


@pytest.fixture
def sync_full_counter(log_lines):
    """sync_interval_counter populated with every line from the log file."""
    c = sync_interval_counter()
    for line in log_lines:
        c.build_dict(line)
    return c

DEATH_LINE = '[CRITICAL] (NODE) @ {tick}: Node {node_id} DIED'


def death(node_id, tick):
    return DEATH_LINE.format(tick=tick, node_id=node_id)


# ---------------------------------------------------------------------------
# deadnodecounter.build_dict
# ---------------------------------------------------------------------------

class TestBuildDict:
    def test_valid_line_adds_entry(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.dict == {1: [100]}

    def test_non_critical_level_ignored(self):
        c = deadnodecounter()
        c.build_dict('[DEBUG] (NODE) @ 100: Node 1 DIED')
        assert c.dict == {}

    def test_info_level_ignored(self):
        c = deadnodecounter()
        c.build_dict('[INFO] (NODE) @ 100: Node 1 DIED')
        assert c.dict == {}

    def test_critical_wrong_component_ignored(self):
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (TRANCEIVER) @ 100: Node 1 DIED')
        assert c.dict == {}

    def test_multiple_deaths_same_node_accumulates_ticks(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(1, 300))
        assert c.dict == {1: [100, 200, 300]}

    def test_multiple_different_nodes_tracked_separately(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 150))
        c.build_dict(death(1, 200))
        assert c.dict == {1: [100, 200], 2: [150]}

    def test_returns_none_for_non_critical(self):
        c = deadnodecounter()
        assert c.build_dict('[DEBUG] (NODE) @ 100: Node 1 DIED') is None


# ---------------------------------------------------------------------------
# deadnodecounter.deathcounter
# ---------------------------------------------------------------------------

class TestDeathcounter:
    def test_empty_dict_returns_empty_lists(self):
        c = deadnodecounter()
        node_ids, counts = c.deathcounter()
        assert node_ids == [] and counts == []

    def test_single_node_single_death(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        node_ids, counts = c.deathcounter()
        assert node_ids == [1] and counts == [1]

    def test_single_node_multiple_deaths_correct_count(self):
        c = deadnodecounter()
        c.build_dict(death(3, 100))
        c.build_dict(death(3, 200))
        node_ids, counts = c.deathcounter()
        assert node_ids == [3] and counts == [2]

    def test_multiple_nodes_correct_counts(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 150))
        c.build_dict(death(1, 200))
        node_ids, counts = c.deathcounter()
        # order matches dict insertion order
        assert dict(zip(node_ids, counts)) == {1: 2, 2: 1}

    def test_repeated_calls_do_not_double_count(self):
        # Regression: self.count used to be an instance list that accumulated
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.deathcounter()                    # first call
        _, counts = c.deathcounter()        # second call
        assert counts == [1]


# ---------------------------------------------------------------------------
# deadnodecounter.plot
# ---------------------------------------------------------------------------

class TestPlot:
    def teardown_method(self):
        plt.close('all')

    def test_empty_dict_plot_does_not_raise(self):
        """stem([], []) must not raise when no death events were recorded."""
        c = deadnodecounter()
        ax = c.plot()          # should not raise ValueError
        assert hasattr(ax, 'stem')

    def test_empty_dict_plot_shows_no_data_message(self):
        """When there is no data, the axes should carry an explanatory text label."""
        c = deadnodecounter()
        _, ax = plt.subplots()
        c.plot(ax=ax)
        texts = [t.get_text() for t in ax.texts]
        assert any("No death events" in t for t in texts)

    def test_returns_axes_object(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        ax = c.plot()
        assert hasattr(ax, 'stem')

    def test_uses_provided_ax(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        _, ax = plt.subplots()
        returned = c.plot(ax=ax)
        assert returned is ax

    def test_creates_own_figure_when_ax_is_none(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        before = set(plt.get_fignums())
        c.plot()
        assert set(plt.get_fignums()) - before  # a new figure was created


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

class TestExecute:
    def test_calls_build_dict_on_every_analyser(self):
        c1, c2 = deadnodecounter(), deadnodecounter()
        execute([c1, c2], death(1, 100))
        assert c1.dict == {1: [100]}
        assert c2.dict == {1: [100]}

    def test_non_matching_line_leaves_dicts_empty(self):
        c = deadnodecounter()
        execute([c], '[DEBUG] (NODE) @ 100: Node 1 DIED')
        assert c.dict == {}

    def test_empty_executable_list_does_not_raise(self):
        execute([], death(1, 100))


# ---------------------------------------------------------------------------
# post_process_and_plot
# ---------------------------------------------------------------------------

class TestPostProcessAndPlot:
    def teardown_method(self):
        plt.close('all')

    def test_single_analyser_produces_one_figure(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        post_process_and_plot([c])
        assert len(plt.get_fignums()) == 1

    def test_two_analysers_render_in_one_figure_with_two_axes(self):
        c1, c2 = deadnodecounter(), deadnodecounter()
        c1.build_dict(death(1, 100))
        c2.build_dict(death(2, 200))
        post_process_and_plot([c1, c2])
        assert len(plt.get_fignums()) == 1
        fig = plt.figure(plt.get_fignums()[0])
        assert len(fig.axes) == 2


# ---------------------------------------------------------------------------
# sync_interval_counter.build_dict
# ---------------------------------------------------------------------------

class TestSyncBuildDict:
    def test_attempt_adds_to_unsync_set(self, log_lines):
        line = next(l for l in log_lines if 'Node 1 attempts gateway connect via WAN' in l)
        c = sync_interval_counter()
        c.build_dict(line)
        assert c.unsync_node_set == {1}
        assert c.sync_node_set == set()

    def test_discovery_complete_moves_to_sync_set(self, log_lines):
        attempt   = next(l for l in log_lines if 'Node 2 attempts gateway connect via WAN' in l)
        discovery = next(l for l in log_lines if 'Node 2 discovery complete' in l)
        c = sync_interval_counter()
        c.build_dict(attempt)
        c.build_dict(discovery)
        assert c.sync_node_set == {2}
        assert c.unsync_node_set == set()

    def test_sync_tick_updated_on_discovery(self, log_lines):
        attempt   = next(l for l in log_lines if 'Node 2 attempts gateway connect via WAN' in l)
        discovery = next(l for l in log_lines if 'Node 2 discovery complete' in l)
        c = sync_interval_counter()
        c.build_dict(attempt)
        c.build_dict(discovery)
        assert c.max_sync_tick == 60

    def test_special_case1_already_synced_attempt_ignored(self, log_lines):
        # Node 1: first attempt (tick 10) → discovery (tick 140) → re-attempt (tick 160)
        node1_attempts = [l for l in log_lines if 'Node 1 attempts gateway connect via WAN' in l]
        discovery      = next(l for l in log_lines if 'Node 1 discovery complete' in l)
        c = sync_interval_counter()
        c.build_dict(node1_attempts[0])   # tick 10 → unsync
        c.build_dict(discovery)            # tick 140 → sync
        c.build_dict(node1_attempts[-1])  # tick 160 → ignored (already synced)
        assert c.sync_node_set == {1}
        assert c.unsync_node_set == set()

    def test_special_case2_double_attempt_ignored(self, log_lines):
        # Node 6 attempts twice — second attempt must be ignored
        node6_attempts = [l for l in log_lines if 'Node 6 attempts gateway connect via WAN' in l]
        c = sync_interval_counter()
        c.build_dict(node6_attempts[0])   # tick 35 → unsync
        c.build_dict(node6_attempts[1])   # tick 75 → ignored
        assert c.unsync_node_set == {6}
        assert c.sync_node_set == set()

    def test_discovery_without_prior_attempt_ignored(self, log_lines):
        # Node 7 has discovery complete but no prior attempt → must be ignored
        discovery = next(l for l in log_lines if 'Node 7 discovery complete' in l)
        c = sync_interval_counter()
        c.build_dict(discovery)
        assert c.sync_node_set == set()
        assert c.unsync_node_set == set()

    def test_node1_death_and_reset_still_syncs(self, log_lines):
        # Node 1: attempt → die → reset attempt → discovery complete → synced
        node1_lines = [l for l in log_lines
                       if 'Node 1 attempts gateway connect via WAN' in l
                       or 'Node 1 discovery complete' in l]
        c = sync_interval_counter()
        for line in node1_lines:
            c.build_dict(line)
        assert 1 in c.sync_node_set
        assert 1 not in c.unsync_node_set

    def test_non_protocol_line_ignored(self, log_lines):
        line = next(l for l in log_lines if l.startswith('[DEBUG] (TRANCEIVER)'))
        c = sync_interval_counter()
        c.build_dict(line)
        assert c.sync_node_set == set()
        assert c.unsync_node_set == set()


# ---------------------------------------------------------------------------
# sync_interval_counter.sync_counter
# ---------------------------------------------------------------------------

class TestSyncCounter:
    def test_empty_returns_empty_lists_and_zero(self):
        c = sync_interval_counter()
        synced, unsynced, tick = c.sync_counter()
        assert synced == [] and unsynced == [] and tick == 0

    def test_full_log_correct_synced_nodes(self, sync_full_counter):
        synced, _, _ = sync_full_counter.sync_counter()
        assert synced == SYNC_EXPECTED_SYNCED

    def test_full_log_correct_unsynced_nodes(self, sync_full_counter):
        _, unsynced, _ = sync_full_counter.sync_counter()
        assert unsynced == SYNC_EXPECTED_UNSYNCED

    def test_full_log_correct_max_tick(self, sync_full_counter):
        _, _, tick = sync_full_counter.sync_counter()
        assert tick == SYNC_EXPECTED_TICK


# ---------------------------------------------------------------------------
# sync_interval_counter.plot
# ---------------------------------------------------------------------------

class TestSyncPlot:
    def teardown_method(self):
        plt.close('all')

    def test_returns_axes_object(self, sync_full_counter):
        ax = sync_full_counter.plot()
        assert hasattr(ax, 'bar')

    def test_uses_provided_ax(self, sync_full_counter):
        _, ax = plt.subplots()
        returned = sync_full_counter.plot(ax=ax)
        assert returned is ax
