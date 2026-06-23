"""
Tests for intersection-driven TDMA slot-collision resolution.

When two downstream children of an intersection node share a TX slot, both
transmissions overlap and are dropped by collision detection. The intersection
must (1) notice a collision happened in that RX slot and (2) move the colliding
children it knows about to free slots via CHANGE_HOP_COUNT.

These tests cover the three pieces of that path:
  - LoRaD2D collision detection raises the blind per-tick flag / event.
  - D2DDLL._resolve_slot_collision reassigns the right child.
  - D2DDLL.tick triggers resolution when a TRANCEIVER_COLLISION event is present.
"""

import os
import tempfile
from unittest.mock import Mock

from custom_types import (
    EventNet,
    EventNetTypes,
    LocalClockInfo,
    LocalEventTypes,
    LoRaD2DFrame,
    LoRaD2DFrameType,
    MediumTypes,
    TransceiverState,
)
from logger.simple_logger import SimpleLogger
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.D2DDLL import D2DDLL, D2DNeighborInfo, DiscoverStates
from node.transceiver.LoRaD2D import LoRaD2D
from payload_types import PayloadHopCntMid


def create_test_logger():
    temp_dir = tempfile.gettempdir()
    log_path = os.path.join(temp_dir, "test_slot_collision.log")
    return SimpleLogger(log_path, buffer_size=100)


def make_data(length: int):
    data = Mock()
    data.length = length
    return data


# --------------------------------------------------------------------------- #
# 1. LoRaD2D detection: a dropped overlap raises the blind collision flag
# --------------------------------------------------------------------------- #
class TestLoRaD2DCollisionFlag:
    def _transceiver(self):
        return LoRaD2D(node_id=1, medium_service=Mock(), local_event_queue=LocalEventQueue(), second_to_global_tick=1.0, log=create_test_logger())

    def test_overlap_sets_collision_flag(self):
        t = self._transceiver()
        # two transmissions from different nodes overlapping in time -> both dropped
        t._receive_queue = [
            EventNet(node_id=2, time_start=100, time_end=150, data=make_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D),
            EventNet(node_id=3, time_start=120, time_end=160, data=make_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D),
        ]
        t._current_reception_start_global_tick = 50

        result = t._get_successful_receptions(200)

        assert result == []  # both lost to collision
        assert t._had_collision() is True  # blind flag raised
        assert t._had_collision() is False  # flag cleared after read

    def test_clean_reception_no_collision(self):
        t = self._transceiver()
        t._receive_queue = [
            EventNet(node_id=2, time_start=100, time_end=150, data=make_data(10), type=EventNetTypes.TRANSMIT, type_medium=MediumTypes.LORA_D2D),
        ]
        t._current_reception_start_global_tick = 50

        result = t._get_successful_receptions(200)

        assert len(result) == 1
        assert t._had_collision() is False


