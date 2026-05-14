from unittest.mock import Mock

import pytest

from custom_types import LoRaD2DFrame, LoRaD2DFrameType, MegaSync
from loraWanFrameHelper import make_uplink
from node.event_local_queue import LocalEventQueue
from node.protocols.V02.V02 import V02
from payload_types import PayloadHopCntFull


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for V02."""
    return {
        "local_event_queue": Mock(spec=LocalEventQueue),
        "log": Mock(),
    }


@pytest.fixture
def v02_instance(mock_dependencies):
    """Create V02 instance with mocks."""
    mock_dependencies["local_event_queue"].get_current_events_by_type.return_value = []
    v02 = V02(node_id=1, local_event_queue=mock_dependencies["local_event_queue"], second_to_global_tick=0.001, log=mock_dependencies["log"])
    return v02


class TestD2DFrameDeduplication:
    """Test D2D frame deduplication based on CRC."""

    def test_no_duplicates_all_frames_kept(self, v02_instance):
        """When no duplicates exist, all frames should be kept."""
        # Create 3 unique frames
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(source_node_id=1, destination_node_id={3}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame2.crc_calc()

        frame3 = LoRaD2DFrame(source_node_id=2, destination_node_id={1}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=3, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame3.crc_calc()

        v02_instance.d2d._rx_buffer = [frame1, frame2, frame3]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 3
        assert v02_instance.d2d._rx_buffer[0].crc == frame1.crc
        assert v02_instance.d2d._rx_buffer[1].crc == frame2.crc
        assert v02_instance.d2d._rx_buffer[2].crc == frame3.crc

    def test_duplicate_d2d_rx_removed(self, v02_instance):
        """Duplicate D2D RX frames should be removed."""
        frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame.crc_calc()

        duplicate = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        duplicate.crc_calc()

        assert frame.crc == duplicate.crc

        v02_instance.d2d._rx_buffer = [frame, duplicate]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 1
        assert v02_instance.d2d._rx_buffer[0].crc == frame.crc

    def test_duplicate_across_rx_tx_keeps_tx_removes_rx(self, v02_instance):
        """Duplicate across RX and TX: TX kept, RX removed."""
        frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=10, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame.crc_calc()

        duplicate = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=10, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        duplicate.crc_calc()

        v02_instance.d2d._rx_buffer = [frame]
        v02_instance.d2d._tx_buffer = [duplicate]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 0  # RX duplicate removed
        assert len(v02_instance.d2d._tx_buffer) == 1  # TX kept

    def test_first_occurrence_kept_second_removed(self, v02_instance):
        """When duplicate exists, first occurrence should be kept."""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=7, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame1.crc_calc()
        original_crc = frame1.crc

        frame2 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=7, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame2.crc_calc()

        v02_instance.d2d._rx_buffer = [frame1, frame2]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 1
        assert v02_instance.d2d._rx_buffer[0].crc == original_crc


class TestWANFrameDeduplication:
    """Test WAN frame deduplication based on MIC."""

    def test_duplicate_wan_removed(self, v02_instance):
        """Duplicate WAN frames should be removed based on MIC."""
        frame1 = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        frame1.mic = b"\x12\x34\x56\x78"

        frame2 = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        frame2.mic = b"\x12\x34\x56\x78"  # Same MIC

        v02_instance.wan._rx_buffer = [frame1, frame2]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.wan._rx_buffer) == 1

    def test_different_mic_kept(self, v02_instance):
        """Frames with different MIC should both be kept."""
        frame1 = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        frame1.mic = b"\x12\x34\x56\x78"

        frame2 = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        frame2.mic = b"\xaa\xbb\xcc\xdd"  # Different MIC

        v02_instance.wan._rx_buffer = [frame1, frame2]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.wan._rx_buffer) == 2


class TestMixedBufferDeduplication:
    """Test deduplication across mixed D2D and WAN buffers."""

    def test_duplicates_across_all_four_buffers(self, v02_instance):
        """Test dedup works across d2d rx/tx and wan rx/tx. TX buffers kept."""
        # Create D2D frame with CRC in RX
        d2d_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d_frame.crc_calc()

        # Create WAN frame in RX
        wan_frame = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        wan_frame.mic = b"\xff\xff\xff\xff"

        # Create duplicate D2D frame in TX
        d2d_dup = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d_dup.crc_calc()

        # Create duplicate WAN frame in TX
        wan_dup = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        wan_dup.mic = b"\xff\xff\xff\xff"

        # Distribute across buffers
        v02_instance.d2d._rx_buffer = [d2d_frame]
        v02_instance.d2d._tx_buffer = [d2d_dup]
        v02_instance.wan._rx_buffer = [wan_frame]
        v02_instance.wan._tx_buffer = [wan_dup]

        v02_instance.dll._remove_duplicates_from_buffers()

        # TX buffers kept, RX duplicates removed
        assert len(v02_instance.d2d._rx_buffer) == 0  # RX duplicate removed
        assert len(v02_instance.d2d._tx_buffer) == 1  # TX kept
        assert len(v02_instance.wan._rx_buffer) == 0  # RX duplicate removed
        assert len(v02_instance.wan._tx_buffer) == 1  # TX kept

    def test_mixed_with_some_duplicates(self, v02_instance):
        """Mixed scenario: some duplicates, some unique."""
        # Unique D2D
        d2d1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d1.crc_calc()

        # Duplicate D2D
        d2d2 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d2.crc_calc()

        # Unique WAN
        wan1 = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        wan1.mic = b"\x11\x11\x11\x11"

        # Unique WAN (different)
        wan2 = make_uplink(dev_addr=2, frame_count=0, payload=MegaSync(), confirmed=False)
        wan2.mic = b"\x22\x22\x22\x22"

        v02_instance.d2d._rx_buffer = [d2d1, d2d2]
        v02_instance.wan._rx_buffer = [wan1, wan2]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 1  # d2d2 removed as duplicate
        assert len(v02_instance.wan._rx_buffer) == 2  # Both unique


class TestCRCCalculationConsistency:
    """Test that CRC is calculated consistently."""

    def test_identical_frames_have_same_crc(self):
        """Identical frames should produce identical CRC."""
        frame1 = LoRaD2DFrame(source_node_id=5, destination_node_id={10, 20}, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=PayloadHopCntFull(cnt=99, slot_period_counter=5, use_slot=1, time_offset_from_period_start=100))
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(source_node_id=5, destination_node_id={10, 20}, type=LoRaD2DFrameType.CHANGE_HOP_COUNT, payload=PayloadHopCntFull(cnt=99, slot_period_counter=5, use_slot=1, time_offset_from_period_start=100))
        frame2.crc_calc()

        assert frame1.crc == frame2.crc

    def test_different_frames_have_different_crc(self):
        """Different frames should produce different CRC."""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(
            source_node_id=2,  # Different source
            destination_node_id={2},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0),
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc

    def test_crc_type_handling_int_vs_bytes(self, v02_instance):
        """Test that CRC comparison works with both int and bytes."""
        # Create frame with CRC (int)
        frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame.crc_calc()

        # Create duplicate
        dup = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        dup.crc_calc()

        v02_instance.d2d._rx_buffer = [frame, dup]

        # Verify both are in buffer
        assert len(v02_instance.d2d._rx_buffer) == 2

        v02_instance.dll._remove_duplicates_from_buffers()

        # After dedup, one should remain
        assert len(v02_instance.d2d._rx_buffer) == 1


class TestTXBufferPreservation:
    """Test that TX buffers are never modified by deduplication."""

    def test_tx_buffer_never_modified(self, v02_instance):
        """TX buffer should remain untouched after deduplication."""
        tx_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        tx_frame.crc_calc()
        original_crc = tx_frame.crc

        v02_instance.d2d._tx_buffer = [tx_frame]
        initial_len = len(v02_instance.d2d._tx_buffer)

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == initial_len
        assert v02_instance.d2d._tx_buffer[0].crc == original_crc

    def test_multiple_tx_frames_preserved(self, v02_instance):
        """Multiple TX frames should be fully preserved."""
        frames = []
        for i in range(5):
            frame = LoRaD2DFrame(source_node_id=1, destination_node_id={i + 2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=i, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
            frame.crc_calc()
            frames.append(frame)

        v02_instance.d2d._tx_buffer = frames.copy()
        original_crcs = [f.crc for f in frames]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 5
        for i, frame in enumerate(v02_instance.d2d._tx_buffer):
            assert frame.crc == original_crcs[i]

    def test_tx_and_rx_separate_buffers_not_mixed(self, v02_instance):
        """Verify TX and RX buffers are kept separate after dedup."""
        tx_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        tx_frame.crc_calc()

        rx_frame = LoRaD2DFrame(source_node_id=2, destination_node_id={1}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        rx_frame.crc_calc()

        v02_instance.d2d._tx_buffer = [tx_frame]
        v02_instance.d2d._rx_buffer = [rx_frame]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 1
        assert len(v02_instance.d2d._rx_buffer) == 1
        assert v02_instance.d2d._tx_buffer[0].crc == tx_frame.crc
        assert v02_instance.d2d._rx_buffer[0].crc == rx_frame.crc


class TestRXDuplicateRemovalFromTX:
    """Test RX frame removal when duplicate exists in TX."""

    def test_single_rx_duplicate_of_tx_removed(self, v02_instance):
        """Single RX frame matching TX should be removed."""
        frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame.crc_calc()

        dup_rx = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        dup_rx.crc_calc()

        v02_instance.d2d._tx_buffer = [frame]
        v02_instance.d2d._rx_buffer = [dup_rx]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 1
        assert len(v02_instance.d2d._rx_buffer) == 0

    def test_multiple_rx_duplicates_of_tx_all_removed(self, v02_instance):
        """All RX duplicates of TX should be removed."""
        tx_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        tx_frame.crc_calc()

        rx_dups = []
        for _ in range(3):
            dup = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
            dup.crc_calc()
            rx_dups.append(dup)

        v02_instance.d2d._tx_buffer = [tx_frame]
        v02_instance.d2d._rx_buffer = rx_dups

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 1
        assert len(v02_instance.d2d._rx_buffer) == 0

    def test_rx_unique_frames_preserved_when_tx_has_duplicates(self, v02_instance):
        """Unique RX frames should be kept even when TX has duplicates."""
        tx_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        tx_frame.crc_calc()

        unique_rx = LoRaD2DFrame(source_node_id=2, destination_node_id={1}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        unique_rx.crc_calc()

        dup_rx = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        dup_rx.crc_calc()

        v02_instance.d2d._tx_buffer = [tx_frame]
        v02_instance.d2d._rx_buffer = [dup_rx, unique_rx]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 1
        assert len(v02_instance.d2d._rx_buffer) == 1
        assert v02_instance.d2d._rx_buffer[0].crc == unique_rx.crc

    def test_rx_order_preserved_after_removing_middle_duplicate(self, v02_instance):
        """RX buffer order should be preserved when removing duplicates from middle."""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame1.crc_calc()

        frame2_in_tx = LoRaD2DFrame(source_node_id=2, destination_node_id={3}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame2_in_tx.crc_calc()

        frame3 = LoRaD2DFrame(source_node_id=3, destination_node_id={1}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=3, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame3.crc_calc()

        # Create RX frame with same CRC as frame2_in_tx
        frame2_rx_dup = LoRaD2DFrame(source_node_id=2, destination_node_id={3}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame2_rx_dup.crc_calc()

        v02_instance.d2d._tx_buffer = [frame2_in_tx]
        v02_instance.d2d._rx_buffer = [frame1, frame2_rx_dup, frame3]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 2
        assert v02_instance.d2d._rx_buffer[0].crc == frame1.crc
        assert v02_instance.d2d._rx_buffer[1].crc == frame3.crc


class TestRXInternalDuplicateRemoval:
    """Test removal of duplicate frames within RX buffer itself."""

    def test_duplicate_within_rx_first_kept(self, v02_instance):
        """First occurrence of duplicate in RX should be kept."""
        frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        frame.crc_calc()
        original_crc = frame.crc

        dup1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        dup1.crc_calc()

        dup2 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        dup2.crc_calc()

        v02_instance.d2d._rx_buffer = [frame, dup1, dup2]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 1
        assert v02_instance.d2d._rx_buffer[0].crc == original_crc

    def test_multiple_sets_of_duplicates_in_rx(self, v02_instance):
        """Multiple sets of duplicates should all be deduped keeping first."""
        set1_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        set1_frame.crc_calc()
        set1_crc = set1_frame.crc

        set1_dup = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        set1_dup.crc_calc()

        set2_frame = LoRaD2DFrame(source_node_id=2, destination_node_id={3}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        set2_frame.crc_calc()
        set2_crc = set2_frame.crc

        set2_dup = LoRaD2DFrame(source_node_id=2, destination_node_id={3}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        set2_dup.crc_calc()

        v02_instance.d2d._rx_buffer = [set1_frame, set2_frame, set1_dup, set2_dup]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._rx_buffer) == 2
        assert v02_instance.d2d._rx_buffer[0].crc == set1_crc
        assert v02_instance.d2d._rx_buffer[1].crc == set2_crc


class TestCrossLayerDuplication:
    """Test deduplication across D2D and WAN layers."""

    def test_wan_tx_removes_d2d_rx_duplicate(self, v02_instance):
        """WAN TX should remove D2D RX duplicates."""
        wan_frame = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        wan_frame.mic = b"\xaa\xbb\xcc\xdd"

        # Create D2D frame with matching checksum
        d2d_dup = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d_dup.crc = int.from_bytes(b"\xaa\xbb\xcc\xdd", "big")

        v02_instance.wan._tx_buffer = [wan_frame]
        v02_instance.d2d._rx_buffer = [d2d_dup]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.wan._tx_buffer) == 1
        assert len(v02_instance.d2d._rx_buffer) == 0

    def test_d2d_tx_removes_wan_rx_duplicate(self, v02_instance):
        """D2D TX should remove WAN RX duplicates."""
        d2d_frame = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0))
        d2d_frame.crc_calc()

        # Create WAN frame with same checksum
        wan_dup = make_uplink(dev_addr=1, frame_count=0, payload=MegaSync(), confirmed=False)
        wan_dup.mic = d2d_frame.crc if isinstance(d2d_frame.crc, bytes) else d2d_frame.crc.to_bytes(4, "big")

        v02_instance.d2d._tx_buffer = [d2d_frame]
        v02_instance.wan._rx_buffer = [wan_dup]

        v02_instance.dll._remove_duplicates_from_buffers()

        assert len(v02_instance.d2d._tx_buffer) == 1
        assert len(v02_instance.wan._rx_buffer) == 0
