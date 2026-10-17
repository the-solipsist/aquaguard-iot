# Eureka Forbes app — complete API reference

Extracted from `com.efl.eurekaforbes` (`libapp.so`, Dart 3.6.0, blutter) across all
32 request modules under `network/requests/`. **~87 endpoint operations** in total.
A path ending in `/` is a prefix: the caller appends an id/serial (shown in *Notes*).

## 1. Common request infrastructure

| Item | Value |
|---|---|
| Base host | `https://www.eurekaforbes.com` (only API host in the binary) |
| Auth | OTP → `session_id`; send as `Cookie: sessionHash=<session_id>` (`Authorization: Bearer` is **rejected**, 401) |
| Headers | `sessionHash` cookie, `app-version`, `userAgent` (`"MOBILE"` on OTP verify), `deviceUniqueId` |
| Relative paths | Most literals start with `api/`; `iot/device/setting/reconfigure` is the lone exception and actually lives at `/api/…` |
| Response envelope | `{"data": …}` on success; `{"error": …}` on failure |
| Validation errors | `400 {"error":"Validation failed","invalidParams":[{"field":…,"message":…}]}` |
| Auth failure | `401` when the cookie is missing/expired |
| Rate limit | `429 {"error":"Too many attempts. Try later"}` (OTP send) |
| Method-not-allowed probe | a real route returns `405 application/json` to `GET`; the web frontend returns HTML `404` |

Auth recipe (verified):
```
POST api/public/ecom/v1/otp/send    {"mobile_number": "<10-digit>"}
POST api/public/ecom/v1/otp/verify  {"mobile_number","otp":<INT>,"userAgent":"MOBILE","deviceUniqueId":"<free-form>"}
   -> {"data":{"session_id","webEngageId"}}
```

## 2. Device / IoT (the purifier-relevant subset)

| Method | Path | Body / query | Status |
|---|---|---|---|
| GET | `api/v1/assets` (alias `api/assets`) | — | **verified**: list of assets incl. `iot` block |
| GET | `api/v1/asset-details` | `assetId, accountId, productId, isIrRequired, warrantyStatus, isExtendedFreeService, hubCode` | **verified**: `productId = deviceId` (`<PRODUCT_ID>`), `warrantyStatus` must be non-empty (`In Warranty` / `Out of Warranty`) |
| GET | `api/iot/device/monitoring/status/<accountId>/<productSerialNo>/` | — | **verified**: `{"online_status","total_consumption"}` |
| GET | `api/iot/device/monitoring/consumption-report/<serial>?page=<n>` | — | **verified** |
| GET | `api/iot/device/extras/custom-attributes?serialNo=<serial>` | — | **verified** (`{"data":{}}`) |
| GET | `api/iot/device/firmware/<macId>` | — | **verified**: controller/iot FW versions; use `asset.iot.part_mac_id` |
| GET | `api/iot/device/health/requests/<requestId>` | — | decoded; `requestId` must be UUID |
| POST | `api/iot/device/health/requests/` | health-check trigger | decoded (`runHealthCheck`) |
| POST | `api/iot/device/health/requests/atds` | `{accountId, productSerialNo, lowerRange, higherRange, requestId:<uuid4>, extras}` | decoded (`saveAutoTds`) |
| POST | `api/iot/device/setting/reconfigure` | `{account_id, product_serial_no, request_id:<uuid4>}` | **route confirmed** (`/api/…`); **not fired** — forces setup/AP mode |
| GET | `api/iotDevice/on-boarding-status?iot_device_serial_no=<serial>` | — | **verified** |
| POST | `api/iotDevice/saveOnboardingStatus` | `{assetId}` | decoded |
| GET | `api/iot/weather/<lat,lng | pincode | city>` | — | **verified** |
| PATCH | `api/asset/product-serial-number` | serial update | decoded |
| GET | `cms/iot-config` | — | public (200 unauthenticated) |
| GET | `cms/iot-config?fields[0]=supportConfig` | — | decoded (`getIotSupportConfig`) |
| GET | `cms/d2c/config/atds` | — | decoded (`getAtdsConfig`) |
| GET | `cms/product-detail/` | `iot, populate` | decoded (`getIotCmsProductDetails`) |
| GET | `cms/d2c/config/scans-data-forbes-pro` | — | decoded (`getCommercialIotConfig`) |

