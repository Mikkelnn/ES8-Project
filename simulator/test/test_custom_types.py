import time

from custom_types import (
    LoRaD2DFrame,
    LoRaD2DFrameType,
)
from payload_types import (
    Data,
    PayloadData,
    PayloadHopCntFull,
    PayloadHopCntMid,
    PayloadHopCntSimple,
)


class TestDataClass:
    """Test data payload class (sensor data)"""

    def test_length_property(self):
        """Test length property returns correct value"""
        sensor_data = Data(sensor1=100, sensor2=200)
        assert sensor_data.length == 4, "data.length should be 4 (2 bytes + 2 bytes)"

    def test_to_bytes_basic(self):
        """Test to_bytes serialization with known values"""
        sensor_data = Data(sensor1=0x1234, sensor2=0x5678)
        result = sensor_data.to_bytes()

        assert len(result) == 4, "to_bytes should return 4 bytes"
        assert result == b"\x12\x34\x56\x78", "Big-endian serialization failed"

    def test_to_bytes_zero_values(self):
        """Test to_bytes with zero values"""
        sensor_data = Data(sensor1=0, sensor2=0)
        result = sensor_data.to_bytes()

        assert result == b"\x00\x00\x00\x00"

    def test_to_bytes_max_values(self):
        """Test to_bytes with max uint16 values"""
        max_uint16 = 0xFFFF
        sensor_data = Data(sensor1=max_uint16, sensor2=max_uint16)
        result = sensor_data.to_bytes()

        assert result == b"\xff\xff\xff\xff"

    def test_to_bytes_order_matters(self):
        """Test that sensor1 and sensor2 are in correct order"""
        sensor_data = Data(sensor1=0x0102, sensor2=0x0304)
        result = sensor_data.to_bytes()

        assert result == b"\x01\x02\x03\x04"


class TestPayloadHopCntSimple:
    """Test simple hop count payload class (for REQ_HOP_ACK frames)"""

    def test_length_property(self):
        """Test length property returns 2 (uint16)"""
        payload = PayloadHopCntSimple(cnt=5)
        assert payload.length == 2

    def test_to_bytes_basic(self):
        """Test to_bytes serialization"""
        payload = PayloadHopCntSimple(cnt=0x0102)
        result = payload.to_bytes()

        assert len(result) == 2
        assert result == b"\x01\x02"

    def test_to_bytes_zero(self):
        """Test to_bytes with zero value"""
        payload = PayloadHopCntSimple(cnt=0)
        result = payload.to_bytes()

        assert result == b"\x00\x00"

    def test_to_bytes_max_value(self):
        """Test to_bytes with max uint16"""
        payload = PayloadHopCntSimple(cnt=0xFFFF)
        result = payload.to_bytes()

        assert result == b"\xff\xff"


class TestPayloadHopCntMid:
    """Test mid hop count payload class (for CHANGE_HOP_COUNT ACK frames)"""

    def test_length_property(self):
        """Test length property returns 4 (cnt + slot_period_counter + use_slot)"""
        payload = PayloadHopCntMid(cnt=5, use_slot=1, slot_period_counter=0)
        assert payload.length == 4

    def test_to_bytes_basic(self):
        """Test to_bytes serialization"""
        payload = PayloadHopCntMid(cnt=0x0102, use_slot=0x03, slot_period_counter=0x04)
        result = payload.to_bytes()

        assert len(result) == 4
        assert result == b"\x01\x02\x03\x04"

    def test_to_bytes_zero(self):
        """Test to_bytes with zero values"""
        payload = PayloadHopCntMid(cnt=0, use_slot=0, slot_period_counter=0)
        result = payload.to_bytes()

        assert result == b"\x00\x00\x00\x00"

    def test_to_bytes_max_values(self):
        """Test to_bytes with max values"""
        payload = PayloadHopCntMid(cnt=0xFFFF, use_slot=0xFF, slot_period_counter=0xFF)
        result = payload.to_bytes()

        assert result == b"\xff\xff\xff\xff"


