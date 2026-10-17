# Eureka Forbes / Aquaguard IoT Onboarding Protocol

Reverse-engineered from the Android app **`com.efl.eurekaforbes` v440**
(base `com.efl.eurekaforbes-440.apk` + `...-config.arm64_v8a.apk`).

The app is **Flutter (Dart AOT)** — all protocol logic lives in
`lib/arm64-v8a/libapp.so`, so it was recovered with **Blutter**, not JADX/Dex.

> **Full API surface:** this document covers the IoT/device protocol. For every
> endpoint in the app (87 across 32 modules), see
> [`AQUAGUARD_API_REFERENCE.md`](./AQUAGUARD_API_REFERENCE.md).

---

## 1. Summary

Provisioning a purifier happens in two stages:

1. **Pair/transfer** over one of two transports:
   - **BLE (GATT)** — write JSON commands to a characteristic.
   - **WiFi** — the phone joins the purifier's soft-AP and opens a raw TCP
     socket to `15.150.15.1:3333`.
2. **Cloud claim** — after the device returns a `SKEY` in its `RMETA` response,
   the app calls the authenticated onboarding endpoints to register the device
   against the logged-in account.

Wire format is **newline-free UTF-8 JSON** with a `"type"` discriminator.

---

## 2. BLE provisioning

### 2.1 GATT identities

| Role | Default (short) | Full UUID | Config key | Getter |
|---|---|---|---|---|
| Service | `00ff` | `000000ff-0000-1000-8000-00805f9b34fb` | `ble_service_uuid` | `AppConfigBloc::getBleServiceUuid` |
| Characteristic | `ff01` | `0000ff01-0000-1000-8000-00805f9b34fb` | `ble_characteristic_uuid` | `AppConfigBloc::getBleCharacteristicUuid` |

- Defaults come from `AppConfigBloc` (`asm/efl_customer_app/features/app_config/bloc/app_config_bloc.dart:463,550`):
  `getBleCharacteristicUuid()` falls back to `"ff01"`, `getBleServiceUuid()` to `"00ff"`.
- Matching is done on `Guid.str` compared to the configured string. `Guid.str`
  (`asm/flutter_blue_plus_platform_interface/src/guid.dart:228`) collapses a
  standard 128-bit UUID to its 4-hex short form, so the configured value must be
  the short form.
- Only one hardcoded UUID is otherwise present: `00002902-0000-1000-8000-00805f9b34fb`
  (the standard **CCCD**, used to enable notifications).

### 2.2 Discovery & connection

`DeviceDiscoveryBloc` (`.../device_discovery/bloc/device_discovery_bloc.dart`):

- `_searchDeviceViaBluetooth` (`0x81fc64`): `FlutterBluePlus.startScan(timeout: 10s)`
  with **no filter**, collects `ScanResult`s into a name-keyed map, streams them
  to the UI.
- `_searchAndPairDeviceViaWifi` (`0x819cc4`): scans WiFi
  (`wifi_scan`), filtering AP SSIDs by `getSsidPattern()`.
- Pairing (`0x81d5e4` region): `device.discoverServices()` → iterate
  `servicesList()`; match `service.uuid.str == bluetoothServiceSsid`; inside the
  match, iterate characteristics and match `characteristic.uuid.str == bluetoothCharSsid`;
  build `DeviceBluetoothDetails(device, characteristic)`.

### 2.3 JSON commands (app → device)

Written as UTF-8 to the `ff01` characteristic. Exact literal strings:

| Operation | Enum ordinal | Payload |
|---|---|---|
| READ_META | 0 | `{"type":"RMETA"}` |
| READ_WIFI_STATUS | 1 | `{"type":"RD_WIFI_STATUS"}` |
| SET_WIFI_CREDENTIAL | 2 | `{"type": "ST_WIFI_CRD","SSID": "<ssid>","PASS": "<pass>"}` |
| SET_SERIALNO | 3 | `{"type": "ST_PR_SNO", "PSNO": "<serial>"}` |
| SETUP_COMPLETE | 4 | `{"type": "SETUP_COMPLETE"}` |

