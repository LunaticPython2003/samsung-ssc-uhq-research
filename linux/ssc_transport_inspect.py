#!/usr/bin/env python3
"""Read-only BlueZ media transport and Samsung vendor codec diagnostics.

Run in user's *normal* Linux desktop session, where /run/dbus/system_bus_socket
exists. Never acquires a transport, pairs a device, starts a stream or touches
the system Bluetooth configuration. Suppresses addresses and identifying paths.

A Bluetooth *write MTU* is not exposed as a passive D-Bus property. It can
only be obtained from MediaTransport1.Acquire() by the process that owns the
negotiated transport, or inferred from a signaling trace with appropriate care.
"""
from __future__ import annotations

import json
import sys

AUDIO_TRANSPORT = "org.bluez.MediaTransport1"
MEDIA_ENDPOINT = "org.bluez.MediaEndpoint1"
ADAPTER = "org.bluez.Adapter1"
VENDOR_ID = 0x75
CODEC_ID = 0x0103


def summarize(managed: dict) -> dict:
    report={"bluetooth_adapters":0,"active_or_known_transports":0,
            "transports":[],"vendor_endpoints":[],"write_mtu":"requires live Acquire()"}
    for interfaces in managed.values():
        if ADAPTER in interfaces:
            report["bluetooth_adapters"]+=1
        for kind in (MEDIA_ENDPOINT,AUDIO_TRANSPORT):
            if kind not in interfaces:continue
            p=interfaces[kind]
            code=int(p.get("Codec",-1))
            entry={"codec":hex(code) if code>=0 else None}
            config=bytes(p.get("Configuration",p.get("Capabilities",[])))
            if code==0xff and len(config)>=7:
                vendor=int.from_bytes(config[:4],"little")
                codec=int.from_bytes(config[4:6],"little")
                entry["vendor_id"]=f"0x{vendor:08x}"
                entry["vendor_codec_id"]=f"0x{codec:04x}"
                entry["sam_ssc"]=vendor==VENDOR_ID and codec==CODEC_ID
                entry["feature_byte"]=f"0x{config[6]:02x}" if entry["sam_ssc"] else None
            if kind==AUDIO_TRANSPORT:
                entry["state"]=str(p.get("State","unknown"))
                entry["a2dp_source"]=str(p.get("UUID","")).lower()=="0000110a-0000-1000-8000-00805f9b34fb"
                report["transports"].append(entry)
                report["active_or_known_transports"]+=1
            elif entry.get("sam_ssc"):
                report["vendor_endpoints"].append(entry)
    return report


def main()->int:
    try:
        import dbus
        bus=dbus.SystemBus()
        manager=dbus.Interface(bus.get_object("org.bluez","/"),"org.freedesktop.DBus.ObjectManager")
        managed=manager.GetManagedObjects()
        print(json.dumps(summarize(managed),indent=2))
    except Exception as exc:
        print(f"BlueZ D-Bus unavailable here: {type(exc).__name__}: {exc}",file=sys.stderr)
        print("Run this from a real Zorin desktop terminal (not a sandbox or container).",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