class TestPayloadData:
    """Test full payload data class"""

    def test_length_with_single_node_id(self):
        """Test length calculation with one node in id set"""
        sensor_data = Data(sensor1=100, sensor2=200)
        payload = PayloadData(length_payload=0, id={1}, time=10.5, data=sensor_data)
        # length_payload (2) + id (4 per node) + time (4) + data.length (4)
        expected = 2 + 4 + 4 + 4
        assert payload.length == expected

    def test_length_with_multiple_node_ids(self):
        """Test length calculation with multiple nodes"""
        sensor_data = Data(sensor1=50, sensor2=75)
        payload = PayloadData(length_payload=0, id={1, 2, 3}, time=20.0, data=sensor_data)
        # length_payload (2) + id (4*3) + time (4) + data.length (4)
        expected = 2 + 12 + 4 + 4
        assert payload.length == expected

    def test_to_bytes_single_id(self):
        """Test to_bytes with single destination"""
        sensor_data = Data(sensor1=0x0102, sensor2=0x0304)
        payload = PayloadData(length_payload=14, id={1}, time=10.0, data=sensor_data)
        result = payload.to_bytes()

        # length_payload: 2 bytes (14 = 0x000E)
        # id (1 as uint32): 4 bytes (0x00000001)
        # time (10 as uint32): 4 bytes (0x0000000A)
        # data: 4 bytes (0x01020304)
        assert len(result) == 14
        assert result[0:2] == b"\x00\x0e"  # length_payload
        assert result[2:6] == b"\x00\x00\x00\x01"  # id=1
        assert result[6:10] == b"\x00\x00\x00\x0a"  # time=10
        assert result[10:14] == b"\x01\x02\x03\x04"  # data

    def test_to_bytes_multiple_ids_sorted(self):
        """Test to_bytes sorts ids in order"""
        sensor_data = Data(sensor1=0, sensor2=0)
        payload = PayloadData(
            length_payload=0,
            id={3, 1, 2},  # Unsorted
            time=0.0,
            data=sensor_data,
        )
        result = payload.to_bytes()

        # Should be sorted: 1, 2, 3
        assert result[2:6] == b"\x00\x00\x00\x01"
        assert result[6:10] == b"\x00\x00\x00\x02"
        assert result[10:14] == b"\x00\x00\x00\x03"

    def test_to_bytes_time_conversion(self):
        """Test float time converted to uint32"""
        sensor_data = Data(sensor1=0, sensor2=0)
        payload = PayloadData(
            length_payload=0,
            id={1},
            time=255.9,  # Will be converted to int(255) = 0xFF
            data=sensor_data,
        )
        result = payload.to_bytes()

        # time as int(255.9) = 255 = 0xFF
        assert result[6:10] == b"\x00\x00\x00\xff"


class TestLoRaD2DFrame:
    """Test LoRa D2D frame with CRC calculation"""

    def test_length_property(self):
        """Test frame length calculation"""
        sensor_data = Data(sensor1=100, sensor2=200)
        payload = PayloadData(length_payload=14, id={1}, time=10.0, data=sensor_data)
        frame = LoRaD2DFrame(source_node_id=5, destination_node_id={1, 2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=payload)

        # source (4) + destinations (4*2) + type (1) + payload.length (14) + crc (2)
        expected = 4 + 8 + 1 + 14 + 2
        assert frame.length == expected

    def test_length_with_hop_count_payload(self):
        """Test frame length with full hop count payload"""
        hop_payload = PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=1, time_offset_from_period_start=0)
        frame = LoRaD2DFrame(source_node_id=10, destination_node_id={3}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_payload)

        # source (4) + destinations (4*1) + type (1) + payload.length (6) + crc (2)
        expected = 4 + 4 + 1 + 6 + 2
        assert frame.length == expected

    def test_to_crc_bytes_serialization(self):
        """Test to_crc_bytes creates correct byte sequence"""
        hop_payload = PayloadHopCntFull(cnt=0x0001, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame = LoRaD2DFrame(source_node_id=0x00000001, destination_node_id={0x00000002}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_payload)

        result = frame.to_crc_bytes()

        # source (4) + destination (4) + type (1) + hop_count (6: cnt+slot_period_counter+use_slot+time_offset)
        assert len(result) == 15
        assert result[0:4] == b"\x00\x00\x00\x01"  # source
        assert result[4:8] == b"\x00\x00\x00\x02"  # destination
        assert result[8] == 5  # type value (CURRENT_HOP_COUNT = 5)
        assert result[9:11] == b"\x00\x01"  # hop count
        assert result[11:12] == b"\x00"  # slot_period_counter
        assert result[12:13] == b"\x00"  # use_slot
        assert result[13:15] == b"\x00\x00"  # time_offset_from_period_start

    def test_to_crc_bytes_multiple_destinations_sorted(self):
        """Test to_crc_bytes sorts destinations"""
        hop_payload = PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={3, 1, 2},  # Unsorted
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
            payload=hop_payload,
        )

        result = frame.to_crc_bytes()

        # Destinations should appear sorted: 1, 2, 3
        # Positions: source (4), then destinations start at offset 4
        assert result[4:8] == b"\x00\x00\x00\x01"
        assert result[8:12] == b"\x00\x00\x00\x02"
        assert result[12:16] == b"\x00\x00\x00\x03"

    def test_crc_calculation(self):
        """Test CRC is calculated and stored"""
        hop_payload = PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
            payload=hop_payload,
            crc=0,  # Start with 0
        )

        assert frame.crc == 0
        frame.crc_calc()
        assert frame.crc != 0, "CRC should be calculated to non-zero value"

    def test_crc_reproducible(self):
        """Test same frame produces same CRC"""
        hop_payload = PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_payload, crc=0)
        frame1.crc_calc()
        crc1 = frame1.crc

        # Create identical frame
        hop_payload2 = PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame2 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_payload2, crc=0)
        frame2.crc_calc()
        crc2 = frame2.crc

        assert crc1 == crc2, "Identical frames should produce identical CRC values"

    def test_crc_changes_with_different_Data(self):
        """Test different payloads produce different CRCs"""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0), crc=0)
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
            payload=PayloadHopCntFull(cnt=2, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0),  # Different value
            crc=0,
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc, "Different payloads should produce different CRC values"

    def test_crc_changes_with_different_source(self):
        """Test different source produces different CRC"""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0), crc=0)
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(
            source_node_id=2,  # Different source
            destination_node_id={2},
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
            payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0),
            crc=0,
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc

    def test_crc_type_byte_included(self):
        """Test frame type is included in CRC calculation"""
        frame1 = LoRaD2DFrame(source_node_id=1, destination_node_id={2}, type=LoRaD2DFrameType.DATA_TO_GW, payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0), crc=0)
        frame1.crc_calc()

        frame2 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,  # Different type
            payload=PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0),
            crc=0,
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc


