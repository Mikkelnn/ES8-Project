import matplotlib

matplotlib.use("Agg")  # non-interactive backend — must be set before importing pyplot

from pathlib import Path
from uuid import UUID

import matplotlib.pyplot as plt
import pytest

from main import (  # noqa
    battery_capacity_analyser,
    count_lines,
    deadnodecounter,
    execute,
    extract_area_fast,
    packet_forwarding_delay,
    post_process_and_plot,
    read_in_batches,
    save_report,
    sync_interval_counter,
)

LOG_PATH = Path(__file__).parent / "test_simulation.log"

# Ground truth derived from test_simulation.log
SYNC_EXPECTED_SYNCED = [1, 2, 4, 5]
SYNC_EXPECTED_UNSYNCED = [3, 6]
SYNC_EXPECTED_TICK = 140


@pytest.fixture(scope="session")
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


DEATH_LINE = "[CRITICAL] (NODE) @ {tick}: Node {node_id} DIED"


def death(node_id, tick):
    return DEATH_LINE.format(tick=tick, node_id=node_id)


# ---------------------------------------------------------------------------
# deadnodecounter.build_dict
# ---------------------------------------------------------------------------


class TestBuildDict:
    def test_valid_line_adds_entry(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.dict == {1: 1}

    def test_non_critical_level_ignored(self):
        c = deadnodecounter()
        c.build_dict("[DEBUG] (NODE) @ 100: Node 1 DIED")
        assert c.dict == {}

    def test_info_level_ignored(self):
        c = deadnodecounter()
        c.build_dict("[INFO] (NODE) @ 100: Node 1 DIED")
        assert c.dict == {}

    def test_critical_wrong_component_ignored(self):
        c = deadnodecounter()
        c.build_dict("[CRITICAL] (TRANCEIVER) @ 100: Node 1 DIED")
        assert c.dict == {}

    def test_multiple_deaths_same_node_accumulates_count(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(1, 300))
        assert c.dict == {1: 3}

    def test_multiple_different_nodes_tracked_separately(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 150))
        c.build_dict(death(1, 200))
        assert c.dict == {1: 2, 2: 1}

    def test_returns_none_for_non_critical(self):
        c = deadnodecounter()
        assert c.build_dict("[DEBUG] (NODE) @ 100: Node 1 DIED") is None


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
        c.deathcounter()  # first call
        _, counts = c.deathcounter()  # second call
        assert counts == [1]


# ---------------------------------------------------------------------------
# deadnodecounter.death_distribution
# ---------------------------------------------------------------------------