# --------------------------------------------------------------------------- #
# 2. D2DDLL._resolve_slot_collision: reassign the children we know about
# --------------------------------------------------------------------------- #
class TestResolveSlotCollision:
    def _intersection(self):
        """A discovered authority node at hopcount 1, own TX slot 1."""
        d2d = D2DDLL(node_id=10, local_event_queue=LocalEventQueue(), log=create_test_logger())
        d2d.hopcount_to_gateway = 1
        d2d.discovery_state = DiscoverStates.DISCOVERED
        d2d._own_tx_slot = 1
        assert d2d.link_established
        return d2d

    def _add_child(self, d2d, nid, slot, rssi):
        d2d._known_neighbors.append(D2DNeighborInfo(neighbor_id=nid, hopcount_to_gateway=2, last_seen=1000, last_rssi=rssi, in_slot=slot, first_tx_start_time_in_period=0))
        d2d._observed_slots[nid] = slot

    def test_two_children_same_slot_one_moved(self):
        d2d = self._intersection()
        contested = 5
        self._add_child(d2d, nid=2, slot=contested, rssi=-40)  # best RSSI -> kept
        self._add_child(d2d, nid=3, slot=contested, rssi=-50)  # weaker -> moved

        d2d._resolve_slot_collision(current_global_tick=0, contested_slot=contested, current_slot_period_counter=0)

        # exactly one child remains in the contested slot
        in_contested = [nid for nid, s in d2d._observed_slots.items() if s == contested]
        assert in_contested == [2]
        # the moved child got a distinct, valid slot
        moved_slot = d2d._observed_slots[3]
        assert moved_slot != contested
        assert 1 <= moved_slot < d2d._slot_count
        assert moved_slot != d2d._own_tx_slot

        # a CHANGE_HOP_COUNT frame addressed to the moved child carries the new slot
        frames = [f for f in d2d._tx_buffer if f.type == LoRaD2DFrameType.CHANGE_HOP_COUNT and 3 in f.destination_node_id]
        assert len(frames) == 1
        payload = frames[0].payload
        assert isinstance(payload, PayloadHopCntMid)
        assert payload.use_slot == moved_slot

    def test_equal_rssi_keeps_lowest_node_id(self):
        # on an RSSI tie the lowest node_id is kept; the result must not depend on
        # the order children were discovered in.
        contested = 5
        for order in ([(8, -45), (3, -45)], [(3, -45), (8, -45)]):
            d2d = self._intersection()
            for nid, rssi in order:
                self._add_child(d2d, nid=nid, slot=contested, rssi=rssi)

            d2d._resolve_slot_collision(current_global_tick=0, contested_slot=contested, current_slot_period_counter=0)

            in_contested = [nid for nid, s in d2d._observed_slots.items() if s == contested]
            assert in_contested == [3], f"insertion order {order} should still keep node 3"
            assert d2d._observed_slots[8] != contested

    def test_single_known_child_is_moved(self):
        # collision in the slot but we only know one child there -> move it anyway,
        # because the collision proves an (unknown) second transmitter shares the slot.
        d2d = self._intersection()
        contested = 7
        self._add_child(d2d, nid=4, slot=contested, rssi=-45)

        d2d._resolve_slot_collision(current_global_tick=0, contested_slot=contested, current_slot_period_counter=0)

        assert d2d._observed_slots[4] != contested
        frames = [f for f in d2d._tx_buffer if f.type == LoRaD2DFrameType.CHANGE_HOP_COUNT and 4 in f.destination_node_id]
        assert len(frames) == 1

    def test_no_known_child_no_action(self):
        # collision not attributable to any child we own -> do not act blindly
        d2d = self._intersection()
        self._add_child(d2d, nid=5, slot=3, rssi=-45)  # child lives in a different slot

        d2d._resolve_slot_collision(current_global_tick=0, contested_slot=9, current_slot_period_counter=0)

        assert d2d._observed_slots[5] == 3  # untouched
        assert d2d._tx_buffer == []  # no reassignment

    def test_foreign_two_hop_node_not_reassigned(self):
        # a node two hops further (not our direct child) shares the slot. We must NOT move it
        # (it obeys its own parent, so reassigning it loops forever); only our direct child moves.
        d2d = self._intersection()  # hopcount 1
        contested = 5
        self._add_child(d2d, nid=2, slot=contested, rssi=-40)  # direct child (hop 2)
        # foreign node two hops away (hop 3)
        d2d._known_neighbors.append(D2DNeighborInfo(neighbor_id=9, hopcount_to_gateway=3, last_seen=1000, last_rssi=-45, in_slot=contested, first_tx_start_time_in_period=0))
        d2d._observed_slots[9] = contested

        d2d._resolve_slot_collision(current_global_tick=0, contested_slot=contested, current_slot_period_counter=0)

        assert d2d._observed_slots[9] == contested  # foreign 2-hop node untouched
        # only the direct child may be moved (single direct child -> it moves)
        assert d2d._observed_slots[2] != contested
        assert not any(9 in f.destination_node_id for f in d2d._tx_buffer)

    def test_upstream_node_not_reassigned(self):
        # a node closer to the gateway (lower hopcount) is not our child -> never moved
        d2d = self._intersection()
        contested = 5
        d2d._known_neighbors.append(D2DNeighborInfo(neighbor_id=6, hopcount_to_gateway=0, last_seen=1000, last_rssi=-40, in_slot=contested, first_tx_start_time_in_period=0))
        d2d._observed_slots[6] = contested

        d2d._resolve_slot_collision(current_global_tick=0, contested_slot=contested, current_slot_period_counter=0)

        assert d2d._observed_slots[6] == contested  # upstream node untouched
        assert d2d._tx_buffer == []


# --------------------------------------------------------------------------- #
# 3. D2DDLL.tick: a TRANCEIVER_COLLISION event triggers resolution
# --------------------------------------------------------------------------- #
class TestTickTriggersResolution:
    def test_collision_event_drives_reassignment(self):
        leq = LocalEventQueue()
        d2d = D2DDLL(node_id=10, local_event_queue=leq, log=create_test_logger())
        d2d.hopcount_to_gateway = 1
        d2d.discovery_state = DiscoverStates.DISCOVERED
        d2d._own_tx_slot = 1
        d2d._current_slot = 5  # currently receiving in slot 5

        for nid, rssi in ((2, -40), (3, -50)):
            d2d._known_neighbors.append(D2DNeighborInfo(neighbor_id=nid, hopcount_to_gateway=2, last_seen=1000, last_rssi=rssi, in_slot=5, first_tx_start_time_in_period=0))
            d2d._observed_slots[nid] = 5

        # current-tick events tick() reads: transceiver status + the blind collision signal
        leq.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_STATUS, {MediumTypes.LORA_D2D: TransceiverState.RECEIVING})
        leq.add_event_to_current_tick(LocalEventTypes.TRANCEIVER_COLLISION, None, sub_type=MediumTypes.LORA_D2D)

        # timer_1_remaining != 0 keeps _advance_slot from changing the current slot
        clock = LocalClockInfo(current_local_time=1000, timer_1_remaining=100, timer_2_remaining=None)
        d2d.tick(current_global_tick=0, current_local_clock_info=clock, slot_period_counter=0)

        in_contested = [nid for nid, s in d2d._observed_slots.items() if s == 5]
        assert in_contested == [2]  # weaker child moved off slot 5
        assert any(f.type == LoRaD2DFrameType.CHANGE_HOP_COUNT and 3 in f.destination_node_id for f in d2d._tx_buffer)


