# Native Fold7 → Buds4 Pro SSC UHQ playback: verbose live capture

**Date:** Wednesday, November 4, 2026 (phone's local clock, Asia/Kolkata).  
**Machine:** user's personal Linux workstation running CatDesk Personal and ADB.  
**Phone:** Samsung Galaxy Z Fold7 SM-F966B, Android 17, firmware F966BXXUCCZIH.  
**Method:** passive ADB `logcat -d`, `dumpsys bluetooth_manager`, `dumpsys audio`, secure/system property reads and btsnooz summary. No codec forcing, Bluetooth service restart, device disconnection or raw audio/HCI payload collection.

## Established during *real* lossless-source playback

At **18:43:41.807**, the **actual native Samsung SSC encoder** logged:

`new bitrate 584000, previous bitrate 0`.

The same session showed a 96-kHz frame encoder at radio-quality index 1 and continued producing frames while the user's Buds4 Pro were connected. The phone's A2DP service reported:

- selected `codecName: SSC`, Android codec type `8`;
- `mSampleRate: 0x8(96000)`;
- `mBitsPerSample: 0x8(8_24)` (24-bit);
- `mChannelMode: 0x2(STEREO)`;
- available alternative codecs AAC and SBC.
- AudioService recorded a playback source with a **96-kHz** audio output format at 18:43:41.536. This is an *Android output format*, not independent evidence that the originating file is natively lossless.

Verbose Samsung stack logs repeatedly reported:
- `a2dp_vendor_ssc_send_frames: sample rate : 96000`;
- `a2dp_ssc_encode_frames: bitrate_idx 1 bit_rate 584000`;
- `a2dp_ssc_encode_frames: nb_frame 1 ... bit rate 584000`;
- `A2DP_ParseInfoSsc: codec info[00000075] codecid[0103] ...`;
- `A2DP_VendorUsesRtpHeaderSsc` and `A2DP_VendorGetPacketTimestampSsc`.

These are direct native **software encoder and packetization path** logs, not merely a codec-capability listing or an offline harness.

### Quantitative snapshots

Two separate overlapping, **rolling logcat ring-buffer snapshots** were analyzed. Do **not add their counters**, as most messages are present in both samples.

| Snapshot | Sender bitrate-index messages | 584,000-bps selections | Any 886,000-bps selection | Vendor CIE reports |
|---|---:|---:|---:|---:|
| First, through ~18:46:00 | 7,085 | 7,085 | 0 | 7,872 |
| Second, through ~18:49:09 | 7,371 | 7,371 | 0 | 8,190 |

Both snapshots showed rate-table index **1** consistently. The native `a2dp_ssc_encode_frames` tags establish that SSC frames were being generated with bitrate selection 584,000. Quality-level summaries reported **level 1**, 96,000 Hz, without bitrate limiting flags.

The initial startup transition `0 -> 584000` was present in the first capture but had already rolled out of the logcat ring when the later analysis ran. **No later transition to 886k was observed**. This establishes stock Samsung transmitter behavior **during this particular session**, not universal impossibility of 886k.

## Newly relevant native Android properties

The device reported:

```text
[log.tag.bluetooth]: [verbose]
[persist.bluetooth.btsnooplogmode]: [full]
[persist.bluetooth.btsnoopsocket.enabled]: [true]
[persist.bluetooth.samsung.a2dp.cap]: [SBC,AAC,APTX,LDAC,SSC,UHQ]
[persist.bluetooth.samsung.a2dp.version]: [1.3]
[persist.bluetooth.samsung.a2dp_offload.cap]: [sbc-aptx-ssc-hifi]
[persist.bluetooth.a2dp_offload.disabled]: [false]
[ro.bluetooth.a2dp_offload.supported]: [true]
[vendor.audio.feature.a2dp_offload.enable]: [true]
```

These settings **differentiate the offered software codec set (includes UHQ) from an offload-capability list (includes SSC HiFi)**. They support an offload-vs-software hypothesis but do NOT prove which hardware/DSP component is encoding each transport. The repeated native `a2dp_ssc_encode_frames` messages show the software sender function was active in this run. `A2dpOffloadEnabled: true` in dumpsys is global availability, **not proof the currently playing SSC stream was offloaded**.

## HCI / MTU limitation

The existing `ssc_btsnooz.py --adb` parser successfully read Samsung's in-memory BTSNOOP_LOG_SUMMARY, finding 6,990 records. The event-only summary contained:

- incoming HCI events and outgoing controller commands;
- **zero ACL audio-data records**;
- no AVDTP codec negotiation candidates.

The user has already enabled verbose logging and full HCI snoop mode. However, no readable full btsnoop file was found under the inspected `/data/misc/bluetooth/logs`, `/data/vendor/bluetooth`, selected `/sdcard` paths, and `/proc/net/unix` showed no accessible snoop socket by name. We therefore **did not** extract an on-air SSC RTP payload or a newly measured peer MTU.

The previously reported Android HAL `peerMtu=1005` remains prior-session evidence, **not newly confirmed in this playback**. We should not claim a measured 584-kbps over-the-air bit count solely from the software encoder rate, although the frame-encode and RTP scheduling log messages make actual SSC packetization clear.

## Interpretation of 886kbps

The original Samsung encoder had already been experimentally verified to generate a complete 1000-byte `E4` frame at 96kHz, unlike an unrecognized arbitrary bitrate. **The current stock Android UHQ2 sender did not select that rate**: all >7k decisions in each rolling snapshot use index 1 and 584,000 bps, and its static table is still `[584000,584000,291000,152000]`.

This live result does not prove E4 is unplayable or unsupported by every Buds firmware/DSP path. It does establish that **playing lossless-source audio with UHQ enabled does not by itself unlock E4**. To test receiver support, a separate validated 886kbps packet-transmission experiment would still be required.

## Files and reproduction

Safe, metadata-only tooling:
```bash
python3 scripts/report_native_ssc_playback.py --start "11-04 18:43:41" --output tools/native_ssc_session.json
python3 ssc_live_report.py --adb -o tools/ssc_playing_live.json
python3 ssc_btsnooz.py --adb -o tools/ssc_playing_btsnooz.json
```

These scripts do not change Bluetooth configuration. The new session parser holds raw `logcat`/`dumpsys` in memory and writes only aggregated, anonymized metadata to the gitignored `tools/` directory. Any future raw HCI captures should be treated as private because they can contain addresses, traffic, and potentially plaintext metadata.

The experiment is complete; the user can stop playback. No audio driver, controller, buds firmware or system setting was modified during capture.
