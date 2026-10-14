
/* FUNCTION FUN_10005c00 ENTRY 10005c00 */

int __thiscall FUN_10005c00(int param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
  if (*(char *)(param_1 + 0x55) != '\0') {
    return -7;
  }
  *(undefined4 *)(param_1 + 0x588) = param_3;
  ac::LogDebug("Device","CALL [Net_StartVideo] Begin");
  iVar1 = Net_StartVideo(*(undefined4 *)(param_1 + 0x574),0,param_3);
  if (iVar1 == 0) {
    ac::LogDebug("Device","CALL [Net_StartVideo] OK");
    *(undefined1 *)(param_1 + 0x55) = 1;
    return 0;
  }
  uVar2 = FUN_100072c0();
  ac::LogError("Device","CALL [Net_StartVideo] FAILED, CODE: %d, MSG: %s",iVar1,uVar2);
  return iVar1;
}



/* FUNCTION FUN_10005c90 ENTRY 10005c90 */

int __fastcall FUN_10005c90(int param_1)

{
  int iVar1;
  undefined4 uVar2;
  
  if (*(char *)(param_1 + 0x55) == '\0') {
    return -7;
  }
  ac::LogDebug("Device","CALL [Net_StopVideo] Begin");
  iVar1 = Net_StopVideo(*(undefined4 *)(param_1 + 0x574));
  if (iVar1 == 0) {
    ac::LogDebug("Device","CALL [Net_StopVideo] OK");
    *(undefined1 *)(param_1 + 0x55) = 0;
    return 0;
  }
  uVar2 = FUN_100072c0();
  ac::LogError("Device","CALL [Net_StopVideo] FAILED, CODE: %d, MSG: %s",iVar1,uVar2);
  *(undefined1 *)(param_1 + 0x55) = 0;
  return iVar1;
}



/* FUNCTION FUN_10005d10 ENTRY 10005d10 */

int __fastcall FUN_10005d10(int param_1)

{
  int iVar1;
  undefined4 uVar2;
  undefined8 local_c;
  
  if (*(char *)(param_1 + 0x54) == '\0') {
    return -7;
  }
  local_c = 0;
  ac::LogDebug("Device","CALL [Net_ImageSnap] Begin");
  iVar1 = Net_ImageSnap(*(undefined4 *)(param_1 + 0x574),&local_c);
  if (iVar1 == 0) {
    ac::LogDebug("Device","CALL [Net_ImageSnap] OK");
    return 0;
  }
  uVar2 = FUN_100072c0();
  ac::LogError("Device","CALL [Net_ImageSnap] FAILED, CODE: %d, MSG: %s",iVar1,uVar2);
  return iVar1;
}



/* FUNCTION FUN_10005f20 ENTRY 10005f20 */

int __thiscall FUN_10005f20(int param_1,int *param_2)

{
  int iVar1;
  undefined4 uVar2;
  
  if (*(char *)(param_1 + 0x54) == '\0') {
    return -7;
  }
  iVar1 = *param_2;
  if (iVar1 == 100) {
    param_2 = (int *)0x1;
  }
  else if (iVar1 == 0x65) {
    param_2 = (int *)0x2;
  }
  else {
    if (iVar1 != 0x66) {
      if (iVar1 == 0xc9) {
        iVar1 = param_2[1];
        FUN_100065c0(param_1,"CAMCMD_UPDATE_WHITE_LIST ...");
        FUN_10004410(*(undefined4 *)(param_1 + 0x574),param_2[3],iVar1);
        FUN_100065c0(param_1,"CAMCMD_UPDATE_WHITE_LIST End");
      }
      return 0;
    }
    param_2 = (int *)(uint)(byte)((char)param_2[1] + 1);
  }
  ac::LogDebug("Device","CALL [Net_GateSetup] Begin");
  iVar1 = Net_GateSetup(*(undefined4 *)(param_1 + 0x574),&param_2);
  if (iVar1 == 0) {
    ac::LogDebug("Device","CALL [Net_GateSetup] OK");
    return 0;
  }
  uVar2 = FUN_100072c0();
  ac::LogError("Device","CALL [Net_GateSetup] FAILED, CODE: %d, MSG: %s",iVar1,uVar2);
  return iVar1;
}



/* FUNCTION FUN_10006120 ENTRY 10006120 */

/* WARNING: Restarted to delay deadcode elimination for space: stack */

int __thiscall FUN_10006120(int param_1,int param_2,int param_3,uint param_4)

{
  uint uVar1;
  int iVar2;
  undefined4 uVar3;
  undefined1 *puVar4;
  undefined1 *local_2c;
  int local_1c;
  undefined1 local_18;
  undefined1 local_17;
  undefined1 local_16;
  undefined1 local_12;
  undefined1 local_11;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  puStack_c = &LAB_10009858;
  local_10 = ExceptionList;
  uVar1 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  if (*(char *)(param_1 + 0x54) == '\0') {
    return -7;
  }
  local_2c = (undefined1 *)0x0;
  local_8 = 0;
  ExceptionList = &local_10;
  if (param_4 * 3 != 0) {
    FUN_10006750(param_4 * 3);
  }
  local_1c = 0;
  if (0 < (int)param_4) {
    do {
      FUN_10004240(&local_18,"%02X ",*(undefined1 *)(local_1c + param_3),uVar1);
      local_12 = local_18;
      local_11 = local_18;
      if (&local_11 < local_2c) {
        if (local_2c == (undefined1 *)0x0) {
          FUN_100066f0(1);
        }
        else {
LAB_10006225:
          *local_2c = local_18;
        }
      }
      else {
        if (local_2c != (undefined1 *)0x0) goto LAB_10006225;
        FUN_100066f0(1);
      }
      puVar4 = local_2c + 1;
      local_12 = local_17;
      local_11 = local_17;
      if (&local_11 < puVar4) {
        if (puVar4 == (undefined1 *)0x0) {
          FUN_100066f0(1);
        }
        else {
LAB_10006287:
          *puVar4 = local_17;
        }
      }
      else {
        if (puVar4 != (undefined1 *)0x0) goto LAB_10006287;
        FUN_100066f0(1);
      }
      puVar4 = local_2c + 2;
      local_12 = local_16;
      local_11 = local_16;
      if (&local_11 < puVar4) {
        if (puVar4 == (undefined1 *)0x0) {
          FUN_100066f0(1);
        }
        else {
LAB_100062e9:
          *puVar4 = local_16;
        }
      }
      else {
        if (puVar4 != (undefined1 *)0x0) goto LAB_100062e9;
        FUN_100066f0(1);
      }
      local_2c = local_2c + 3;
      local_1c = local_1c + 1;
    } while (local_1c < (int)param_4);
  }
  param_4 = param_4 & 0xffffff;
  if ((undefined1 *)((int)&param_4 + 3) < local_2c) {
    if (local_2c == (undefined1 *)0x0) {
      FUN_100066f0(1);
    }
    else {
      *local_2c = 0;
    }
  }
  else if (local_2c == (undefined1 *)0x0) {
    FUN_100066f0(1);
  }
  else {
    *local_2c = 0;
  }
  FUN_100065c0(param_1,"Net_TransRS485HexDataEx: ucRs485Id: %d, %s",param_2 + -20000,0);
  ac::LogDebug("Device","CALL [Net_TransRS485HexDataEx] Begin");
  iVar2 = Net_TransRS485HexDataEx(*(undefined4 *)(param_1 + 0x574),param_2 + -20000,0,local_2c);
  if (iVar2 == 0) {
    ac::LogDebug("Device","CALL [Net_TransRS485HexDataEx] OK");
  }
  else {
    uVar3 = FUN_100072c0();
    ac::LogError("Device","CALL [Net_TransRS485HexDataEx] FAILED, CODE: %d, MSG: %s",iVar2,uVar3);
  }
  FUN_10006680();
  ExceptionList = local_10;
  return iVar2;
}



