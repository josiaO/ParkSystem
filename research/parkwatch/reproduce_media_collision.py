"""Synthetic callbacks only: no DLL, camera, network or gate access."""
import sys,threading,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.hvx_sdk_host.hvx_sdk import HVXSDK,T_ImageUserInfo
sdk=HVXSDK.__new__(HVXSDK)
sdk._lock=threading.Lock()
for name in ('_last_capture','_last_event_jpeg','_last_event_crop','_pending_events','_event_media'):
 setattr(sdk,name,{})
# Exercise real callback insertion; inject buffer-copy bytes to avoid native pointers.
from types import SimpleNamespace
pic=SimpleNamespace(contents=SimpleNamespace(ptPanoramaPicBuff=1,uiPanoramaPicLen=3,ptVehiclePicBuff=0,uiVehiclePicLen=0))
for plate,jpeg in [(b'TEST_A',b'\xff\xd8A'),(b'TEST_B',b'\xff\xd8B')]:
 info=T_ImageUserInfo();info.szLprResult=plate
 sdk._copy_buffer=lambda ptr,length,data=jpeg: data if ptr else b''
 sdk._on_image(7,0,ctypes.pointer(info),pic,None)
assert len(sdk._pending_events[7])==2
assert sdk.event_jpeg_for(7,0)==b'\xff\xd8B'
assert sdk.event_jpeg_for(7,999)==b'\xff\xd8B'
print('CONFIRMED: two queued events with image_id=0 share the second image; missing ID 999 also returns the latest image.')
