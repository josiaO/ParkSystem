from __future__ import annotations

class T_DCImageSnap(ctypes.Structure):
    _fields_ = [
        ("uiImageId", ctypes.c_uint),
        ("ucLightIndex", ctypes.c_ubyte),
        ("ucLightMode", ctypes.c_ubyte),
        ("usGroupId", ctypes.c_ushort),
    ]

class T_ImageUserInfo(ctypes.Structure):
    _fields_ = [
        ("usWidth", ctypes.c_ushort),
        ("usHeight", ctypes.c_ushort),
        ("ucVehicleColor", ctypes.c_ubyte),
        ("ucVehicleBrand", ctypes.c_ubyte),
        ("ucVehicleSize", ctypes.c_ubyte),
        ("ucPlateColor", ctypes.c_ubyte),
        ("szLprResult", ctypes.c_char * 16),
        ("usLpBox", ctypes.c_ushort * 4),
        ("ucLprType", ctypes.c_ubyte),
        ("usSpeed", ctypes.c_ushort),
        ("ucSnapType", ctypes.c_ubyte),
        ("ucHaveVehicle", ctypes.c_ubyte),
        ("acSnapTime", ctypes.c_char * 18),
        ("ucViolateCode", ctypes.c_ubyte),
        ("ucLaneNo", ctypes.c_ubyte),
        ("uiVehicleId", ctypes.c_uint),
        ("ucScore", ctypes.c_ubyte),
        ("ucDirection", ctypes.c_ubyte),
        ("ucTotalNum", ctypes.c_ubyte),
        ("ucSnapshotIndex", ctypes.c_ubyte),
    ]

class T_Point(ctypes.Structure):
    _fields_ = [("sX", ctypes.c_short), ("sY", ctypes.c_short)]

class T_Line(ctypes.Structure):
    _fields_ = [("tStartPoint", T_Point), ("tEndPoint", T_Point)]

class T_DivisionLine(ctypes.Structure):
    _fields_ = [
        ("ucDashedLine", ctypes.c_ubyte),
        ("ucReserved", ctypes.c_ubyte),
        ("tLine", T_Line),
    ]

class T_VideoDetectParamSetup(ctypes.Structure):
    """QY Net_Setup.h T_VideoDetectParamSetup (ONE_DIRECTION_LANES == 5).

    This is intentionally a query-only binding.  The camera remains the
    authority for its trigger polygon and lines; SmartPark never writes this
    structure during normal startup.
    """

    _fields_ = [
        ("ucLanes", ctypes.c_ubyte),
        ("ucSnapAutoBike", ctypes.c_ubyte),
        ("ucMinScore", ctypes.c_ubyte),
        ("ucReserved", ctypes.c_ubyte),
        ("ucCpMode", ctypes.c_ubyte),
        ("ucWidthFlag", ctypes.c_ubyte),
        ("ucLprHead", ctypes.c_ubyte),
        ("ucZoomSlop", ctypes.c_ubyte),
        ("atPlateRegion", T_Point * 4),
        ("aStopLine", T_Line),
        ("atSpeedRegion", T_Point * 4),
        ("atOccupCheckLine", T_Line * 2),
        ("atDivisionLine", T_DivisionLine * 6),
        ("tPrefixLine", T_Line),
        ("tLeftBorderLine", T_Line),
        ("tRightBorderLine", T_Line),
        ("atVirLoop", (T_Point * 4) * 5),
        ("atBanRegion", T_Point * 4),
        ("usCameraHeight", ctypes.c_ushort),
        ("usRectLength", ctypes.c_ushort),
        ("usRectWidth", ctypes.c_ushort),
        ("usTotalDis", ctypes.c_ushort),
    ]

class T_VehicleVAFunSetup(ctypes.Structure):
    _fields_ = [
        ("ucPlateRealTimeShowEn", ctypes.c_ubyte),
        ("ucRecRegShowEn", ctypes.c_ubyte),
        ("ucArmyLprPrior", ctypes.c_ubyte),
        ("ucNoPlateVehicleSnapEn", ctypes.c_ubyte),
        ("ucCpHightTI", ctypes.c_ubyte),
        ("ucLocalCity", ctypes.c_ubyte),
        ("ucPlateDirection", ctypes.c_ubyte),
        ("ucCpTimeInterval", ctypes.c_ubyte),
        ("uiPlateDefaultWord", ctypes.c_uint),
        ("usMinPlateW", ctypes.c_ushort),
        ("usMaxPlateW", ctypes.c_ushort),
        ("ucInvalidLprLevel", ctypes.c_ubyte),
        ("ucVehicleInterval", ctypes.c_ubyte),
        ("ucPolicePlate", ctypes.c_ubyte),
        ("ucPlateFeature", ctypes.c_ubyte),
    ]

class T_ControlGate(ctypes.Structure):
    _fields_ = [
        ("ucState", ctypes.c_ubyte),
        ("ucIndex", ctypes.c_ubyte),
        ("ucGateDefSta", ctypes.c_ubyte),
        ("ucReserved", ctypes.c_ubyte),
    ]

class T_PicInfo(ctypes.Structure):
    _fields_ = [
        ("uiPanoramaPicLen", ctypes.c_uint),
        ("uiVehiclePicLen", ctypes.c_uint),
        ("ptPanoramaPicBuff", ctypes.c_void_p),
        ("ptVehiclePicBuff", ctypes.c_void_p),
    ]