# --------------------------------------------------------------------------- #
# 4. D2DDLL: a child adopts a slot only from its elected parent
# --------------------------------------------------------------------------- #
class TestParentLockedSlot:
    def _child(self):
        """A DISCOVERED child at hopcount 3, currently in slot 8."""
        d2d = D2DDLL(node_id=6, local_event_queue=LocalEventQueue(), log=create_test_logger())
        d2d.hopcount_to_gateway = 3
        d2d.discovery_state = DiscoverStates.DISCOVERED
        d2d._own_tx_slot = 8
        return d2d

    def _add_upstream(self, d2d, nid, hop, rssi):
        d2d._known_neighbors.append(D2DNeighborInfo(neighbor_id=nid, hopcount_to_gateway=hop, last_seen=1000, last_rssi=rssi, in_slot=0, first_tx_start_time_in_period=0))

    def _change_hop_frame(self, src, dst, slot, cnt=3):
        f = LoRaD2DFrame(source_node_id=src, destination_node_id={dst}, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=PayloadHopCntMid(cnt=cnt, use_slot=slot, slot_period_counter=0))
        f.crc_calc()
        return f

    def test_slot_from_non_parent_ignored(self):
        d2d = self._child()
        self._add_upstream(d2d, nid=7, hop=2, rssi=-40)  # parent (best RSSI)
        self._add_upstream(d2d, nid=8, hop=2, rssi=-50)  # non-parent
        assert d2d._elected_parent_id() == 7

        d2d._process_change_hop_count(self._change_hop_frame(src=8, dst=6, slot=15), current_global_tick=0, current_slot_period_counter=0)
        assert d2d._own_tx_slot == 8  # non-parent command ignored

    def test_slot_from_parent_applied(self):
        d2d = self._child()
        self._add_upstream(d2d, nid=7, hop=2, rssi=-40)
        self._add_upstream(d2d, nid=8, hop=2, rssi=-50)

        d2d._process_change_hop_count(self._change_hop_frame(src=7, dst=6, slot=15), current_global_tick=0, current_slot_period_counter=0)
        assert d2d._own_tx_slot == 15  # parent command applied

    def test_hopcount_beats_rssi_for_parent(self):
        d2d = self._child()
        self._add_upstream(d2d, nid=7, hop=1, rssi=-60)  # closer to GW -> parent despite worse RSSI
        self._add_upstream(d2d, nid=8, hop=2, rssi=-30)
        assert d2d._elected_parent_id() == 7

        d2d._process_change_hop_count(self._change_hop_frame(src=8, dst=6, slot=15, cnt=3), current_global_tick=0, current_slot_period_counter=0)
        assert d2d._own_tx_slot == 8  # higher-hop neighbor is not the parent

    def test_parent_reelection_after_parent_lost(self):
        d2d = self._child()
        self._add_upstream(d2d, nid=7, hop=2, rssi=-40)
        self._add_upstream(d2d, nid=8, hop=2, rssi=-50)
        assert d2d._elected_parent_id() == 7

        # parent 7 drops out -> 8 becomes the parent and its command is now honored
        d2d._known_neighbors = [n for n in d2d._known_neighbors if n.neighbor_id != 7]
        assert d2d._elected_parent_id() == 8

        d2d._process_change_hop_count(self._change_hop_frame(src=8, dst=6, slot=12), current_global_tick=0, current_slot_period_counter=0)
        assert d2d._own_tx_slot == 12

    def test_hopcount_always_accepted_even_from_non_parent(self):
        d2d = self._child()
        self._add_upstream(d2d, nid=7, hop=2, rssi=-40)
        self._add_upstream(d2d, nid=8, hop=2, rssi=-50)

        # non-parent slot ignored, but the routing hopcount update still applies
        d2d._process_change_hop_count(self._change_hop_frame(src=8, dst=6, slot=15, cnt=4), current_global_tick=0, current_slot_period_counter=0)
        assert d2d._own_tx_slot == 8
        assert d2d.hopcount_to_gateway == 4