## 3. Authentication / account / contacts

| Method | Path | Params | Operation |
|---|---|---|---|
| POST | `api/public/ecom/v1/otp/send` | `mobile_number` | `sendOTP` |
| POST | `api/public/ecom/v1/otp/verify` | `mobile_number, otp, userAgent, deviceUniqueId` | `verifyOTP` |
| DELETE | `api/account/signout/` | — | `userSignOut` |
| GET | `api/customer/account/profileV2` | `d365UserId` (= `accountId`, verified) | `getProfile` |
| PATCH | `api/customer/account/profile/update-primary-name` | — | `requestUpdateName` |
| POST | `api/customer/account/profile/request-delete` | — | `requestDeleteContact` |
| PATCH | `api/customer/account/profile/request-change` | — | `requestUpdateContact` |
| POST | `api/customer/account/profile/request-change` | — | `requestCreateContact` |
| POST | `api/customer/account/profile/verify-update` | — | `verifyUpdateContact` |
| POST | `api/customer/account/profile/verify-create` | — | `verifyCreateContact` |

## 4. Assets / warranty / installation

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `api/v1/assets` | — | `getAssets` |
| GET | `api/assets` | — | `getAssets` (home) |
| PATCH | `api/assets/register-warranty` | `assetId` | `registerWarranty` |
| GET | `api/assets/location/` | — | `getLocationDetails` |
| PATCH | `api/assets/location` | — | `updateAddress` |
| GET | `api/assets/ir-work-order` | — | `getInstallationRequest` |
| POST | `api/assets/ir-job-card` | — | `fetchIrJobCard` |
| POST | `api/assets/saving-promo` | — | `getAmcPromoSavings` |
| GET | `api/asset/work-order-invoice-download` | `invoiceType, workOrderId` | `downloadInvoice` |
| PATCH | `api/asset/product-serial-number` | — | `updateAssetSerialNumber` |

## 5. Service & scheduling

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `api/service/service-booking-eligibility` | `assetId` | `checkServiceBookingBlock` |
| GET | `api/service/followup/options` | `caseNumber` | `getFollowUpOptions` |
| POST | `api/service/followup/save` | — | `submitFollowUpReq` |
| GET | `api/service/job-card/v2` | `accountId, assetId` | `fetchServiceCard` |
| POST | `api/service/job-card` | — | `submitFeedback` |
| POST | `api/service/schedule` | — | `scheduleService` |
| GET | `api/service/assign-green-vn` | `account_id, bookable_resource_id` | `getExotelData` |
| GET | `api/service-product/price` | `assetId[, incidentTypeId]` | `getServiceProduct` / `getServiceProductPrice` |
| POST | `api/cart/service-product-checkout` | — | `prepaidServiceCheckout` |
| POST | `api/schedule/slotData` | — | `fetchAvailableSlot` / `getServiceTimeSlots` |
| GET | `api/schedule/getServices` | `assetId, home` | `getBookedServices` |
| GET | `api/schedule/getTracking/` | `name` | `getServiceDetails` |
| GET | `api/schedule/getServiceMetadata/` | — | `getServiceMetadata` |
| POST | `api/schedule/rescheduleAService` | `accountId` | `rescheduleService` |
| PATCH | `api/schedule/ir-reschedule` | — | `rescheduleInstallationRequest` |
| GET | `api/schedule/verify-spare` | `serialNo` | `verifyFilter` |
| GET | `/api/slot/dispositions/` | `isExtendedFreeService, isIrRequired, warrantyStatus` | `getDispositions` |
| PUT | `api/public/sos/whitelist` | — | `addToWhitelist` |
| GET | `api/product/attachment-categories` | `productSkuId` | `getSpares` |

