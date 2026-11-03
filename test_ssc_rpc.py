"""Offline transport tests; no ADB or Samsung codec required.

Run: python -m unittest -v test_ssc_rpc.py
These exercise WAV conversion, protocol compatibility, and the container,
not the proprietary encoder's correctness.
"""
from __future__ import annotations

import socket
import struct
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from ssc_rpc import encode_wav, pcm32_frame, recv_exact, signed_24


class MockEncoder(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.count = 0
        self.errors = []

    def run(self):
        try:
            with self.listener:
                client, _ = self.listener.accept()
                with client:
                    magic, rate, ch, depth, bitrate, samples, ver = struct.unpack(
                        "<4s6I", recv_exact(client, 28))
                    assert (magic, rate, ch, depth, bitrate, samples, ver) == (
                        b"SSC1",48000,2,24,328000,864,1)
                    client.sendall(struct.pack("<4sii",b"SSCR",0,9540))
                    while True:
                        (n,) = struct.unpack("<I",recv_exact(client,4))
                        if n == 0:
                            break
                        assert n == 864*2*4
                        pcm=recv_exact(client,n)
                        self.count += 1
                        payload=b"\xff\xee" + bytes([self.count])*14
                        client.sendall(struct.pack("<i",len(payload)) + payload)
        except Exception as exc:
            self.errors.append(exc)


class EncoderClientTests(unittest.TestCase):
    def test_signed_24(self):
        self.assertEqual(signed_24(b"\x00\x00\x00"),0)
        self.assertEqual(signed_24(b"\xff\xff\x7f"),8388607)
        self.assertEqual(signed_24(b"\x00\x00\x80"),-8388608)

    def test_pcm32_frame_16(self):
        pcm=pcm32_frame(struct.pack("<hh",-32768,32767),2,1)
        self.assertEqual(struct.unpack("<ii",pcm),(-8388608,8388352))

    def test_pcm32_frame_24(self):
        pcm=pcm32_frame(b"\x00\x00\x80\xff\xff\x7f",3,1)
        self.assertEqual(struct.unpack("<ii",pcm),(-8388608,8388607))

    def test_pcm32_frame_pads(self):
        self.assertEqual(len(pcm32_frame(b"",2,864)),864*2*4)

    def test_full_mock_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            wavfile=Path(d)/"test.wav"
            outfile=Path(d)/"test.sscf"
            with wave.open(str(wavfile),"wb") as w:
                w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
                w.writeframes(struct.pack("<hh",100,-100)*1000)
            server=MockEncoder()
            server.start()
            result=encode_wav(wavfile,outfile,host="127.0.0.1",
                              port=server.port,bitrate=328000,depth=24,
                              samples=864)
            server.join(timeout=5)
            self.assertFalse(server.errors)
            self.assertEqual(server.count,2)
            self.assertEqual(result,(2,32))
            data=outfile.read_bytes()
            (magic,ver,rate,ch,depth,bitrate,samples,nframes,valid) = \
                struct.unpack_from("<4s8I",data,0)
            self.assertEqual((magic,ver,rate,ch,depth,bitrate,samples,nframes,valid),
                             (b"SSCF",1,48000,2,24,328000,864,2,1000))
            n1,v1=struct.unpack_from("<2I",data,36)
            self.assertEqual((n1,v1),(16,864))
            n2,v2=struct.unpack_from("<2I",data,60)
            self.assertEqual((n2,v2),(16,136))
            self.assertEqual(len(data),84)


if __name__=="__main__":
    unittest.main()
