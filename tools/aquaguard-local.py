#!/usr/bin/env python3
import argparse
import asyncio
import json
import socket
import sys

BT_BASE = "-0000-1000-8000-00805f9b34fb"
DEFAULT_SVC = "00ff"
DEFAULT_CHAR = "ff01"
WIFI_HOST = "15.150.15.1"
WIFI_PORT = 3333

RAW = {
    "meta": '{"type":"RMETA"}',
    "wifi-status": '{"type":"RD_WIFI_STATUS"}',
    "setup-complete": '{"type": "SETUP_COMPLETE"}',
}


def payload(op, args):
    if op in RAW:
        return RAW[op]
    if op == "set-wifi":
        return '{"type": "ST_WIFI_CRD","SSID": "%s","PASS": "%s"}' % (args.ssid, args.password)
    if op == "set-serial":
        if not args.psno:
            raise SystemExit("--psno required")
        return '{"type": "ST_PR_SNO", "PSNO": "%s"}' % args.psno
    raise SystemExit(f"unknown op: {op}")


def full_uuid(short, base=BT_BASE):
    s = short.lower().replace("-", "")
    if len(s) == 32:
        return "-".join(s[i:i + 8] for i in (0, 8, 12, 16, 20)).rstrip("-")
    if len(s) == 4:
        return "0000" + s + base
    if len(s) == 8:
        return s + base
    return short


def wifi_send(frame, host, port, timeout):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(frame.encode())
        buf = b""
        s.settimeout(timeout)
        while not buf.endswith(b"}"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    return buf.decode(errors="replace")


async def ble_send(frame, address, svc, char, timeout):
    from bleak import BleakClient

    svc_full = full_uuid(svc)
    char_full = full_uuid(char)
    got = bytearray()
    done = asyncio.Event()

    def on_notify(_, data):
        got.extend(data)
        if bytes(got).rstrip().endswith(b"}"):
            done.set()

    async with BleakClient(address, timeout=timeout) as client:
        target_svc = client.services.get_service(svc_full)
        target_char = target_svc.get_characteristic(char_full)
        await client.start_notify(target_char, on_notify)
        await client.write_gatt_char(target_char, frame.encode(), response=False)
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        await client.stop_notify(target_char)
    return bytes(got).decode(errors="replace")


def do_ble(args):
    frame = payload(args.op, args)
    raw = asyncio.run(ble_send(frame, args.address, args.svc, args.char, args.timeout))
    print(raw)


def do_wifi(args):
    frame = payload(args.op, args)
    print(wifi_send(frame, args.host, args.port, args.timeout))


def do_scan(args):
    from bleak import BleakScanner

    async def run():
        devs = await BleakScanner.discover(timeout=args.timeout)
        for d in devs:
            name = d.name or ""
            if args.name and args.name.lower() not in name.lower():
                continue
            print(f"{d.address}  {name}  rssi={d.rssi}")

    asyncio.run(run())


def main(argv=None):
    p = argparse.ArgumentParser(prog="aquaguard-local.py",
                                description="Direct BLE / soft-AP control of an Aquaguard purifier")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="BLE scan")
    ps.add_argument("--name", default="Aquaguard")
    ps.add_argument("--timeout", type=float, default=10.0)
    ps.set_defaults(func=do_scan)

    def add_op_args(sp):
        sp.add_argument("op", choices=[*RAW, "set-wifi", "set-serial"])
        sp.add_argument("ssid", nargs="?")
        sp.add_argument("password", nargs="?")
        sp.add_argument("--psno")
        sp.add_argument("--timeout", type=float, default=15.0)

    pb = sub.add_parser("ble", help="send a command over BLE GATT")
    pb.add_argument("address")
    pb.add_argument("--svc", default=DEFAULT_SVC)
    pb.add_argument("--char", default=DEFAULT_CHAR)
    add_op_args(pb)
    pb.set_defaults(func=do_ble)

    pw = sub.add_parser("wifi", help="send a command over the soft-AP TCP socket")
    pw.add_argument("op", choices=[*RAW, "set-wifi", "set-serial"])
    pw.add_argument("ssid", nargs="?")
    pw.add_argument("password", nargs="?")
    pw.add_argument("--psno")
    pw.add_argument("--host", default=WIFI_HOST)
    pw.add_argument("--port", type=int, default=WIFI_PORT)
    pw.add_argument("--timeout", type=float, default=15.0)
    pw.set_defaults(func=do_wifi)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
