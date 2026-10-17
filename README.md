# Aquaguard / Eureka Forbes IoT protocol

Unofficial notes and working clients for **Aquaguard** water purifiers that use the
Eureka Forbes app (`com.efl.eurekaforbes`). Everything here was recovered by
reverse-engineering the app's Flutter AOT binary — there is no public documentation
for any of it.

> **Not affiliated with Eureka Forbes.** For interoperability, research and
> personal use. Use at your own risk; some operations are destructive (see Safety).
> Do not use on equipment you do not own.

## What's here

| File | Contents |
|---|---|
| [`docs/AQUAGUARD_PROTOCOL.md`](docs/AQUAGUARD_PROTOCOL.md) | The protocol: cloud auth, IoT REST endpoints, and the BLE / soft-AP wire protocol |
| [`docs/AQUAGUARD_API_REFERENCE.md`](docs/AQUAGUARD_API_REFERENCE.md) | Every HTTP endpoint in the app (~87 across 32 modules), with methods/params |
| [`docs/AQUAGUARD_RUNBOOK.md`](docs/AQUAGUARD_RUNBOOK.md) | Step-by-step direct-WiFi (setup/AP mode) procedure, rollback and go/no-go checklist |
| `tools/aquaguard.py` | Cloud CLI: login, assets, status, consumption, firmware, weather, onboarding |
| `tools/aquaguard-local.py` | Local BLE / soft-AP TCP client (raw device protocol) |
| `tools/aquaguard-monitor.py` | Poller that alerts on offline / low filter life / high TDS |

No credentials, device identifiers or personal data are included.

## How it works (short version)

- **Cloud:** OTP login (`api/public/ecom/v1/otp/{send,verify}`) returns a `session_id`,
  sent as `Cookie: sessionHash=<id>`. Telemetry is polled (the app has no realtime
  channel; it refreshes every 30 min). Status, consumption, firmware, weather and
  onboarding live under `api/iot/...`.
- **Local:** the purifier exposes a GATT service `00ff` / characteristic `ff01`, and
  in setup mode a TCP socket at `15.150.15.1:3333`. Both speak the same JSON
  messages (`RMETA`, `RD_WIFI_STATUS`, `ST_WIFI_CRD`, `ST_PR_SNO`,
  `SETUP_COMPLETE`). Frames are raw JSON with **no** newline terminator; replies end
  with `}`.

## Quick start

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install requests            # only dependency for the cloud CLI
python3 tools/aquaguard.py login        # reads the OTP SMS or prompts for it
python3 tools/aquaguard.py assets
python3 tools/aquaguard.py status
python3 tools/aquaguard.py consumption
```

The local client additionally needs `bleak` for BLE (WiFi socket mode uses the
standard library):

```sh
pip install bleak
python3 tools/aquaguard-local.py scan
python3 tools/aquaguard-local.py wifi meta --host 15.150.15.1
```

## Safety

- `POST /api/iot/device/setting/reconfigure` and the local `set-wifi` /
  `setup-complete` commands **change the unit's WiFi configuration**. If the
  re-provisioning step fails, the device may need a physical power-cycle and
  re-setup in the official app.
- Read [`docs/AQUAGUARD_RUNBOOK.md`](docs/AQUAGUARD_RUNBOOK.md) before touching
  setup mode, and keep someone on-site who can power-cycle the unit.
- Everything else in this repo is read-only.

## Layout

```
docs/    protocol, full API reference, runbook
tools/   cloud CLI, local BLE/TCP client, monitor
```

## License

MIT (see [LICENSE](LICENSE)).