/* FUNCTION FUN_10005b10 ENTRY 10005b10 */

undefined4 __fastcall FUN_10005b10(int param_1)

{
  undefined1 *puVar1;
  bool bVar2;
  int iVar3;
  undefined8 uVar4;
  
  if (*(char *)(param_1 + 0x54) == '\0') {
    return 0xfffffff9;
  }
  FUN_100065c0(param_1,"Close ...");
  puVar1 = (undefined1 *)(param_1 + 0x7bc);
  FUN_10004a00(puVar1,"EndUpdate Begin");
  FUN_10004a00(puVar1,"TryEndUpdate Begin");
  bVar2 = ab::Thread::IsStarted((Thread *)(param_1 + 0x7c0));
  if (bVar2) {
    *puVar1 = 1;
    ab::Thread::Join((Thread *)(param_1 + 0x7c0));
  }
  FUN_10004a00(puVar1,"TryEndUpdate End");
  FUN_10004a00(puVar1,"EndUpdate End");
  FUN_10005c90();
  ac::LogDebug("Device","CALL [Net_DisConnCamera] Begin");
  iVar3 = Net_DisConnCamera(*(undefined4 *)(param_1 + 0x574));
  if (iVar3 == 0) {
    ac::LogDebug("Device","CALL [Net_DisConnCamera] OK");
  }
  else {
    uVar4 = FUN_100072c0();
    ac::LogError("Device","CALL [Net_DisConnCamera] FAILED, CODE: %d, MSG: %s",
                 (int)((ulonglong)uVar4 >> 0x20),(int)uVar4);
  }
  *(undefined1 *)(param_1 + 0x54) = 0;
  FUN_100065c0(param_1,"Close End");
  return 0;
}



/* FUNCTION FUN_10005550 ENTRY 10005550 */

void FUN_10005550(void)

{
  char cVar1;
  uint uVar2;
  int iVar3;
  undefined8 uVar4;
  undefined4 local_2c;
  uint local_18;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009828;
  local_10 = ExceptionList;
  uVar2 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  ac::LogDebug("Device","Init",uVar2);
  if (DAT_1000f9a0 == '\0') {
    ac::LogDebug("Device","CALL [Net_Init] Begin",uVar2);
    iVar3 = Net_Init();
    if (iVar3 == 0) {
      ac::LogDebug("Device","CALL [Net_Init] OK",uVar2);
    }
    else {
      uVar4 = FUN_100072c0();
      ac::LogError("Device","CALL [Net_Init] FAILED, CODE: %d, MSG: %s",
                   (int)((ulonglong)uVar4 >> 0x20),(int)uVar4);
    }
    Net_SetSynTimePeriod(10);
    FUN_10007c00();
    local_8 = 0;
    cVar1 = FUN_10003930();
    if (cVar1 != '\0') {
      FUN_10003560();
    }
    if (0xf < local_18) {
      FUN_10002a80(local_2c,local_18 + 1);
    }
    DAT_1000f9a0 = '\x01';
  }
  ExceptionList = local_10;
  FUN_100080b5();
  return;
}



/* FUNCTION FUN_10005750 ENTRY 10005750 */

undefined4 __thiscall FUN_10005750(int param_1,int param_2)

