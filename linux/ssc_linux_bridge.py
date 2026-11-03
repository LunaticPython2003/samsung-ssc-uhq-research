#!/usr/bin/env python3
"""Linux SSC encoder-to-RTP *loopback* prototype.

This exercises a real, phone-hosted Samsung encoder from Linux:
    WAV PCM -> ADB TCP encoder -> SSC frame -> provisional RTPv2 header
            -> Unix SOCK_SEQPACKET loopback receiver.

This DOES NOT register a Bluetooth endpoint or write Bluetooth packets.
The actual Samsung A2DP media header, MTU convention, codec ID, and
fragmentation are unverified. Packet bytes are provisional and must not
be sent to earbuds merely because the loopback test succeeds.

Usage:
    python3 linux/ssc_linux_bridge.py --wav tools/setup_test_tone.wav --bitrate 584000
    python3 linux/ssc_linux_bridge.py --wav tools/setup_test_tone.wav --bitrate 886000
    python3 linux/ssc_linux_bridge.py --wav tools/setup_test_tone.wav --bitrate 886000 --mtu 1200
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import socket
import statistics
import struct
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ssc_rpc import BITRATES, open_backend, pcm32_frame, recv_exact, setup_adb, stop_adb  # noqa: E402

RTP_HEADER_LEN = 12
PCM_FRAMES_PER_CODEC_FRAME = 864
RTP_PAYLOAD_TYPE = 96
# Identified by encoder get_header_from_bitrate and confirmed via the actual
# 96kHz/24-bit encoded frames. Stored in the low nibble of byte 3 for UHQ.
UHQ_FRAME_MARKERS = {291000: 0, 308000: 1, 442000: 2, 584000: 3, 886000: 4}


@dataclass(frozen=True)
class RtpState:
    sequence: int = 0
    timestamp: int = 0
    ssrc: int = 0x53534321

    def pack_candidate(self, encoded_frame: bytes) -> bytes:
        # This is a deliberately incomplete RTP skeleton, *not* verified SSC
        # media packetization. No claim is made about payload-specific headers.
        if not encoded_frame:
            raise ValueError("empty SSC encoded frame")
        header = struct.pack(
            "!BBHII", 0x80, RTP_PAYLOAD_TYPE, self.sequence & 0xFFFF,
            self.timestamp & 0xFFFFFFFF, self.ssrc
        )
        return header + encoded_frame

    def next_frame(self, samples_per_channel: int = PCM_FRAMES_PER_CODEC_FRAME) -> "RtpState":
        return RtpState(
            sequence=(self.sequence + 1) & 0xFFFF,
            timestamp=(self.timestamp + samples_per_channel) & 0xFFFFFFFF,
            ssrc=self.ssrc,
        )


def capacity(mtu: int, frame_length: int, unknown_header_bytes: int = 0) -> tuple[bool, int]:
    """Preflight with an *assumed* RTP-inclusive media transport MTU."""
    if mtu <= RTP_HEADER_LEN or frame_length <= 0 or unknown_header_bytes < 0:
        raise ValueError("invalid MTU, frame length, or header budget")
    available = mtu - RTP_HEADER_LEN - unknown_header_bytes
    return frame_length <= available, max(0, frame_length - available)


def _read_wav(path: Path):
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 2 or w.getframerate() not in (44100, 48000, 96000):
            raise ValueError("WAV must be stereo 44.1, 48 or 96 kHz PCM")
        if w.getsampwidth() not in (2, 3, 4) or w.getcomptype() != "NONE":
            raise ValueError("WAV must have uncompressed PCM16/24/32")
        yield w, (w.getframerate(), w.getsampwidth(), w.getnframes())


def validate_uhq_frame(encoded: bytes, returned_length: int, bitrate: int | None = None) -> bool:
    """Guard against accepting a short status as a real frame length.

    This checks the *returned* buffer only; it cannot detect encoder writes
    beyond the return value. The Android backend still needs its canary and
    last-written-byte check, and rates >= 1.2Mbps remain disabled there.
    """
    structurally_valid = (
        len(encoded) == returned_length
        and returned_length >= 4
        and encoded[0] == 0xFF
        and (encoded[1] & 0xF0) == 0xE0
    )
    if not structurally_valid:
        return False
    expected_marker = UHQ_FRAME_MARKERS.get(bitrate)
    return expected_marker is None or (encoded[3] & 0x0F) == expected_marker


def bridge_wav(
    wav_path: Path, *, bitrate: int = 584000, depth: int = 24, mtu: int = 1005,
    media_header_reserve: int = 0, no_adb: bool = False, port: int = 23187,
    batch_frames: int = 1,
) -> dict:
    if batch_frames < 1 or batch_frames > 16:
        raise ValueError('batch_frames must be in 1..16')
    if bitrate not in BITRATES:
        raise ValueError("Bitrate not allowlisted in the original Android encoder backend")
    if depth not in (16, 24):
        raise ValueError("Invalid encoder depth")
    if mtu <= RTP_HEADER_LEN or media_header_reserve < 0:
        raise ValueError("Invalid provisional MTU assumptions")
    if not wav_path.is_file():
        raise FileNotFoundError(wav_path)

    with wave.open(str(wav_path), "rb") as w:
        hz, width, total = w.getframerate(), w.getsampwidth(), w.getnframes()
        if hz not in (44100, 48000, 96000) or w.getnchannels() != 2:
            raise ValueError("Requires stereo 44.1/48/96 kHz WAV")
        if w.getcomptype() != "NONE" or width not in (2, 3, 4):
            raise ValueError("Requires uncompressed 16-/24-/32-bit PCM")

        # SOCK_SEQPACKET preserves individual packet boundaries, unlike a
        # stream; no external port or Bluetooth adapter is accessed.
        tx, rx = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        frame_times: list[float] = []
        rtp = RtpState()
        frames = encoded_bytes = sent_packets = mtu_blocked = invalid_frames = 0
        max_frame = 0
        packet_digest = hashlib.sha256()
        frame_sizes: dict[str, int] = {}
        start = time.perf_counter()
        backend = None
        try:
            if not no_adb:
                setup_adb(port, build=True)
            backend = open_backend("127.0.0.1", port, rate=hz, depth=depth, bitrate=bitrate,
                                   samples=PCM_FRAMES_PER_CODEC_FRAME)
            active_start = time.perf_counter()
            total_frames = (total + PCM_FRAMES_PER_CODEC_FRAME - 1) // PCM_FRAMES_PER_CODEC_FRAME
            for batch_start in range(0, total_frames, batch_frames):
                batch_size = min(batch_frames, total_frames - batch_start)
                # Request pipelining avoids one USB/ADB roundtrip per 9ms
                # codec frame, but it adds batch-size-dependent latency.
                pcm_requests = bytearray()
                for _ in range(batch_size):
                    raw = w.readframes(PCM_FRAMES_PER_CODEC_FRAME)
                    pcm = pcm32_frame(raw, width, PCM_FRAMES_PER_CODEC_FRAME)
                    pcm_requests.extend(struct.pack("<I", len(pcm)))
                    pcm_requests.extend(pcm)
                before = time.perf_counter()
                backend.sendall(pcm_requests)
                for _ in range(batch_size):
                    (encoded_len,) = struct.unpack("<i", recv_exact(backend, 4))
                    if encoded_len < 4 or encoded_len > 16384:
                        raise RuntimeError("Unsafe encoded length received")
                    encoded = recv_exact(backend, encoded_len)
                    frames += 1
                    max_frame = max(max_frame, len(encoded))
                    encoded_bytes += len(encoded)
                    frame_sizes[str(len(encoded))] = frame_sizes.get(str(len(encoded)), 0) + 1
                    if not validate_uhq_frame(encoded, encoded_len, bitrate):
                        invalid_frames += 1
                        rtp = rtp.next_frame()
                        continue
                    ok, _ = capacity(mtu, len(encoded), media_header_reserve)
                    if not ok:
                        mtu_blocked += 1
                    else:
                        packet = rtp.pack_candidate(encoded)
                        tx.send(packet)
                        seen = rx.recv(max(mtu + 4096, 65536))
                        if seen != packet:
                            raise AssertionError("SOCK_SEQPACKET loopback payload mismatch")
                        sent_packets += 1
                        packet_digest.update(seen)
                    rtp = rtp.next_frame()
                frame_times.append(time.perf_counter() - before)
            encoder_active_elapsed = time.perf_counter() - active_start
            with contextlib.suppress(Exception):
                backend.sendall(struct.pack("<I", 0))
        finally:
            if backend is not None:
                backend.close()
            tx.close()
            rx.close()
            if not no_adb:
                stop_adb(port)
        elapsed = time.perf_counter() - start
        duration = total / hz
        return {
            "mode": "linux-adb-encoder-to-rtp-seqpacket-loopback-NOT-BLUETOOTH",
            "bitrate_bps": bitrate,
            "sample_rate_hz": hz,
            "source_duration_s": round(duration, 4),
            "elapsed_s": round(elapsed, 4),
            "throughput_realtime_factor": round(duration / elapsed, 3) if elapsed else None,
            "encoder_active_elapsed_s": round(encoder_active_elapsed, 4),
            "encoder_active_realtime_factor": round(duration / encoder_active_elapsed, 3) if encoder_active_elapsed else None,
            "batch_frames": batch_frames,
            "frames_encoded": frames,
            "encoded_bytes": encoded_bytes,
            "encoded_frame_lengths": frame_sizes,
            "max_frame_bytes": max_frame,
            "provisional_rtp_packets_loopback": sent_packets,
            "frames_blocked_by_provisional_mtu": mtu_blocked,
            "frames_rejected_by_header_check": invalid_frames,
            "assumed_mtu": mtu,
            "reserved_unknown_media_header_bytes": media_header_reserve,
            "amortized_ms_per_frame": round(sum(frame_times) * 1000 / frames, 3) if frames else None,
            "avg_batch_roundtrip_ms": round(statistics.mean(frame_times) * 1000, 3) if frame_times else None,
            "p95_batch_roundtrip_ms": (
                round(sorted(frame_times)[min(len(frame_times) - 1, int(len(frame_times) * 0.95))] * 1000, 3)
                if frame_times else None
            ),
            "loopback_sha256": packet_digest.hexdigest(),
            "caveat": "RTP skeleton only; vendor media header, on-air ID and MTU semantics unverified",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--bitrate", type=int, choices=BITRATES, default=584000)
    parser.add_argument("--depth", type=int, choices=(16, 24), default=24)
    parser.add_argument("--mtu", type=int, default=1005)
    parser.add_argument("--batch-frames", type=int, default=1,
                        help="pipeline 1..16 encoder requests over ADB (batching increases live latency)")
    parser.add_argument("--media-header-reserve", type=int, default=0)
    parser.add_argument("--no-adb", action="store_true")
    parser.add_argument("--port", type=int, default=23187)
    parser.add_argument("--output", type=Path, help="save sanitized JSON statistics; no PCM/SSC/HCI data")
    args = parser.parse_args()
    try:
        report = bridge_wav(
            args.wav, bitrate=args.bitrate, depth=args.depth, mtu=args.mtu,
            media_header_reserve=args.media_header_reserve,
            no_adb=args.no_adb, port=args.port, batch_frames=args.batch_frames
        )
    except Exception as exc:
        parser.exit(2, f"Linux SSC loopback failed: {exc}\n")
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