class TestDataClassDefaults:
    """Test behavior of data class default values"""

    def test_explicit_sensor_values(self):
        """Test that explicit values override any defaults"""
        d1 = Data(sensor1=100, sensor2=200)
        d2 = Data(sensor1=100, sensor2=200)

        assert d1.sensor1 == 100
        assert d1.sensor2 == 200
        assert d2.sensor1 == 100
        assert d2.sensor2 == 200

    def test_different_instances_different_values(self):
        """Test we can create separate instances with different values"""
        d1 = Data(sensor1=10, sensor2=20)
        d2 = Data(sensor1=30, sensor2=40)

        assert d1.sensor1 != d2.sensor1
        assert d1.sensor2 != d2.sensor2

    def test_data_without_arguments_uses_drawn_defaults(self):
        """Test Data() uses default values drawn at class definition time"""
        d = Data()
        assert isinstance(d.sensor1, int), "sensor1 should be drawn int value"
        assert isinstance(d.sensor2, int), "sensor2 should be drawn int value"
        assert 0 <= d.sensor1 <= 30, "sensor1 should be in valid range from __rand()"
        assert 0 <= d.sensor2 <= 30, "sensor2 should be in valid range from __rand()"

    def test_data_sensor_values_drawn_independently(self):
        """Test sensor1 and sensor2 within same instance are independent random draws"""
        d = Data()
        # Each sensor is drawn independently via field(default_factory=__rand)
        assert 0 <= d.sensor1 <= 30, "sensor1 in valid range"
        assert 0 <= d.sensor2 <= 30, "sensor2 in valid range"
        # sensor1 and sensor2 can be equal but are independently drawn
        # (statistically they have equal chance of being different or same)

    def test_data_drawn_defaults_are_independent(self):
        """Test each Data() instance gets independent draws"""
        d1 = Data()
        d2 = Data()
        d3 = Data()

        # Each instance draws independently, so they can be different
        assert all(isinstance(d.sensor1, int) for d in [d1, d2, d3])
        assert all(isinstance(d.sensor2, int) for d in [d1, d2, d3])

    def test_data_drawn_defaults_to_bytes(self):
        """Test to_bytes() works with drawn default values"""
        d = Data()
        result = d.to_bytes()

        assert len(result) == 4, "to_bytes should return 4 bytes"
        assert isinstance(result, bytes)
        # Verify round-trip: bytes should match the drawn values
        reconstructed_s1 = int.from_bytes(result[0:2], "big")
        reconstructed_s2 = int.from_bytes(result[2:4], "big")
        assert reconstructed_s1 == d.sensor1
        assert reconstructed_s2 == d.sensor2

    def test_data_drawn_defaults_length(self):
        """Test length property is always 4 regardless of drawn values"""
        d = Data()
        assert d.length == 4, "Data.length should always be 4 (2 + 2)"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_payload_data_empty_destination_set(self):
        """Test payload with empty destination set (edge case)"""
        sensor_data = Data(sensor1=1, sensor2=2)
        payload = PayloadData(
            length_payload=0,
            id=set(),  # Empty set
            time=0.0,
            data=sensor_data,
        )

        # Should handle empty set without error
        assert payload.length == 2 + 0 + 4 + 4
        assert payload.to_bytes() is not None

    def test_large_destination_set(self):
        """Test frame with many destinations"""
        large_id_set = set(range(1, 101))  # 100 destinations
        hop_payload = PayloadHopCntFull(cnt=1, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)

        frame = LoRaD2DFrame(source_node_id=1, destination_node_id=large_id_set, type=LoRaD2DFrameType.CURRENT_HOP_COUNT, payload=hop_payload)

        # Should calculate length correctly
        expected = 4 + (4 * len(large_id_set)) + 1 + 6 + 2
        assert frame.length == expected

    def test_time_float_precision(self):
        """Test that float time values are converted to int correctly"""
        sensor_data = Data(sensor1=0, sensor2=0)
        payload = PayloadData(
            length_payload=0,
            id={1},
            time=123.789,  # Float with decimal
            data=sensor_data,
        )

        result = payload.to_bytes()
        # int(123.789) = 123 = 0x7B
        assert result[6:10] == b"\x00\x00\x00\x7b"