{
  char cVar1;
  int iVar2;
  int iVar3;
  undefined4 uVar4;
  char *pcVar5;
  undefined8 uVar6;
  void *local_14;
  code *pcStack_10;
  uint local_c;
  undefined4 local_8;
  
  local_8 = 0xfffffffe;
  pcStack_10 = FUN_10008bfa;
  local_14 = ExceptionList;
  local_c = DAT_1000f014 ^ 0x1000cbb8;
  if (*(char *)(param_1 + 0x54) != '\0') {
    return 0xfffffff9;
  }
  ExceptionList = &local_14;
  FUN_100065c0(param_1,"Open ...");
  FUN_10005650(param_2);
  ac::LogDebug("Device","CALL [Net_AddCamera] Begin");
  FUN_100065c0(param_1,"%s, %d, %s, %s",param_1 + 0x58,*(undefined4 *)(param_1 + 0xd8),
               param_1 + 0xdc,param_1 + 0x15c);
  iVar2 = Net_AddCamera(param_1 + 0x58);
  if (iVar2 == -1) {
    ac::LogError("Device","CALL [Net_AddCamera] Failed");
  }
  else {
    ac::LogDebug("Device","CALL [Net_RegReportMessEx] Begin");
    iVar3 = Net_RegReportMessEx(iVar2,FUN_10006bf0,param_1);
    if (iVar3 == 0) {
      ac::LogDebug("Device","CALL [Net_RegReportMessEx] OK");
    }
    else {
      uVar6 = FUN_100072c0();
      ac::LogError("Device","CALL [Net_RegReportMessEx] FAILED, CODE: %d, MSG: %s",
                   (int)((ulonglong)uVar6 >> 0x20),(int)uVar6);
    }
    local_8 = 0;
    ac::LogDebug("Device","CALL [Net_ConnCamera] Begin");
    iVar3 = Net_ConnCamera(iVar2,*(undefined2 *)(param_1 + 0xd8),5);
    if (iVar3 == 0) {
      ac::LogDebug("Device","CALL [Net_ConnCamera] OK");
      local_8 = 0xfffffffe;
      *(int *)(param_1 + 0x574) = iVar2;
      FUN_100065c0(param_1,&DAT_1000aa6c);
      ac::LogDebug("Device","CALL [Net_RegOffLineClient] Begin");
      iVar3 = Net_RegOffLineClient(iVar2);
      if (iVar3 == 0) {
        ac::LogDebug("Device","CALL [Net_RegOffLineClient] OK");
      }
      else {
        uVar6 = FUN_100072c0();
        ac::LogError("Device","CALL [Net_RegOffLineClient] FAILED, CODE: %d, MSG: %s",
                     (int)((ulonglong)uVar6 >> 0x20),(int)uVar6);
      }
      FUN_100065c0(param_1,&DAT_1000aaf4);
      ac::LogDebug("Device","CALL [Net_RegImageRecvEx] Begin");
      iVar3 = Net_RegImageRecvEx(iVar2,FUN_10006c30,param_1);
      if (iVar3 == 0) {
        ac::LogDebug("Device","CALL [Net_RegImageRecvEx] OK");
      }
      else {
        uVar6 = FUN_100072c0();
        ac::LogError("Device","CALL [Net_RegImageRecvEx] FAILED, CODE: %d, MSG: %s",
                     (int)((ulonglong)uVar6 >> 0x20),(int)uVar6);
      }
      FUN_100065c0(param_1,&DAT_1000ab80);
      ac::LogDebug("Device","CALL [Net_BlackWhiteListSendReportMess] Begin");
      iVar3 = Net_BlackWhiteListSendReportMess(iVar2,FUN_10006c70,param_1);
      if (iVar3 == 0) {
        ac::LogDebug("Device","CALL [Net_BlackWhiteListSendReportMess] OK");
      }
      else {
        uVar6 = FUN_100072c0();
        ac::LogError("Device","CALL [Net_BlackWhiteListSendReportMess] FAILED, CODE: %d, MSG: %s",
                     (int)((ulonglong)uVar6 >> 0x20),(int)uVar6);
      }
      FUN_100065c0(param_1,&DAT_1000ac4c);
      ac::LogDebug("Device","CALL [Net_SetControlCallBackEx] Begin");
      iVar2 = Net_SetControlCallBackEx(iVar2,&DAT_10006ca0,param_1);
      if (iVar2 == 0) {
        ac::LogDebug("Device","CALL [Net_SetControlCallBackEx] OK");
      }
      else {
        uVar6 = FUN_100072c0();
        ac::LogError("Device","CALL [Net_SetControlCallBackEx] FAILED, CODE: %d, MSG: %s",
                     (int)((ulonglong)uVar6 >> 0x20),(int)uVar6);
      }
      pcVar5 = (char *)(param_2 + 0x310);
      do {
        cVar1 = *pcVar5;
        pcVar5 = pcVar5 + 1;
      } while (cVar1 != '\0');
      if (pcVar5 == (char *)(param_2 + 0x311)) {
        FUN_100065c0(param_1,&DAT_1000acfc);
      }
      else {
        FUN_100065c0(param_1,&DAT_1000acf0);
        FUN_100016a0((char *)(param_2 + 0x310),*(undefined4 *)(param_2 + 0x390),param_2 + 0x394,
                     param_2 + 0x414);
      }
      FUN_100065c0(param_1,"Open OK");
      *(undefined1 *)(param_1 + 0x54) = 1;
      ExceptionList = local_14;
      return 0;
    }
    uVar4 = FUN_100072c0();
    ac::LogError("Device","CALL [Net_ConnCamera] FAILED, CODE: %d, MSG: %s",iVar3,uVar4);
    local_8 = 0xfffffffe;
  }
  FUN_100065c0(param_1,"Open Faild");
  ExceptionList = local_14;
  return 0xfffffe08;
}



/* FUNCTION CAM_InitSDK ENTRY 10005070 */

undefined4 CAM_InitSDK(void)

{
  int iVar1;
  
                    /* 0x5070  6  CAM_InitSDK */
  ac::SetLogPriority(7);
  if (DAT_1000f8a8 == 0) {
    iVar1 = FUN_100069d0();
    if (*(char *)(iVar1 + 0xc) == '\0') {
      InitializeCriticalSection((LPCRITICAL_SECTION)(iVar1 + 0x10));
      *(undefined1 *)(iVar1 + 0xc) = 1;
    }
    DAT_1000f8a8 = DAT_1000f8a8 + 1;
    return 0;
  }
  DAT_1000f8a8 = DAT_1000f8a8 + 1;
  return 0;
}



/* FUNCTION CAM_UninitSDK ENTRY 100050c0 */

undefined4 CAM_UninitSDK(void)

{
  int iVar1;
  
                    /* 0x50c0  15  CAM_UninitSDK */
  DAT_1000f8a8 = DAT_1000f8a8 + -1;
  if ((DAT_1000f8a8 == 0) && (iVar1 = FUN_100069d0(), *(char *)(iVar1 + 0xc) != '\0')) {
    DeleteCriticalSection((LPCRITICAL_SECTION)(iVar1 + 0x10));
    *(undefined1 *)(iVar1 + 0xc) = 0;
  }
  if (DAT_1000f8a8 < 0) {
    DAT_1000f8a8 = 0;
  }
  return 0;
}



/* FUNCTION CAM_OpenDevice ENTRY 10005100 */

undefined4 CAM_OpenDevice(undefined4 param_1,int *param_2)

{
  void *pvVar1;
  int iVar2;
  int iVar3;
  undefined4 extraout_ECX;
  
                    /* 0x5100  7  CAM_OpenDevice */
  FUN_100069d0();
  pvVar1 = operator_new(0x7d8);
  if (pvVar1 == (void *)0x0) {
    iVar2 = 0;
  }
  else {
    iVar2 = FUN_100053a0();
  }
  FUN_100068e0(iVar2);
  iVar3 = FUN_10005550();
  if (iVar3 == 0) {
    iVar3 = FUN_10005750(param_1);
    if (iVar3 == 0) {
      *param_2 = iVar2;
      return 0;
    }
    FUN_100069d0();
    FUN_10006970(iVar2);
    if (iVar2 != 0) {
      FUN_10006830(extraout_ECX);
    }
    return 0xfffffe08;
  }
  return 0xfffffe0a;
}



/* FUNCTION CAM_CloseDevice ENTRY 10005190 */

undefined4 CAM_CloseDevice(int param_1)

{
  undefined4 extraout_ECX;
  
                    /* 0x5190  3  CAM_CloseDevice */
  FUN_100069d0();
  FUN_10006970(param_1);
  if (param_1 != 0) {
    FUN_10006830(extraout_ECX);
  }
  return 0;
}



/* FUNCTION CAM_StartStream ENTRY 100051c0 */

undefined4 CAM_StartStream(int param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x51c0  13  CAM_StartStream */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005c00(param_1,param_3);
  return uVar1;
}



/* FUNCTION CAM_StopStream ENTRY 100051e0 */

undefined4 CAM_StopStream(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x51e0  14  CAM_StopStream */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005c90();
  return uVar1;
}



