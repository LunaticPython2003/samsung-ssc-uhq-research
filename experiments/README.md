# Experimental native Android SSC rate override

**Restricted to the exact Fold7 Bluetooth JNI library analyzed on November 4, 2026.**
This is a research experiment on the user's own temporarily rooted phone, **not a firmware patch, codec driver, or permanent quality setting**.

Files:
- `read_ssc_table.c`: read-only verification of the JNI module's four-entry UHQ2 table in the live Bluetooth process.
- `inspect_ssc_globals.c`: read-only inspection of the desired/applied SSC rate and table. `DAT_` addresses incorporate Ghidra's image-base offset; do not re-use on another build.
- `native_ssc_temp_override.c`: temporarily sets **table index 1** from 584000 to **886000**, checks readback, restores the original value after a bounded 250–5000-ms duration and starts a backup rollback watchdog. Does not change on-disk system files.

**Safety requirements:** Confirm the exact ELF hash and current table before every experiment. Keep ADB connected and be prepared for Bluetooth audio dropouts or a temporary Bluetooth process restart. If the link-quality index is not **1**, the override may have *no effect*. A previous index-2 run still selected 291000. Never hardcode this rate override into an always-on boot service.

Example for the **already verified** phone firmware, using Termux's on-device Clang:

```bash
adb push experiments/read_ssc_table.c /data/local/tmp/read_ssc_table.c
adb push experiments/native_ssc_temp_override.c /data/local/tmp/native_ssc_temp_override.c
adb shell su -c '/data/data/com.termux/files/usr/bin/clang -O2 /data/local/tmp/read_ssc_table.c -o /data/local/tmp/read_ssc_table'
adb shell su -c '/data/data/com.termux/files/usr/bin/clang -O2 /data/local/tmp/native_ssc_temp_override.c -o /data/local/tmp/native_ssc_temp_override'
# Read-only check before making any change:
adb shell su -c '/data/local/tmp/read_ssc_table $(pidof com.android.bluetooth)'
# Short transient experiment, only with informed acceptance of disconnect risk:
adb shell su -c '/data/local/tmp/native_ssc_temp_override $(pidof com.android.bluetooth) 1500'
# Independently verify rollback:
adb shell su -c '/data/local/tmp/read_ssc_table $(pidof com.android.bluetooth)'
```

See the [complete research report](../docs/fold7-native-ssc-e4-live-override-2026-11-04.md).

During the successful index-1 test, Samsung's native sender logged 95 decisions selecting 886000 and Android submitted a 1012-byte AVDTP/L2CAP media payload. The Buds' **actual decoding and audible playback are not yet verified**.