## 6. AMC / gift cards / savings / agreements

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `api/amc/amcData` | `assetId, product_id, validity` | `fetchAmcInfo` |
| GET | `api/amc/gift-card-availability` | — | (pool) |
| GET | `api/amc/gift-card-denomination` | — | `fetchAmcGiftCardDenominations` |
| GET | `api/amc/personal-gift-cards` | `customerHash` | `fetchUserGiftCards` |
| GET | `api/amc/savings` | `agreementId, assetId` | `getAgreementSavings` |
| GET | `api/amc/st-code-validation` | — | (pool) |
| GET | `api/order/getOrderDetails` | `orderId` | `fetchPurchasedAmcGiftCardDetails` |
| GET | `api/product/agreementData` | `agreementId, assetId` | `fetchProductAgreement` |
| GET | `cms/amc-plans-page` | `deviceFamilyName` | `getAmcPage` |
| GET | `cms/amc-service-plan-page` | `deviceFamilyName` | `getAmcServicePlanPage` |
| GET | `cms/amc-prepaid-service?populate[…]` | — | (pool; uninstall/reinstall variants) |
| GET | `amc/relevantAmcPlans` | — | (pool; literal without `api/` prefix) |

## 7. Cart / orders / payments

| Method | Path | Params | Operation |
|---|---|---|---|
| POST | `cart/addItem` | — | (pool) |
| GET | `cart/fetchV2` | — | (pool) |
| POST | `cart/checkoutV2` | — | (pool) |
| POST | `api/v1/order/confirmation/` | `paymentIdHex` | `confirmOrder` |
| GET | `api/order/getOrderDetails` | `orderId` | order detail |
| GET | `api/product/agreementData` | `agreementId, assetId` | agreement |

## 8. Location / places

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `api/location/places` | `place_id` | `getPlaceDetails` |
| GET | `api/location/geocode` | `latitude, longitude` | `getAddressFromLatLng` |
| GET | `api/location/reverse-geocode` | `address` | `getAddressFromPinCode` |
| GET | `api/location/suggestions` | `input` | `getPlacesList` |

## 9. CMS content configuration (`cms/…`, Strapi-style)

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `cms/app-config` | — | `getConfig` |
| GET | `cms/iot-config` | — | `getIotAppConfig` |
| GET | `cms/d2c/config/atds` | — | `getAtdsConfig` |
| GET | `cms/d2c/config/prefect-service-config` | — | `getPerfectServiceConfig` |
| GET | `cms/d2c/config/perfect-paid-service-config` | — | `getPerfectPaidServiceConfig` |
| GET | `cms/d2c/config/savings-calculator-config` | — | `getAgreementSavingsContent` |
| GET | `cms/d2c/config/paid-service-tracking-config` | — | `getPaidServiceTrackingConfig` |
| GET | `cms/d2c/config/offer-app-config` | — | `getOfferConfig` |
| GET | `cms/d2c/config/rejection-reasons` | — | `fetchRescheduleReasons` |
| GET | `cms/d2c/config/cancellation-reasons` | — | `fetchCancellationReasons` |
| GET | `cms/d2c/config/home-page-promotions` | — | `getHomePagePromotions` |
| GET | `cms/d2c/config/scans-data-forbes-pro` | — | `getCommercialIotConfig` |
| GET | `cms/product-detail/` | `iot, populate` | `getIotCmsProductDetails` |
| GET | `cms/fg-products/` | `populate` | `getProduct` (example id `GWPD1000LPHRO0`) |

## 10. App config / misc

| Method | Path | Params | Operation |
|---|---|---|---|
| GET | `/app-version` | query | `getAppUpdateConfig` |
| GET | `<caller-supplied URL>` | query | `downloadInvoicePdf` (generic authenticated GET; path is an argument, not a literal) |
| — | — | — | `ab_experiment` module is an empty stub (no endpoints) |

## 11. Live probe results (read-only, GET against the live account)

All calls used `Cookie: sessionHash=…`. 