/* FUNCTION CAM_SetCaptureCallback ENTRY 10005200 */

undefined4 CAM_SetCaptureCallback(int param_1,undefined4 param_2,undefined4 param_3)

{
                    /* 0x5200  12  CAM_SetCaptureCallback */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  *(undefined4 *)(param_1 + 0x56c) = param_2;
  *(undefined4 *)(param_1 + 0x570) = param_3;
  return 0;
}



/* FUNCTION CAM_Capture ENTRY 10005230 */

undefined4 CAM_Capture(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x5230  1  CAM_Capture */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005d10();
  return uVar1;
}



/* FUNCTION CAM_CaptureTo ENTRY 10005250 */

undefined4 CAM_CaptureTo(int param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x5250  2  CAM_CaptureTo */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005da0(param_2);
  return uVar1;
}



/* FUNCTION CAM_Exec ENTRY 10005270 */

undefined4 CAM_Exec(int param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x5270  4  CAM_Exec */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005f20(param_2);
  return uVar1;
}



/* FUNCTION CAM_SerialWrite ENTRY 10005350 */

undefined4 CAM_SerialWrite(int param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4)

{
  undefined4 uVar1;
  
                    /* 0x5350  11  CAM_SerialWrite */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10006020(param_2,param_3,param_4);
  return uVar1;
}



/* FUNCTION FUN_100072c0 ENTRY 100072c0 */

undefined * __fastcall FUN_100072c0(int param_1)

{
  if (param_1 < 0x3e9) {
    if (param_1 == 1000) {
      return &DAT_1000b438;
    }
    switch(param_1) {
    case 0:
      return &DAT_1000b314;
    case 1:
      return &DAT_1000b31c;
    case 2:
      return &DAT_1000b328;
    case 3:
      return &DAT_1000b334;
    case 4:
      return &DAT_1000b33c;
    case 5:
      return &DAT_1000b348;
    case 6:
      return &DAT_1000b354;
    case 7:
      return &DAT_1000b360;
    case 8:
      return &DAT_1000b36c;
    case 9:
      return &DAT_1000b37c;
    case 10:
      return &DAT_1000b38c;
    case 0xb:
      return &DAT_1000b39c;
    case 0xc:
      return &DAT_1000b3a8;
    case 0xd:
      return &DAT_1000b3b8;
    case 0x12:
      return &DAT_1000b3d0;
    case 0x13:
      return &DAT_1000b3dc;
    case 0x14:
      return &DAT_1000b3e8;
    case 0x15:
      return &DAT_1000b3f4;
    case 0x16:
      return &DAT_1000b400;
    case 0x17:
      return &DAT_1000b410;
    case -1:
      return &DAT_1000b428;
    }
  }
  else if (param_1 < 0x515) {
    if (param_1 == 0x514) {
      return &DAT_1000b820;
    }
    switch(param_1) {
    case 0x3e9:
      return &DAT_1000b44c;
    case 0x3ea:
      return &DAT_1000b460;
    case 0x3eb:
      return &DAT_1000b474;
    case 0x3ec:
      return &DAT_1000b48c;
    case 0x3ed:
      return &DAT_1000b4a4;
    case 0x3ee:
      return &DAT_1000b4bc;
    case 0x3ef:
      return &DAT_1000b4cc;
    case 0x44c:
      return &DAT_1000b4d8;
    case 0x44d:
      return &DAT_1000b4ec;
    case 0x44e:
      return &DAT_1000b4fc;
    case 0x44f:
      return &DAT_1000b510;
    case 0x450:
    case 0x456:
      return &DAT_1000b528;
    case 0x451:
      return &DAT_1000b53c;
    case 0x452:
      return &DAT_1000b550;
    case 0x453:
      return &DAT_1000b564;
    case 0x454:
      return &DAT_1000b578;
    case 0x455:
      return &DAT_1000b58c;
    case 0x457:
      return &DAT_1000b5a0;
    case 0x458:
      return &DAT_1000b5b4;
    case 0x459:
      return &DAT_1000b5c8;
    case 0x45a:
      return &DAT_1000b5dc;
    case 0x45b:
      return &DAT_1000b5f4;
    case 0x45d:
      return &DAT_1000b608;
    case 0x45e:
      return &DAT_1000b61c;
    case 0x45f:
      return &DAT_1000b634;
    case 0x460:
      return &DAT_1000b64c;
    case 0x461:
      return &DAT_1000b668;
    case 0x462:
      return &DAT_1000b688;
    case 0x463:
      return &DAT_1000b69c;
    case 0x464:
      return &DAT_1000b6b0;
    case 0x465:
      return &DAT_1000b6c4;
    case 0x466:
      return &DAT_1000b6e4;
    case 0x467:
      return &DAT_1000b6fc;
    case 0x4b0:
    case 0x4c4:
      return &DAT_1000b714;
    case 0x4b1:
      return &DAT_1000b728;
    case 0x4b2:
      return &DAT_1000b73c;
    case 0x4b3:
      return &DAT_1000b754;
    case 0x4b4:
      return &DAT_1000b76c;
    case 0x4b5:
      return &DAT_1000b780;
    case 0x4c5:
      return &DAT_1000b794;
    case 0x4e2:
      return &DAT_1000b7ac;
    case 0x4e3:
      return &DAT_1000b7c0;
    case 0x4e4:
      return &DAT_1000b7d8;
    case 0x4e5:
      return &DAT_1000b7f0;
    case 0x4e6:
      return &DAT_1000b808;
    }
  }
  else {
    if (param_1 == 0x515) {
      return &DAT_1000b838;
    }
    if (param_1 == 0x516) {
      return &DAT_1000b854;
    }
    if (param_1 == 0x578) {
      return &DAT_1000b868;
    }
  }
  return &DAT_1000b87c;
}



/* FUNCTION FUN_100065c0 ENTRY 100065c0 */

void FUN_100065c0(undefined4 param_1,char *param_2)

{
  ac::LogArg("IPC_QY::Device",6,param_2,&stack0x0000000c);
  return;
}



/* FUNCTION FUN_10004410 ENTRY 10004410 */

void __thiscall FUN_10004410(undefined1 *param_1,undefined4 param_2,int param_3,int param_4)

