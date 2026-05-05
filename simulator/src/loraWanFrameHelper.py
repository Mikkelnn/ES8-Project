from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Optional

from Interfaces import ILength

# =========================================================
# ENUMS
# =========================================================


class MType(IntEnum):
	JOIN_REQUEST = 0b000
	JOIN_ACCEPT = 0b001
	UNCONFIRMED_DATA_UP = 0b010
	UNCONFIRMED_DATA_DOWN = 0b011
	CONFIRMED_DATA_UP = 0b100
	CONFIRMED_DATA_DOWN = 0b101


class Major(IntEnum):
	LORAWAN_R1 = 0b00


def build_mhdr(mtype: MType, major: Major = Major.LORAWAN_R1) -> int:
	return (mtype << 5) | major


class FCtrlUplink(IntFlag):
	ADR = 1 << 7
	ADR_ACK_REQ = 1 << 6
	ACK = 1 << 5
	CLASS_B = 1 << 4


class FCtrlDownlink(IntFlag):
	ADR = 1 << 7
	ACK = 1 << 5
	FPENDING = 1 << 4


# =========================================================
# MAC PAYLOAD
# =========================================================


@dataclass
class MACPayload:
	# FHDR
	dev_addr: int
	fctrl_flags: IntFlag
	fcnt: int
	fopts: bytes = field(default_factory=bytes)

	# Optional
	fport: Optional[int] = None
	frm_payload: bytes = field(default_factory=bytes)

	# ---- Derived ----

	@property
	def fctrl(self) -> int:
		return int(self.fctrl_flags) | (len(self.fopts) & 0x0F)

	@property
	def fhdr_length(self) -> int:
		# DevAddr (4) + FCtrl (1) + FCnt (2) + FOpts
		return 4 + 1 + 2 + len(self.fopts)

	@property
	def length(self) -> int:
		length = self.fhdr_length

		if self.frm_payload:
			length += 1  # FPort

		length += len(self.frm_payload)
		return length

	# alias (as requested)
	@property
	def mac_payload_length(self) -> int:
		return self.length

	# ---- Validation ----

	def validate(self):
		if len(self.fopts) > 15:
			raise ValueError("FOpts max length is 15 bytes")

		if self.frm_payload and self.fport is None:
			raise ValueError("FPort required when FRMPayload exists")

		if not self.frm_payload and self.fport is not None:
			raise ValueError("FPort must not be present without FRMPayload")


# =========================================================
# JOIN PAYLOAD (OTAA support)
# =========================================================


@dataclass
class JoinRequestPayload:
	join_eui: bytes  # 8 bytes
	dev_eui: bytes  # 8 bytes
	dev_nonce: int  # 2 bytes

	@property
	def length(self) -> int:
		return 8 + 8 + 2


@dataclass
class JoinAcceptPayload:
	app_nonce: bytes  # 3 bytes
	net_id: bytes  # 3 bytes
	dev_addr: int  # 4 bytes
	dl_settings: int  # 1 byte
	rx_delay: int  # 1 byte
	cf_list: bytes = b""  # optional (16 bytes)

	@property
	def length(self) -> int:
		return 3 + 3 + 4 + 1 + 1 + len(self.cf_list)


# =========================================================
# LoRaWanPHYPayload
# =========================================================


@dataclass
class LoRaWanPHYPayload(ILength):
	mhdr: int

	# One of:
	mac_payload: Optional[MACPayload] = None
	join_request: Optional[JoinRequestPayload] = None
	join_accept: Optional[JoinAcceptPayload] = None

	mic: bytes = b"\x00\x00\x00\x00"  # 4 bytes

	# ---- Derived ----

	@property
	def payload_length(self) -> int:
		if self.mac_payload:
			return self.mac_payload.length
		if self.join_request:
			return self.join_request.length
		if self.join_accept:
			return self.join_accept.length
		return 0

	@property
	def length(self) -> int:
		# MHDR (1) + payload + MIC (4)
		return 1 + self.payload_length + 4

	# ---- Helpers ----

	def is_uplink(self) -> bool:
		return ((self.mhdr >> 5) & 0b111) in (
			MType.UNCONFIRMED_DATA_UP,
			MType.CONFIRMED_DATA_UP,
		)

	def is_downlink(self) -> bool:
		return ((self.mhdr >> 5) & 0b111) in (
			MType.UNCONFIRMED_DATA_DOWN,
			MType.CONFIRMED_DATA_DOWN,
		)

	def is_ack(self) -> bool:
		if not self.mac_payload:
			return False
		return bool(self.mac_payload.fctrl_flags & FCtrlDownlink.ACK)

	def is_confirmed_uplink(self) -> bool:
		return ((self.mhdr >> 5) & 0b111) == MType.CONFIRMED_DATA_UP


# =========================================================
# CONVENIENCE BUILDERS
# =========================================================


def make_uplink(dev_addr: int, frame_count: int, payload: bytes, confirmed: bool) -> LoRaWanPHYPayload:
	mtype = MType.CONFIRMED_DATA_UP if confirmed else MType.UNCONFIRMED_DATA_UP

	mac = MACPayload(
		dev_addr=dev_addr,
		fctrl_flags=FCtrlUplink(0),
		fcnt=frame_count,
		frm_payload=payload,
		fport=1 if payload else None,
	)

	return LoRaWanPHYPayload(
		mhdr=build_mhdr(mtype),
		mac_payload=mac,
	)


def make_downlink_ack(dev_addr: int, frame_count: int) -> LoRaWanPHYPayload:
	mac = MACPayload(
		dev_addr=dev_addr,
		fctrl_flags=FCtrlDownlink.ACK,
		fcnt=frame_count,
		frm_payload=b"",
		fport=None,
	)

	return LoRaWanPHYPayload(mhdr=build_mhdr(MType.UNCONFIRMED_DATA_DOWN), mac_payload=mac)