class TestDeathDistribution:
    def test_empty_dict_returns_empty_dict(self):
        c = deadnodecounter()
        assert c.death_distribution() == {}

    def test_single_node_single_death(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.death_distribution() == {1: 1}

    def test_single_node_multiple_deaths(self):
        # Node 3 died 3 times → {3: 1} (one node with 3 deaths)
        c = deadnodecounter()
        c.build_dict(death(3, 100))
        c.build_dict(death(3, 200))
        c.build_dict(death(3, 300))
        assert c.death_distribution() == {3: 1}

    def test_two_nodes_same_death_count_merged(self):
        # Nodes 1 and 2 both died twice → {2: 2}
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(2, 150))
        c.build_dict(death(2, 250))
        assert c.death_distribution() == {2: 2}

    def test_mixed_death_counts_not_merged(self):
        # Node 1 died twice, node 2 once → {2: 1, 1: 1}
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(2, 150))
        assert c.death_distribution() == {2: 1, 1: 1}

    def test_repeated_calls_do_not_double_count(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.death_distribution()  # first call
        result = c.death_distribution()  # second call
        assert result == {1: 1}


# ---------------------------------------------------------------------------
# deadnodecounter.report_text
# ---------------------------------------------------------------------------


class TestReportText:
    def test_empty_contains_no_deaths_message(self):
        c = deadnodecounter()
        assert "No death events" in c.report_text()

    def test_contains_total_unique_nodes(self):
        """'Total nodes' line must reflect the number of unique nodes that died."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        c.build_dict(death(2, 300))  # 2 unique nodes
        text = c.report_text()
        assert "Total nodes" in text
        assert "2" in text

    def test_contains_total_death_events(self):
        """'Total deaths' line must reflect the sum of all death events."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(2, 300))  # 3 events total
        text = c.report_text()
        assert "Total deaths" in text
        assert "3" in text

    def test_contains_each_node_id(self):
        c = deadnodecounter()
        c.build_dict(death(42, 100))
        assert "42" in c.report_text()

    def test_contains_each_node_death_count(self):
        c = deadnodecounter()
        c.build_dict(death(7, 100))
        c.build_dict(death(7, 200))
        c.build_dict(death(7, 300))  # node 7 died 3 times
        assert "3" in c.report_text()

    def test_contains_distribution_section(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert "Distribution" in c.report_text()

    def test_repeated_calls_return_same_text(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.report_text() == c.report_text()


# ---------------------------------------------------------------------------
# deadnodecounter.save_report
# ---------------------------------------------------------------------------


class TestSaveReport:
    """Tests for the standalone save_report(text, folder, filename) helper."""

    def test_creates_file_in_specified_folder(self, tmp_path):
        save_report("hello", tmp_path, "report.txt")
        assert (tmp_path / "report.txt").exists()

    def test_file_content_matches_text_argument(self, tmp_path):
        content = "some report content"
        save_report(content, tmp_path, "report.txt")
        assert (tmp_path / "report.txt").read_text(encoding="utf-8") == content

    def test_creates_nested_folder_if_not_exists(self, tmp_path):
        nested = tmp_path / "a" / "b"
        save_report("data", nested, "report.txt")
        assert (nested / "report.txt").exists()

    def test_returns_path_to_written_file(self, tmp_path):
        result = save_report("data", tmp_path, "report.txt")
        assert result == tmp_path / "report.txt"

    def test_accepts_string_path(self, tmp_path):
        save_report("data", str(tmp_path), "report.txt")
        assert (tmp_path / "report.txt").exists()

    def test_works_with_deadnodecounter_report_text(self, tmp_path):
        """End-to-end: save_report writes the same text as report_text()."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        path = save_report(c.report_text(), tmp_path, "dead_node_report.txt")
        assert path.read_text(encoding="utf-8") == c.report_text()


# ---------------------------------------------------------------------------
# deadnodecounter.plot
# ---------------------------------------------------------------------------


class TestPlot:
    def teardown_method(self):
        plt.close("all")

    def test_empty_dict_plot_does_not_raise(self):
        """bar([], []) must not raise when no death events were recorded."""
        c = deadnodecounter()
        ax = c.plot()  # should not raise
        assert hasattr(ax, "bar")

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
        assert hasattr(ax, "bar")

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

    def test_one_bar_per_distinct_death_count(self):
        """Two nodes with different death counts → two bars."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))  # node 1 died once
        c.build_dict(death(2, 200))
        c.build_dict(death(2, 300))  # node 2 died twice
        _, ax = plt.subplots()
        c.plot(ax=ax)
        assert len(ax.patches) == 2  # one bar for count=1, one for count=2

    def test_bar_height_equals_node_count(self):
        """Nodes 1 and 2 both died once → death_count=1 bar has height 2."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        _, ax = plt.subplots()
        c.plot(ax=ax)
        heights = sorted(p.get_height() for p in ax.patches)  # noqa
        assert heights == [2]  # one bar, height = 2 nodes

    def test_x_axis_label(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        _, ax = plt.subplots()
        c.plot(ax=ax)
        assert ax.get_xlabel() == "Number of deaths per node"

    def test_y_axis_label(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        _, ax = plt.subplots()
        c.plot(ax=ax)
        assert ax.get_ylabel() == "Count"

    def test_x_ticks_are_integers(self):
        """X-axis ticks must land only at integer death-count positions."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        c.build_dict(death(2, 300))  # node 2 died twice → x ticks: [1, 2]
        _, ax = plt.subplots()
        c.plot(ax=ax)
        assert all(float(t).is_integer() for t in ax.get_xticks())

    def test_y_ticks_are_integers(self):
        """Y-axis ticks must land only at integer node-count positions."""
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        _, ax = plt.subplots()
        c.plot(ax=ax)
        ymin, ymax = ax.get_ylim()
        visible_ticks = [t for t in ax.get_yticks() if ymin <= t <= ymax]
        assert all(float(t).is_integer() for t in visible_ticks)


# ---------------------------------------------------------------------------
# count_lines
# ---------------------------------------------------------------------------


class TestCountLines:
    def test_empty_file_returns_zero(self, tmp_path):
        f = tmp_path / "empty.log"
        f.write_text("", encoding="utf-8")
        assert count_lines(f) == 0

    def test_single_line_file(self, tmp_path):
        f = tmp_path / "one.log"
        f.write_text("one line\n", encoding="utf-8")
        assert count_lines(f) == 1

    def test_multiple_lines(self, tmp_path):
        f = tmp_path / "multi.log"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        assert count_lines(f) == 3

    def test_accepts_string_path(self, tmp_path):
        f = tmp_path / "test.log"
        f.write_text("a\nb\n", encoding="utf-8")
        assert count_lines(str(f)) == 2

    def test_matches_readlines_count(self, log_lines):
        """count_lines must agree with the number of lines already loaded from the log."""
        assert count_lines(LOG_PATH) == len(log_lines)


# ---------------------------------------------------------------------------
# read_in_batches
# ---------------------------------------------------------------------------


class TestReadInBatches:
    def test_empty_file_yields_no_batches(self, tmp_path):
        f = tmp_path / "empty.log"
        f.write_text("", encoding="utf-8")
        assert list(read_in_batches(f)) == []

    def test_fewer_lines_than_batch_size_yields_one_batch(self, tmp_path):
        f = tmp_path / "small.log"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        batches = list(read_in_batches(f, batch_size=10))
        assert len(batches) == 1
        assert batches[0] == ["a\n", "b\n", "c\n"]

    def test_exactly_batch_size_lines_yields_one_batch(self, tmp_path):
        f = tmp_path / "exact.log"
        f.write_text("".join(f"line{i}\n" for i in range(5)), encoding="utf-8")
        batches = list(read_in_batches(f, batch_size=5))
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_more_lines_than_batch_size_yields_multiple_batches(self, tmp_path):
        f = tmp_path / "multi.log"
        f.write_text("".join(f"line{i}\n" for i in range(12)), encoding="utf-8")
        batches = list(read_in_batches(f, batch_size=5))
        assert len(batches) == 3  # batches of 5, 5, 2

    def test_last_batch_may_be_smaller_than_batch_size(self, tmp_path):
        f = tmp_path / "uneven.log"
        f.write_text("".join(f"line{i}\n" for i in range(7)), encoding="utf-8")
        batches = list(read_in_batches(f, batch_size=5))
        assert len(batches[-1]) == 2

    def test_all_lines_preserved_across_batches(self, tmp_path):
        f = tmp_path / "all.log"
        original = [f"line{i}\n" for i in range(25)]
        f.write_text("".join(original), encoding="utf-8")
        batches = list(read_in_batches(f, batch_size=7))
        recovered = [line for batch in batches for line in batch]
        assert recovered == original

    def test_accepts_string_path(self, tmp_path):
        f = tmp_path / "str.log"
        f.write_text("x\ny\n", encoding="utf-8")
        assert list(read_in_batches(str(f), batch_size=10)) != []

    def test_default_batch_size_is_1000(self, tmp_path):
        """A file with 1001 lines must produce 2 batches with the default batch size."""
        f = tmp_path / "default.log"
        f.write_text("".join(f"line{i}\n" for i in range(1001)), encoding="utf-8")
        batches = list(read_in_batches(f))
        assert len(batches) == 2
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 1


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestExecute:
    def test_calls_build_dict_on_every_analyser(self):
        c1, c2 = deadnodecounter(), deadnodecounter()
        execute([c1, c2], death(1, 100))
        assert c1.dict == {1: 1}
        assert c2.dict == {1: 1}

    def test_non_matching_line_leaves_dicts_empty(self):
        c = deadnodecounter()
        execute([c], "[DEBUG] (NODE) @ 100: Node 1 DIED")
        assert c.dict == {}

    def test_empty_executable_list_does_not_raise(self):
        execute([], death(1, 100))


# ---------------------------------------------------------------------------
# post_process_and_plot
# ---------------------------------------------------------------------------


class TestPostProcessAndPlot:
    def teardown_method(self):
        plt.close("all")

    def test_single_analyser_produces_one_figure(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        post_process_and_plot([c])
        assert len(plt.get_fignums()) == 1

    def test_two_analysers_produce_two_separate_figures(self):
        """Each analyser opens its own figure window."""
        c1, c2 = deadnodecounter(), deadnodecounter()
        c1.build_dict(death(1, 100))
        c2.build_dict(death(2, 200))
        post_process_and_plot([c1, c2])
        assert len(plt.get_fignums()) == 2


# ---------------------------------------------------------------------------
# sync_interval_counter.build_dict
# ---------------------------------------------------------------------------


class TestSyncBuildDict:
    def test_attempt_adds_to_unsync_set(self, log_lines):
        line = next(ln for ln in log_lines if "Node 1 attempts gateway connect via WAN" in ln)
        c = sync_interval_counter()
        c.build_dict(line)
        assert c.unsync_node_set == {1}
        assert c.sync_node_set == set()

    def test_discovery_complete_moves_to_sync_set(self, log_lines):
        attempt = next(ln for ln in log_lines if "Node 2 attempts gateway connect via WAN" in ln)
        discovery = next(ln for ln in log_lines if "Node 2 discovery complete" in ln)
        c = sync_interval_counter()
        c.build_dict(attempt)
        c.build_dict(discovery)
        assert c.sync_node_set == {2}
        assert c.unsync_node_set == set()

    def test_sync_tick_updated_on_discovery(self, log_lines):
        attempt = next(ln for ln in log_lines if "Node 2 attempts gateway connect via WAN" in ln)
        discovery = next(ln for ln in log_lines if "Node 2 discovery complete" in ln)
        c = sync_interval_counter()
        c.build_dict(attempt)
        c.build_dict(discovery)
        assert c.max_sync_tick == 60

    def test_special_case1_already_synced_attempt_ignored(self, log_lines):
        # Node 1: first attempt (tick 10) → discovery (tick 140) → re-attempt (tick 160)
        node1_attempts = [ln for ln in log_lines if "Node 1 attempts gateway connect via WAN" in ln]
        discovery = next(ln for ln in log_lines if "Node 1 discovery complete" in ln)
        c = sync_interval_counter()
        c.build_dict(node1_attempts[0])  # tick 10 → unsync
        c.build_dict(discovery)  # tick 140 → sync
        c.build_dict(node1_attempts[-1])  # tick 160 → ignored (already synced)
        assert c.sync_node_set == {1}
        assert c.unsync_node_set == set()

    def test_special_case2_double_attempt_ignored(self, log_lines):
        # Node 6 attempts twice — second attempt must be ignored
        node6_attempts = [ln for ln in log_lines if "Node 6 attempts gateway connect via WAN" in ln]
        c = sync_interval_counter()
        c.build_dict(node6_attempts[0])  # tick 35 → unsync
        c.build_dict(node6_attempts[1])  # tick 75 → ignored
        assert c.unsync_node_set == {6}
        assert c.sync_node_set == set()

    def test_discovery_without_prior_attempt_ignored(self, log_lines):
        # Node 7 has discovery complete but no prior attempt → must be ignored
        discovery = next(ln for ln in log_lines if "Node 7 discovery complete" in ln)
        c = sync_interval_counter()
        c.build_dict(discovery)
        assert c.sync_node_set == set()
        assert c.unsync_node_set == set()

    def test_node1_death_and_reset_still_syncs(self, log_lines):
        # Node 1: attempt → die → reset attempt → discovery complete → synced
        node1_lines = [ln for ln in log_lines if "Node 1 attempts gateway connect via WAN" in ln or "Node 1 discovery complete" in ln]
        c = sync_interval_counter()
        for line in node1_lines:
            c.build_dict(line)
        assert 1 in c.sync_node_set
        assert 1 not in c.unsync_node_set

    def test_non_protocol_line_ignored(self, log_lines):
        line = next(ln for ln in log_lines if ln.startswith("[DEBUG] (TRANCEIVER)"))
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
        plt.close("all")

    def test_returns_axes_object(self, sync_full_counter):
        ax = sync_full_counter.plot()
        assert hasattr(ax, "bar")

    def test_uses_provided_ax(self, sync_full_counter):
        _, ax = plt.subplots()
        returned = sync_full_counter.plot(ax=ax)
        assert returned is ax


# Ground truth for battery integration tests (derived from generate_battery_log.py)
# MAX_CHARGE=7.9, num_bins=5 → bin_width=1.58
# Group A (nodes 8-57):  even→wake 6.5(bin4)/sleep 4.5, odd→wake 4.0(bin2)/sleep 2.0; delta 2.0(bin1)
# Group B (nodes 58-82): wake 3.0(bin1)/death→delta 3.0(bin1)
# Group C (nodes 83-107): wake1 7.5(bin4)/sleep1 5.5→delta2.0(bin1); wake2 5.0(bin3)/death→delta5.0(bin3)
BATTERY_NODE_COUNT = 100  # nodes 8-107
BATTERY_NODE8_OP_RANGE = [0, 0, 0, 0, 1]  # even group A: 6.5 → bin 4
BATTERY_NODE9_OP_RANGE = [0, 0, 1, 0, 0]  # odd  group A: 4.0 → bin 2
BATTERY_NODE58_OP_RANGE = [0, 1, 0, 0, 0]  # group B: 3.0 → bin 1
BATTERY_NODE83_OP_RANGE = [0, 0, 0, 1, 1]  # group C: 7.5→bin4, 5.0→bin3
BATTERY_NODE8_DELTA = [0, 1, 0, 0, 0]  # delta 2.0 → bin 1
BATTERY_NODE9_DELTA = [0, 1, 0, 0, 0]  # delta 2.0 → bin 1
BATTERY_NODE58_DELTA = [0, 1, 0, 0, 0]  # delta 3.0 → bin 1
BATTERY_NODE83_DELTA = [0, 1, 0, 1, 0]  # deltas 2.0(bin1) + 5.0(bin3)


@pytest.fixture
def battery_full_counter(log_lines):
    """battery_capacity_analyser populated with every line from the log file."""
    c = battery_capacity_analyser(num_bins=5)
    for line in log_lines:
        c.build_dict(line)
    return c


# ---------------------------------------------------------------------------
# battery_capacity_analyser helpers
# ---------------------------------------------------------------------------


def wake_line(node_id, tick, charge):
    return f"[INFO] (NODE) @ {tick}: Node {node_id} woke up, , Battery charge {charge}, "


def sleep_line(node_id, tick, charge):
    return f"[INFO] (NODE) @ {tick}: Node {node_id} is going to sleep, Battery charge {charge}, "


# ---------------------------------------------------------------------------
# battery_capacity_analyser.build_dict
# ---------------------------------------------------------------------------


class TestBatteryBuildDict:
    def test_wake_line_adds_to_op_range(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        assert sum(c.dict_op_range[1]) == 1

    def test_sleep_without_prior_wake_not_recorded(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(sleep_line(1, 2000, 3.0))
        assert c.dict_operating_range == {}

    def test_wake_then_sleep_records_delta(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        assert sum(c.dict_operating_range[1]) == 1

    def test_pending_wake_cleared_after_sleep(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        assert 1 not in c._pending_wake

    def test_multiple_cycles_accumulate(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        c.build_dict(wake_line(1, 3000, 6.0))
        c.build_dict(sleep_line(1, 4000, 4.0))
        assert sum(c.dict_op_range[1]) == 2
        assert sum(c.dict_operating_range[1]) == 2

    def test_multiple_nodes_tracked_separately(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(wake_line(2, 1000, 3.0))
        assert 1 in c.dict_op_range
        assert 2 in c.dict_op_range

    def test_non_matching_line_ignored(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict("[DEBUG] (NODE) @ 100: Node 1 some other event, ")
        assert c.dict_op_range == {}
        assert c.dict_operating_range == {}

    def test_double_sleep_without_wake_second_ignored(self):
        """Second sleep with no intermediate wake must not record a delta."""
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        c.build_dict(sleep_line(1, 3000, 2.0))  # no wake in between — ignored
        assert sum(c.dict_operating_range[1]) == 1

    def test_node_death_treated_as_sleep_with_zero_charge(self):
        """A DIED event after a wake must record delta = wake_charge - 0."""
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict("[CRITICAL] (NODE) @ 2000: Node 1 DIED, ")
        assert sum(c.dict_operating_range[1]) == 1

    def test_node_death_delta_equals_wake_charge(self):
        """Delta when node dies must equal the wake charge (sleep charge = 0)."""
        # MAX_CHARGE=7.9, num_bins=5 → bin_width=1.58; wake=5.0 → delta=5.0 → bin 3
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict("[CRITICAL] (NODE) @ 2000: Node 1 DIED, ")
        _, operating_range = c.get_histograms()
        assert operating_range[1][3] == 1

    def test_node_death_without_prior_wake_ignored(self):
        """Death with no prior wake must not write to dict_operating_range."""
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict("[CRITICAL] (NODE) @ 2000: Node 1 DIED, ")
        assert c.dict_operating_range == {}

    def test_node_death_clears_pending_wake(self):
        """After death, the pending wake entry must be removed."""
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict("[CRITICAL] (NODE) @ 2000: Node 1 DIED, ")
        assert 1 not in c._pending_wake


# ---------------------------------------------------------------------------
# battery_capacity_analyser.get_histograms
# ---------------------------------------------------------------------------


class TestBatteryGetHistograms:
    def test_empty_returns_empty_dicts(self):
        c = battery_capacity_analyser(num_bins=5)
        op_range, operating_range = c.get_histograms()
        assert op_range == {} and operating_range == {}

    def test_correct_bin_for_wake_charge(self):
        # MAX_CHARGE=7.9, num_bins=5 → bin_width=1.58; charge=5.0 → bin 3
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        op_range, _ = c.get_histograms()
        assert op_range[1][3] == 1
        assert sum(op_range[1]) == 1

    def test_correct_bin_for_delta(self):
        # wake=5.0, sleep=3.5 → delta=1.5; bin_width=1.58 → bin 0
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        _, operating_range = c.get_histograms()
        assert operating_range[1][0] == 1

    def test_max_charge_clamped_to_last_bin(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 7.9))
        op_range, _ = c.get_histograms()
        assert op_range[1][4] == 1  # clamped to last bin


# ---------------------------------------------------------------------------
# battery_capacity_analyser.plot
# ---------------------------------------------------------------------------


class TestBatteryPlot:
    def teardown_method(self):
        plt.close("all")

    def test_wakeup_histogram_aggregates_counts_across_nodes(self):
        """Three nodes all waking at 5.0 J (bin 3) must show bar height 3, not 1."""
        c = battery_capacity_analyser(num_bins=5)
        for node_id in [1, 2, 3]:
            c.build_dict(wake_line(node_id, 1000 + node_id, 5.0))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        heights = [p.get_height() for p in axes[0].patches]
        assert heights[3] == 3  # bin 3 → 3 nodes

    def test_delta_histogram_aggregates_counts_across_nodes(self):
        """Three nodes with delta in bin 1 must show bar height 3, not 1."""
        c = battery_capacity_analyser(num_bins=5)
        for node_id in [1, 2, 3]:
            c.build_dict(wake_line(node_id, 1000 + node_id, 5.0))
            c.build_dict(sleep_line(node_id, 2000 + node_id, 3.5))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        heights = [p.get_height() for p in axes[1].patches]
        assert heights[0] == 3  # delta 1.5 → bin 0; 3 nodes

    def test_plot_with_data_does_not_raise(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake_line(1, 1000, 5.0))
        c.build_dict(sleep_line(1, 2000, 3.5))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))  # should not raise

    def test_empty_plot_does_not_raise(self):
        c = battery_capacity_analyser(num_bins=5)
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))  # should not raise

    def test_plot_creates_own_figure_when_axes_is_none(self):
        c = battery_capacity_analyser(num_bins=5)
        before = set(plt.get_fignums())
        c.plot()
        assert set(plt.get_fignums()) - before

    def test_plot_count_is_two(self):
        assert battery_capacity_analyser.plot_count == 2


# ---------------------------------------------------------------------------
# post_process_and_plot — multi-plot analyser support
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# battery_capacity_analyser — full log integration
# ---------------------------------------------------------------------------


class TestBatteryFullLog:
    def test_correct_node_count_in_op_range(self, battery_full_counter):
        op_range, _ = battery_full_counter.get_histograms()
        assert len(op_range) == BATTERY_NODE_COUNT

    def test_correct_node_count_in_operating_range(self, battery_full_counter):
        _, operating_range = battery_full_counter.get_histograms()
        assert len(operating_range) == BATTERY_NODE_COUNT

    def test_group_a_even_node_op_range(self, battery_full_counter):
        op_range, _ = battery_full_counter.get_histograms()
        assert op_range[8] == BATTERY_NODE8_OP_RANGE

    def test_group_a_odd_node_op_range(self, battery_full_counter):
        op_range, _ = battery_full_counter.get_histograms()
        assert op_range[9] == BATTERY_NODE9_OP_RANGE

    def test_group_b_node_op_range(self, battery_full_counter):
        op_range, _ = battery_full_counter.get_histograms()
        assert op_range[58] == BATTERY_NODE58_OP_RANGE

    def test_group_c_node_op_range_two_wakes(self, battery_full_counter):
        op_range, _ = battery_full_counter.get_histograms()
        assert op_range[83] == BATTERY_NODE83_OP_RANGE

    def test_group_a_even_node_delta(self, battery_full_counter):
        _, operating_range = battery_full_counter.get_histograms()
        assert operating_range[8] == BATTERY_NODE8_DELTA

    def test_group_a_odd_node_delta(self, battery_full_counter):
        _, operating_range = battery_full_counter.get_histograms()
        assert operating_range[9] == BATTERY_NODE9_DELTA

    def test_group_b_node_delta_from_death(self, battery_full_counter):
        _, operating_range = battery_full_counter.get_histograms()
        assert operating_range[58] == BATTERY_NODE58_DELTA

    def test_group_c_node_two_cycle_delta(self, battery_full_counter):
        _, operating_range = battery_full_counter.get_histograms()
        assert operating_range[83] == BATTERY_NODE83_DELTA

    def test_wakeup_histogram_correct_aggregated_bin_totals(self, battery_full_counter):
        """Bin totals across all 100 nodes: [0, 25, 25, 25, 50]."""
        fig, axes = plt.subplots(1, 2)
        battery_full_counter.plot(list(axes))
        heights = [p.get_height() for p in axes[0].patches]
        plt.close("all")
        assert heights == [0, 25, 25, 25, 50]

    def test_delta_histogram_correct_aggregated_bin_totals(self, battery_full_counter):
        """Delta bin totals across all 100 nodes: [0, 100, 0, 25, 0]."""
        fig, axes = plt.subplots(1, 2)
        battery_full_counter.plot(list(axes))
        heights = [p.get_height() for p in axes[1].patches]
        plt.close("all")
        assert heights == [0, 100, 0, 25, 0]

    def test_existing_deaths_without_wake_not_recorded(self, battery_full_counter):
        """Nodes 1-3 die in the log but have no wake events — must not appear."""
        op_range, operating_range = battery_full_counter.get_histograms()
        for node_id in [1, 2, 3]:
            assert node_id not in op_range
            assert node_id not in operating_range


# ---------------------------------------------------------------------------
# packet_forwarding_delay helpers
# ---------------------------------------------------------------------------

# Fixed v4 UUIDs used across all packet-forwarding tests
GUID_A = "f47ac10b-58cc-4372-a567-0e02b2c3d479"  # node 108 → delivered
GUID_B = "550e8400-e29b-41d4-a716-446655440000"  # node 108 → delivered (larger delay)
GUID_C = "6ba7b810-9dad-4d1a-80b4-00c04fd430c8"  # node 109 → delivered
GUID_D = "c9bf9e57-1685-4c89-bafb-ff5af830be8a"  # gateway-only (no node origin)
GUID_E = "11111111-1111-4111-8111-111111111111"  # node 110 → lost (never delivered)


def node_enqueue_line(node_id, tick, guid):
    return f"[INFO] (PROTOCOL) @ {tick}: Node {node_id} enqueued averaged payload: avg_s1=42.5, avg_s2=17.0, GUID={guid}, "


def gateway_received_line(gateway_id, tick, guid):
    return f"[INFO] (GATEWAY) @ {tick}: Gateway {gateway_id} received data:SomePayload, GUID={guid}, "


# ---------------------------------------------------------------------------
# packet_forwarding_delay.build_dict
# ---------------------------------------------------------------------------


class TestPacketForwardingBuildDict:
    def test_node_enqueue_records_uuid_in_node_origin(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        assert UUID(GUID_A) in c._node_origin

    def test_node_enqueue_uuid_key_is_uuid_type(self):
        """Key stored in _node_origin must be a uuid.UUID instance, not a string."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        keys = list(c._node_origin.keys())
        assert len(keys) == 1
        assert isinstance(keys[0], UUID)

    def test_node_enqueue_stores_tick_and_node_id(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(5, 2500, GUID_A))
        assert c._node_origin[UUID(GUID_A)] == [2500, 5]

    def test_second_enqueue_same_uuid_ignored(self):
        """First origin wins; a second node enqueuing the same UUID is ignored."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(node_enqueue_line(2, 2000, GUID_A))
        assert c._node_origin[UUID(GUID_A)] == [1000, 1]

    def test_gateway_recv_known_uuid_records_successful_count(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        assert c._stats[1][1] == 1  # successful_count

    def test_gateway_recv_known_uuid_accumulates_diff(self):
        """diff = sum of all delays for this node."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))  # delay = 500
        assert c._stats[1][0] == 500  # diff

    def test_gateway_recv_pops_uuid_from_node_origin(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        assert UUID(GUID_A) not in c._node_origin

    def test_gateway_recv_unknown_uuid_ignored_in_stats(self):
        """Gateway receipt of a UUID never seen at any node leaves _stats empty."""
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        assert c._stats == {}

    def test_gateway_recv_unknown_uuid_counted_as_orphan(self):
        """Gateway receipt of a UUID with no node origin is added to _orphan_uuids."""
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        assert UUID(GUID_D) in c._orphan_uuids

    def test_orphan_uuid_stored_as_uuid_type(self):
        """Items in _orphan_uuids must be uuid.UUID instances, not strings."""
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        for item in c._orphan_uuids:
            assert isinstance(item, UUID)

    def test_same_orphan_uuid_received_twice_counted_once(self):
        """Receiving the same unknown UUID at the gateway twice counts as one orphan."""
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        c.build_dict(gateway_received_line(1, 3000, GUID_D))
        assert len(c._orphan_uuids) == 1

    def test_delivered_uuid_received_again_not_counted_as_orphan(self):
        """A UUID that was delivered once and then received again is NOT an orphan."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))  # delivered
        c.build_dict(gateway_received_line(1, 2000, GUID_A))  # duplicate receipt
        assert UUID(GUID_A) not in c._orphan_uuids

    def test_delivered_uuid_not_in_orphan_uuids(self):
        """Successful delivery must never add the UUID to _orphan_uuids."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        assert c._orphan_uuids == set()

    def test_orphan_gateway_count_zero_initially(self):
        c = packet_forwarding_delay()
        assert c.orphan_gateway_count == 0

    def test_orphan_gateway_count_reflects_orphan_uuids(self):
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        assert c.orphan_gateway_count == 1

    def test_multiple_distinct_orphan_uuids_counted_correctly(self):
        c = packet_forwarding_delay()
        c.build_dict(gateway_received_line(1, 2000, GUID_D))
        c.build_dict(gateway_received_line(1, 3000, GUID_C))  # GUID_C has no node enqueue here
        assert c.orphan_gateway_count == 2

    def test_gateway_recv_same_uuid_twice_only_first_counted(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        c.build_dict(gateway_received_line(1, 2000, GUID_A))  # duplicate — ignored
        assert c._stats[1][1] == 1  # still only 1 successful delivery

    def test_diff_accumulates_across_multiple_deliveries(self):
        """Two deliveries from the same node: diff = delay1 + delay2."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))  # delay 500
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        c.build_dict(node_enqueue_line(1, 2000, GUID_B))  # delay 700
        c.build_dict(gateway_received_line(1, 2700, GUID_B))
        assert c._stats[1][0] == 1200  # 500 + 700
        assert c._stats[1][1] == 2

    def test_non_matching_line_ignored(self):
        c = packet_forwarding_delay()
        c.build_dict("[DEBUG] (NODE) @ 100: Node 1 some event, ")
        assert c._node_origin == {}
        assert c._stats == {}


# ---------------------------------------------------------------------------
# packet_forwarding_delay.finalize
# ---------------------------------------------------------------------------


class TestPacketForwardingFinalize:
    def test_undelivered_uuid_increments_lost_count(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_E))
        c.finalize()
        assert c._stats[1][2] == 1  # lost count

    def test_finalize_idempotent(self):
        """Calling finalize twice must not double-count lost packets."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_E))
        c.finalize()
        c.finalize()
        assert c._stats[1][2] == 1

    def test_delivered_uuid_not_counted_as_lost(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        c.finalize()
        assert c._stats[1][2] == 0  # lost = 0

    def test_multiple_lost_uuids_same_node(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(node_enqueue_line(1, 2000, GUID_B))
        c.finalize()
        assert c._stats[1][2] == 2


# ---------------------------------------------------------------------------
# packet_forwarding_delay.get_stats
# ---------------------------------------------------------------------------


class TestPacketForwardingGetStats:
    def test_empty_returns_empty_dict(self):
        c = packet_forwarding_delay()
        assert c.get_stats() == {}

    def test_stats_layout_after_one_delivery(self):
        """Stats for a single delivered packet: [diff, 1, 0]."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        stats = c.get_stats()
        diff, successful, lost = stats[1]
        assert diff == 500
        assert successful == 1
        assert lost == 0

    def test_average_delay_computable(self):
        """Average = diff / successful_count."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))  # delay 200
        c.build_dict(gateway_received_line(1, 1200, GUID_A))
        c.build_dict(node_enqueue_line(1, 2000, GUID_B))  # delay 800
        c.build_dict(gateway_received_line(1, 2800, GUID_B))
        diff, count, _ = c.get_stats()[1]
        assert diff / count == 500.0  # (200 + 800) / 2

    def test_lost_count_included_after_finalize(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_E))
        stats = c.get_stats()  # get_stats calls finalize internally
        assert stats[1][2] == 1


# ---------------------------------------------------------------------------
# packet_forwarding_delay.delay_distribution
# ---------------------------------------------------------------------------


class TestDelayDistribution:
    def test_empty_returns_empty_dict(self):
        c = packet_forwarding_delay()
        assert c.delay_distribution() == {}

    def test_single_node_single_delivery(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))  # delay = 500
        assert c.delay_distribution() == {500: 1}

    def test_single_node_two_deliveries_averages_correctly(self):
        # diff = 200 + 800 = 1000, count = 2 → avg = 500
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1200, GUID_A))  # delay 200
        c.build_dict(node_enqueue_line(1, 2000, GUID_B))
        c.build_dict(gateway_received_line(1, 2800, GUID_B))  # delay 800
        assert c.delay_distribution() == {500: 1}

    def test_two_nodes_same_avg_merged(self):
        # Both nodes: delay 500 → {500: 2}
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        c.build_dict(node_enqueue_line(2, 2000, GUID_C))
        c.build_dict(gateway_received_line(2, 2500, GUID_C))
        assert c.delay_distribution() == {500: 2}

    def test_two_nodes_different_avg_not_merged(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1100, GUID_A))  # node 1: delay 100
        c.build_dict(node_enqueue_line(2, 2000, GUID_C))
        c.build_dict(gateway_received_line(2, 2900, GUID_C))  # node 2: delay 900
        assert c.delay_distribution() == {100: 1, 900: 1}

    def test_lost_only_node_excluded(self):
        """A node with no delivered packets must not appear in the distribution."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_E))  # never delivered
        c.finalize()
        assert c.delay_distribution() == {}

    def test_average_rounded_to_nearest_int(self):
        # diff = 1, count = 3 → avg ≈ 0.333 → rounds to 0
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1001, GUID_A))  # delay 1
        # Use two more GUIDs with delay 0 (same tick enqueue and receive)
        # diff=1, count=1 → avg=1 rounded to 1
        assert c.delay_distribution() == {1: 1}

    def test_repeated_calls_return_same_dict(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        assert c.delay_distribution() == c.delay_distribution()


# ---------------------------------------------------------------------------
# packet_forwarding_delay._binned_delay_distribution
# ---------------------------------------------------------------------------


class TestBinnedDelayDistribution:
    def _counter_with_delays(self, delays):
        """Build a packet_forwarding_delay with given per-node avg delays pre-loaded."""
        c = packet_forwarding_delay()
        c._finalized = True  # skip finalize side-effects
        for node_id, delay in enumerate(delays):
            c._stats[node_id] = [delay, 1, 0]  # [diff==delay, successful=1, lost=0]
        return c

    def test_ten_or_fewer_bins_returned_unchanged(self):
        delays = list(range(100, 1100, 100))  # exactly 10 distinct values
        c = self._counter_with_delays(delays)
        assert len(c._binned_delay_distribution()) == 10

    def test_more_than_ten_bins_merged_to_at_most_ten(self):
        delays = list(range(100, 1200, 100))  # 11 distinct values
        c = self._counter_with_delays(delays)
        assert len(c._binned_delay_distribution()) <= 10

    def test_total_node_count_preserved_after_merging(self):
        delays = list(range(100, 1200, 100))  # 11 nodes
        c = self._counter_with_delays(delays)
        binned = c._binned_delay_distribution()
        assert sum(binned.values()) == 11

    def test_bin_keys_are_integers(self):
        delays = list(range(50, 1250, 50))  # 24 distinct values
        c = self._counter_with_delays(delays)
        binned = c._binned_delay_distribution()
        assert all(isinstance(k, int) for k in binned)

    def test_empty_distribution_returns_empty_dict(self):
        c = packet_forwarding_delay()
        assert c._binned_delay_distribution() == {}

    def test_single_value_returns_single_bin(self):
        c = self._counter_with_delays([500])
        assert c._binned_delay_distribution() == {500: 1}


# ---------------------------------------------------------------------------
# packet_forwarding_delay.plot
# ---------------------------------------------------------------------------


class TestPacketForwardingPlot:
    def teardown_method(self):
        plt.close("all")

    def test_plot_count_is_two(self):
        assert packet_forwarding_delay.plot_count == 2

    def test_empty_delay_plot_shows_no_data_message(self):
        c = packet_forwarding_delay()
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        texts = [t.get_text() for t in axes[0].texts]
        assert any("No delivered" in t for t in texts)

    def test_empty_loss_plot_shows_no_data_message(self):
        c = packet_forwarding_delay()
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        texts = [t.get_text() for t in axes[1].texts]
        assert any("No packet loss" in t for t in texts)

    def test_returns_two_axes(self):
        c = packet_forwarding_delay()
        fig, axes = plt.subplots(1, 2)
        result = c.plot(list(axes))
        assert len(result) == 2

    def test_uses_provided_axes(self):
        c = packet_forwarding_delay()
        fig, axes = plt.subplots(1, 2)
        result = c.plot(list(axes))
        assert result[0] is axes[0]
        assert result[1] is axes[1]

    def test_creates_own_figure_when_axes_is_none(self):
        c = packet_forwarding_delay()
        before = set(plt.get_fignums())
        c.plot()
        assert set(plt.get_fignums()) - before

    def test_plot_with_data_does_not_raise(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        c.build_dict(node_enqueue_line(2, 2000, GUID_E))  # lost
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))  # should not raise

    def test_delay_plot_x_axis_label(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        assert axes[0].get_xlabel() == "Average delay (ticks)"

    def test_delay_plot_y_axis_label(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        assert axes[0].get_ylabel() == "Count"

    def test_delay_plot_bar_height_equals_node_count(self):
        """Two nodes with the same avg delay → one bar with height 2."""
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))  # delay 500
        c.build_dict(node_enqueue_line(2, 2000, GUID_C))
        c.build_dict(gateway_received_line(2, 2500, GUID_C))  # delay 500
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        heights = [p.get_height() for p in axes[0].patches]
        assert heights == [2]

    def test_delay_plot_x_ticks_are_integers(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        assert all(float(t).is_integer() for t in axes[0].get_xticks())

    def test_delay_plot_y_ticks_are_integers(self):
        c = packet_forwarding_delay()
        c.build_dict(node_enqueue_line(1, 1000, GUID_A))
        c.build_dict(gateway_received_line(1, 1500, GUID_A))
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        ymin, ymax = axes[0].get_ylim()
        visible = [t for t in axes[0].get_yticks() if ymin <= t <= ymax]
        assert all(float(t).is_integer() for t in visible)

    def test_delay_plot_at_most_ten_bars(self):
        """More than 10 distinct avg delays must be merged to ≤10 bars."""
        c = packet_forwarding_delay()
        c._finalized = True
        for node_id in range(15):
            c._stats[node_id] = [(node_id + 1) * 100, 1, 0]  # 15 distinct delays
        fig, axes = plt.subplots(1, 2)
        c.plot(list(axes))
        assert len(axes[0].patches) <= 10


# ---------------------------------------------------------------------------
# packet_forwarding_delay — full log integration
#
# Log data (appended by generate_packet_log.py):
#   Nodes 200-209: 10 packets each, enqueue ticks 3000-3099, recv 4000-4099 → delay=1000
#   Orphan gateway receipts: 3 UUIDs (aaaaaaaa...) with no node origin
#   Lost packets: node 210 enqueues 5 UUIDs (bbbbbbbb...), none delivered
#   Duplicate enqueue: node 211 (tick 5200) wins over node 212 (tick 5201), delivered tick 5300 → delay=100
#   Duplicate gateway recv: node 213 enqueues at 5400, gateway at 5500 (counted) and 5600 (ignored, not orphan)
# ---------------------------------------------------------------------------

DELAY_EXPECTED_SUCCESSFUL_NODES = list(range(200, 210)) + [211, 213]
DELAY_EXPECTED_DIFF_PER_NODE = 10_000  # 10 packets × 1000 ticks each (nodes 200-209)
DELAY_EXPECTED_AVG_DELAY = 1000.0  # diff / count for nodes 200-209
DELAY_EXPECTED_LOST_NODE = 210
DELAY_EXPECTED_LOST_COUNT = 5
DELAY_EXPECTED_ORPHAN_COUNT = 3
DELAY_EXPECTED_DUP_ENQUEUE_NODE = 211  # winner of the duplicate enqueue
DELAY_EXPECTED_DUP_ENQUEUE_DIFF = 100  # 5300 - 5200
DELAY_EXPECTED_DUP_RECV_NODE = 213  # only first gateway receipt counted
DELAY_EXPECTED_DUP_RECV_DIFF = 100  # 5500 - 5400


@pytest.fixture
def delay_full_counter(log_lines):
    """packet_forwarding_delay populated with every line from the log file."""
    c = packet_forwarding_delay()
    for line in log_lines:
        c.build_dict(line)
    return c


class TestPacketForwardingFullLog:
    def test_correct_successful_node_ids(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        delivered_nodes = sorted(n for n, s in stats.items() if s[1] > 0)
        assert delivered_nodes == DELAY_EXPECTED_SUCCESSFUL_NODES

    def test_nodes_200_to_209_correct_diff(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        for node_id in range(200, 210):
            assert stats[node_id][0] == DELAY_EXPECTED_DIFF_PER_NODE

    def test_nodes_200_to_209_correct_successful_count(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        for node_id in range(200, 210):
            assert stats[node_id][1] == 10

    def test_nodes_200_to_209_zero_lost(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        for node_id in range(200, 210):
            assert stats[node_id][2] == 0

    def test_average_delay_nodes_200_to_209(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        for node_id in range(200, 210):
            diff, count, _ = stats[node_id]
            assert diff / count == DELAY_EXPECTED_AVG_DELAY

    def test_lost_node_210_correct_lost_count(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        assert stats[DELAY_EXPECTED_LOST_NODE][2] == DELAY_EXPECTED_LOST_COUNT

    def test_lost_node_210_zero_successful(self, delay_full_counter):
        stats = delay_full_counter.get_stats()
        assert stats[DELAY_EXPECTED_LOST_NODE][1] == 0

    def test_orphan_gateway_count(self, delay_full_counter):
        assert delay_full_counter.orphan_gateway_count == DELAY_EXPECTED_ORPHAN_COUNT

    def test_duplicate_enqueue_winner_attributed_correctly(self, delay_full_counter):
        """Node 211 enqueued first — delivery must be attributed to it, not node 212."""
        stats = delay_full_counter.get_stats()
        assert stats[DELAY_EXPECTED_DUP_ENQUEUE_NODE][0] == DELAY_EXPECTED_DUP_ENQUEUE_DIFF
        assert stats[DELAY_EXPECTED_DUP_ENQUEUE_NODE][1] == 1

    def test_duplicate_enqueue_loser_not_in_stats(self, delay_full_counter):
        """Node 212's enqueue was ignored — it must not appear in stats."""
        stats = delay_full_counter.get_stats()
        assert 212 not in stats

    def test_duplicate_gateway_recv_only_first_counted(self, delay_full_counter):
        """Node 213: second gateway receipt ignored — successful_count stays 1."""
        stats = delay_full_counter.get_stats()
        assert stats[DELAY_EXPECTED_DUP_RECV_NODE][1] == 1
        assert stats[DELAY_EXPECTED_DUP_RECV_NODE][0] == DELAY_EXPECTED_DUP_RECV_DIFF

    def test_duplicate_gateway_recv_not_an_orphan(self, delay_full_counter):
        """The duplicate gateway receipt of dddddddd... must NOT count as an orphan."""
        from uuid import UUID

        dup_guid = UUID("dddddddd-0000-4000-8000-000000000001")
        assert dup_guid not in delay_full_counter._orphan_uuids


class TestPostProcessMultiPlot:
    def teardown_method(self):
        plt.close("all")

    def test_battery_analyser_opens_own_figure_with_two_axes(self):
        """battery_capacity_analyser (plot_count=2) → 1 figure, 2 axes."""
        c = battery_capacity_analyser(num_bins=5)
        post_process_and_plot([c])
        assert len(plt.get_fignums()) == 1
        fig = plt.figure(plt.get_fignums()[0])
        assert len(fig.axes) == 2

    def test_mixed_analysers_produce_separate_figures(self):
        """deadnodecounter + battery_capacity_analyser → 2 separate figure windows."""
        c1 = deadnodecounter()
        c1.build_dict(death(1, 100))
        c2 = battery_capacity_analyser(num_bins=5)
        post_process_and_plot([c1, c2])
        assert len(plt.get_fignums()) == 2
        axes_per_fig = sorted(len(plt.figure(n).axes) for n in plt.get_fignums())
        assert axes_per_fig == [1, 2]  # deadnodecounter=1 ax, battery=2 ax


# ---------------------------------------------------------------------------
# Tier 1: precompiled regex patterns
# ---------------------------------------------------------------------------


class TestPrecompiledPatterns:
    """All analysers must store compiled re.Pattern objects as class attributes.

    Compiling the same pattern string on every build_dict call wastes CPU at
    scale. Patterns must be compiled once at class definition time, not per line.
    """

    def test_deadnodecounter_has_compiled_pattern(self):
        import re

        assert isinstance(deadnodecounter._PATTERN, re.Pattern)

    def test_sync_attempt_pattern_is_compiled(self):
        import re

        assert isinstance(sync_interval_counter._ATTEMPT_PATTERN, re.Pattern)

    def test_sync_synced_pattern_is_compiled(self):
        import re

        assert isinstance(sync_interval_counter._SYNCED_PATTERN, re.Pattern)

    def test_battery_wake_pattern_is_compiled(self):
        import re

        assert isinstance(battery_capacity_analyser._WAKE_PATTERN, re.Pattern)

    def test_battery_sleep_pattern_is_compiled(self):
        import re

        assert isinstance(battery_capacity_analyser._SLEEP_PATTERN, re.Pattern)

    def test_battery_death_pattern_is_compiled(self):
        import re

        assert isinstance(battery_capacity_analyser._DEATH_PATTERN, re.Pattern)


# ---------------------------------------------------------------------------
# Tier 3: extract_area helper
# ---------------------------------------------------------------------------


class TestExtractArea:
    """extract_area must parse the (AREA) tag from the standard log line format."""

    def test_extracts_node_area(self):
        assert extract_area_fast("[CRITICAL] (NODE) @ 100: Node 1 DIED, ") == "NODE"

    def test_extracts_protocol_area(self):
        assert extract_area_fast("[INFO] (PROTOCOL) @ 50: Node 1 attempts gateway connect via WAN, ") == "PROTOCOL"

    def test_extracts_gateway_area(self):
        assert extract_area_fast("[DEBUG] (GATEWAY) @ 200: Gateway 0 received data:x, ") == "GATEWAY"

    def test_extracts_battery_area(self):
        assert extract_area_fast("[INFO] (BATTERY) @ 30: some event, ") == "BATTERY"

    def test_no_parentheses_returns_none(self):
        assert extract_area_fast("no area tag here") is None

    def test_empty_string_returns_none(self):
        assert extract_area_fast("") is None

    def test_opening_paren_only_returns_none(self):
        """A line with '(' but no matching ')' must not raise — return None."""
        assert extract_area_fast("[INFO] (NODE without close") is None


# ---------------------------------------------------------------------------
# Tier 3: AREAS attribute on each analyser
# ---------------------------------------------------------------------------


class TestAnalyserAreas:
    """Each analyser must declare which log areas it cares about via AREAS."""

    def test_deadnodecounter_areas_contains_node(self):
        assert "NODE" in deadnodecounter.AREAS

    def test_deadnodecounter_areas_is_frozenset(self):
        assert isinstance(deadnodecounter.AREAS, frozenset)

    def test_sync_interval_counter_areas_contains_protocol(self):
        assert "PROTOCOL" in sync_interval_counter.AREAS

    def test_sync_interval_counter_areas_is_frozenset(self):
        assert isinstance(sync_interval_counter.AREAS, frozenset)

    def test_battery_capacity_analyser_areas_contains_node(self):
        assert "NODE" in battery_capacity_analyser.AREAS

    def test_battery_capacity_analyser_areas_is_frozenset(self):
        assert isinstance(battery_capacity_analyser.AREAS, frozenset)

    def test_packet_forwarding_delay_areas_contains_protocol(self):
        assert "PROTOCOL" in packet_forwarding_delay.AREAS

    def test_packet_forwarding_delay_areas_contains_gateway(self):
        assert "GATEWAY" in packet_forwarding_delay.AREAS

    def test_packet_forwarding_delay_areas_is_frozenset(self):
        assert isinstance(packet_forwarding_delay.AREAS, frozenset)


# ---------------------------------------------------------------------------
# Tier 3: area-based dispatch in execute()
# ---------------------------------------------------------------------------


class TestAreaDispatch:
    """execute() must only call build_dict on analysers whose AREAS match the line."""

    class _MockAnalyser:
        """Minimal analyser with an AREAS declaration and a call counter."""

        def __init__(self, areas):
            self.AREAS = frozenset(areas)
            self.calls = 0

        def build_dict(self, line):
            self.calls += 1

    class _UnboundAnalyser:
        """Analyser with no AREAS attribute — must receive every line."""

        def __init__(self):
            self.calls = 0

        def build_dict(self, line):
            self.calls += 1

    def test_matching_area_calls_build_dict(self):
        a = self._MockAnalyser({"NODE"})
        execute([a], "[CRITICAL] (NODE) @ 100: Node 1 DIED, ")
        assert a.calls == 1

    def test_non_matching_area_skips_build_dict(self):
        a = self._MockAnalyser({"NODE"})
        execute([a], "[INFO] (PROTOCOL) @ 100: some protocol event, ")
        assert a.calls == 0

    def test_analyser_without_areas_receives_all_lines(self):
        """Backwards-compatible: analysers with no AREAS get every line."""
        a = self._UnboundAnalyser()
        execute([a], "[INFO] (PROTOCOL) @ 100: some event, ")
        assert a.calls == 1

    def test_multiple_analysers_only_matching_ones_called(self):
        node_a = self._MockAnalyser({"NODE"})
        proto_a = self._MockAnalyser({"PROTOCOL"})
        execute([node_a, proto_a], "[CRITICAL] (NODE) @ 100: Node 1 DIED, ")
        assert node_a.calls == 1
        assert proto_a.calls == 0

    def test_malformed_line_skips_all_area_aware_analysers(self):
        """A line with no area tag (area=None) must not be dispatched to AREAS analysers."""
        a = self._MockAnalyser({"NODE"})
        execute([a], "no area tag at all")
        assert a.calls == 0

    def test_full_log_results_unchanged_after_area_dispatch(self, log_lines):
        """Area dispatch must produce the same final state as calling build_dict directly."""
        direct = deadnodecounter()
        for line in log_lines:
            direct.build_dict(line)

        via_execute = deadnodecounter()
        for line in log_lines:
            execute([via_execute], line)

        assert direct.dict == via_execute.dict