{
  bool bVar1;
  uint uVar2;
  int iVar3;
  ThreadParam *this;
  int iVar4;
  undefined4 *puVar5;
  undefined4 *puVar6;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_1000976f;
  local_10 = ExceptionList;
  uVar2 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  FUN_10004a00(param_1,"BeginUpdate Begin",uVar2);
  FUN_10004a00(param_1,"TryEndUpdate Begin");
  bVar1 = ab::Thread::IsStarted((Thread *)(param_1 + 4));
  if (bVar1) {
    *param_1 = 1;
    ab::Thread::Join((Thread *)(param_1 + 4));
  }
  FUN_10004a00(param_1,"TryEndUpdate End",uVar2);
  *(undefined4 *)(param_1 + 0xc) = param_2;
  FUN_10004b10(param_4);
  if (0 < param_4) {
    iVar3 = 0;
    do {
      puVar6 = (undefined4 *)(*(int *)(param_1 + 0x10) + iVar3);
      puVar5 = (undefined4 *)(param_3 + iVar3);
      iVar3 = iVar3 + 0xe4;
      for (iVar4 = 0x39; iVar4 != 0; iVar4 = iVar4 + -1) {
        *puVar6 = *puVar5;
        puVar5 = puVar5 + 1;
        puVar6 = puVar6 + 1;
      }
      param_4 = param_4 + -1;
    } while (param_4 != 0);
  }
  FUN_10004a00(param_1,"Start ThreadProc ...");
  *param_1 = 0;
  this = operator_new(0x10);
  local_8 = 0;
  if (this == (ThreadParam *)0x0) {
    this = (ThreadParam *)0x0;
  }
  else {
    ab::ThreadParam::ThreadParam(this,true);
    *(undefined ***)this = ab::ThreadFunction<BWListUpdater>::vftable;
    *(undefined1 **)(this + 8) = param_1;
    *(code **)(this + 0xc) = FUN_10004530;
  }
  local_8 = 0xffffffff;
  ab::Thread::Start((Thread *)(param_1 + 4),this);
  FUN_10004a00(param_1,"BeginUpdate End");
  ExceptionList = local_10;
  return;
}



/* FUNCTION FUN_10006750 ENTRY 10006750 */

void __thiscall FUN_10006750(uint *param_1,uint param_2)

{
  uint uVar1;
  void *pvVar2;
  void *pvVar3;
  void *_Dst;
  
  if (param_2 == 0) {
    _Dst = (void *)0x0;
  }
  else if (param_2 < 0x1000) {
    _Dst = operator_new(param_2);
    if (_Dst == (void *)0x0) {
                    /* WARNING: Subroutine does not return */
      _invalid_parameter_noinfo_noreturn();
    }
  }
  else {
    if (param_2 + 0x23 <= param_2) {
                    /* WARNING: Subroutine does not return */
      std::_Xbad_alloc();
    }
    pvVar2 = operator_new(param_2 + 0x23);
    if (pvVar2 == (void *)0x0) {
                    /* WARNING: Subroutine does not return */
      _invalid_parameter_noinfo_noreturn();
    }
    _Dst = (void *)((int)pvVar2 + 0x23U & 0xffffffe0);
    *(void **)((int)_Dst + -4) = pvVar2;
  }
  memmove(_Dst,(void *)*param_1,param_1[1] - (int)*param_1);
  pvVar2 = (void *)*param_1;
  uVar1 = param_1[1];
  if (pvVar2 != (void *)0x0) {
    pvVar3 = pvVar2;
    if (0xfff < param_1[2] - (int)pvVar2) {
      if (((uint)pvVar2 & 0x1f) != 0) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      pvVar3 = *(void **)((int)pvVar2 - 4);
      if (pvVar2 <= pvVar3) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      if ((uint)((int)pvVar2 - (int)pvVar3) < 4) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      if (0x23 < (uint)((int)pvVar2 - (int)pvVar3)) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
    }
    operator_delete(pvVar3);
  }
  param_1[2] = (int)_Dst + param_2;
  param_1[1] = (uVar1 - (int)pvVar2) + (int)_Dst;
  *param_1 = (uint)_Dst;
  return;
}



/* FUNCTION FUN_10004240 ENTRY 10004240 */

int FUN_10004240(undefined4 param_1,undefined4 param_2)

{
  uint *puVar1;
  int iVar2;
  
  puVar1 = (uint *)FUN_10002040(param_1,0xffffffff,param_2,0,&stack0x0000000c);
  iVar2 = __stdio_common_vsprintf(*puVar1 | 1,puVar1[1]);
  if (iVar2 < 0) {
    iVar2 = -1;
  }
  return iVar2;
}



/* FUNCTION FUN_100066f0 ENTRY 100066f0 */

void __thiscall FUN_100066f0(int *param_1,uint param_2)

{
  int iVar1;
  int iVar2;
  uint uVar3;
  uint uVar4;
  
  iVar1 = param_1[1];
  if ((uint)(param_1[2] - iVar1) < param_2) {
    iVar2 = *param_1;
    if ((iVar2 - iVar1) - 1U < param_2) {
                    /* WARNING: Subroutine does not return */
      std::_Xlength_error("vector<T> too long");
    }
    uVar4 = param_1[2] - iVar2;
    param_2 = (iVar1 - iVar2) + param_2;
    uVar3 = 0;
    if (uVar4 <= ~(uVar4 >> 1)) {
      uVar3 = (uVar4 >> 1) + uVar4;
    }
    if (param_2 <= uVar3) {
      param_2 = uVar3;
    }
    FUN_10006750(param_2);
  }
  return;
}



/* FUNCTION FUN_10004a00 ENTRY 10004a00 */

void FUN_10004a00(undefined4 param_1,char *param_2)

{
  ac::LogArg("BWListUpdater",7,param_2,&stack0x0000000c);
  return;
}



/* FUNCTION FUN_10007c00 ENTRY 10007c00 */

/* WARNING: Removing unreachable block (ram,0x10007c55) */

basic_string<char,std::char_traits<char>,std::allocator<char>_> * __fastcall
FUN_10007c00(basic_string<char,std::char_traits<char>,std::allocator<char>_> *param_1,char param_2)

{
  char cVar1;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  puStack_c = &LAB_10009929;
  local_10 = ExceptionList;
  ExceptionList = &local_10;
  local_8 = 0;
  FUN_10002920("TMP\\IPC_QY",10);
  FUN_10003fc0();
  local_8 = 0;
  if ((param_2 != '\0') && (cVar1 = FUN_10003930(), cVar1 == '\0')) {
    ac::CreateDirectories(param_1);
  }
  ExceptionList = local_10;
  return param_1;
}



/* FUNCTION FUN_10003930 ENTRY 10003930 */

void __fastcall FUN_10003930(LPCSTR param_1)

{
  int iVar1;
  HANDLE hFindFile;
  undefined1 auStack_154 [4];
  _WIN32_FIND_DATAA local_150;
  uint local_c;
  
  local_c = DAT_1000f014 ^ (uint)auStack_154;
  iVar1 = FUN_100042b0(&DAT_1000a5b0,0);
  if (iVar1 != 0) {
    if (0xf < *(uint *)(param_1 + 0x14)) {
      param_1 = *(LPCSTR *)param_1;
    }
    hFindFile = FindFirstFileA(param_1,&local_150);
    if (hFindFile != (HANDLE)0xffffffff) {
      if (((byte)local_150.dwFileAttributes & 0x10) != 0) {
        FindClose(hFindFile);
        FUN_100080b5();
        return;
      }
      FindClose(hFindFile);
    }
  }
  FUN_100080b5();
  return;
}