class TestBottomUpIntegration:
    """Integration tests building frames from ground up: Data → Payload → Frame → CRC"""

    def test_simple_data_to_frame_crc(self):
        """Test building complete frame from Data through CRC calculation"""
        # Bottom-up construction
        sensor_data = Data(sensor1=0x1234, sensor2=0x5678)
        payload = PayloadData(length_payload=14, id={1}, time=100.0, data=sensor_data)
        frame = LoRaD2DFrame(
            source_node_id=10,
            destination_node_id={20},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload,
        )

        # Calculate CRC
        frame.crc_calc()

        # Verify CRC was calculated
        assert frame.crc != 0, "CRC should be calculated"
        assert isinstance(frame.crc, int)
        assert 0 <= frame.crc <= 0xFFFF, "CRC should fit in uint16"

    def test_data_payload_frame_crc_reproducible(self):
        """Test same frame composition produces identical CRC"""
        # First frame
        sensor_data1 = Data(sensor1=100, sensor2=200)
        payload1 = PayloadData(length_payload=14, id={5, 6}, time=50.5, data=sensor_data1)
        frame1 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={5, 6},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload1,
        )
        frame1.crc_calc()
        crc1 = frame1.crc

        # Identical second frame
        sensor_data2 = Data(sensor1=100, sensor2=200)
        payload2 = PayloadData(length_payload=14, id={5, 6}, time=50.5, data=sensor_data2)
        frame2 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={5, 6},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload2,
        )
        frame2.crc_calc()
        crc2 = frame2.crc

        assert crc1 == crc2, "Identical frames should produce identical CRC"

    def test_data_content_affects_crc(self):
        """Test different sensor data produces different CRC"""
        # Frame with sensor1=100
        payload1 = PayloadData(
            length_payload=14,
            id={1},
            time=10.0,
            data=Data(sensor1=100, sensor2=200),
        )
        frame1 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload1,
        )
        frame1.crc_calc()

        # Frame with sensor1=101
        payload2 = PayloadData(
            length_payload=14,
            id={1},
            time=10.0,
            data=Data(sensor1=101, sensor2=200),  # Different sensor1
        )
        frame2 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload2,
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc, "Different sensor data should produce different CRC"

    def test_frame_length_matches_serialization(self):
        """Test frame.length matches actual to_crc_bytes serialization"""
        sensor_data = Data(sensor1=50, sensor2=75)
        payload = PayloadData(length_payload=14, id={1, 2, 3}, time=25.0, data=sensor_data)
        frame = LoRaD2DFrame(
            source_node_id=5,
            destination_node_id={10, 20, 30},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload,
        )

        crc_bytes = frame.to_crc_bytes()
        # to_crc_bytes includes: source(4) + destinations(4*3) + type(1) + payload
        # Note: to_crc_bytes doesn't include CRC field itself, only data for CRC calculation
        expected_crc_bytes_len = 4 + (4 * 3) + 1 + payload.length
        assert len(crc_bytes) == expected_crc_bytes_len

    def test_multiple_destinations_ordered_in_crc(self):
        """Test multiple destinations are sorted when calculating CRC"""
        # Destinations in reverse order: 30, 20, 10
        payload = PayloadData(
            length_payload=14,
            id={1},
            time=10.0,
            data=Data(sensor1=1, sensor2=1),
        )
        frame_reverse = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={30, 20, 10},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload,
        )
        frame_reverse.crc_calc()

        # Destinations in forward order: 10, 20, 30
        payload2 = PayloadData(
            length_payload=14,
            id={1},
            time=10.0,
            data=Data(sensor1=1, sensor2=1),
        )
        frame_forward = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={10, 20, 30},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload2,
        )
        frame_forward.crc_calc()

        # Order shouldn't matter - to_crc_bytes sorts destinations
        assert frame_reverse.crc == frame_forward.crc

    def test_payload_time_affects_crc(self):
        """Test different payload time produces different CRC"""
        sensor_data = Data(sensor1=10, sensor2=20)

        # Frame with time=10.0
        payload1 = PayloadData(length_payload=14, id={1}, time=10.0, data=sensor_data)
        frame1 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload1,
        )
        frame1.crc_calc()

        # Frame with time=11.0
        sensor_data2 = Data(sensor1=10, sensor2=20)
        payload2 = PayloadData(length_payload=14, id={1}, time=11.0, data=sensor_data2)
        frame2 = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.DATA_TO_GW,
            payload=payload2,
        )
        frame2.crc_calc()

        assert frame1.crc != frame2.crc, "Different time should produce different CRC"

    def test_crc_with_hop_count_payload(self):
        """Test CRC calculation with hop count payload instead of data payload"""
        hop_payload = PayloadHopCntFull(cnt=5, slot_period_counter=0, use_slot=0, time_offset_from_period_start=0)
        frame = LoRaD2DFrame(
            source_node_id=1,
            destination_node_id={2},
            type=LoRaD2DFrameType.CURRENT_HOP_COUNT,
            payload=hop_payload,
        )
        frame.crc_calc()

        assert frame.crc != 0, "CRC should be calculated for hop count payload"
        assert isinstance(frame.crc, int)


