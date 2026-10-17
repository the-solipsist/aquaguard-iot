#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("AQUAGUARD_BASE", "https://www.eurekaforbes.com")
CONF_DIR = os.path.expanduser("~/.config/aquaguard")
CONF = os.path.join(CONF_DIR, "session.json")


def load_conf():
    try:
        with open(CONF) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_conf(conf):
    os.makedirs(CONF_DIR, exist_ok=True)
    fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(conf, f, indent=2)


def request(method, path, data=None, session=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("app-version", "440")
    req.add_header("platform", "android")
    req.add_header("event_source", "customer_app")
    req.add_header("userAgent", "MOBILE")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("Cookie", "sessionHash=" + session)
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def need_session(conf):
    sid = conf.get("session_id")
    if not sid:
        sys.exit("no session; run: aquaguard.py login <mobile>")
    return sid


def device_id(conf):
    if conf.get("device_id"):
        return conf["device_id"]
    conf["device_id"] = uuid.uuid4().hex
    save_conf(conf)
    return conf["device_id"]


def resolve_account(sid, serial):
    code, data = request("GET", "/api/v1/assets", session=sid)
    if code != 200:
        sys.exit(f"assets failed: {code} {data}")
    assets = data.get("data", {}).get("assets", [])
    if serial:
        for a in assets:
            if a.get("serialNumber") == serial:
                return a
        sys.exit(f"serial {serial} not found in account")
    if len(assets) != 1:
        sys.exit("multiple assets; pass --serial")
    return assets[0]


def cmd_login(args):
    conf = load_conf()
    conf["device_id"] = args.device_id or device_id(conf)
    if not args.otp:
        code, data = request("POST", "/api/public/ecom/v1/otp/send",
                             {"mobile_number": args.mobile})
        if code != 200:
            sys.exit(f"otp send failed: {code} {data}")
        print("OTP sent.", file=sys.stderr)
        otp = input("Enter OTP: ").strip()
    else:
        otp = args.otp
    body = {
        "mobile_number": args.mobile,
        "otp": int(otp),
        "userAgent": "MOBILE",
        "deviceUniqueId": conf["device_id"],
    }
    code, data = request("POST", "/api/public/ecom/v1/otp/verify", body)
    if code != 200:
        sys.exit(f"otp verify failed: {code} {data}")
    conf["session_id"] = data["data"]["session_id"]
    conf["mobile"] = args.mobile
    save_conf(conf)
    print(conf["session_id"])


def cmd_logout(args):
    conf = load_conf()
    conf.pop("session_id", None)
    save_conf(conf)
    print("session cleared")


def cmd_assets(args):
    sid = need_session(load_conf())
    code, data = request("GET", "/api/v1/assets", session=sid)
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_status(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    path = f"/api/iot/device/monitoring/status/{asset['accountId']}/{asset['serialNumber']}"
    code, data = request("GET", path, session=sid)
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_consumption(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    path = f"/api/iot/device/monitoring/consumption-report/{asset['serialNumber']}"
    code, data = request("GET", path, session=sid, params={"page": args.page})
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_device(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    out = {
        "serialNumber": asset.get("serialNumber"),
        "name": asset.get("name"),
        "accountId": asset.get("accountId"),
        "assetId": asset.get("id"),
        "materialId": asset.get("materialId"),
        "isAtdsEnabled": asset.get("isAtdsEnabled"),
        "iot": asset.get("iot"),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_firmware(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    mac = args.mac or (asset.get("iot") or {}).get("part_mac_id")
    if not mac:
        sys.exit("no MAC found (asset has no iot.part_mac_id); pass --mac")
    code, data = request("GET", "/api/iot/device/firmware/" + mac, session=sid)
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_reconfigure(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    body = {
        "account_id": asset["accountId"],
        "product_serial_no": asset["serialNumber"],
        "request_id": str(uuid.uuid4()),
    }
    code, data = request("POST", "/api/iot/device/setting/reconfigure", body, session=sid)
    print(json.dumps(data, indent=2))
    return 0 if code in (200, 201, 202) else 1


def cmd_extras(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    code, data = request("GET", "/api/iot/device/extras/custom-attributes",
                         session=sid, params={"serialNo": asset["serialNumber"]})
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_onboard(args):
    conf = load_conf()
    sid = need_session(conf)
    asset = resolve_account(sid, args.serial)
    code, data = request("GET", "/api/iotDevice/on-boarding-status",
                         session=sid, params={"iot_device_serial_no": asset["serialNumber"]})
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_weather(args):
    conf = load_conf()
    sid = need_session(conf)
    code, data = request("GET", "/api/iot/weather/" + urllib.parse.quote(args.query, safe=","),
                         session=sid)
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def cmd_get(args):
    conf = load_conf()
    sid = need_session(conf)
    params = dict(p.split("=", 1) for p in args.query) if args.query else None
    code, data = request("GET", args.path, session=sid, params=params)
    print(json.dumps(data, indent=2))
    return 0 if code == 200 else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="aquaguard.py", description="Eureka Forbes / Aquaguard cloud client")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("login", help="OTP login, stores session")
    pl.add_argument("mobile")
    pl.add_argument("--otp", help="skip prompt (integer)")
    pl.add_argument("--device-id", help="deviceUniqueId override")
    pl.set_defaults(func=cmd_login)

    sub.add_parser("logout").set_defaults(func=cmd_logout)

    pa = sub.add_parser("assets", help="list account assets")
    pa.set_defaults(func=cmd_assets)

    ps = sub.add_parser("status", help="device online status + total consumption")
    ps.add_argument("--serial")
    ps.set_defaults(func=cmd_status)

    pc = sub.add_parser("consumption", help="daily consumption / TDS / filter life")
    pc.add_argument("--serial")
    pc.add_argument("--page", type=int, default=1)
    pc.set_defaults(func=cmd_consumption)

    pe = sub.add_parser("extras", help="custom attributes")
    pe.add_argument("--serial")
    pe.set_defaults(func=cmd_extras)

    pd = sub.add_parser("device", help="asset + iot block (MAC, SSID, UUIDs)")
    pd.add_argument("--serial")
    pd.set_defaults(func=cmd_device)

    pf = sub.add_parser("firmware", help="controller/iot firmware versions")
    pf.add_argument("--serial")
    pf.add_argument("--mac")
    pf.set_defaults(func=cmd_firmware)

    pr = sub.add_parser("reconfigure", help="trigger device WiFi reset (setup/AP mode) [disruptive]")
    pr.add_argument("--serial")
    pr.set_defaults(func=cmd_reconfigure)

    po = sub.add_parser("onboard", help="onboarding status")
    po.add_argument("--serial")
    po.set_defaults(func=cmd_onboard)

    pw = sub.add_parser("weather", help="weather by 'lat,lng' | pincode | city")
    pw.add_argument("query")
    pw.set_defaults(func=cmd_weather)

    pg = sub.add_parser("get", help="raw authenticated GET")
    pg.add_argument("path")
    pg.add_argument("--query", nargs="*", help="key=value pairs")
    pg.set_defaults(func=cmd_get)

    args = p.parse_args(argv)
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