`SET_WIFI_CRD` is assembled from three literals concatenated with the SSID/password:
`{"type": "ST_WIFI_CRD","SSID": "` + ssid + `","PASS": "` + pass + `"}`.

### 2.4 JSON responses (device → app)

Matched by comparing the decoded map's `"type"` value to the enum name.

| Operation | Enum ordinal | `type` value |
|---|---|---|
| META | 0 | `META` |
| WIFI_STATUS | 1 | `WIFI_STATUS` |
| ACK_WIFI_CRD | 2 | `ACK_WIFI_CRD` |
| ACK_PR_SNO | 3 | `ACK_PR_SNO` |
| SETUP_COMPLETE_ACK | 4 | `SETUP_COMPLETE_ACK` |
| RSP_SSID | 5 | `RSP_SSID` |

Parsing: the raw notified bytes are `jsonDecode`d, then
`List<ProtocolResponseType>.firstWhere(...)` matches the response (predicate
`0x819bc4`). For a `META` response the app reads (`DeviceConnectionBloc::_setMetaInfo`, `0xd2d710`):

| Key | Meaning |
|---|---|
| `SKEY` | device secret key — presence triggers the cloud onboarding-status call |
| `MAC` | device MAC address |
| `CTRL_FW_VER` | controller firmware version |
| `IOT_FW_VER` | IoT module firmware version |
| `STATUS` | device status |
| `ERROR_CODES` | error bitfield/codes |
| `mode` | operating mode |

### 2.5 Advertised / AP name

- WiFi soft-AP SSID pattern default: **`Aquaguard_W`** (`AppConfigBloc::getSsidPattern`,
  `0x8115b0`; config key `ssid_pattern`).

---

## 3. WiFi (soft-AP) transport

`DeviceConnectionBloc::_initiateConnectionViaWifi` (`0xd2c5bc`):

1. `WiFiForIoTPlugin::forceWifiUsage()` — route traffic over the purifier's AP.
2. `Socket.connect("15.150.15.1", 3333)` — **TCP, port 3333**
   (`_startSocketListen` at `0xd2cec0`).

| Field | Value |
|---|---|
| Host | `15.150.15.1` |
| Port | `3333` |
| Paths | `_initiateConnectionViaBluetooth` (`0xd2dbc4`), `_initiateConnectionViaWifi` (`0xd2c5bc`), `sendMessageToPCBViaWifi` (`0xd2c884`), `_startSocketListen` (`0xd2cec0`) |

Socket frames are the **same JSON payloads** as §2.3/§2.4. Reads are accumulated
in chunks (`"Read Chunk: "` debug log; a frame is considered complete when it
ends with `}`).

---

## 4. Transport selector

`DeviceConnectionBloc` constructor (`0xd2b210`) stores:
- `field_33` = `"15.150.15.1"`
- `field_37` = `3333`
- mode strings `"wifi"` / `"bluetooth"`

`DeviceConnectionBloc` command slots: `READ_WIFI_STATUS`=0x4c,
`SET_WIFI_CREDENTIAL`=0x50, `READ_META`=0x54, `SETUP_COMPLETE`=0x58,
`SET_SERIALNO`=0x5c, `pcbIdentifier`=0x60.

Both transports funnel into the same command→JSON switch; the switch selects the
payload from §2.3 by command index and an `AnonymousClosure` (`0xd2df24`,
`_sendMessageToPCBViaBluetooth`) writes it to the characteristic.

---

## 5. Cloud REST endpoints

Discovered from string constants (`libapp.so`). Base URL **`https://www.eurekaforbes.com`**
(config keys `efl_base_url` / `base_urls`), Dio HTTP.

### 5.1 Authentication (verified)

Login is a two-step OTP flow on the **`public/ecom`** endpoints (no prior auth):

1. `POST /api/public/ecom/v1/otp/send`
   body `{"mobile_number": "<10-digit>"}` → `{"data":{"message":"OTP sent!"}}`
