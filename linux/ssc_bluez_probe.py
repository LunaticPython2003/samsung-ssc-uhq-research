#!/usr/bin/env python3
"""Read-only BlueZ introspection and opt-in *passive* SSC A2DP source endpoint.

Default:
    python3 linux/ssc_bluez_probe.py
    (only introspects BlueZ D-Bus; does not register or pair)

Opt-in temporary endpoint:
    python3 linux/ssc_bluez_probe.py --register --codec-id 0x0103 --flags 0x8a

IMPORTANT: This is not SSC streaming. It advertises a *candidate* source
endpoint so we can log peer codec capabilities during SelectConfiguration.
The callback always rejects selection and never acquires a media fd or
sends audio. It unregisters on exit. The exact on-air codec ID and features
are not yet verified. Never change a working audio configuration to use
this until independent HCI evidence supports the negotiation.

This can only be run from a desktop shell with access to the system D-Bus
socket; CatDesk's isolated shell intentionally lacks that access.
"""
from __future__ import annotations

import argparse
import json
import sys

A2DP_SOURCE_UUID = "0000110a-0000-1000-8000-00805f9b34fb"
MEDIA1 = "org.bluez.Media1"
ENDPOINT1 = "org.bluez.MediaEndpoint1"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
VENDOR_ID = 0x75
CODEC_IDS = (0x0103, 0x0E03)
OBJECT_PATH = "/org/ssc_research/passive_endpoint"


def vendor_info(payload: bytes) -> dict | None:
    """Return vendor codec fields, never device identifiers or raw frames."""
    if len(payload) == 10 and payload[:3] == bytes([9, 0, 0xFF]):
        payload = payload[3:]
    if len(payload) < 7:
        return None
    vendor = int.from_bytes(payload[:4], "little")
    codec = int.from_bytes(payload[4:6], "little")
    if vendor != VENDOR_ID or codec not in CODEC_IDS:
        return None
    flags = payload[6]
    return {
        "vendor_id": f"0x{vendor:08x}",
        "codec_id": f"0x{codec:04x}",
        "flags": f"0x{flags:02x}",
        "96khz_advertised": bool(flags & 0x80),
        "uhq2_feature": bool(flags & 0x02),
        "unrestricted_feature": bool(flags & 0x08),
    }


def describe_bluez_objects(objects) -> dict:
    """Anonymized system-bus scan; deliberately suppresses device addresses."""
    adapters = 0
    endpoints = 0
    candidates: list[dict] = []
    for _, interfaces in objects.items():
        if "org.bluez.Adapter1" in interfaces:
            adapters += 1
        if ENDPOINT1 in interfaces:
            endpoints += 1
            props = interfaces[ENDPOINT1]
            info = vendor_info(bytes(props.get("Capabilities", [])))
            if info is not None:
                candidates.append(info)
    return {
        "bluez_adapter_count": adapters,
        "remote_or_local_endpoint_count": endpoints,
        "samsung_ssc_endpoint_candidates": candidates,
        "note": "Remote SEPs may not be exposed in ObjectManager until an appropriate connection; no configuration changes performed.",
    }


