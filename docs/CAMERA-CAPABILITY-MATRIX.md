# Camera capability matrix

Do not claim universal camera support without a row here.

| Vendor/model | Connection | ONVIF | RTSP | Native ALPR | FastALPR | Main/sub | Reconnect | 24h soak | Limits |
|---|---|---|---|---|---|---|---|---|---|
| HVX / QY (this site) | NetSDK :30000 | discover only | optional | yes (`Net_RegImageRecvEx`) | fallback | SDK sub for live | yes | site-proven | 32-bit host + NetSDK.dll |
| Generic Dahua HTTP/RTSP | HTTP snapshot / RTSP | optional | yes | no | yes | if ONVIF/RTSP finds two URIs | yes | not claimed | no GPIO native plates |
| Generic Hikvision HTTP/RTSP | HTTP snapshot / RTSP | optional | yes | no | yes | if ONVIF/RTSP finds two URIs | yes | not claimed | no GPIO native plates |
| ONVIF identify-only | not a login | GetProfiles | URI only | no | n/a | profiles only | n/a | n/a | never `SDK_CONNECTED` |

Fill new rows after a real camera soak, not from the adapter name.