2. `POST /api/public/ecom/v1/otp/verify`
   body `{"mobile_number":"<10-digit>","otp":<int>,"userAgent":"MOBILE","deviceUniqueId":"<android_id>"}`
   → `{"data":{"session_id":"<40-hex>","webEngageId":"<40-hex>"}}`

Critical details (all confirmed against the live API):

- **`userAgent` must be the literal `"MOBILE"`** (hardcoded in
  `NetworkServiceImpl::verifyOTP`). Wrong value → `400 invalidParams[userAgent]`.
- **`otp` must be a JSON number, not a string.** A string returns
  `406 "Incorrect OTP"`; the integer yields the real result (`406 "OTP expired."`
  once the code has aged out).
- `deviceUniqueId` is free-form; the device `android_id` works.
- The **only** credential for authenticated calls is
  **`Cookie: sessionHash=<session_id>`**. `Authorization: Bearer <session_id>`
  returns **401**. `request_interceptor.dart` attaches `Authorization: Bearer`,
  `Cookie: sessionHash`, plus `app-version`, `platform`, `android_device_id`,
  `firebase_install_id`, `device_uuid`, `event_source: customer_app`, `ad_id`.
- `otp/send` is **IP-rate-limited** → `429 {"error":"Too many attempts. Try later"}`;
  retry from a different egress IP.

### 5.2 Endpoint catalogue

