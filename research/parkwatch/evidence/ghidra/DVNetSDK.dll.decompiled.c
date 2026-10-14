
/* FUNCTION DV_InitSDK ENTRY 100063d0 */

undefined4 DV_InitSDK(void)

{
  int iVar1;
  
                    /* 0x63d0  21  DV_InitSDK */
  EnterCriticalSection((LPCRITICAL_SECTION)&DAT_1000e9e4);
  FUN_100073d0();
  FUN_10007790();
  if (DAT_1000e78c == '\0') {
    ac::SetLogPriority(7);
    CoInitialize((LPVOID)0x0);
    FUN_100059f0();
    FUN_10005800();
    iVar1 = FUN_100059f0();
    if (*(int *)(iVar1 + 0x38) != 0) {
      *(undefined4 *)(iVar1 + 0x38) = 0;
    }
    DAT_1000e78c = '\x01';
  }
  LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_1000e9e4);
  return 0;
}



/* FUNCTION DV_ReleaseSDK ENTRY 10006440 */

undefined4 DV_ReleaseSDK(void)

{
  int iVar1;
  
                    /* 0x6440  25  DV_ReleaseSDK */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  EnterCriticalSection((LPCRITICAL_SECTION)&DAT_1000e9e4);
  iVar1 = FUN_100059f0();
  if (*(int *)(iVar1 + 0x38) != 0) {
    *(undefined4 *)(iVar1 + 0x38) = 0;
  }
  iVar1 = FUN_100059f0();
  if (*(char *)(iVar1 + 0xc) != '\0') {
    *(undefined1 *)(iVar1 + 0x34) = 1;
    WaitForSingleObject(*(HANDLE *)(iVar1 + 0x30),0xffffffff);
    DeleteCriticalSection((LPCRITICAL_SECTION)(iVar1 + 0x10));
    FUN_10007770("CDeviceManager",&DAT_1000ac2c);
    *(undefined1 *)(iVar1 + 0xc) = 0;
  }
  DAT_1000e78c = 0;
  LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_1000e9e4);
  return 0;
}



/* FUNCTION DV_OpenDevice ENTRY 10006530 */

int DV_OpenDevice(int param_1,int *param_2)

{
  int iVar1;
  int iVar2;
  undefined4 extraout_ECX;
  
                    /* 0x6530  22  DV_OpenDevice */
  if (DAT_1000e78c == '\0') {
    return -0x38;
  }
  if ((param_1 != 0) && (param_2 != (int *)0x0)) {
    FUN_10007c31(0x408);
    iVar1 = FUN_10004100();
    iVar2 = FUN_100044f0(param_1);
    if (iVar2 == 0) {
      *param_2 = iVar1;
      FUN_100059f0(iVar1);
      FUN_10005870(iVar1);
      return 0;
    }
    if (iVar1 != 0) {
      FUN_100065c0(extraout_ECX);
    }
    return iVar2;
  }
  return -0x36;
}



/* FUNCTION DV_CloseDevice ENTRY 100065e0 */

undefined4 DV_CloseDevice(int param_1)

{
  int iVar1;
  
                    /* 0x65e0  8  DV_CloseDevice */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  iVar1 = param_1;
  FUN_100059f0(param_1);
  FUN_10005900(iVar1);
  FUN_10004340();
  FUN_10007c64(param_1,0x408);
  return 0;
}



/* FUNCTION DV_StartStream ENTRY 100066b0 */

undefined4 DV_StartStream(int param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x66b0  39  DV_StartStream */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  uVar1 = FUN_100047b0(param_2,param_3);
  return uVar1;
}



/* FUNCTION DV_SetCaptureCallback ENTRY 10006760 */

undefined4 DV_SetCaptureCallback(undefined4 *param_1,undefined4 param_2,undefined4 param_3)

{
                    /* 0x6760  31  DV_SetCaptureCallback */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == (undefined4 *)0x0) {
    return 0xffffffcb;
  }
  (*(code *)param_1[0xef])(*param_1,FUN_10005c30,param_1);
  param_1[0xba] = param_2;
  param_1[0xbb] = param_3;
  return 0;
}



/* FUNCTION DV_Capture ENTRY 100067b0 */

undefined4 DV_Capture(int param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x67b0  5  DV_Capture */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  uVar1 = FUN_10004890(param_2);
  return uVar1;
}



/* FUNCTION DV_CaptureToFile ENTRY 100067e0 */

undefined4 DV_CaptureToFile(int param_1,int param_2)

{
  undefined4 uVar1;
  
                    /* 0x67e0  6  DV_CaptureToFile */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  if (param_2 == 0) {
    return 0xffffffca;
  }
  uVar1 = FUN_10004cb0();
  return uVar1;
}



/* FUNCTION DV_CaptureToMem ENTRY 10006820 */

undefined4 DV_CaptureToMem(int param_1,int param_2,undefined4 param_3,int param_4)

{
                    /* 0x6820  7  DV_CaptureToMem */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  if ((param_2 != 0) && (param_4 != 0)) {
    FUN_10004f30(param_1,"[GLOBAL]",&DAT_1000a8d0);
    return 0xfffffdc5;
  }
  return 0xffffffca;
}



/* FUNCTION DV_Exec ENTRY 10006970 */

undefined4 DV_Exec(int param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x6970  11  DV_Exec */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == 0) {
    return 0xffffffcb;
  }
  uVar1 = FUN_10004d10(param_2);
  return uVar1;
}



/* FUNCTION DV_OpenRS485 ENTRY 10007150 */

undefined4 DV_OpenRS485(undefined4 *param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  
                    /* 0x7150  23  DV_OpenRS485 */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  if (param_1 == (undefined4 *)0x0) {
    return 0xffffffcb;
  }
  iVar1 = (*(code *)param_1[0xf5])(*param_1,param_2,param_3);
  if (iVar1 != 0) {
    FUN_10004f30(param_1,"CAM_SerialOpen Failed");
    return 0xfffffdd6;
  }
  FUN_10004f30(param_1,"CAM_SerialClose OK");
  return 0;
}



/* FUNCTION DV_CloseRS485 ENTRY 100071c0 */

undefined4 DV_CloseRS485(undefined4 *param_1,undefined4 param_2)

{
  int iVar1;
  
                    /* 0x71c0  9  DV_CloseRS485 */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  iVar1 = (*(code *)param_1[0xf6])(*param_1,param_2);
  if (iVar1 != 0) {
    FUN_10004f30(param_1,"CAM_SerialClose Failed");
    return 0xfffffdd8;
  }
  FUN_10004f30(param_1,"CAM_SerialClose OK");
  return 0;
}



/* FUNCTION DV_WriteRS485 ENTRY 10007220 */

