#!/usr/bin/env python3
"""Windows WAV -> experimental SSC encoded frames, backed by Android ARM64.

Encodes through an isolated on-phone Samsung binary using USB ADB forwarding.
This is NOT a native x64 port or a Bluetooth/A2DP transmitter. The .sscf
output format is a deliberately nonstandard length-prefixed research container.

Usage:
    python ssc_rpc.py input.wav -o encoded.sscf --bitrate 328000
    python ssc_rpc.py input.wav -o encoded.sscf --no-adb --port 23187
"""
from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAGIC = b"SSCF"
BITRATES = (88000, 96000, 128000, 152000, 192000, 229000, 250000,
            256000, 291000, 308000, 328000, 442000, 584000, 886000)
REMOTE_C = "/data/local/tmp/ssc_rpc_server.c"
REMOTE_EXE = "/data/local/tmp/ssc_rpc_server"
TERMUX_CLANG = "/data/data/com.termux/files/usr/bin/clang"


def invoke(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args), file=sys.stderr)
    return subprocess.run(args, check=check, text=True, capture_output=True)


def adb(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return invoke("adb", *args, check=check)


def setup_adb(port: int, build: bool) -> None:
    state = adb("get-state")
    if state.stdout.strip() != "device":
        raise RuntimeError(f"ADB device missing: {state.stdout.strip()}")
    if build:
        src = HERE / "ssc_rpc_server.c"
        if not src.is_file():
            raise RuntimeError("Missing ssc_rpc_server.c")
        adb("push", str(src), REMOTE_C)
        compile_cmd = (
            "PATH=/data/data/com.termux/files/usr/bin:$PATH "
            f"{TERMUX_CLANG} {REMOTE_C} -O2 -Wall -Wextra -ldl "
            f"-o {REMOTE_EXE}"
        )
        compilation = adb("shell", "su", "-c", compile_cmd, check=False)
        if compilation.returncode:
            raise RuntimeError("Android compilation failed: " + compilation.stderr)
    # One-shot loopback-only daemon; no Android Bluetooth changes.
    start = adb("shell", "su", "-c",
                f"{REMOTE_EXE} {port} >/data/local/tmp/ssc_rpc.log 2>&1 </dev/null &",
                check=False)
    if start.returncode:
        raise RuntimeError("Unable to start on-phone encoder: " + start.stderr)
    adb("forward", f"tcp:{port}", f"tcp:{port}")


def stop_adb(port: int) -> None:
    with contextlib.suppress(Exception):
        adb("forward", "--remove", f"tcp:{port}", check=False)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    pieces = []
    while n:
        part = sock.recv(n)
        if not part:
            raise ConnectionError("Encoder backend closed the connection")
        pieces.append(part)
        n -= len(part)
    return b"".join(pieces)


def open_backend(host: str, port: int, *, rate: int, depth: int,
                 bitrate: int, samples: int) -> socket.socket:
    deadline = time.monotonic() + 10
    # ADB can accept the host-side TCP connection before the Android process
    # reaches listen(). In that case the forward immediately returns EOF.
    # Retry the complete handshake, not just connect(), during startup.
    while True:
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.settimeout(2)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.sendall(struct.pack("<4s6I", b"SSC1", rate, 2, depth, bitrate, samples, 1))
            magic, status, ctx_size = struct.unpack("<4sii", recv_exact(sock, 12))
            if magic != b"SSCR" or status != 0:
                raise RuntimeError(
                    f"SSC backend rejected configuration: {magic!r}, "
                    f"status={status}, context={ctx_size}"
                )
            sock.settimeout(30)
            print(f"SSC encoder ready: context={ctx_size} bytes", file=sys.stderr)
            return sock
        except OSError as exc:
            if sock is not None:
                sock.close()
            if time.monotonic() >= deadline:
                raise ConnectionError("SSC backend handshake unavailable after 10 seconds") from exc
            time.sleep(0.2)
        except Exception:
            if sock is not None:
                sock.close()
            raise


def signed_24(raw: bytes) -> int:
    # Explicit sign extension, independent of source endian.
    i = raw[0] | (raw[1] << 8) | (raw[2] << 16)
    return i - (1 << 24) if i & (1 << 23) else i


def pcm32_frame(raw: bytes, sample_width: int, samples: int) -> bytes:
    """PCM 16/24/32 -> signed 24-bit values carried as int32 LE.

    Samsung's exact PCM normalization still needs comparison with its caller.
    """
    if sample_width not in (2, 3, 4):
        raise ValueError("Only PCM 16/24/32-bit WAV is supported")
    expect = samples * 2 * sample_width
    if len(raw) > expect or len(raw) % (2 * sample_width):
        raise ValueError("Malformed interleaved stereo sample data")
    if len(raw) < expect:
        raw += bytes(expect - len(raw))
    if sample_width == 2:
        values = (int.from_bytes(raw[i:i+2], "little", signed=True) * 256
                  for i in range(0, len(raw), 2))
    elif sample_width == 3:
        values = (signed_24(raw[i:i+3]) for i in range(0, len(raw), 3))
    else:
        values = (int.from_bytes(raw[i:i+4], "little", signed=True) >> 8
                  for i in range(0, len(raw), 4))
    result = bytearray(expect // sample_width * 4)
    for i, value in enumerate(values):
        struct.pack_into("<i", result, i*4, value)
    return bytes(result)


def encode_wav(source: Path, destination: Path, *, host: str, port: int,
               bitrate: int, depth: int, samples: int) -> tuple[int, int]:
    with wave.open(str(source), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        frame_total = wav.getnframes()
        if wav.getcomptype() != "NONE" or rate not in (44100,48000,96000):
            raise ValueError("Input must be uncompressed PCM 44.1/48/96 kHz WAV")
        if channels != 2 or width not in (2,3,4):
            raise ValueError("Input must be stereo PCM16/24/32")
        frame_count = (frame_total + samples - 1) // samples
        if frame_count > 500000:
            raise ValueError("Input too long for test backend")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".partial")
        if temporary.exists():
            raise FileExistsError(f"Refusing to overwrite unfinished file {temporary}")
        sock = open_backend(host, port, rate=rate, depth=depth,
                            bitrate=bitrate, samples=samples)
        completed = False
        written = 0
        try:
            with sock, temporary.open("wb") as dst:
                # Nonstandard research container. Definitely not a valid
                # Bluetooth media stream or normal audio file.
                dst.write(struct.pack("<4s8I", MAGIC, 1, rate, channels, depth,
                                      bitrate, samples, frame_count, frame_total))
                for index in range(frame_count):
                    data = wav.readframes(samples)
                    valid_samples = len(data) // (width * channels)
                    payload = pcm32_frame(data, width, samples)
                    sock.sendall(struct.pack("<I", len(payload)) + payload)
                    (length,) = struct.unpack("<i", recv_exact(sock, 4))
                    if not 4 <= length <= 16384:
                        raise RuntimeError(f"Frame {index}: encoder error {length}")
                    encoded = recv_exact(sock, length)
                    dst.write(struct.pack("<2I", length, valid_samples))
                    dst.write(encoded)
                    written += length
                    if (index + 1) % 100 == 0:
                        print(f"{index+1}/{frame_count} frames", file=sys.stderr)
                sock.sendall(struct.pack("<I", 0))
            os.replace(temporary, destination)
            completed = True
            return frame_count, written
        finally:
            if not completed:
                with contextlib.suppress(FileNotFoundError):
                    temporary.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wav", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--bitrate", type=int, choices=BITRATES, default=328000)
    ap.add_argument("--depth", type=int, choices=(16, 24), default=24)
    ap.add_argument("--samples", type=int, default=864)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=23187)
    ap.add_argument("--no-adb", action="store_true",
                    help="Connect to an existing test/backend server")
    ap.add_argument("--no-build", action="store_true",
                    help="Use an existing compiled ARM64 backend on phone")
    args = ap.parse_args()
    if not (16 <= args.samples <= 1024):
        ap.error("samples must be 16..1024")
    if not (1025 <= args.port <= 65535):
        ap.error("port must be 1025..65535")
    target = args.output or args.wav.with_suffix(".sscf")
    if target.resolve() == args.wav.resolve():
        ap.error("Output cannot overwrite input WAV")
    if not args.wav.is_file():
        ap.error("Input WAV not found")
    started = False
    try:
        if not args.no_adb:
            setup_adb(args.port, not args.no_build)
            started = True
        frames, nbytes = encode_wav(args.wav, target, host=args.host,
                                    port=args.port, bitrate=args.bitrate,
                                    depth=args.depth, samples=args.samples)
        print(f"Wrote {frames} experimental SSC frames ({nbytes} encoded bytes) "
              f"to {target}")
        return 0
    finally:
        if started:
            stop_adb(args.port)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