/* FUNCTION FUN_10003560 ENTRY 10003560 */

void FUN_10003560(void)

{
  char cVar1;
  uint uVar2;
  uint uVar3;
  int iVar4;
  LPCSTR *****ppppppCVar5;
  HANDLE hFindFile;
  char ******ppppppcVar6;
  BOOL BVar7;
  CHAR *pCVar8;
  _WIN32_FIND_DATAA local_1cc;
  undefined4 local_8c [5];
  uint local_78;
  uint local_74;
  undefined4 local_64;
  uint local_60;
  LPCSTR ****local_5c [4];
  undefined4 local_4c;
  uint local_48;
  LPCSTR ****local_44 [4];
  undefined4 local_34;
  uint local_30;
  char *****local_2c [4];
  undefined4 local_1c;
  uint local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009639;
  local_10 = ExceptionList;
  local_14 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  iVar4 = FUN_100042b0(&DAT_1000a5b0,0,local_14);
  if (iVar4 != 0) {
    FUN_10003ad0();
    local_8 = 0;
    memset(&local_1cc,0,0x140);
    local_30 = 0xf;
    local_34 = 0;
    local_44[0] = (LPCSTR ****)((uint)local_44[0] & 0xffffff00);
    FUN_10002920(&DAT_1000a5b0,0);
    local_8 = CONCAT31(local_8._1_3_,1);
    FUN_10002230(&DAT_1000a644,4);
    FUN_10002320(local_8c,0,0xffffffff);
    ppppppCVar5 = (LPCSTR *****)FUN_100039d0();
    if (local_44 != ppppppCVar5) {
      if (0xf < local_30) {
        FUN_10002a80(local_44[0],local_30 + 1);
      }
      local_30 = 0xf;
      local_34 = 0;
      local_44[0] = (LPCSTR ****)((uint)local_44[0] & 0xffffff00);
      FUN_10002410(ppppppCVar5);
    }
    local_8._0_1_ = 1;
    if (0xf < local_60) {
      FUN_10002a80(local_74,local_60 + 1);
    }
    FUN_10002230(&DAT_1000a64c,3);
    local_48 = 0xf;
    local_4c = 0;
    local_5c[0] = (LPCSTR ****)((uint)local_5c[0] & 0xffffff00);
    FUN_10002920(&DAT_1000a5b0,0);
    local_8 = CONCAT31(local_8._1_3_,3);
    FUN_10002230(&DAT_1000a644,4);
    FUN_10002320(local_8c,0,0xffffffff);
    ppppppCVar5 = local_44;
    if (0xf < local_30) {
      ppppppCVar5 = (LPCSTR *****)local_44[0];
    }
    hFindFile = FindFirstFileA((LPCSTR)ppppppCVar5,&local_1cc);
    if (hFindFile != (HANDLE)0xffffffff) {
      do {
        local_18 = 0xf;
        local_1c = 0;
        local_2c[0] = (char *****)((uint)local_2c[0] & 0xffffff00);
        FUN_10002920(&DAT_1000a5b0,0);
        local_8 = CONCAT31(local_8._1_3_,4);
        FUN_10002320(local_8c,0,0xffffffff);
        ppppppcVar6 = (char ******)FUN_100039d0();
        if (local_2c != ppppppcVar6) {
          if (0xf < local_18) {
            FUN_10002a80(local_2c[0],local_18 + 1);
          }
          local_18 = 0xf;
          local_1c = 0;
          local_2c[0] = (char *****)((uint)local_2c[0] & 0xffffff00);
          FUN_10002410(ppppppcVar6);
        }
        local_8._0_1_ = 4;
        if (0xf < local_60) {
          FUN_10002a80(local_74,local_60 + 1);
        }
        if (local_1cc.cFileName[0] == '\0') {
          iVar4 = 0;
        }
        else {
          pCVar8 = local_1cc.cFileName;
          do {
            cVar1 = *pCVar8;
            pCVar8 = pCVar8 + 1;
          } while (cVar1 != '\0');
          iVar4 = (int)pCVar8 - (int)(local_1cc.cFileName + 1);
        }
        FUN_10002230(local_1cc.cFileName,iVar4);
        if (((byte)local_1cc.dwFileAttributes & 0x10) == 0) {
          ppppppcVar6 = local_2c;
          if (0xf < local_18) {
            ppppppcVar6 = (char ******)local_2c[0];
          }
          _unlink((char *)ppppppcVar6);
        }
        else {
          FUN_10003be0();
          uVar3 = local_60;
          uVar2 = local_74;
          local_8._0_1_ = 6;
          iVar4 = FUN_100042b0(&DAT_1000a66c,1);
          if ((iVar4 == 0) || (iVar4 = FUN_100042b0(&DAT_1000a650,2), iVar4 == 0)) {
            if (0xf < uVar3) {
              FUN_10002a80(uVar2,uVar3 + 1);
            }
            local_60 = 0xf;
            local_64 = 0;
            local_74 = local_74 & 0xffffff00;
          }
          else {
            FUN_10003560();
            if (0xf < local_60) {
              FUN_10002a80(local_74,local_60 + 1);
            }
          }
        }
        local_8 = CONCAT31(local_8._1_3_,3);
        if (0xf < local_18) {
          FUN_10002a80(local_2c[0],local_18 + 1);
        }
        BVar7 = FindNextFileA(hFindFile,&local_1cc);
      } while (BVar7 == 1);
      FindClose(hFindFile);
    }
    ppppppCVar5 = local_5c;
    if (0xf < local_48) {
      ppppppCVar5 = (LPCSTR *****)local_5c[0];
    }
    RemoveDirectoryA((LPCSTR)ppppppCVar5);
    if (0xf < local_48) {
      FUN_10002a80(local_5c[0],local_48 + 1);
    }
    local_48 = 0xf;
    local_4c = 0;
    local_5c[0] = (LPCSTR ****)((uint)local_5c[0] & 0xffffff00);
    if (0xf < local_30) {
      FUN_10002a80(local_44[0],local_30 + 1);
    }
    local_30 = 0xf;
    local_34 = 0;
    local_44[0] = (LPCSTR ****)((uint)local_44[0] & 0xffffff00);
    if (0xf < local_78) {
      FUN_10002a80(local_8c[0],local_78 + 1);
    }
  }
  ExceptionList = local_10;
  FUN_100080b5();
  return;
}



/* FUNCTION FUN_10005650 ENTRY 10005650 */