undefined4
DV_WriteRS485(undefined4 *param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4,
             undefined4 *param_5)

{
  int iVar1;
  
                    /* 0x7220  42  DV_WriteRS485 */
  if (DAT_1000e78c == '\0') {
    return 0xffffffc8;
  }
  iVar1 = (*(code *)param_1[0xf7])(*param_1,param_2,param_3,param_4);
  if (iVar1 != 0) {
    FUN_10004f30(param_1,"CAM_SerialWrite Failed");
    return 0xfffffdd8;
  }
  FUN_10004f30(param_1,"CAM_SerialWrite OK");
  if (param_5 != (undefined4 *)0x0) {
    *param_5 = param_4;
  }
  return 0;
}



/* FUNCTION FUN_10001060 ENTRY 10001060 */

void __thiscall FUN_10001060(undefined4 *param_1,char *param_2)

{
  bool bVar1;
  char cVar2;
  uint *puVar3;
  undefined4 ****ppppuVar4;
  void *pvVar5;
  undefined4 *puVar6;
  FARPROC pFVar7;
  int iVar8;
  undefined4 extraout_ECX;
  char *pcVar9;
  code *pcVar10;
  undefined4 uVar11;
  uint uStack_dc;
  undefined1 local_c4 [4];
  uint local_c0;
  undefined4 local_b0;
  uint local_ac;
  uint local_a8;
  undefined4 local_98;
  uint local_94;
  undefined4 local_90 [5];
  uint local_7c;
  uint local_78;
  undefined4 local_68;
  uint local_64;
  uint local_60 [4];
  undefined4 local_50;
  uint local_4c;
  uint local_48 [4];
  undefined4 local_38;
  uint local_34;
  undefined4 ***local_30 [4];
  undefined4 local_20;
  uint local_1c;
  uint local_18;
  undefined1 *local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined1 local_8;
  undefined3 uStack_7;
  
  local_8 = 0xff;
  uStack_7 = 0xffffff;
  puStack_c = &LAB_100089dc;
  local_10 = ExceptionList;
  uStack_dc = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  local_14 = (undefined1 *)&uStack_dc;
  ExceptionList = &local_10;
  local_18 = uStack_dc;
  puVar3 = &uStack_dc;
  if (*(char *)(param_1 + 0x11) != '\0') {
    if (*param_2 == '\0') {
      iVar8 = 0;
    }
    else {
      pcVar9 = param_2;
      do {
        cVar2 = *pcVar9;
        pcVar9 = pcVar9 + 1;
      } while (cVar2 != '\0');
      iVar8 = (int)pcVar9 - (int)(param_2 + 1);
    }
    iVar8 = FUN_10001b70(iVar8,param_1[0x17],param_2,iVar8);
    puVar3 = (uint *)local_14;
    if (iVar8 == 0) goto LAB_100016ab;
  }
  local_14 = (undefined1 *)puVar3;
  ac::LogInfo("DeviceSDK","Load: %s",param_2);
  local_1c = 0xf;
  local_20 = 0;
  local_30[0] = (undefined4 ***)((uint)local_30[0] & 0xffffff00);
  if (*param_2 == '\0') {
    iVar8 = 0;
  }
  else {
    pcVar9 = param_2;
    do {
      cVar2 = *pcVar9;
      pcVar9 = pcVar9 + 1;
    } while (cVar2 != '\0');
    iVar8 = (int)pcVar9 - (int)(param_2 + 1);
  }
  FUN_100024a0(param_2,iVar8);
  pcVar10 = IsFile_exref;
  local_8 = 0;
  uStack_7 = 0;
  bVar1 = ac::IsFile((basic_string<char,std::char_traits<char>,std::allocator<char>_> *)local_30);
  if (!bVar1) {
    local_4c = 0xf;
    local_50 = 0;
    local_60[0] = CONCAT31(local_60[0]._1_3_,bVar1);
    if (*param_2 == '\0') {
      iVar8 = 0;
    }
    else {
      pcVar9 = param_2;
      do {
        cVar2 = *pcVar9;
        pcVar9 = pcVar9 + 1;
      } while (cVar2 != '\0');
      iVar8 = (int)pcVar9 - (int)(param_2 + 1);
    }
    pcVar9 = param_2;
    FUN_100024a0(param_2,iVar8);
    local_8 = 1;
    local_c4[0] = 0x2e;
    iVar8 = FUN_10001850(local_c4,pcVar9,iVar8);
    if (iVar8 != -1) {
      puVar3 = (uint *)FUN_10001810(local_48,extraout_ECX,iVar8);
      if (local_60 != puVar3) {
        if (0xf < local_4c) {
          FUN_10002630(local_60[0],local_4c + 1);
        }
        local_4c = 0xf;
        local_50 = 0;
        local_60[0] = local_60[0] & 0xffffff00;
        FUN_10001f80(puVar3);
      }
      local_8 = 1;
      pcVar10 = IsFile_exref;
      if (0xf < local_34) {
        FUN_10002630(local_48[0],local_34 + 1);
        pcVar10 = IsFile_exref;
      }
    }
    puVar6 = local_90;
    uVar11 = 0;
    ac::GetModuleParentPath(puVar6);
    local_8 = 4;
    FUN_100018c0("\\VideoDrivers\\",puVar6,uVar11);
    local_8 = 5;
    FUN_10001910(local_60);
    local_8 = 6;
    FUN_100018c0(&DAT_1000a3a0);
    _local_8 = CONCAT31(uStack_7,7);
    ppppuVar4 = (undefined4 ****)FUN_100018c0(param_2);
    if (local_30 != ppppuVar4) {
      if (0xf < local_1c) {
        FUN_10002630(local_30[0],local_1c + 1);
      }
      local_1c = 0xf;
      local_20 = 0;
      local_30[0] = (undefined4 ***)((uint)local_30[0] & 0xffffff00);
      FUN_10001f80(ppppuVar4);
    }
    if (0xf < local_94) {
      FUN_10002630(local_a8,local_94 + 1);
    }
    local_94 = 0xf;
    local_98 = 0;
    local_a8 = local_a8 & 0xffffff00;
    if (0xf < local_ac) {
      FUN_10002630(local_c0,local_ac + 1);
    }
    local_ac = 0xf;
    local_b0 = 0;
    local_c0 = local_c0 & 0xffffff00;
    if (0xf < local_64) {
      FUN_10002630(local_78,local_64 + 1);
    }
    local_64 = 0xf;
    local_68 = 0;
    local_78 = local_78 & 0xffffff00;
    if (0xf < local_34) {
      FUN_10002630(local_48[0],local_34 + 1);
    }
    local_8 = 1;
    local_34 = 0xf;
    local_38 = 0;
    local_48[0] = local_48[0] & 0xffffff00;
    if (0xf < local_7c) {
      FUN_10002630(local_90[0],local_7c + 1);
    }
    cVar2 = (*pcVar10)(local_30);
    if (cVar2 == '\0') {
      puVar6 = local_90;
      uVar11 = 0;
      ac::GetModuleParentPath(puVar6);
      local_8 = 10;
      FUN_100018c0(&DAT_1000a3a0,puVar6,uVar11);
      local_8 = 0xb;
      ppppuVar4 = (undefined4 ****)FUN_100018c0(param_2);
      if (local_30 != ppppuVar4) {
        if (0xf < local_1c) {
          FUN_10002630(local_30[0],local_1c + 1);
        }
        local_1c = 0xf;
        local_20 = 0;
        local_30[0] = (undefined4 ***)((uint)local_30[0] & 0xffffff00);
        FUN_10001f80(ppppuVar4);
      }
      if (0xf < local_34) {
        FUN_10002630(local_48[0],local_34 + 1);
      }
      local_34 = 0xf;
      local_38 = 0;
      local_48[0] = local_48[0] & 0xffffff00;
      if (0xf < local_64) {
        FUN_10002630(local_78,local_64 + 1);
      }
      local_64 = 0xf;
      local_68 = 0;
      local_78 = local_78 & 0xffffff00;
      if (0xf < local_7c) {
        FUN_10002630(local_90[0],local_7c + 1);
      }
    }
    local_8 = 0;
    if (0xf < local_4c) {
      FUN_10002630(local_60[0],local_4c + 1);
    }
  }
  cVar2 = (*pcVar10)(local_30);
  if (cVar2 == '\0') {
    ppppuVar4 = local_30;
    if (0xf < local_1c) {
      ppppuVar4 = (undefined4 ****)local_30[0];
    }
    ac::LogInfo("DeviceSDK","Driver File Not Found: %s",ppppuVar4);
    if (0xf < local_1c) {
      FUN_10002630(local_30[0],local_1c + 1);
    }
  }
  else {
    if (param_1[0x10] == 0) {
      local_8 = 0xe;
      ppppuVar4 = local_30;
      if (0xf < local_1c) {
        ppppuVar4 = (undefined4 ****)local_30[0];
      }
      FUN_10002560(ppppuVar4);
      _local_8 = CONCAT31(uStack_7,0xf);
      pvVar5 = cx::Module::LoadModule
                         ((basic_string<char,std::char_traits<char>,std::allocator<char>_> *)
                          local_48,true);
      param_1[0x10] = pvVar5;
      if (0xf < local_34) {
        FUN_10002630(local_48[0],local_34 + 1);
      }
      local_8 = 0;
      uStack_7 = 0;
      if (param_1[0x10] == 0) {
        puVar6 = (undefined4 *)FUN_10003b00();
        local_8 = 0x11;
        if (0xf < (uint)puVar6[5]) {
          puVar6 = (undefined4 *)*puVar6;
        }
        ppppuVar4 = local_30;
        if (0xf < local_1c) {
          ppppuVar4 = (undefined4 ****)local_30[0];
        }
        ac::LogError("DeviceSDK",&DAT_1000a3d0,ppppuVar4,puVar6);
        FUN_100025c0();
        FUN_100025c0();
        goto LAB_100016ab;
      }
      ppppuVar4 = local_30;
      if (0xf < local_1c) {
        ppppuVar4 = (undefined4 ****)local_30[0];
      }
      ac::LogDebug("DeviceSDK","LoadLibrary(%s) OK",ppppuVar4);
    }
    ac::LogInfo("DeviceSDK","Load APIs");
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_InitSDK");
    *param_1 = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_UninitSDK");
    param_1[1] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_OpenDevice");
    param_1[2] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_CloseDevice");
    param_1[3] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_StartStream");
    param_1[4] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_StopStream");
    param_1[5] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SetCaptureCallback");
    param_1[6] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_Capture");
    param_1[7] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_CaptureTo");
    param_1[8] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_Exec");
    param_1[9] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SerialSetParam");
    param_1[10] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SerialSetReceiveCallback");
    param_1[0xb] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SerialOpen");
    param_1[0xc] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SerialClose");
    param_1[0xd] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_SerialWrite");
    param_1[0xe] = pFVar7;
    pFVar7 = GetProcAddress((HMODULE)param_1[0x10],"CAM_GetNativeHandle");
    param_1[0xf] = pFVar7;
    if (*param_2 == '\0') {
      iVar8 = 0;
    }
    else {
      pcVar9 = param_2;
      do {
        cVar2 = *pcVar9;
        pcVar9 = pcVar9 + 1;
      } while (cVar2 != '\0');
      iVar8 = (int)pcVar9 - (int)(param_2 + 1);
    }
    FUN_100024a0(param_2,iVar8);
    *(undefined1 *)(param_1 + 0x11) = 1;
    if (0xf < local_1c) {
      FUN_10002630(local_30[0],local_1c + 1);
    }
  }
LAB_100016ab:
  ExceptionList = local_10;
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_100044f0 ENTRY 100044f0 */

void __thiscall FUN_100044f0(undefined4 *param_1,char *param_2)

{
  char cVar1;
  code *pcVar2;
  undefined4 uVar3;
  int iVar4;
  int iVar5;
  char *pcVar6;
  undefined4 *puVar7;
  undefined *puVar8;
  char local_51c [128];
  undefined4 local_49c;
  char local_498 [128];
  char local_418 [524];
  char local_20c [128];
  undefined4 local_18c;
  char local_188 [128];
  char local_108 [256];
  uint local_8;
  
  local_8 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  if (*(char *)(param_1 + 0xe4) != '\0') {
    FUN_100078dd();
    return;
  }
  FUN_10004f30(param_1,&DAT_1000a630,*(undefined4 *)(param_2 + 0x188));
  iVar4 = FUN_100016d0(*(undefined4 *)(param_2 + 0x188));
  if (iVar4 != 0) {
    FUN_100078dd(iVar4);
    return;
  }
  iVar5 = (*(code *)param_1[0xe9])();
  if (iVar5 == 0) {
    FUN_10004f30(param_1,"IP:%s, Port:%d, User:%s, Pwd:%s, Timeout:%d",param_1 + 7,param_1[0x27],
                 param_1 + 0x28,param_1 + 0x48,param_1[0x68]);
    memset(local_51c,0,0x514);
    pcVar6 = param_2;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_51c + (-1 - (int)param_2))] = cVar1;
    } while (cVar1 != '\0');
    local_49c = *(undefined4 *)(param_2 + 0x80);
    pcVar6 = param_2 + 0x84;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_498 + (-1 - (int)(param_2 + 0x84)))] = cVar1;
    } while (cVar1 != '\0');
    pcVar6 = param_2 + 0x104;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_498 + (0x7f - (int)(param_2 + 0x104)))] = cVar1;
    } while (cVar1 != '\0');
    pcVar6 = param_2 + 0x18c;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_418 + (0x20b - (int)(param_2 + 0x18c)))] = cVar1;
    } while (cVar1 != '\0');
    local_18c = *(undefined4 *)(param_2 + 0x1cc);
    pcVar6 = param_2 + 0x1d0;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_188 + (-1 - (int)(param_2 + 0x1d0)))] = cVar1;
    } while (cVar1 != '\0');
    pcVar6 = param_2 + 0x210;
    do {
      cVar1 = *pcVar6;
      pcVar6 = pcVar6 + 1;
      pcVar6[(int)(local_188 + (0x7f - (int)(param_2 + 0x210)))] = cVar1;
    } while (cVar1 != '\0');
    iVar5 = (*(code *)param_1[0xeb])(local_51c,param_1);
    if (iVar5 == 0) {
      pcVar2 = (code *)param_1[0xf5];
      uVar3 = *param_1;
      puVar7 = param_1 + 7;
      for (iVar5 = 0xa3; iVar5 != 0; iVar5 = iVar5 + -1) {
        *puVar7 = *(undefined4 *)param_2;
        param_2 = param_2 + 4;
        puVar7 = puVar7 + 1;
      }
      iVar5 = (*pcVar2)(uVar3,0,param_1 + 1);
      if (iVar5 == 0) {
        puVar8 = &DAT_1000a688;
      }
      else {
        puVar8 = &DAT_1000a6a4;
      }
      FUN_10004f30(param_1,puVar8);
      *(undefined1 *)(param_1 + 0xe4) = 1;
    }
    else {
      FUN_10004f30(param_1,"CAM_OpenDevice Failed");
    }
    FUN_10004f30(param_1,"Open End");
  }
  else {
    FUN_10004f30(param_1,&DAT_1000a644);
  }
  FUN_100078dd(iVar4);
  return;
}



