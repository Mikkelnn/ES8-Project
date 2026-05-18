import matplotlib
matplotlib.use('Agg')

import pytest
from uuid import UUID
from main_string import (
    deadnodecounter,
    sync_interval_counter,
    battery_capacity_analyser,
    packet_forwarding_delay,
)

# ---------------------------------------------------------------------------
# Helpers — mirror the exact log format the simulator emits
# ---------------------------------------------------------------------------

def death(node_id: int, tick: int) -> str:
    """Produce a valid death log line (logger always appends ', ')."""
    return f'[CRITICAL] (NODE) @ {tick}: Node {node_id} DIED, '


# ---------------------------------------------------------------------------
# deadnodecounter.build_dict — string-based parsing
# ---------------------------------------------------------------------------

class TestBuildDict:
    def test_valid_death_line_adds_entry(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.dict == {1: 1}

    def test_non_critical_severity_ignored(self):
        c = deadnodecounter()
        c.build_dict('[DEBUG] (NODE) @ 100: Node 1 DIED, ')
        assert c.dict == {}

    def test_info_severity_ignored(self):
        c = deadnodecounter()
        c.build_dict('[INFO] (NODE) @ 100: Node 1 DIED, ')
        assert c.dict == {}

    def test_warning_severity_ignored(self):
        c = deadnodecounter()
        c.build_dict('[WARNING] (NODE) @ 100: Node 1 DIED, ')
        assert c.dict == {}

    def test_critical_wrong_area_ignored(self):
        # TRANCEIVER area — not a NODE death
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (TRANCEIVER) @ 100: Node 1 DIED, ')
        assert c.dict == {}

    def test_critical_node_without_died_keyword_ignored(self):
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (NODE) @ 100: Node 1 is sleeping, ')
        assert c.dict == {}

    def test_same_node_dying_multiple_times_accumulates(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(1, 200))
        c.build_dict(death(1, 300))
        assert c.dict == {1: 3}

    def test_different_nodes_tracked_separately(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 150))
        c.build_dict(death(1, 200))
        assert c.dict == {1: 2, 2: 1}

    def test_large_node_id_parsed_correctly(self):
        c = deadnodecounter()
        c.build_dict(death(99999, 500))
        assert c.dict == {99999: 1}

    def test_trailing_comma_space_does_not_break_parse(self):
        # Logger always appends ', {data}' — verify trailing content is ignored
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (NODE) @ 100: Node 5 DIED, some_extra_data, ')
        assert c.dict == {5: 1}

    def test_line_with_no_node_marker_ignored(self):
        # Malformed line missing ': Node '
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (NODE) @ 100: something unrelated DIED, ')
        assert c.dict == {}

    def test_non_digit_node_id_ignored(self):
        c = deadnodecounter()
        c.build_dict('[CRITICAL] (NODE) @ 100: Node abc DIED, ')
        assert c.dict == {}

    def test_returns_none(self):
        c = deadnodecounter()
        assert c.build_dict(death(1, 100)) is None


# ---------------------------------------------------------------------------
# deadnodecounter.deathcounter
# ---------------------------------------------------------------------------