def dbus_probe(register: bool, codec_id: int, flags: int, lifetime_seconds: int) -> dict | None:
    try:
        import dbus
        import dbus.service
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as exc:
        raise RuntimeError("Requires the distro python3-dbus and python3-gi packages") from exc

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), OBJECT_MANAGER)
    devices = manager.GetManagedObjects()
    summary = describe_bluez_objects(devices)
    print(json.dumps(summary, indent=2), flush=True)
    if not register:
        return summary

    adapter_paths = [str(p) for p, v in devices.items() if "org.bluez.Adapter1" in v]
    if not adapter_paths:
        raise RuntimeError("No BlueZ adapter on system D-Bus")
    path = adapter_paths[0]
    media = dbus.Interface(bus.get_object("org.bluez", path), MEDIA1)
    mainloop = GLib.MainLoop()

    class PassiveSscEndpoint(dbus.service.Object):
        @dbus.service.method(ENDPOINT1, in_signature="ay", out_signature="ay")
        def SelectConfiguration(self, capabilities):
            info = vendor_info(bytes(capabilities))
            print(json.dumps({"callback": "SelectConfiguration",
                              "peer_codec": info or "not recognized SSC",
                              "result": "rejected: no verified SSC media packetizer"}), flush=True)
            raise dbus.exceptions.DBusException(
                "SSC transport is disabled while AVDTP framing remains unverified",
                name="org.bluez.Error.Rejected",
            )

        @dbus.service.method(ENDPOINT1, in_signature="oa{sv}", out_signature="")
        def SetConfiguration(self, transport, properties):
            print('{"callback":"SetConfiguration","result":"rejected (passive only)"}', flush=True)
            raise dbus.exceptions.DBusException(
                "SSC media streaming deliberately disabled",
                name="org.bluez.Error.NotSupported",
            )

        @dbus.service.method(ENDPOINT1, in_signature="o", out_signature="")
        def ClearConfiguration(self, transport):
            print('{"callback":"ClearConfiguration"}', flush=True)

        @dbus.service.method(ENDPOINT1, in_signature="", out_signature="")
        def Release(self):
            print('{"callback":"Release"}', flush=True)
            mainloop.quit()

    endpoint = PassiveSscEndpoint(bus, OBJECT_PATH)
    # A2DP CodecSpecific information = vendor uint32 LE, codec uint16 LE,
    # flags. "Vendor" is the combined tuple, as documented by BlueZ.
    capabilities = (
        VENDOR_ID.to_bytes(4, "little")
        + codec_id.to_bytes(2, "little")
        + bytes([flags])
    )
    props = dbus.Dictionary(
        {
            "UUID": dbus.String(A2DP_SOURCE_UUID),
            "Codec": dbus.Byte(0xFF),
            "Vendor": dbus.UInt32((codec_id << 16) | VENDOR_ID),
            "Capabilities": dbus.Array([dbus.Byte(x) for x in capabilities], signature="y"),
        }, signature="sv"
    )
    registered = False
    try:
        media.RegisterEndpoint(dbus.ObjectPath(OBJECT_PATH), props)
        registered = True
        print(json.dumps({
            "registered": True,
            "codec_id_candidate": f"0x{codec_id:04x}",
            "local_capability_flags_hypothetical": f"0x{flags:02x}",
            "transmission_enabled": False,
            "registration_lifetime_seconds": lifetime_seconds,
        }), flush=True)
        GLib.timeout_add_seconds(lifetime_seconds, lambda: (mainloop.quit(), False)[1])
        mainloop.run()
    finally:
        if registered:
            try:
                media.UnregisterEndpoint(dbus.ObjectPath(OBJECT_PATH))
            except dbus.exceptions.DBusException:
                pass
        endpoint.remove_from_connection()
        print('{"endpoint_cleaned_up":true}', flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true", help="temporarily register a passive, reject-only source endpoint")
    parser.add_argument("--codec-id", type=lambda v: int(v, 0), choices=CODEC_IDS, default=0x0103)
    parser.add_argument("--flags", type=lambda v: int(v, 0), default=0x8A,
                        help="candidate flags only: 0x8a is NOT a verified negotiated value")
    parser.add_argument("--lifetime-seconds", type=int, default=45)
    args = parser.parse_args()
    if not (0 <= args.flags <= 255) or not (1 <= args.lifetime_seconds <= 300):
        parser.error("invalid flags or lifetime")
    try:
        dbus_probe(args.register, args.codec_id, args.flags, args.lifetime_seconds)
    except Exception as exc:
        print(f"BlueZ probe unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Run from the actual Linux desktop session; do not use sudo or replace Bluetooth drivers.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