/* FUNCTION FUN_100047b0 ENTRY 100047b0 */

undefined4 __thiscall FUN_100047b0(undefined4 *param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
  if (*(char *)(param_1 + 0xe4) == '\0') {
    return 0xfffffdd7;
  }
  if (*(char *)((int)param_1 + 0x391) != '\0') {
    return 0xfffffdca;
  }
  FUN_10004f30(param_1,"StartStream");
  uVar2 = 0;
  iVar1 = (*(code *)param_1[0xed])(*param_1,param_2,param_3);
  if (iVar1 == 0) {
    *(undefined1 *)((int)param_1 + 0x391) = 1;
    param_1[0xe5] = param_3;
  }
  else {
    FUN_10004f30(param_1,"CAM_StartStream Failed");
    uVar2 = 0xfffffdd8;
  }
  FUN_10004f30(param_1,"StartStream End");
  return uVar2;
}



/* FUNCTION FUN_10004890 ENTRY 10004890 */

undefined4 __thiscall FUN_10004890(undefined4 *param_1,int param_2)

{
  int iVar1;
  undefined4 local_20;
  void *local_14;
  code *pcStack_10;
  uint local_c;
  undefined4 local_8;
  
  local_8 = 0xfffffffe;
  pcStack_10 = FUN_1000863b;
  local_14 = ExceptionList;
  local_c = DAT_1000e00c ^ 0x1000bde8;
  ExceptionList = &local_14;
  FUN_10004f30(param_1,"Capture");
  if (param_2 == 1) {
    param_1[0xd8] = param_1[0xd8] + 1;
    if (5 < (int)param_1[0xd8]) {
      param_1[0xd8] = 5;
    }
  }
  else {
    param_1[0xd8] = param_2;
  }
  EnterCriticalSection((LPCRITICAL_SECTION)(param_1 + 0xc4));
  local_8 = 1;
  if (*(char *)(param_1 + 0xe4) == '\0') {
    local_20 = 0xfffffdd7;
  }
  else {
    local_20 = 0;
    iVar1 = (*(code *)param_1[0xf0])(*param_1);
    if (iVar1 == 0) {
      FUN_10004f30(param_1,&DAT_1000a77c);
    }
    else {
      FUN_10004f30(param_1,"CAM_Capture Failed");
      local_20 = 0xfffffdd8;
    }
  }
  local_8 = 0;
  FUN_10004986();
  local_8 = 0xfffffffe;
  LeaveCriticalSection((LPCRITICAL_SECTION)(param_1 + 0xc4));
  FUN_10004f30(param_1,"Capture End");
  ExceptionList = local_14;
  return local_20;
}