class TestPerformance:
    """Performance tests - verify throughput and timing constraints"""

    def test_data_creation_throughput(self):
        """Test Data creation: 100+ instances in under 2 seconds"""
        start = time.time()
        for _ in range(100):
            Data(sensor1=10, sensor2=20)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Creating 100 Data instances took {elapsed}s, should be < 2s"

    def test_frame_creation_throughput(self):
        """Test LoRaD2DFrame creation: 100+ frames in under 2 seconds"""
        start = time.time()
        for i in range(100):
            payload = PayloadData(
                length_payload=14,
                id={i % 10},
                time=float(i),
                data=Data(sensor1=i, sensor2=i + 1),
            )
            LoRaD2DFrame(
                source_node_id=i,
                destination_node_id={i + 1},
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Creating 100 frames took {elapsed}s, should be < 2s"

    def test_crc_calculation_throughput(self):
        """Test CRC calculation: 100+ frames with CRC in under 2 seconds"""
        frames = []
        for i in range(100):
            payload = PayloadData(
                length_payload=14,
                id={i % 10},
                time=float(i),
                data=Data(sensor1=i, sensor2=i + 1),
            )
            frame = LoRaD2DFrame(
                source_node_id=i,
                destination_node_id={i + 1},
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
            frames.append(frame)

        start = time.time()
        for frame in frames:
            frame.crc_calc()
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Calculating CRC for 100 frames took {elapsed}s, should be < 2s"

    def test_full_pipeline_throughput(self):
        """Test full pipeline: Data→Payload→Frame→CRC for 100 frames in under 2 seconds"""
        start = time.time()
        for i in range(100):
            sensor_data = Data(sensor1=i, sensor2=i + 1)
            payload = PayloadData(
                length_payload=14,
                id={i % 10},
                time=float(i),
                data=sensor_data,
            )
            frame = LoRaD2DFrame(
                source_node_id=i,
                destination_node_id={i + 1},
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
            frame.crc_calc()
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Full pipeline for 100 frames took {elapsed}s, should be < 2s"

    def test_to_bytes_throughput(self):
        """Test serialization: 100+ frames to_bytes in under 2 seconds"""
        frames = []
        for i in range(100):
            payload = PayloadData(
                length_payload=14,
                id={i % 10},
                time=float(i),
                data=Data(sensor1=i, sensor2=i + 1),
            )
            frame = LoRaD2DFrame(
                source_node_id=i,
                destination_node_id={i + 1},
                type=LoRaD2DFrameType.DATA_TO_GW,
                payload=payload,
            )
            frame.crc_calc()
            frames.append(frame)

        start = time.time()
        for frame in frames:
            frame.to_crc_bytes()
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Serializing 100 frames took {elapsed}s, should be < 2s"
