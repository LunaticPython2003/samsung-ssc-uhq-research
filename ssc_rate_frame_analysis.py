#!/usr/bin/env python3
"""SSC bitrate and transport-size preflight; no packet transmission.

Samsung's 96 kHz software encoder consumes 864 samples per channel per frame.
The returned lengths below were measured in *isolated* ARM64 tests, not in
over-the-air A2DP captures. Treat the 1005-byte MTU as HAL-reported, not a
fully established packet-size boundary.
"""
from dataclasses import dataclass

FRAME_SAMPLES = 864
SAMPLE_RATE_HZ = 96_000
RTP_FIXED_HEADER_BYTES = 12
HAL_REPORTED_PEER_MTU = 1005


@dataclass(frozen=True)
class Mode:
    selected_bitrate_bps: int
    observed_frame_bytes: int


OBSERVED_MODES = (
    Mode(152_000, 174),
    Mode(291_000, 330),
    Mode(328_000, 372),
    Mode(584_000, 660),
    Mode(886_000, 1000),
)


def expected_bytes_per_frame(bitrate_bps: int) -> float:
    if bitrate_bps <= 0:
        raise ValueError("bitrate must be positive")
    return bitrate_bps * FRAME_SAMPLES / SAMPLE_RATE_HZ / 8


def max_complete_frames(mtu: int, frame_bytes: int, media_header_bytes: int = 0) -> int:
    """Conditional RTP-based upper bound, *not* a Bluetooth packetizer."""
    if mtu <= 0 or frame_bytes <= 0 or media_header_bytes < 0:
        raise ValueError("MTU and frame length must be positive; headers nonnegative")
    payload_budget = mtu - RTP_FIXED_HEADER_BYTES - media_header_bytes
    return max(0, payload_budget // frame_bytes)


def main() -> None:
    print("rate_bps,frame_bytes,expected_bytes,overhead_bytes,max_frames_if_header_0")
    for mode in OBSERVED_MODES:
        target = expected_bytes_per_frame(mode.selected_bitrate_bps)
        capacity = max_complete_frames(HAL_REPORTED_PEER_MTU, mode.observed_frame_bytes)
        print(
            f"{mode.selected_bitrate_bps},{mode.observed_frame_bytes},"
            f"{target:.3f},{mode.observed_frame_bytes - target:+.3f},{capacity}"
        )
    print("Note: Bluetooth codec-media headers and true transport MTU semantics are unknown.")


if __name__ == "__main__":
    main()