void __thiscall FUN_10005650(int param_1,undefined4 *param_2)

{
  char cVar1;
  int iVar2;
  char *pcVar3;
  undefined4 *puVar4;
  
  puVar4 = (undefined4 *)(param_1 + 0x58);
  for (iVar2 = 0x145; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *param_2;
    param_2 = param_2 + 1;
    puVar4 = puVar4 + 1;
  }
  if (*(int *)(param_1 + 0xd8) == 0) {
    *(undefined4 *)(param_1 + 0xd8) = 30000;
  }
  pcVar3 = (char *)(param_1 + 0xdc);
  do {
    cVar1 = *pcVar3;
    pcVar3 = pcVar3 + 1;
  } while (cVar1 != '\0');
  if (pcVar3 == (char *)(param_1 + 0xdd)) {
    *(undefined4 *)(param_1 + 0xdc) = s_admin_1000a914._0_4_;
    *(undefined2 *)(param_1 + 0xe0) = s_admin_1000a914._4_2_;
  }
  pcVar3 = (char *)(param_1 + 0x15c);
  do {
    cVar1 = *pcVar3;
    pcVar3 = pcVar3 + 1;
  } while (cVar1 != '\0');
  if (pcVar3 == (char *)(param_1 + 0x15d)) {
    *(undefined4 *)(param_1 + 0x15c) = s_admin_1000a914._0_4_;
    *(undefined2 *)(param_1 + 0x160) = s_admin_1000a914._4_2_;
  }
  if (*(int *)(param_1 + 0x25c) == 0) {
    *(undefined4 *)(param_1 + 0x25c) = 30000;
  }
  pcVar3 = (char *)(param_1 + 0x260);
  do {
    cVar1 = *pcVar3;
    pcVar3 = pcVar3 + 1;
  } while (cVar1 != '\0');
  if (pcVar3 == (char *)(param_1 + 0x261)) {
    *(undefined4 *)(param_1 + 0x260) = s_admin_1000a914._0_4_;
    *(undefined2 *)(param_1 + 0x264) = s_admin_1000a914._4_2_;
  }
  pcVar3 = (char *)(param_1 + 0x2e0);
  do {
    cVar1 = *pcVar3;
    pcVar3 = pcVar3 + 1;
  } while (cVar1 != '\0');
  if (pcVar3 == (char *)(param_1 + 0x2e1)) {
    *(undefined4 *)(param_1 + 0x2e0) = s_admin_1000a914._0_4_;
    *(undefined2 *)(param_1 + 0x2e4) = s_admin_1000a914._4_2_;
  }
  return;
}



/* FUNCTION FUN_100016a0 ENTRY 100016a0 */

void __thiscall FUN_100016a0(int param_1,char *param_2,int param_3,char *param_4,char *param_5)

{
  char cVar1;
  int *piVar2;
  char *pcVar3;
  int iVar4;
  int iVar5;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  puStack_c = &LAB_100093d0;
  local_10 = ExceptionList;
  if (*(int *)(param_1 + 4) != 0) {
    return;
  }
  local_8 = 0;
  iVar5 = 0x238b;
  if (param_3 != 0) {
    iVar5 = param_3;
  }
  if (param_2 == (char *)0x0) {
LAB_1000170b:
    param_2 = "127.0.0.1";
  }
  else {
    pcVar3 = param_2;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    if (pcVar3 == param_2 + 1) goto LAB_1000170b;
  }
  if (param_4 == (char *)0x0) {
LAB_1000172b:
    param_4 = "1";
  }
  else {
    pcVar3 = param_4;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    if (pcVar3 == param_4 + 1) goto LAB_1000172b;
  }
  if (param_5 != (char *)0x0) {
    pcVar3 = param_5;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    if (pcVar3 != param_5 + 1) goto LAB_10001751;
  }
  param_5 = &DAT_1000a538;
LAB_10001751:
  ExceptionList = &local_10;
  FUN_10001ac0(param_1,&DAT_1000a540,param_2,iVar5,param_4,param_5);
  FUN_100013e0();
  piVar2 = (int *)(*DAT_1000f8a4)();
  (**(code **)(*piVar2 + 4))(param_2,iVar5,param_4,param_5);
  (**(code **)(*piVar2 + 0x10))(FUN_10001840,param_1);
  if (*param_2 == '\0') {
    iVar4 = 0;
  }
  else {
    pcVar3 = param_2;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    iVar4 = (int)pcVar3 - (int)(param_2 + 1);
  }
  FUN_10002920(param_2,iVar4);
  *(int *)(param_1 + 0x20) = iVar5;
  if (*param_4 == '\0') {
    iVar5 = 0;
  }
  else {
    pcVar3 = param_4;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    iVar5 = (int)pcVar3 - (int)(param_4 + 1);
  }
  FUN_10002920(param_4,iVar5);
  if (*param_5 == '\0') {
    iVar5 = 0;
  }
  else {
    pcVar3 = param_5;
    do {
      cVar1 = *pcVar3;
      pcVar3 = pcVar3 + 1;
    } while (cVar1 != '\0');
    iVar5 = (int)pcVar3 - (int)(param_5 + 1);
  }
  FUN_10002920(param_5,iVar5);
  ExceptionList = local_10;
  return;
}



/* FUNCTION FUN_100069d0 ENTRY 100069d0 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 * FUN_100069d0(void)

{
  if (*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000f9ac) {
    FUN_10008352(&DAT_1000f9ac);
    if (DAT_1000f9ac == -1) {
      DAT_1000f9b0 = 0;
      _DAT_1000f9b4 = 0;
      DAT_1000f9b8 = 0;
      DAT_1000f9bc = 0;
      FUN_10008771(&LAB_100099a0);
      FUN_10008313(&DAT_1000f9ac);
    }
  }
  return &DAT_1000f9b0;
}



/* FUNCTION FUN_100053a0 ENTRY 100053a0 */

undefined4 * __fastcall FUN_100053a0(undefined4 *param_1)

