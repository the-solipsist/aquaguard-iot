#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import aquaguard

STATE = os.path.expanduser("~/.config/aquaguard/monitor_state.json")
SENDXMPP = os.path.expanduser("~/.local/bin/sendxmpp.sh")


def notify(msg, args):
    if args.dry_run:
        print("[notify]", msg)
        return
    if args.command:
        subprocess.run([*args.command.split(), msg], check=False)
        return
    snd = shutil.which("sendxmpp.sh") or SENDXMPP
    if os.path.exists(snd):
        subprocess.run([snd, msg], check=False)
    else:
        print("[notify]", msg)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)


def collect(sid, serial):
    asset = aquaguard.resolve_account(sid, serial)
    sn = asset["serialNumber"]
    acc = asset["accountId"]
    _, st = aquaguard.request("GET", f"/api/iot/device/monitoring/status/{acc}/{sn}", session=sid)
    _, cr = aquaguard.request("GET", f"/api/iot/device/monitoring/consumption-report/{sn}",
                              session=sid, params={"page": 1})
    data = st.get("data", {}) if isinstance(st, dict) else {}
    rep = (cr.get("data", {}) or {}).get("consumptionReport", {}) if isinstance(cr, dict) else {}
    return asset, data, rep


def evaluate(name, data, rep, args):
    online = data.get("online_status")
    filterlife = rep.get("filterLife")
    tds_out = rep.get("tdsOut")
    tds_in = rep.get("tdsIn")
    checks = {}

    checks["offline"] = (
        online is False,
        f"Aquaguard {name}: purifier is OFFLINE",
        f"Aquaguard {name}: purifier back ONLINE",
    )
    checks["filter"] = (
        filterlife is not None and filterlife <= args.filter_min,
        f"Aquaguard {name}: filter life LOW ({filterlife}% <= {args.filter_min}%)",
        f"Aquaguard {name}: filter life recovered ({filterlife}%)",
    )
    checks["tds"] = (
        tds_out is not None and tds_out >= args.tds_max,
        f"Aquaguard {name}: TDS-out HIGH ({tds_out} >= {args.tds_max}; in={tds_in})",
        f"Aquaguard {name}: TDS-out back to normal ({tds_out})",
    )
    return checks, {"online": online, "filterLife": filterlife, "tdsIn": tds_in, "tdsOut": tds_out}


def run_once(args):
    conf = aquaguard.load_conf()
    sid = conf.get("session_id")
    if not sid:
        sys.exit("no session; run: aquaguard.py login <mobile>")
    asset, data, rep = collect(sid, args.serial)
    name = asset.get("name", asset.get("serialNumber"))
    checks, snap = evaluate(name, data, rep, args)

    state = load_state()
    changed = False
    for rule, (firing, bad_msg, ok_msg) in checks.items():
        was = state.get(rule)
        if firing and was is not True:
            notify(bad_msg, args)
            state[rule] = True
            changed = True
        elif not firing and was is True:
            notify(ok_msg, args)
            state[rule] = False
            changed = True
        elif firing and was is True and args.realert:
            notify(bad_msg, args)
    if (args.notify_ok or args.realert) and not any(f for f, _, _ in checks.values()):
        notify(f"Aquaguard {name}: OK (online={snap['online']} filter={snap['filterLife']}% "
               f"tdsIn={snap['tdsIn']} tdsOut={snap['tdsOut']})", args)
    if changed:
        save_state(state)

    print(json.dumps({"asset": name, **snap,
                      "alerts": {r: v[0] for r, v in checks.items()}}, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="aquaguard-monitor.py",
                                description="Poll an Aquaguard purifier and alert on problems")
    p.add_argument("--serial")
    p.add_argument("--filter-min", type=float, default=10.0, help="alert when filterLife <= this %%")
    p.add_argument("--tds-max", type=float, default=500.0, help="alert when tdsOut >= this")
    p.add_argument("--realert", action="store_true", help="re-send active alerts every run")
    p.add_argument("--notify-ok", action="store_true", help="also send a heartbeat OK message")
    p.add_argument("--command", help="override notifier command (message appended)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--interval", type=float, help="loop every N seconds instead of one-shot")
    args = p.parse_args(argv)

    if args.interval:
        while True:
            try:
                run_once(args)
            except Exception as e:
                print("error:", e, file=sys.stderr)
            time.sleep(args.interval)
    else:
        sys.exit(run_once(args))


if __name__ == "__main__":
    main()