/* FUNCTION FUN_100050c0 ENTRY 100050c0 */

/* WARNING: Type propagation algorithm not settling */

void __thiscall FUN_100050c0(undefined4 *param_1,int param_2,undefined4 param_3)

{
  int local_a4 [4];
  int local_94;
  uint local_c;
  
  local_c = DAT_1000e00c ^ (uint)local_a4;
  local_a4[0] = param_2;
  if (*(char *)(param_1 + 0xe4) == '\0') {
    FUN_100078dd();
    return;
  }
  FUN_10004f30(param_1,"SendWhiteList Begin");
  if (param_2 == 0) {
    FUN_100078dd();
    return;
  }
  FUN_10004f30(param_1,"CAM_Exec CAMCMD_UPDATE_WHITE_LIST Count: %d",param_3);
  memset(local_a4 + 1,0,0x90);
  local_94 = local_a4[0];
  local_a4[1] = 0xc9;
  local_a4[2] = param_3;
  (*(code *)param_1[0xf2])(*param_1,local_a4 + 1);
  FUN_10004f30(param_1,"CAM_Exec CAMCMD_UPDATE_WHITE_LIST End");
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_100073d0 ENTRY 100073d0 */

/* WARNING: Removing unreachable block (ram,0x1000748f) */
/* WARNING: Removing unreachable block (ram,0x100074c1) */

void FUN_100073d0(void)

{
  LPCSTR ***ppppCVar1;
  uint local_48;
  uint local_30;
  LPCSTR **local_2c [4];
  undefined4 local_1c;
  uint local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10008ed7;
  local_10 = ExceptionList;
  local_14 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  if (DAT_1000ea0d == '\0') {
    FUN_10007340();
    FUN_10003800();
    local_8 = 0;
    FUN_100018c0();
    local_8._0_1_ = 2;
    if (0xf < local_30) {
      FUN_10002630();
    }
    ppppCVar1 = local_2c;
    if (0xf < local_18) {
      ppppCVar1 = (LPCSTR ***)local_2c[0];
    }
    CreateDirectoryA((LPCSTR)ppppCVar1,(LPSECURITY_ATTRIBUTES)0x0);
    FUN_100024a0();
    local_8._0_1_ = 3;
    FUN_100024a0(&DAT_1000b318,4);
    local_8 = CONCAT31(local_8._1_3_,2);
    ppppCVar1 = (LPCSTR ***)FUN_100038a0();
    if (local_2c != ppppCVar1) {
      if (0xf < local_18) {
        FUN_10002630();
      }
      local_18 = 0xf;
      local_1c = 0;
      local_2c[0] = (LPCSTR **)((uint)local_2c[0] & 0xffffff00);
      FUN_10001f80();
    }
    local_8 = CONCAT31(local_8._1_3_,2);
    if (0xf < local_48) {
      FUN_10002630();
    }
    FUN_10002720();
    FUN_100028b0();
    DAT_1000ea0d = '\x01';
    if (0xf < local_18) {
      FUN_10002630();
    }
  }
  ExceptionList = local_10;
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_10007790 ENTRY 10007790 */

void FUN_10007790(void)

{
  int iVar1;
  undefined1 local_19c [404];
  uint local_8;
  
  local_8 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  if (DAT_1000ea0c == '\0') {
    iVar1 = Ordinal_115(0x202,local_19c);
    if (iVar1 != 0) {
      FUN_10007770("GLOBAL","WSAStartup failed with error: %d\n",iVar1);
      FUN_100078dd();
      return;
    }
    if (((char)local_19c._0_2_ == '\x02') && (SUB21(local_19c._0_2_,1) == '\x02')) {
      DAT_1000ea0c = 1;
      FUN_10007770("GLOBAL","WSAStartup OK");
      FUN_100078dd();
      return;
    }
    Ordinal_116();
  }
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_100059f0 ENTRY 100059f0 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined4 * FUN_100059f0(void)

{
  if (*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000ea10) {
    FUN_10007ed2(&DAT_1000ea10);
    if (DAT_1000ea10 == -1) {
      DAT_1000ea18 = 0;
      _DAT_1000ea1c = 0;
      DAT_1000ea20 = 0;
      DAT_1000ea24 = 0;
      FUN_10007bf9(&LAB_10008f60);
      FUN_10007e93(&DAT_1000ea10);
    }
  }
  return &DAT_1000ea18;
}



/* FUNCTION FUN_10005800 ENTRY 10005800 */

void __fastcall FUN_10005800(void *param_1)

{
  uintptr_t uVar1;
  
  if (*(char *)((int)param_1 + 0xc) == '\0') {
    InitializeCriticalSection((LPCRITICAL_SECTION)((int)param_1 + 0x10));
    *(undefined1 *)((int)param_1 + 0x34) = 0;
    uVar1 = _beginthread(FUN_10005960,0,param_1);
    *(uintptr_t *)((int)param_1 + 0x30) = uVar1;
    *(undefined4 *)((int)param_1 + 0x38) = 0;
    *(undefined2 *)((int)param_1 + 0x3c) = 40000;
    *(undefined4 *)((int)param_1 + 0x28) = 0;
    *(undefined4 *)((int)param_1 + 0x2c) = 0;
    FUN_10007770("CDeviceManager",&DAT_1000ac14);
    *(undefined1 *)((int)param_1 + 0xc) = 1;
  }
  return;
}



/* FUNCTION FUN_10007770 ENTRY 10007770 */

void FUN_10007770(void)

{
  FUN_10007590(&stack0x0000000c);
  return;
}



/* FUNCTION FUN_10007c31 ENTRY 10007c31 */

void FUN_10007c31(size_t param_1)

{
  int iVar1;
  void *pvVar2;
  
  while( true ) {
    pvVar2 = malloc(param_1);
    if (pvVar2 != (void *)0x0) break;
    iVar1 = _callnewh(param_1);
    if (iVar1 == 0) {
      if (param_1 == 0xffffffff) {
        FUN_10008757();
      }
      else {
        FUN_1000873a();
      }
    }
  }
  return;
}



/* FUNCTION FUN_10004100 ENTRY 10004100 */

undefined4 * __fastcall FUN_10004100(undefined4 *param_1)

{
  uint uVar1;
  undefined4 uVar2;
  undefined4 *puVar3;
  HANDLE pvVar4;
  undefined4 in_stack_ffffffd4;
  undefined4 uVar5;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  puStack_c = &LAB_10008d48;
  local_10 = ExceptionList;
  uVar1 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  puVar3 = param_1 + 0xab;
  *param_1 = 0;
  param_1[1] = 0;
  param_1[2] = 0;
  param_1[3] = 0;
  param_1[4] = 0;
  param_1[5] = 0;
  param_1[6] = 0;
  param_1[0xb0] = 0xf;
  param_1[0xaf] = 0;
  if (0xf < (uint)param_1[0xb0]) {
    puVar3 = (undefined4 *)*puVar3;
  }
  *(undefined1 *)puVar3 = 0;
  local_8 = 0;
  param_1[0xb3] = 0;
  param_1[0xb4] = 0;
  uVar5 = 0x1000419d;
  uVar2 = FUN_10005640(uVar1);
  param_1[0xb3] = uVar2;
  puVar3 = param_1 + 0xcc;
  param_1[0xca] = 0;
  param_1[0xd1] = 0xf;
  param_1[0xd0] = 0;
  if (0xf < (uint)param_1[0xd1]) {
    puVar3 = (undefined4 *)*puVar3;
  }
  *(undefined1 *)puVar3 = 0;
  param_1[0xd3] = 500;
  param_1[0xd4] = 0;
  param_1[0xd5] = 0;
  param_1[0xd6] = 0;
  param_1[0xd7] = 0;
  local_8 = CONCAT31(local_8._1_3_,3);
  param_1[0xd8] = 0;
  param_1[0xd9] = 0;
  param_1[0xda] = 0;
  uVar2 = FUN_10005610(in_stack_ffffffd4,uVar5);
  param_1[0xd9] = uVar2;
  param_1[0xe2] = 0;
  param_1[0xe3] = 0;
  *(undefined2 *)(param_1 + 0xe4) = 0;
  param_1[0xe5] = 0;
  param_1[0xe6] = 0;
  param_1[0xe7] = 0;
  param_1[0xe8] = 0;
  param_1[0x101] = 0xf;
  param_1[0x100] = 0;
  *(undefined1 *)(param_1 + 0xfc) = 0;
  param_1[0xf9] = 0;
  *(undefined1 *)(param_1 + 0xfa) = 0;
  memset(param_1 + 7,0,0x28c);
  InitializeCriticalSection((LPCRITICAL_SECTION)(param_1 + 0xbe));
  InitializeCriticalSection((LPCRITICAL_SECTION)(param_1 + 0xc4));
  param_1[0xca] = 0;
  pvVar4 = CreateEventA((LPSECURITY_ATTRIBUTES)0x0,1,0,(LPCSTR)0x0);
  param_1[0xcb] = pvVar4;
  param_1[0xe1] = 0;
  InitializeCriticalSection((LPCRITICAL_SECTION)(param_1 + 0xdb));
  ExceptionList = local_10;
  return param_1;
}



/* FUNCTION FUN_10005900 ENTRY 10005900 */

void __thiscall FUN_10005900(int *param_1,int param_2)

{
  int *_Dst;
  int *piVar1;
  
  EnterCriticalSection((LPCRITICAL_SECTION)(param_1 + 4));
  _Dst = (int *)*param_1;
  piVar1 = (int *)param_1[1];
  if (_Dst != piVar1) {
    do {
      if (*_Dst == param_2) {
        memmove(_Dst,_Dst + 1,(int)piVar1 - (int)(_Dst + 1) & 0xfffffffc);
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



/* FUNCTION FUN_10004340 ENTRY 10004340 */

void __fastcall FUN_10004340(int param_1)

{
  int *piVar1;
  int *_Memory;
  undefined4 *puVar2;
  int local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 uStack_8;
  
  uStack_8 = 0xffffffff;
  puStack_c = &LAB_10008d70;
  local_10 = ExceptionList;
  ExceptionList = &local_10;
  local_14 = param_1;
  FUN_10004720(DAT_1000e00c ^ (uint)&stack0xfffffffc);
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x2f8));
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x310));
  DeleteObject(*(HGDIOBJ *)(param_1 + 0x32c));
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x36c));
  puVar2 = (undefined4 *)(param_1 + 0x3f0);
  if (0xf < *(uint *)(param_1 + 0x404)) {
    FUN_10002630(*puVar2,*(uint *)(param_1 + 0x404) + 1);
  }
  *(undefined4 *)(param_1 + 0x404) = 0xf;
  *(undefined4 *)(param_1 + 0x400) = 0;
  if (0xf < *(uint *)(param_1 + 0x404)) {
    puVar2 = (undefined4 *)*puVar2;
  }
  *(undefined1 *)puVar2 = 0;
  FUN_10005770();
  piVar1 = *(int **)(param_1 + 0x364);
  _Memory = (int *)*piVar1;
  *piVar1 = (int)piVar1;
  *(int *)(*(int *)(param_1 + 0x364) + 4) = *(int *)(param_1 + 0x364);
  *(undefined4 *)(param_1 + 0x368) = 0;
  if (_Memory != *(int **)(param_1 + 0x364)) {
    do {
      piVar1 = (int *)*_Memory;
      free(_Memory);
      _Memory = piVar1;
    } while (piVar1 != (int *)*(int *)(param_1 + 0x364));
  }
  free(*(void **)(param_1 + 0x364));
  FUN_10005770();
  puVar2 = (undefined4 *)(param_1 + 0x330);
  if (0xf < *(uint *)(param_1 + 0x344)) {
    FUN_10002630(*puVar2,*(uint *)(param_1 + 0x344) + 1);
  }
  *(undefined4 *)(param_1 + 0x344) = 0xf;
  *(undefined4 *)(param_1 + 0x340) = 0;
  if (0xf < *(uint *)(param_1 + 0x344)) {
    puVar2 = (undefined4 *)*puVar2;
  }
  *(undefined1 *)puVar2 = 0;
  FUN_100051c0(&local_14,**(undefined4 **)(param_1 + 0x2cc),*(undefined4 **)(param_1 + 0x2cc));
  free(*(void **)(param_1 + 0x2cc));
  if (0xf < *(uint *)(param_1 + 0x2c0)) {
    FUN_10002630(*(undefined4 *)(param_1 + 0x2ac),*(uint *)(param_1 + 0x2c0) + 1);
  }
  *(undefined4 *)(param_1 + 0x2c0) = 0xf;
  *(undefined4 *)(param_1 + 700) = 0;
  if (0xf < *(uint *)(param_1 + 0x2c0)) {
    **(undefined1 **)(param_1 + 0x2ac) = 0;
    ExceptionList = local_10;
    return;
  }
  *(undefined1 *)(param_1 + 0x2ac) = 0;
  ExceptionList = local_10;
  return;
}



/* FUNCTION FUN_10007c64 ENTRY 10007c64 */

void FUN_10007c64(void *param_1)

{
  free(param_1);
  return;
}



/* FUNCTION FUN_10004cb0 ENTRY 10004cb0 */

undefined4 __fastcall FUN_10004cb0(undefined4 param_1)

{
  void *local_14;
  code *pcStack_10;
  uint local_c;
  undefined4 uStack_8;
  
  uStack_8 = 0xfffffffe;
  pcStack_10 = FUN_1000863b;
  local_14 = ExceptionList;
  local_c = DAT_1000e00c ^ 0x1000be38;
  ExceptionList = &local_14;
  FUN_10004f30(param_1,"[GLOBAL]",&DAT_1000a8a0);
  ExceptionList = local_14;
  return 0xfffffdc5;
}



/* FUNCTION FUN_10004f30 ENTRY 10004f30 */

void FUN_10004f30(void)

{
  FUN_10007590(&stack0x0000000c);
  return;
}



/* FUNCTION FUN_10004d10 ENTRY 10004d10 */

void __thiscall FUN_10004d10(undefined4 *param_1,int *param_2)

{
  char cVar1;
  uint uVar2;
  int iVar3;
  char *pcVar4;
  undefined4 ****ppppuVar5;
  char *pcVar6;
  int iVar7;
  int iVar8;
  undefined *puVar9;
  char local_f4 [4];
  undefined4 local_f0;
  int local_ec;
  int local_e8;
  undefined4 ***local_60 [4];
  undefined4 local_50;
  uint local_4c;
  undefined1 local_48 [52];
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10008d98;
  local_10 = ExceptionList;
  uVar2 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_14 = uVar2;
  FUN_10004f30(param_1,&DAT_1000a8f4,*param_2,param_2[1],uVar2);
  iVar7 = *param_2;
  if (iVar7 == 100) {
    iVar7 = param_2[1];
    puVar9 = &DAT_1000a90c;
  }
  else {
    if (iVar7 != 0x65) {
      if (iVar7 == 0x66) {
        FUN_10004f30(param_1,&DAT_1000a940,param_2[1]);
        memset(&local_f0,0,0x90);
        local_ec = param_2[1];
        local_e8 = param_2[2];
        local_f0 = 0x66;
        (*(code *)param_1[0xf2])(*param_1,&local_f0);
      }
      else if (iVar7 == 200) {
        local_4c = 0xf;
        local_50 = 0;
        local_60[0] = (undefined4 ***)((uint)local_60[0] & 0xffffff00);
        local_8 = 0;
        pcVar6 = (char *)param_2[3];
        pcVar4 = pcVar6 + 1;
        do {
          cVar1 = *pcVar6;
          pcVar6 = pcVar6 + 1;
        } while (cVar1 != '\0');
        iVar7 = (int)pcVar6 - (int)pcVar4;
        FUN_10002c90(local_48,"fd00%02x0101",iVar7 + 2);
        FUN_10003be0(local_48);
        iVar8 = 0;
        if (0 < iVar7) {
          do {
            local_f4[0] = '\0';
            local_f4[1] = '\0';
            local_f4[2] = 0;
            FUN_10002c90(local_f4,&DAT_1000a960,*(undefined1 *)(param_2[3] + iVar8));
            if (local_f4[0] == '\0') {
              iVar3 = 0;
            }
            else {
              pcVar4 = local_f4;
              do {
                cVar1 = *pcVar4;
                pcVar4 = pcVar4 + 1;
              } while (cVar1 != '\0');
              iVar3 = (int)pcVar4 - (int)(local_f4 + 1);
            }
            FUN_10001a00(local_f4,iVar3);
            iVar8 = iVar8 + 1;
          } while (iVar8 < iVar7);
        }
        ppppuVar5 = local_60;
        if (0xf < local_4c) {
          ppppuVar5 = (undefined4 ****)local_60[0];
        }
        FUN_10004f30(param_1,&DAT_1000a968,param_2[3],ppppuVar5,uVar2);
        ppppuVar5 = local_60;
        if (0xf < local_4c) {
          ppppuVar5 = (undefined4 ****)local_60[0];
        }
        (*(code *)param_1[0xf7])(*param_1,param_1[1],ppppuVar5,local_50);
        if (0xf < local_4c) {
          FUN_10002630(local_60[0],local_4c + 1);
        }
      }
      goto LAB_10004f12;
    }
    iVar7 = param_2[1];
    puVar9 = &DAT_1000a934;
  }
  FUN_10004f30(param_1,puVar9,iVar7);
  FUN_10004f30(param_1,"[GLOBAL]",&DAT_1000a918);
LAB_10004f12:
  ExceptionList = local_10;
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_10001b70 ENTRY 10001b70 */

uint __thiscall
FUN_10001b70(byte *param_1,undefined4 param_2,uint param_3,byte *param_4,uint param_5)

{
  uint uVar1;
  uint uVar2;
  bool bVar3;
  
  if (*(uint *)(param_1 + 0x10) < param_3) {
    param_3 = *(uint *)(param_1 + 0x10);
  }
  if (0xf < *(uint *)(param_1 + 0x14)) {
    param_1 = *(byte **)param_1;
  }
  uVar2 = param_5;
  if (param_3 < param_5) {
    uVar2 = param_3;
  }
  if (uVar2 == 0) goto LAB_10001bf1;
  while (uVar1 = uVar2 - 4, 3 < uVar2) {
    if (*(int *)param_1 != *(int *)param_4) goto LAB_10001bb6;
    param_1 = param_1 + 4;
    param_4 = param_4 + 4;
    uVar2 = uVar1;
  }
  if (uVar1 == 0xfffffffc) {
LAB_10001bea:
    uVar2 = 0;
  }
  else {
LAB_10001bb6:
    bVar3 = *param_1 < *param_4;
    if ((*param_1 == *param_4) &&
       ((uVar1 == 0xfffffffd ||
        ((bVar3 = param_1[1] < param_4[1], param_1[1] == param_4[1] &&
         ((uVar1 == 0xfffffffe ||
          ((bVar3 = param_1[2] < param_4[2], param_1[2] == param_4[2] &&
           ((uVar1 == 0xffffffff || (bVar3 = param_1[3] < param_4[3], param_1[3] == param_4[3]))))))
         )))))) goto LAB_10001bea;
    uVar2 = -(uint)bVar3 | 1;
  }
  if (uVar2 != 0) {
    return uVar2;
  }
LAB_10001bf1:
  if (param_5 <= param_3) {
    return (uint)(param_3 != param_5);
  }
  return 0xffffffff;
}



/* FUNCTION FUN_100024a0 ENTRY 100024a0 */

int * __thiscall FUN_100024a0(int *param_1,int *param_2,size_t param_3)

{
  uint uVar1;
  char cVar2;
  int *piVar3;
  
  if (param_2 != (int *)0x0) {
    uVar1 = param_1[5];
    piVar3 = param_1;
    if (0xf < uVar1) {
      piVar3 = (int *)*param_1;
    }
    if (piVar3 <= param_2) {
      piVar3 = param_1;
      if (0xf < uVar1) {
        piVar3 = (int *)*param_1;
      }
      if (param_2 < (int *)(param_1[4] + (int)piVar3)) {
        if (uVar1 < 0x10) {
          piVar3 = (int *)FUN_10002140(param_1,(int)param_2 - (int)param_1,param_3);
          return piVar3;
        }
        piVar3 = (int *)FUN_10002140(param_1,(int)param_2 - *param_1,param_3);
        return piVar3;
      }
    }
  }
  cVar2 = FUN_10002420(param_3,0);
  if (cVar2 != '\0') {
    piVar3 = param_1;
    if (0xf < (uint)param_1[5]) {
      piVar3 = (int *)*param_1;
    }
    if (param_3 != 0) {
      memcpy(piVar3,param_2,param_3);
    }
    param_1[4] = param_3;
    if (0xf < (uint)param_1[5]) {
      *(undefined1 *)(*param_1 + param_3) = 0;
      return param_1;
    }
    *(undefined1 *)((int)param_1 + param_3) = 0;
  }
  return param_1;
}



/* FUNCTION FUN_10001850 ENTRY 10001850 */

/* WARNING: Removing unreachable block (ram,0x10001863) */

int __thiscall FUN_10001850(undefined4 *param_1,char *param_2)

{
  char cVar1;
  undefined4 *extraout_ECX;
  undefined4 *puVar2;
  char *pcVar3;
  int iVar4;
  undefined8 uVar5;
  
  if (param_1[4] != 0) {
    puVar2 = param_1;
    if (0xf < (uint)param_1[5]) {
      puVar2 = (undefined4 *)*param_1;
    }
    pcVar3 = (char *)((int)puVar2 + param_1[4] + -1);
    cVar1 = *param_2;
    while( true ) {
      if ((*pcVar3 == cVar1) && (*pcVar3 == *param_2)) {
        if (0xf < (uint)param_1[5]) {
          param_1 = (undefined4 *)*param_1;
        }
        return (int)pcVar3 - (int)param_1;
      }
      uVar5 = FUN_10001c50();
      iVar4 = (int)((ulonglong)uVar5 >> 0x20);
      if (iVar4 == (int)uVar5) break;
      pcVar3 = (char *)(iVar4 + -1);
      param_1 = extraout_ECX;
    }
  }
  return -1;
}



/* FUNCTION FUN_10001810 ENTRY 10001810 */

undefined1 * __thiscall
FUN_10001810(undefined4 param_1,undefined1 *param_2,undefined4 param_3,undefined4 param_4)

{
  *(undefined4 *)(param_2 + 0x14) = 0xf;
  *(undefined4 *)(param_2 + 0x10) = 0;
  *param_2 = 0;
  FUN_10002140(param_1,0,param_4);
  return param_2;
}



/* FUNCTION FUN_100078dd ENTRY 100078dd */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __fastcall FUN_100078dd(int param_1)

{
  code *pcVar1;
  uint uVar2;
  undefined4 extraout_ECX;
  undefined4 extraout_ECX_00;
  undefined4 uVar3;
  uint extraout_EDX;
  undefined4 unaff_EBX;
  undefined4 unaff_EBP;
  undefined4 unaff_ESI;
  undefined4 unaff_EDI;
  undefined2 in_ES;
  undefined2 in_CS;
  undefined2 in_SS;
  undefined2 in_DS;
  undefined2 in_FS;
  undefined2 in_GS;
  byte bVar4;
  byte bVar5;
  byte in_AF;
  byte bVar6;
  byte bVar7;
  byte in_TF;
  byte in_IF;
  byte bVar8;
  byte in_NT;
  byte in_AC;
  byte in_VIF;
  byte in_VIP;
  byte in_ID;
  longlong lVar9;
  undefined4 unaff_retaddr;
  
  if (param_1 == DAT_1000e00c) {
    return;
  }
  uVar2 = IsProcessorFeaturePresent(0x17);
  bVar4 = 0;
  bVar8 = 0;
  bVar7 = (int)uVar2 < 0;
  bVar6 = uVar2 == 0;
  bVar5 = (POPCOUNT(uVar2 & 0xff) & 1U) == 0;
  lVar9 = (ulonglong)extraout_EDX << 0x20;
  uVar3 = extraout_ECX;
  if (!(bool)bVar6) {
    pcVar1 = (code *)swi(0x29);
    lVar9 = (*pcVar1)();
    uVar3 = extraout_ECX_00;
  }
  _DAT_1000e510 = (undefined4)((ulonglong)lVar9 >> 0x20);
  _DAT_1000e518 = (undefined4)lVar9;
  _DAT_1000e528 =
       (uint)(in_NT & 1) * 0x4000 | (uint)(bVar8 & 1) * 0x800 | (uint)(in_IF & 1) * 0x200 |
       (uint)(in_TF & 1) * 0x100 | (uint)(bVar7 & 1) * 0x80 | (uint)(bVar6 & 1) * 0x40 |
       (uint)(in_AF & 1) * 0x10 | (uint)(bVar5 & 1) * 4 | (uint)(bVar4 & 1) |
       (uint)(in_ID & 1) * 0x200000 | (uint)(in_VIP & 1) * 0x100000 | (uint)(in_VIF & 1) * 0x80000 |
       (uint)(in_AC & 1) * 0x40000;
  _DAT_1000e52c = &stack0x00000004;
  _DAT_1000e468 = 0x10001;
  _DAT_1000e418 = 0xc0000409;
  _DAT_1000e41c = 1;
  _DAT_1000e428 = 1;
  DAT_1000e42c = 2;
  _DAT_1000e424 = unaff_retaddr;
  _DAT_1000e4f4 = in_GS;
  _DAT_1000e4f8 = in_FS;
  _DAT_1000e4fc = in_ES;
  _DAT_1000e500 = in_DS;
  _DAT_1000e504 = unaff_EDI;
  _DAT_1000e508 = unaff_ESI;
  _DAT_1000e50c = unaff_EBX;
  _DAT_1000e514 = uVar3;
  _DAT_1000e51c = unaff_EBP;
  DAT_1000e520 = unaff_retaddr;
  _DAT_1000e524 = in_CS;
  _DAT_1000e530 = in_SS;
  FUN_10007c77(&PTR_DAT_1000a2ac);
  return;
}



/* FUNCTION FUN_100016d0 ENTRY 100016d0 */

void __thiscall FUN_100016d0(int param_1,int param_2)

{
  uint uVar1;
  undefined4 ***pppuVar2;
  int iVar3;
  char *pcVar4;
  undefined4 **local_2c [4];
  undefined4 local_1c;
  uint local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10008a18;
  local_10 = ExceptionList;
  uVar1 = DAT_1000e00c ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_14 = uVar1;
  if ((*(char *)(param_1 + 0x44) != '\0') && (*(int *)(param_1 + 0x48) == param_2))
  goto LAB_100017e7;
  local_18 = 0xf;
  local_1c = 0;
  local_2c[0] = (undefined4 **)((uint)local_2c[0] & 0xffffff00);
  FUN_100024a0(&DAT_1000a5c0,0);
  local_8 = 0;
  if (param_2 == -1) {
    FUN_100024a0("IPC_SIM.dll",0xb);
LAB_1000179c:
    pppuVar2 = local_2c;
    if (0xf < local_18) {
      pppuVar2 = (undefined4 ***)local_2c[0];
    }
    iVar3 = FUN_10001060(pppuVar2);
    if (iVar3 == 0) {
      *(int *)(param_1 + 0x48) = param_2;
    }
  }
  else {
    if (param_2 < 2) {
      FUN_100024a0("IPC_ZS.dll",10);
      goto LAB_1000179c;
    }
    if (param_2 == 2) {
      pcVar4 = "IPC_HX.dll";
LAB_10001794:
      FUN_10001c10(pcVar4);
      goto LAB_1000179c;
    }
    if (param_2 == 3) {
      pcVar4 = "IPC_QY.dll";
      goto LAB_10001794;
    }
    if (param_2 == 6) {
      pcVar4 = "IPC_DH.dll";
      goto LAB_10001794;
    }
    if (param_2 == 7) {
      pcVar4 = "IPC_TVT.dll";
      goto LAB_10001794;
    }
    ac::LogError("DeviceSDK",&DAT_1000a574,param_2,uVar1);
  }
  if (0xf < local_18) {
    FUN_10002630(local_2c[0],local_18 + 1);
  }
LAB_100017e7:
  ExceptionList = local_10;
  FUN_100078dd();
  return;
}



/* FUNCTION FUN_10004986 ENTRY 10004986 */

void FUN_10004986(void)

{
  return;
}