| Method | Path | Notes |
|---|---|---|
| GET | `api/v1/assets` (alias `api/assets`) | account's assets: `id` (assetId), `accountId`, `deviceId`, `serialNumber`, `name`, `isIotAsset`, … |
| GET | `api/iotDevice/on-boarding-status` | query `iot_device_serial_no=<serial>`; response `{"data":{"isOnboarded":bool}}` (**verified**) |
| POST | `api/iotDevice/saveOnboardingStatus` | body contains `assetId`; `iotDevice/saveOnboardingStatus` |
| GET | `api/iot/device/extras/custom-attributes` | query **`serialNo=<serial>`** (**verified** → `{"data":{}}`) |
| GET | `api/iot/device/firmware/<macId>` | firmware versions (**verified** → `{"macId","controllerFWVersion":1.32,"iotFWVersion":1.97}`); `<macId>` is the asset's `iot.part_mac_id` (serial → `404`) |
| GET | `api/iot/device/health/requests/<requestId>` | poll a health request; `<requestId>` must be a UUID (else `400 "should be valid UUID"`) |
| POST | `api/iot/device/health/requests/atds` | **auto-TDS save** (`saveAutoTds`). Body `{"accountId","productSerialNo","lowerRange","higherRange","requestId":"<uuid-v4>","extras"}` |
| GET | `api/v1/asset-details` | query `assetId`,`accountId`,`productId`,`isIrRequired`,`warrantyStatus`,`isExtendedFreeService`,`hubCode` (**verified**: `productId = deviceId`, `warrantyStatus` required, e.g. `In Warranty`) |
| GET | `api/iot/device/monitoring/consumption-report/<serial>?page=<n>` | daily usage + `tdsIn`/`tdsOut`/`filterLife` (**verified**) |
| GET | `api/iot/device/monitoring/status/<account_id>/<product_serial_number>/` | `{"online_status":bool,"total_consumption":int}` (**verified**) |
| POST | `api/iot/device/setting/reconfigure` | **WiFi-reset** (device → setup mode). Body `{"account_id","product_serial_no","request_id":"<uuid-v4>"}` (**decoded, not fired**; route confirmed: `GET` → `405 application/json`, whereas `/iot/device/setting/reconfigure` is the web app's HTML `404`) |
| GET | `api/iot/weather/<lat,lng | pin | city>` | temp / feels-like / aqi / humidity (**verified**; e.g. `/api/iot/weather/13.0827,80.2707`, `/api/iot/weather/<PIN>`) |
| GET | `cms/iot-config` | public IoT config (HTTP 200 unauthenticated) |

After the device returns `SKEY`, the app calls
`GET api/iotDevice/on-boarding-status?iot_device_serial_no=<serial>` to decide
whether the unit is already claimed.

Public CMS config `https://www.eurekaforbes.com/cms/iot-config` keys:
`scansData`, `filterLife`, `iotSupoortFaq`, `isAtdsEnabled`, `supportConfig`,
`weatherDataSource` (`"Microsoft Azure"`), `healthCheckLoadingMsg`,
`refreshMonitoringTime`, `maxWaterConsumptionLimit`, `weeklyConsumptionReportLimit`.
It contains **no** BLE UUIDs — those come from the authenticated app config
(`ble_service_uuid` / `ble_characteristic_uuid`).

Azure data-channel endpoint: `https://prod-az-d2c-function.azurewebsites.net/`.

---

## 6. Config-driven defaults (no login required)

| Config key | Default | Consumer |
|---|---|---|
| `ble_service_uuid` | `00ff` | `AppConfigBloc::getBleServiceUuid` |
| `ble_characteristic_uuid` | `ff01` | `AppConfigBloc::getBleCharacteristicUuid` |
| `ssid_pattern` | `Aquaguard_W` | `AppConfigBloc::getSsidPattern` |
| `efl_base_url`, `base_urls` | remote | HTTP client base URL |

`ssid_pattern` / `ble_service_uuid` / `ble_characteristic_uuid` live in the
`FeatureFlags` model of `AppConfigResponse`
(`asm/efl_customer_app/network/models/app_config/app_config_response.dart:1099`).

---

## 7. Dependencies / libraries observed

- `flutter_blue_plus` — BLE scan/connect/GATT (`com.lib.flutter_blue_plus.FlutterBluePlusPlugin`)
- `wifi_iot` — `forceWifiUsage`
- `wifi_scan` — AP scanning
- `dio` — HTTP
- `firebase_crashlytics` / `firebase_analytics` — telemetry
- No MQTT client library present.

Android permissions (confirms BLE + WiFi provisioning):
`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `CHANGE_WIFI_STATE`, `ACCESS_WIFI_STATE`,
`ACCESS_FINE_LOCATION`.
Manifest declares `<uses-feature android:name="android.hardware.bluetooth_le" android:required="false"/>`.

---

## 8. Source / artifact map

| Item | Path |
|---|---|
| Base APK | `~/com.efl.eurekaforbes-440.apk` |
| Native APK (`libapp.so`) | `~/com.efl.eurekaforbes-440-config.arm64_v8a.apk` |
| Object pool (exact strings/enums) | `blutter_out/pp.txt` |
| Connection bloc (protocol core) | `blutter_out/asm/efl_customer_app/features/iot/iot_onboarding/device_connection/bloc/device_connection_bloc.dart` |
| Discovery bloc (scan/pair) | `blutter_out/asm/efl_customer_app/features/iot/iot_onboarding/device_discovery/bloc/device_discovery_bloc.dart` |
| App config defaults | `blutter_out/asm/efl_customer_app/features/app_config/bloc/app_config_bloc.dart` |
| Enums | `.../device_connection/data/protocol_request_type.dart` (`ProtocolRequestType`/`ProtocolResponseType`) |
| Onboarding requests | `.../network/requests/iot_device_onboarding/iot_device_onboarding_request.dart` |
| Manifest / permissions | `artifacts/rea_pkg.json` |
| Public IoT config | `artifacts/iotconfig.json` |

### Toolchain notes
- Dart **3.6.0**, snapshot hash `f956f595844a2f845a55707faaaa51e4`.
- Blutter required **capstone 5.0.3** (6.x breaks the API); installed at
  `capstone-install`. Python venv (`cmake`, `pyelftools`) at
  `.venv`.
- REA jadx jar: `~/.local/share/rea/android/jadx-headless-mcp-0.7.1-all.jar`.
  JDK 21 needed for JADX (`JAVA_HOME=/path/to/openjdk-21`).

---

## 9. Onboarding sequence (reconstructed)

```
scan (BLE unfiltered 10s  |  WiFi by ssid_pattern)
  -> connect
     BLE: discoverServices -> match 00ff / ff01 -> subscribe notify
     WiFi: forceWifiUsage -> connect 15.150.15.1:3333
  -> WRITE {"type":"RMETA"}
       <- {"type":"META","SKEY":"..","MAC":"..","CTRL_FW_VER":"..","IOT_FW_VER":"..","STATUS":..,"ERROR_CODES":..,"mode":..}
       -> GET api/iotDevice/on-boarding-status?iot_device_serial_no=<serial>
  -> WRITE {"type":"RD_WIFI_STATUS"}     <- {"type":"WIFI_STATUS", ...}
  -> WRITE {"type": "ST_WIFI_CRD","SSID": "<ssid>","PASS": "<pass>"}   <- {"type":"ACK_WIFI_CRD"}
  -> WRITE {"type": "ST_PR_SNO", "PSNO": "<serial>"}                   <- {"type":"ACK_PR_SNO"}
  -> WRITE {"type": "SETUP_COMPLETE"}                                  <- {"type":"SETUP_COMPLETE_ACK"}
  -> POST api/iotDevice/saveOnboardingStatus  {assetId}
```

`RSP_SSID` is emitted when the device reports the AP SSID it is connected to.

---

## 10. Confirmed live session

Everything below was executed against the production API and returned HTTP 200,
using only the session cookie from §5.1.

Target (from `GET /api/v1/assets`):

| Field | Value |
|---|---|
| Name | AQUAGUARD ENRICH RITZ PRO ROUVCASS 4X |
| serialNumber | `3450000000000001` |
| assetId (`id`) | `00000000-0000-0000-0000-000000000002` |
| accountId | `00000000-0000-0000-0000-000000000001` |
| deviceId | `00000000-0000-0000-0000-000000000003` |
| componentId | `CA-0000-000000000` |
| materialId | `GWPDERRCS0002X` |

The asset also carries a nested **`iot`** block — this is the cloud source of the
MAC (no need to read it off BLE) and re-confirms the BLE UUIDs:

| `iot` field | Value |
|---|---|
| `part_serial_no` | `PART0000000000` |
| `part_mac_id` | `AABBCCDDEEFF` |
| `ssid` | `Aquaguard_WP_AABBCC` |
| `ble_service_uuid` / `ble_characteristic_uuid` | `00ff` / `ff01` |
| `onboard_status` | `true` |

(`iot.onboard_status` here is `true` while `on-boarding-status` returned
`isOnboarded:false` — different flags; the latter tracks app onboarding.)

Observed telemetry:

- `status/<acct>/<serial>/` → `{"online_status":true,"latest_enqueued_time":null,"total_consumption":12345}`
- `consumption-report/<serial>?page=1` → per-day litres (`2024-01-01:1200`, `2024-01-02:3400`),
  `tdsIn:300`, `tdsOut:30`, `filterLife:95.0`
- `on-boarding-status?iot_device_serial_no=3450000000000001` → `{"isOnboarded":false}`
- `extras/custom-attributes?serialNo=3450000000000001` → `{"data":{}}`

Notes / gotchas found while probing:

- `status/` requires **`<account_id>/<product_serial_number>`** in that order;
  errors name the fields: `invalidParams[account_id] should be valid UUID`, and
  wrong order → `404 "IoT device not found for the account_id and product_serial_number"`.
- The trailing slash on `status/` triggers a **308**; follow it (or omit the slash).
- `firmware/` is keyed by **MAC ID** (take it from the asset's `iot.part_mac_id`; it also appears in the
  device's BLE/WiFi `META` response), not by serial.
- `iot/device/setting/reconfigure` was **not** sent (it resets the unit's WiFi /
  forces re-provisioning).

### Reproduce

```
SID=$(curl -s -X POST https://www.eurekaforbes.com/api/public/ecom/v1/otp/verify \
  -H 'Content-Type: application/json' \
  --data '{"mobile_number":"<10d>","otp":<int>,"userAgent":"MOBILE","deviceUniqueId":"<android_id>"}' \
  | sed -E 's/.*"session_id":"([^"]+)".*/\1/')

curl -s https://www.eurekaforbes.com/api/v1/assets -H "Cookie: sessionHash=$SID"
curl -s https://www.eurekaforbes.com/api/iot/device/monitoring/status/00000000-0000-0000-0000-000000000001/3450000000000001/ -H "Cookie: sessionHash=$SID"
```

---

## 11. Tooling

Two stdlib-only scripts (Python 3.11+). BLE in the local script additionally needs `bleak`.

### 11.1 `aquaguard.py` — cloud client

Session persisted at `~/.config/aquaguard/session.json` (mode 0600).

```
python3 aquaguard.py login 9999999999            # sends OTP, prompts, stores session_id
python3 aquaguard.py login 9999999999 --otp 5468
python3 aquaguard.py assets                      # list account assets
python3 aquaguard.py status      [--serial S]
python3 aquaguard.py consumption [--serial S] [--page 1]
python3 aquaguard.py extras      [--serial S]
python3 aquaguard.py device      [--serial S]    # asset + iot block (MAC/SSID/UUIDs)
python3 aquaguard.py firmware    [--serial S] [--mac M]
python3 aquaguard.py onboard     [--serial S]
python3 aquaguard.py weather <PIN>              # 'lat,lng' | pincode | city
python3 aquaguard.py get <path> [--query k=v ...]
python3 aquaguard.py logout
```

`--serial` is optional when the account has exactly one asset. Override host with
`AQUAGUARD_BASE`.

### 11.2 `aquaguard-local.py` — direct BLE / soft-AP

```
python3 aquaguard-local.py scan [--name Aquaguard]
python3 aquaguard-local.py ble <addr> meta [--svc 00ff --char ff01]
python3 aquaguard-local.py ble <addr> set-serial --psno 3450000000000001
python3 aquaguard-local.py ble <addr> set-wifi "MySSID" "MyPass"
python3 aquaguard-local.py wifi  meta                         # default 15.150.15.1:3333
python3 aquaguard-local.py wifi  set-wifi "MySSID" "MyPass"
```

ops: `meta`, `wifi-status`, `set-wifi <SSID> <PASS>`, `set-serial --psno <SN>`,
`setup-complete`.

**Disruptive ops not executed here:** cloud `api/iot/device/setting/reconfigure`, and
local `set-wifi` / `setup-complete` (both re-point the unit's WiFi).

> The step-by-step procedure to enter setup mode and re-provision safely
> (go/no-go checklist, rollback, failure handling) is in
> [`AQUAGUARD_RUNBOOK.md`](./AQUAGUARD_RUNBOOK.md).

### 11.3 `aquaguard-monitor.py` — scheduled polling + alerts

There is **no realtime channel** (no WebSocket/SignalR in the app; the Azure
`prod-az-d2c-function` host is device→cloud). The app polls on
`refreshMonitoringTime` from `cms/iot-config`, so a poller is the right model.

```
python3 aquaguard-monitor.py [--serial S] \
    [--filter-min 10] [--tds-max 500] \
    [--notify-ok] [--realert] [--interval N] [--dry-run] [--command CMD]
```

Alerts (on state transition only, so no spam) when: device **offline**,
`filterLife <= --filter-min`, or `tdsOut >= --tds-max`. Notifier defaults to
`~/.local/bin/sendxmpp.sh` (XMPP); override with `--command`. State kept at
`~/.config/aquaguard/monitor_state.json`. One-shot by default (cron-friendly);
`--interval` loops. Example cron (every 30 min):

```
*/30 * * * * cd ~/code/laptop && AQUAGUARD_BASE=https://www.eurekaforbes.com \
  python3 aquaguard-monitor.py >/dev/null 2>&1
```

Note: the session expires, so a fully unattended monitor needs hands-free
re-login (re-run `aquaguard.py login`, or auto-read the OTP SMS via the paired
phone over `adb`).