{
  undefined4 *puVar1;
  HANDLE pvVar2;
  void *local_10;
  undefined1 *puStack_c;
  undefined1 local_8;
  undefined3 uStack_7;
  
  puStack_c = &LAB_10009802;
  local_10 = ExceptionList;
  ExceptionList = &local_10;
  *(undefined2 *)(param_1 + 0x15) = 0;
  puVar1 = param_1 + 2;
  *param_1 = CloudGateDevice::vftable;
  param_1[1] = 0;
  param_1[7] = 0xf;
  param_1[6] = 0;
  if (0xf < (uint)param_1[7]) {
    puVar1 = (undefined4 *)*puVar1;
  }
  *(undefined1 *)puVar1 = 0;
  puVar1 = param_1 + 9;
  param_1[8] = 0;
  param_1[0xe] = 0xf;
  param_1[0xd] = 0;
  if (0xf < (uint)param_1[0xe]) {
    puVar1 = (undefined4 *)*puVar1;
  }
  *(undefined1 *)puVar1 = 0;
  puVar1 = param_1 + 0xf;
  param_1[0x14] = 0xf;
  param_1[0x13] = 0;
  if (0xf < (uint)param_1[0x14]) {
    puVar1 = (undefined4 *)*puVar1;
  }
  *(undefined1 *)puVar1 = 0;
  *param_1 = Device::vftable;
  param_1[0x15e] = 0;
  param_1[0x15f] = 0;
  param_1[0x160] = 0;
  param_1[0x163] = 0;
  param_1[0x164] = 0;
  param_1[0x165] = 0;
  local_8 = 2;
  uStack_7 = 0;
  *(undefined1 *)(param_1 + 0x1ef) = 0;
  ab::Thread::Thread((Thread *)(param_1 + 0x1f0));
  param_1[499] = 0;
  param_1[500] = 0;
  param_1[0x1f5] = 0;
  _local_8 = CONCAT31(uStack_7,3);
  memset(param_1 + 0x16,0,0x514);
  param_1[0x15b] = 0;
  param_1[0x15c] = 0;
  param_1[0x15d] = 0;
  param_1[0x162] = 0;
  FUN_10006620(0x300000);
  InitializeCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x1e3));
  InitializeCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x1e9));
  pvVar2 = CreateEventA((LPSECURITY_ATTRIBUTES)0x0,1,0,(LPCSTR)0x0);
  param_1[0x166] = pvVar2;
  *(undefined1 *)(param_1 + 0x167) = 0;
  ExceptionList = local_10;
  return param_1;
}



/* FUNCTION FUN_100068e0 ENTRY 100068e0 */

void __thiscall FUN_100068e0(uint *param_1,undefined4 param_2)

{
  LPCRITICAL_SECTION lpCriticalSection;
  undefined4 *puVar1;
  undefined4 *puVar2;
  
  lpCriticalSection = (LPCRITICAL_SECTION)(param_1 + 4);
  EnterCriticalSection(lpCriticalSection);
  puVar1 = (undefined4 *)param_1[1];
  puVar2 = &param_2;
  if (puVar2 < puVar1) {
    puVar2 = (undefined4 *)*param_1;
    if (puVar2 <= &param_2) {
      if (puVar1 == (undefined4 *)param_1[2]) {
        FUN_10006a50(puVar2);
      }
      if ((undefined4 *)param_1[1] != (undefined4 *)0x0) {
        *(undefined4 *)param_1[1] =
             *(undefined4 *)(*param_1 + ((int)&param_2 - (int)puVar2 >> 2) * 4);
      }
      param_1[1] = param_1[1] + 4;
      LeaveCriticalSection(lpCriticalSection);
      return;
    }
  }
  if (puVar1 == (undefined4 *)param_1[2]) {
    FUN_10006a50(puVar2);
  }
  if ((undefined4 *)param_1[1] != (undefined4 *)0x0) {
    *(undefined4 *)param_1[1] = param_2;
  }
  param_1[1] = param_1[1] + 4;
  LeaveCriticalSection(lpCriticalSection);
  return;
}



/* FUNCTION FUN_10006970 ENTRY 10006970 */

void __thiscall FUN_10006970(int *param_1,int param_2)

{
  int *_Dst;
  int *piVar1;
  
  EnterCriticalSection((LPCRITICAL_SECTION)(param_1 + 4));
  _Dst = (int *)*param_1;
  piVar1 = (int *)param_1[1];
  if (_Dst != piVar1) {
    do {
      if (*_Dst == param_2) {
        memmove(_Dst,_Dst + 1,(int)piVar1 - (int)(_Dst + 1));
        param_1[1] = param_1[1] + -4;
        _Dst = (int *)*param_1;
      }
      else {
        _Dst = _Dst + 1;
      }
      piVar1 = (int *)param_1[1];
    } while (_Dst != piVar1);
  }
  LeaveCriticalSection((LPCRITICAL_SECTION)(param_1 + 4));
  return;
}



/* FUNCTION FUN_10006830 ENTRY 10006830 */

undefined4 * __fastcall FUN_10006830(undefined4 *param_1)

{
  uint uVar1;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  puStack_c = &LAB_10009527;
  local_10 = ExceptionList;
  uVar1 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_8 = 0;
  *param_1 = Device::vftable;
  FUN_10005b10(uVar1);
  DeleteObject((HGDIOBJ)param_1[0x166]);
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x1e3));
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x1e9));
  FUN_10004340();
  FUN_10006680();
  FUN_10006680();
  FUN_100015b0();
  FUN_100080c6(param_1,0x7d8);
  ExceptionList = local_10;
  return param_1;
}



/* FUNCTION FUN_10005da0 ENTRY 10005da0 */

undefined4 __thiscall FUN_10005da0(int param_1,undefined4 param_2)

{
  undefined4 uVar1;
  void *local_14;
  code *pcStack_10;
  uint local_c;
  undefined4 local_8;
  
  local_8 = 0xfffffffe;
  pcStack_10 = FUN_10008bfa;
  local_14 = ExceptionList;
  local_c = DAT_1000f014 ^ 0x1000cbd8;
  if (*(char *)(param_1 + 0x54) == '\0') {
    return 0xfffffff9;
  }
  ExceptionList = &local_14;
  EnterCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x78c));
  *(undefined1 *)(param_1 + 0x59c) = 1;
  local_8 = 1;
  uVar1 = FUN_10005eb0(param_2);
  local_8 = 0;
  FUN_10005e4d();
  local_8 = 0xfffffffe;
  *(undefined1 *)(param_1 + 0x59c) = 0;
  LeaveCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x78c));
  ExceptionList = local_14;
  return uVar1;
}



/* FUNCTION FUN_10006020 ENTRY 10006020 */

undefined4 __thiscall
FUN_10006020(int param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4)

{
  undefined4 uVar1;
  void *local_14;
  code *pcStack_10;
  uint local_c;
  undefined4 local_8;
  
  local_8 = 0xfffffffe;
  pcStack_10 = FUN_10008bfa;
  local_14 = ExceptionList;
  local_c = DAT_1000f014 ^ 0x1000cc00;
  if (*(char *)(param_1 + 0x54) == '\0') {
    return 0xfffffff9;
  }
  ExceptionList = &local_14;
  FUN_100065c0(param_1,"SerialWrite: hSerial: %d",param_2);
  local_8 = 1;
  uVar1 = FUN_10006120(param_2,param_3,param_4);
  local_8 = 0;
  FUN_100060cd();
  ExceptionList = local_14;
  return uVar1;
}


