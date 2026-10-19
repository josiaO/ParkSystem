# MediaMTX browser reader

`mediamtx-reader.js` is the unmodified official reader from MediaMTX v1.12.3:
https://github.com/bluenviron/mediamtx/blob/v1.12.3/internal/servers/webrtc/reader.js

It implements WHEP negotiation, trickle ICE and reconnection. SmartPark only
attaches the received track to its video element and closes the reader on camera
switch. It uses standard WHEP with the existing v1.11.3 MediaMTX server.

License: MIT, reproduced in `vendor/mediamtx/LICENSE` in the application bundle.
