# Camera capability matrix

Do not claim universal camera support without a row here.

| Vendor/model | Connection | ONVIF | RTSP | Native ALPR | FastALPR | Main/sub | Reconnect | 24h soak | Limits |
|---|---|---|---|---|---|---|---|---|---|
| HVX / QY (this site) | NetSDK :30000 | discover only | optional | yes (`Net_RegImageRecvEx`) | fallback | SDK sub for live | yes | site-proven | 32-bit host + NetSDK.dll |
| Generic Dahua HTTP/RTSP | HTTP snapshot / RTSP | optional | yes | no | yes | if ONVIF/RTSP finds two URIs | yes | not claimed | no GPIO native plates |
| Generic Hikvision HTTP/RTSP | HTTP snapshot / RTSP | optional | yes | no | yes | if ONVIF/RTSP finds two URIs | yes | not claimed | no GPIO native plates |
| ONVIF identify-only | not a login | GetProfiles | URI only | no | n/a | profiles only | n/a | n/a | never `SDK_CONNECTED` |
| Generic ONVIF Media2 (`adapter_id=onvif`) | ONVIF discovery, RTSP media | GetServices → Media2 GetProfiles/GetStreamUri/GetSnapshotUri, Media1 fallback | from device URIs | only via Profile M plate topics (see below) | yes | MAIN/SUB from profiles | pull-point backoff | not claimed | WS-UsernameToken; never guesses URLs |
| ONVIF Profile M with plate topics | as above + Events pull-point | GetEventProperties advertises `…/LicensePlate` | as above | metadata → `onvif_profile_m` captures | HYBRID possible | as above | Renew 40 s, Unsubscribe on stop | not claimed | vendor item names HARDWARE-VERIFICATION-REQUIRED |

Fill new rows after a real camera soak, not from the adapter name. ONVIF details: `ONVIF-MEDIA2-PROFILE-M.md`.
