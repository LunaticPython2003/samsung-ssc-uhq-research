# instructions.md — locating and extracting the Samsung SSC libraries

These steps document the exact environment used for the SSC UHQ research. Work only on devices you own or have authorization to inspect.

## Tested environment and root provenance

- Phone: Samsung Galaxy Z Fold7, model SM-F966B, Android 17 / One UI 9 at the time of the research.
- Root: **temporary root was obtained on this device using DirtyFrag**. The analysis ran from `adb shell su -c ...` with a kernel-assisted root context; the bootloader remained locked. DirtyFrag itself is not included here.
- Temporary root availability depends on firmware, patch level and device state. These notes **do not claim DirtyFrag works on all devices, and do not provide exploit steps**. Obtain and verify appropriate root access separately before attempting protected-file extraction.
- Tools on Windows: `adb` (Android Platform Tools), PowerShell, Ghidra for static analysis; Termux `clang` was present on the phone for building the native test probe.

### 1. Verify the phone and root

In Windows PowerShell:

```powershell
adb devices -l
adb shell id
adb shell su -c id
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
```

`adb shell su -c id` should show UID 0 for the authorized root shell. It is **not necessary to use `adb root`**. The device may lose temporary root after a full reboot.

### 2. Locate the libraries without changing the device

The following paths were observed on the research device:

| Library | Observed device path | Why it matters |
| --- | --- | --- |
| `libScalable_Encoder.so` | `/system/lib64/libScalable_Encoder.so` | Original ARM64 SSC software encoder |
| `libScalable_Encoder.so` | `/apex/com.android.bt/lib64/libScalable_Encoder.so` | APEX-provided encoder copy |
| `libbluetooth_jni.so` | `/apex/com.android.bt/lib64/libbluetooth_jni.so` | Android/Samsung Bluetooth stack and SSC A2DP functions |
| `libsehbluetooth_audio_session_aidl.so` | `/vendor/lib64/libsehbluetooth_audio_session_aidl.so` | Samsung audio-session IPC |
| `vendor.samsung.hardware.bluetooth.audio-impl.so` | `/vendor/lib64/vendor.samsung.hardware.bluetooth.audio-impl.so` | Samsung vendor Bluetooth audio implementation |
| `libssc_default_listener.so` | `/vendor/lib64/libssc_default_listener.so` | Qualcomm DSP listener; not the Windows encoder |

List the matching names on your firmware:

```powershell
adb shell su -c 'find /system /system_ext /vendor /odm /product /apex -name libScalable_Encoder.so -o -name libbluetooth_jni.so -o -name libsehbluetooth_audio_session_aidl.so -o -name vendor.samsung.hardware.bluetooth.audio-impl.so -o -name libssc_default_listener.so'
```

Some `find` implementations print harmless permission-denied messages on protected paths; with working root, inspect the specific paths above directly.

### 3. Pull only the libraries you need

Make a **local-only, ignored** extraction folder:

```powershell
New-Item -ItemType Directory -Force .\vendor-local | Out-Null
adb pull /system/lib64/libScalable_Encoder.so .\vendor-local\libScalable_Encoder.so
adb pull /apex/com.android.bt/lib64/libbluetooth_jni.so .\vendor-local\libbluetooth_jni.so
adb pull /vendor/lib64/libsehbluetooth_audio_session_aidl.so .\vendor-local\libsehbluetooth_audio_session_aidl.so
adb pull /vendor/lib64/vendor.samsung.hardware.bluetooth.audio-impl.so .\vendor-local\vendor.samsung.hardware.bluetooth.audio-impl.so
adb pull /vendor/lib64/libssc_default_listener.so .\vendor-local\libssc_default_listener.so
```

Read-only direct `adb pull` will work when the files are accessible to `adbd`. If a vendor library is blocked from `adb pull` but `su` can read it, you can copy that individual library to a temporary, root-controlled extraction directory and pull the copy. **Do not change the permissions or ownership of the original system/vendor files, or remount partitions read/write.**

Example for a library you are authorized to extract:

```powershell
adb shell su -c 'mkdir -p /data/local/tmp/ssc-export'
adb shell su -c 'cp /vendor/lib64/libssc_default_listener.so /data/local/tmp/ssc-export/'
adb shell su -c 'chmod 0644 /data/local/tmp/ssc-export/libssc_default_listener.so'
adb pull /data/local/tmp/ssc-export/libssc_default_listener.so .\vendor-local\
adb shell su -c 'rm /data/local/tmp/ssc-export/libssc_default_listener.so'
```

The fallback temporarily writes a **copy** under `/data/local/tmp`, not the underlying firmware.

### 4. Fingerprint and inspect what you extracted

```powershell
Get-FileHash .\vendor-local\libScalable_Encoder.so -Algorithm SHA256
python .\inspect_elf.py .\vendor-local
```

The original encoder version analyzed during this project had SHA-256:

```text
90C4C1CBD59B0EDB9DF6D255ACC1F752E542E0CB99D3DE8E842AFC7CA9914CE7
```

Your hash may differ if firmware changed. For static reverse engineering, use the Ghidra scripts in `ghidra-scripts/`. The actual entry-point ABI still requires device-specific testing; the decompiler's argument types are not authoritative.

### 5. Run an isolated encoder test, if appropriate

With Termux's `clang` already available on the rooted device:

```powershell
adb push .\ssc_arm64_probe.c /data/local/tmp/ssc_arm64_probe.c
adb shell su -c '/data/data/com.termux/files/usr/bin/clang /data/local/tmp/ssc_arm64_probe.c -O1 -Wall -Wextra -lm -ldl -o /data/local/tmp/ssc_arm64_probe'
adb shell su -c '/data/local/tmp/ssc_arm64_probe info 48000 2 24'
adb shell su -c '/data/local/tmp/ssc_arm64_probe encode 96000 2 24 584000 864 2'
```

This generates **synthetic** test data, calls the device's original library, and checks buffer guards. It does not pair earbuds, alter Bluetooth settings, or write firmware.

### 6. Private-data and redistribution precautions

- **Do not commit or redistribute extracted `.so` files**, proprietary firmware, device storage dumps, or full Ghidra decompilations from proprietary binaries.
- Keep HCI snoop logs and bugreports private: they may include Bluetooth addresses, pairing-related data and unrelated application activity. Prefer `ssc_live_report.py` to export a minimal anonymized codec profile.
- Keep `vendor-local/`, `*.sscf`, audio test files, build artifacts and Ghidra project databases outside version control.
- The reported research result is an encoder bridge, **not** an unlocked bootloader, Windows Bluetooth driver, or confirmed on-air SSC stream.