**200 — readable**
`cms/app-config`, `cms/iot-config`, `cms/iot-config?fields[0]=supportConfig`,
`cms/d2c/config/{atds,prefect-service-config,perfect-paid-service-config,savings-calculator-config,paid-service-tracking-config,offer-app-config,rejection-reasons,cancellation-reasons,home-page-promotions,scans-data-forbes-pro}`,
`cms/product-detail/<materialId>?populate=*`, `cms/amc-prepaid-service?populate[…]`,
`/app-version`, `api/customer/account/profileV2`, `api/assets/ir-work-order`,
`api/amc/{amcData,gift-card-denomination,gift-card-availability,personal-gift-cards}`,
`api/schedule/getServices`, `api/service-product/price`,
`api/service/service-booking-eligibility`, `api/location/{geocode,reverse-geocode,suggestions}`,
`api/iot/weather`, `api/v1/asset-details` (with `warrantyStatus`).

**Non-200 (route/params, not auth)**
| Result | Endpoint | Meaning |
|---|---|---|
| 405 | `api/assets/location/?assetId=` | route is `PATCH` only; GET not allowed |
| 400 | `api/assets/location/<assetId>` | validation (needs body/params) |
| 400 | `api/amc/savings`, `api/product/agreementData` | needs `agreementId` |
| 400 | `api/amc/st-code-validation` | needs `stCode` (+ likely asset) |
| 400 | `api/service/job-card/v2` | valid route: "No recent repair history found" |
| 406 | `api/schedule/verify-spare` | `INVALID_SCAN` — expects a consumable barcode, not serial |
| 400 | `api/product/attachment-categories` | expects a SKU id on `efl_sbomlines` (not materialId) |
| 400 | `cms/amc-plans-page`, `cms/amc-service-plan-page` | server 400 even with `deviceFamilyName` |
| 404 | `cms/product-detail/` (list), `cms/fg-products[/<id>]` | not found |
| 404 | `/api/slot/dispositions/`, `/api/schedule/getServiceMetadata/` | prefix is incomplete — need path id (returned HTML 404) |
| 404 | `amc/relevantAmcPlans` | frontend HTML (not an API route) |

**Values learned**
- `productId == deviceId` = `00000000-0000-0000-0000-000000000003`; asset `hubCode=00000`, `isIrRequired=true`, `category=Water Purifiers`.
- `d365UserId == accountId`; profile returns customer id, `firstName`, `webEngageId`, contact.
- `/app-version`: live `2.2.5` (code 435), supported `2.2.5`.
- `cms/iot-config`: `refreshMonitoringTime=30`, `isAtdsEnabled=false`, `weeklyConsumptionReportLimit=5`, `weatherDataSource="Microsoft Azure"`.
- `cms/product-detail/<materialId>`: title "Aquaguard ENRICH Ritz Pro", slug, specifications, channel/commission data (22 KB).

## 12. Gaps / caveats

- `api/v1/asset-details`: resolved — `productId = deviceId`, and a non-empty
  `warrantyStatus` is required.
- `api/product/attachment-categories`, `api/amc/savings`, `api/product/agreementData`,
  `api/amc/st-code-validation`: valid routes but need ids (SKU / agreementId / stCode)
  that this account does not expose.
- `api/slot/dispositions/` and `api/schedule/getServiceMetadata/`: prefixes need a
  path id; bare prefix returns the frontend's HTML 404.
- `cms/amc-plans-page`, `cms/amc-service-plan-page`: server returns 400 regardless
  of `deviceFamilyName`.
- `pdf.downloadInvoicePdf`: takes the full URL as an argument → it is a generic
  authenticated GET, so any signed URL the API returns can be fetched this way.
- `cart/*` and `cms/amc-prepaid-service?populate[…]` appear in the string pool but
  their request builders were not separately decoded; methods inferred/typical.
- `ab_experiment` is declared but empty in the build (feature-flagged off).
- Methods shown in parentheses in the Operation column (e.g. `fetchIrJobCard`) reflect
  the extraction's nearest literal; the path is authoritative, method is from asm.