class TestDeathcounter:
    def test_empty_returns_empty_lists(self):
        c = deadnodecounter()
        node_ids, counts = c.deathcounter()
        assert node_ids == [] and counts == []

    def test_single_node_single_death(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        node_ids, counts = c.deathcounter()
        assert node_ids == [1] and counts == [1]

    def test_multiple_nodes_correct_pairs(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 150))
        c.build_dict(death(1, 200))
        node_ids, counts = c.deathcounter()
        assert dict(zip(node_ids, counts)) == {1: 2, 2: 1}

    def test_repeated_calls_do_not_double_count(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.deathcounter()
        _, counts = c.deathcounter()
        assert counts == [1]


# ---------------------------------------------------------------------------
# deadnodecounter.death_distribution
# ---------------------------------------------------------------------------

class TestDeathDistribution:
    def test_empty_returns_empty_dict(self):
        assert deadnodecounter().death_distribution() == {}

    def test_single_node_single_death(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        assert c.death_distribution() == {1: 1}

    def test_single_node_multiple_deaths(self):
        # Node 3 died 3 times → {3: 1} (one node with death_count=3)
        c = deadnodecounter()
        for tick in [100, 200, 300]:
            c.build_dict(death(3, tick))
        assert c.death_distribution() == {3: 1}

    def test_two_nodes_same_death_count_merged(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        assert c.death_distribution() == {1: 2}

    def test_two_nodes_different_death_counts(self):
        c = deadnodecounter()
        c.build_dict(death(1, 100))
        c.build_dict(death(2, 200))
        c.build_dict(death(2, 300))
        assert c.death_distribution() == {1: 1, 2: 1}


# ---------------------------------------------------------------------------
# deadnodecounter.merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_merge_adds_counts_for_same_node(self):
        a = deadnodecounter()
        a.build_dict(death(1, 100))
        b = deadnodecounter()
        b.build_dict(death(1, 200))
        a.merge(b)
        assert a.dict == {1: 2}

    def test_merge_adds_new_node_from_other(self):
        a = deadnodecounter()
        a.build_dict(death(1, 100))
        b = deadnodecounter()
        b.build_dict(death(2, 200))
        a.merge(b)
        assert a.dict == {1: 1, 2: 1}

    def test_merge_empty_other_leaves_self_unchanged(self):
        a = deadnodecounter()
        a.build_dict(death(1, 100))
        a.merge(deadnodecounter())
        assert a.dict == {1: 1}


# ---------------------------------------------------------------------------
# Helpers for sync_interval_counter
# ---------------------------------------------------------------------------

def attempt(node_id: int, tick: int) -> str:
    return f'[INFO] (PROTOCOL) @ {tick}: Node {node_id} attempts gateway connect via WAN, '

def synced_wan(node_id: int, tick: int) -> str:
    return f'[INFO] (PROTOCOL) @ {tick}: Node {node_id} connected to gateway via WAN, '

def synced_discovery(node_id: int, tick: int, hop: int = 2) -> str:
    return f'[INFO] (PROTOCOL) @ {tick}: Node {node_id} discovery complete with hop count {hop}, '


# ---------------------------------------------------------------------------
# sync_interval_counter.build_dict
# ---------------------------------------------------------------------------

class TestSyncBuildDict:
    def test_attempt_line_adds_node_to_unsync_set(self):
        c = sync_interval_counter()
        c.build_dict(attempt(5, 100))
        assert 5 in c.unsync_node_set

    def test_wan_synced_line_adds_node_to_sync_set(self):
        c = sync_interval_counter()
        c.build_dict(synced_wan(5, 140))
        assert 5 in c.sync_node_set

    def test_discovery_synced_line_adds_node_to_sync_set(self):
        c = sync_interval_counter()
        c.build_dict(synced_discovery(5, 140))
        assert 5 in c.sync_node_set

    def test_non_info_line_ignored(self):
        c = sync_interval_counter()
        c.build_dict('[DEBUG] (PROTOCOL) @ 100: Node 5 attempts gateway connect via WAN, ')
        assert c.unsync_node_set == set()

    def test_wrong_area_ignored(self):
        c = sync_interval_counter()
        c.build_dict('[INFO] (GATEWAY) @ 100: Node 5 attempts gateway connect via WAN, ')
        assert c.unsync_node_set == set()

    def test_already_synced_node_not_added_to_unsync(self):
        c = sync_interval_counter()
        c.build_dict(synced_wan(5, 100))
        c.build_dict(attempt(5, 200))          # late attempt after sync
        assert 5 not in c.unsync_node_set

    def test_duplicate_attempt_not_added_twice(self):
        c = sync_interval_counter()
        c.build_dict(attempt(5, 100))
        c.build_dict(attempt(5, 150))          # second attempt same node
        assert c.unsync_node_set == {5}        # still just one entry

    def test_synced_line_updates_max_tick(self):
        c = sync_interval_counter()
        c.build_dict(synced_wan(5, 140))
        assert c.max_sync_tick == 140

    def test_later_sync_tick_overwrites_earlier(self):
        c = sync_interval_counter()
        c.build_dict(synced_wan(1, 100))
        c.build_dict(synced_wan(2, 200))
        assert c.max_sync_tick == 200

    def test_attempt_does_not_update_max_tick(self):
        c = sync_interval_counter()
        c.build_dict(attempt(5, 999))
        assert c.max_sync_tick == 0

    def test_full_flow_attempt_then_synced(self):
        c = sync_interval_counter()
        c.build_dict(attempt(3, 50))
        c.build_dict(synced_wan(3, 100))
        synced, unsynced, tick = c.sync_counter()
        assert 3 in synced
        assert 3 not in unsynced
        assert tick == 100


# ---------------------------------------------------------------------------
# Helpers for battery_capacity_analyser
# ---------------------------------------------------------------------------

def wake(node_id: int, tick: int, charge: float) -> str:
    return f'[INFO] (NODE) @ {tick}: Node {node_id} woke up, , Battery charge {charge}, '

def sleep_line(node_id: int, tick: int, charge: float) -> str:
    return f'[INFO] (NODE) @ {tick}: Node {node_id} is going to sleep, Battery charge {charge}, '

def battery_death(node_id: int, tick: int) -> str:
    return f'[CRITICAL] (NODE) @ {tick}: Node {node_id} DIED, '


# ---------------------------------------------------------------------------
# battery_capacity_analyser.build_dict
# ---------------------------------------------------------------------------

class TestBatteryBuildDict:
    def test_wake_line_recorded_in_op_range(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 6.0))
        op, _ = c.get_histograms()
        assert sum(op[1]) == 1

    def test_wake_stores_pending(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 6.0))
        assert 1 in c._pending_wake

    def test_sleep_after_wake_records_delta(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 6.0))
        c.build_dict(sleep_line(1, 200, 5.0))
        _, operating = c.get_histograms()
        assert sum(operating[1]) == 1

    def test_sleep_clears_pending_wake(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 6.0))
        c.build_dict(sleep_line(1, 200, 5.0))
        assert 1 not in c._pending_wake

    def test_sleep_with_no_prior_wake_ignored(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(sleep_line(1, 200, 5.0))
        _, operating = c.get_histograms()
        assert operating == {}

    def test_death_treated_as_sleep_with_zero_charge(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 4.0))
        c.build_dict(battery_death(1, 200))
        _, operating = c.get_histograms()
        assert sum(operating[1]) == 1

    def test_death_with_no_prior_wake_ignored(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(battery_death(1, 200))
        _, operating = c.get_histograms()
        assert operating == {}

    def test_non_info_non_critical_ignored(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict('[DEBUG] (NODE) @ 100: Node 1 woke up, , Battery charge 5.0, ')
        op, _ = c.get_histograms()
        assert op == {}

    def test_wrong_area_ignored(self):
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict('[INFO] (PROTOCOL) @ 100: Node 1 woke up, , Battery charge 5.0, ')
        op, _ = c.get_histograms()
        assert op == {}

    def test_second_death_before_new_wake_ignored(self):
        # Only the first death after a wake should record a delta
        c = battery_capacity_analyser(num_bins=5)
        c.build_dict(wake(1, 100, 6.0))
        c.build_dict(battery_death(1, 200))
        c.build_dict(battery_death(1, 300))   # no wake between — ignored
        _, operating = c.get_histograms()
        assert sum(operating[1]) == 1


# ---------------------------------------------------------------------------
# Helpers for packet_forwarding_delay
# ---------------------------------------------------------------------------

TEST_GUID = '550e8400-e29b-4d41-a716-446655440000'
TEST_UUID = UUID(TEST_GUID)

def enqueue(node_id: int, tick: int, guid: str = TEST_GUID) -> str:
    return (
        f'[INFO] (PROTOCOL) @ {tick}: Node {node_id} enqueued averaged payload: '
        f'avg_s1=1.0, avg_s2=2.0, GUID={guid}, '
    )

def gateway_recv(gw_id: int, tick: int, guid: str = TEST_GUID) -> str:
    return (
        f'[INFO] (GATEWAY) @ {tick}: Gateway {gw_id} received data: some_data, '
        f'GUID={guid}, '
    )


# ---------------------------------------------------------------------------
# packet_forwarding_delay.build_dict
# ---------------------------------------------------------------------------

class TestPacketBuildDict:
    def test_enqueue_line_stored_in_node_origin(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        assert TEST_UUID in c._node_origin

    def test_enqueue_stores_correct_tick_and_node(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        assert c._node_origin[TEST_UUID] == [1000, 12]

    def test_gateway_receipt_matches_enqueue_computes_delay(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        c.build_dict(gateway_recv(1, 1080))
        stats = c.get_stats()
        assert stats[12][0] == 80    # diff
        assert stats[12][1] == 1     # successful_count

    def test_gateway_receipt_removes_uuid_from_node_origin(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        c.build_dict(gateway_recv(1, 1080))
        assert TEST_UUID not in c._node_origin

    def test_gateway_receipt_without_enqueue_adds_to_orphans(self):
        c = packet_forwarding_delay()
        c.build_dict(gateway_recv(1, 1080))
        assert TEST_UUID in c._orphan_uuids

    def test_duplicate_enqueue_uses_first_tick(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        c.build_dict(enqueue(12, 2000))   # second enqueue same UUID — ignored
        assert c._node_origin[TEST_UUID][0] == 1000

    def test_non_info_line_ignored(self):
        c = packet_forwarding_delay()
        c.build_dict('[DEBUG] (PROTOCOL) @ 1000: Node 12 enqueued averaged payload: '
                     'avg_s1=1.0, avg_s2=2.0, GUID=' + TEST_GUID + ', ')
        assert c._node_origin == {}

    def test_finalize_marks_undelivered_as_lost(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        c.finalize()
        assert c._stats[12][2] == 1    # lost count

    def test_finalize_idempotent(self):
        c = packet_forwarding_delay()
        c.build_dict(enqueue(12, 1000))
        c.finalize()
        c.finalize()                   # second call must not double-count
        assert c._stats[12][2] == 1
