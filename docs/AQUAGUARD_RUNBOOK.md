# Aquaguard direct-WiFi (setup/AP mode) runbook

Purpose: talk to the purifier over its soft-AP socket instead of the cloud.
**This temporarily takes the unit off the home Wi-Fi.** Run it only with someone
able to power-cycle the purifier if recovery fails.

## Target facts

| Item | Value |
|---|---|
| Device | AQUAGUARD ENRICH RITZ PRO ROUVCASS 4X |
| Serial | `3450000000000001` |
| MAC (part) | `AABBCCDDEEFF` |
| AP SSID | `Aquaguard_WP_AABBCC` |
| AP socket | `15.150.15.1:3333` (TCP, raw JSON, no newline terminator) |
| Home Wi-Fi | `<YOUR_WIFI_SSID>` / `<YOUR_WIFI_PASSWORD>` |
| Cloud reset route | `POST /api/iot/device/setting/reconfigure` |

## Why this is risky

- The unit exposes **no local service** while connected to the home Wi-Fi
  (`<DEVICE_LAN_IP>`, no TCP/UDP ports open) — verified. The socket only exists in
  AP/setup mode.
- Entering setup mode drops it off `<YOUR_WIFI_SSID>` → the app and `aquaguard-monitor.py`
  go dark until it is re-provisioned.
- Recovery depends on the `ST_WIFI_CRD` step succeeding on the socket. There is
  **no prior successful run** of that step against a real device, so the first
  attempt is the risky one.
- If it fails, the only fix is physical: power-cycle + re-run setup in the app.

## Go / No-go checklist (all must be true)

- [ ] Someone is physically at the purifier, or can power-cycle it on request.
- [ ] Phone with the Eureka Forbes app is logged in and ready to run device setup.
- [ ] Home SSID/password confirmed: `<YOUR_WIFI_SSID>` / `<YOUR_WIFI_PASSWORD>`.
- [ ] This laptop can manage its own Wi-Fi (`nmcli` works; `sudo` available if needed).
- [ ] Cloud session valid (`python3 aquaguard.py status` returns data), or re-login ready.
- [ ] You accept the unit will be offline until step 7 completes.

## Procedure

Working dir: `~/code/laptop`.

### 0. Baseline
```sh
python3 aquaguard.py status          # expect online_status: true
python3 aquaguard.py firmware        # note versions (expect 1.32 / 1.97)
ping -c1 <DEVICE_LAN_IP>               # device present on LAN
```

### 1. Trigger setup mode
```sh
python3 aquaguard.py reconfigure     # POST /api/iot/device/setting/reconfigure
```
Expect JSON (a `message`), **not** an HTML page. If HTML → STOP, the route is wrong.

### 2. Wait for the AP
```sh
nmcli -f SSID,SIGNAL dev wifi list --rescan yes | grep -i aquaguard
```
Expect `Aquaguard_WP_AABBCC`. If it never appears after ~5 min, STOP (needs manual reset).

### 3. Join the AP from this laptop
```sh
nmcli dev wifi connect 'Aquaguard_WP_AABBCC'      # open AP expected; add password= if prompted
ip -4 addr show wlan0                            # expect 15.150.15.x
ping -c2 15.150.15.1
```
If it asks for a password the AP is not open → STOP and use the phone instead.

### 4. Talk to the device
```sh
python3 aquaguard-local.py wifi meta
```
Expect `META` JSON. **Go/no-go:** the returned `MAC` must equal `AABBCCDDEEFF`;
if not, STOP immediately and go to step 7 anyway to restore Wi-Fi.
```sh
python3 aquaguard-local.py wifi wifi-status
```

### 5. Re-provision (rollback to home Wi-Fi)
```sh
python3 aquaguard-local.py wifi set-wifi "<YOUR_WIFI_SSID>" "<YOUR_WIFI_PASSWORD>"   # expect ACK_WIFI_CRD
python3 aquaguard-local.py wifi set-serial --psno 3450000000000001    # expect ACK_PR_SNO
python3 aquaguard-local.py wifi setup-complete                        # expect SETUP_COMPLETE_ACK
```

### 6. Rejoin home Wi-Fi on this laptop
```sh
nmcli con up <YOUR_WIFI_SSID>
```

### 7. Verify the device is back
```sh
sleep 60; ping -c1 <DEVICE_LAN_IP>
python3 aquaguard.py status          # expect online_status: true
```
If still offline after ~3 min → the unit needs physical/app re-provisioning.

## Failure handling

| Symptom | Action |
|---|---|
| `reconfigure` returns HTML | Wrong route. Do NOT retry blindly; re-check with `GET /api/iot/device/setting/reconfigure` (expect `405`). |
| AP never appears | Device may need a physical reset to enter setup. |
| Laptop can't join AP (password/unsupported) | Do it from the phone: `adb shell cmd wifi connect-network Aquaguard_WP_AABBCC open`, then run the socket via `adb shell`. |
| No `META` / wrong MAC | STOP; go to step 5 to restore Wi-Fi, then re-run at home. |
| `set-wifi` no ACK | Retry once; else stop and re-provision via the app. |
| Device offline after restore | Wait 3 min, then re-provision via the app. |

## Notes

- While on the AP the host has no internet — cloud commands will fail; that's expected.
- `aquaguard-local.py` emits byte-exact frames (spacing matches the app): e.g.
  `{"type":"RMETA"}`, `{"type": "ST_WIFI_CRD","SSID": "<YOUR_WIFI_SSID>","PASS": "<YOUR_WIFI_PASSWORD>"}`,
  `{"type": "ST_PR_SNO", "PSNO": "..."}`, `{"type": "SETUP_COMPLETE"}`.
- Reads complete when a chunk ends with `}` (no newline framing).
