
/* FUNCTION Net_UNinit ENTRY 10026700 */

void Net_UNinit(void)

{
  int iVar1;
  int *piVar2;
  
                    /* 0x26700  464  Net_UNinit */
  if (DAT_1004dc18 == 0) {
    Log("%s SDK not Init\n","Net_UNinit");
    return;
  }
  piVar2 = &DAT_1004e55c;
  iVar1 = 0x20;
  do {
    if (piVar2 == (int *)0x5c) {
      Log("%s invalid parameter\n","DCReleaseManageItem");
    }
    else if ((char)piVar2[-0x17] != '\0') {
      FUN_10025370();
      if (*piVar2 != 0) {
        OSAL_MemFree(0,*piVar2,0);
        *piVar2 = 0;
      }
      *(undefined1 *)(piVar2 + -0x17) = 0;
    }
    OSAL_DestroyMutex(piVar2 + -3);
    OSAL_DestroyMutex(piVar2 + -2);
    piVar2 = piVar2 + 0xc649f;
    iVar1 = iVar1 + -1;
  } while (iVar1 != 0);
  DAT_1004dc18 = 0;
  DeleteCriticalSection((LPCRITICAL_SECTION)&DAT_16373480);
  DeleteCriticalSection((LPCRITICAL_SECTION)&DAT_1004e4e0);
  DeleteCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
  Play_UnInit();
  Log(&DAT_1003efec,"Net_UNinit");
  return;
}



/* FUNCTION Net_SetRealDataCallBack ENTRY 1002adb0 */

undefined4 Net_SetRealDataCallBack(uint param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x2adb0  412  Net_SetRealDataCallBack */
  if (param_1 < 0x20) {
    if ((&DAT_1004e500 + param_1 * 0x31927c != (char *)0x0) &&
       ((&DAT_1004e500)[param_1 * 0x31927c] != '\0')) {
      uVar1 = Play_SetRealDataCallBack
                        (*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c),param_1,param_2);
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_SetRealDataCallBack",param_1);
  return 4;
}



/* FUNCTION Net_GetJpgBuffer ENTRY 1002b0b0 */

undefined4 Net_GetJpgBuffer(uint param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x2b0b0  79  Net_GetJpgBuffer */
  if (param_1 < 0x20) {
    if ((&DAT_1004e500 + param_1 * 0x31927c != (char *)0x0) &&
       ((&DAT_1004e500)[param_1 * 0x31927c] != '\0')) {
      uVar1 = Play_GetJpgBuffer(*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c),param_2,param_3)
      ;
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_GetJpgBuffer",param_1);
  return 4;
}



/* FUNCTION Net_SetRealDataCallBackEx ENTRY 1002ae10 */

undefined4 Net_SetRealDataCallBackEx(uint param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x2ae10  413  Net_SetRealDataCallBackEx */
  if (param_1 < 0x20) {
    if ((&DAT_1004e500 + param_1 * 0x31927c != (char *)0x0) &&
       ((&DAT_1004e500)[param_1 * 0x31927c] != '\0')) {
      uVar1 = Play_SetRealDataCallBackEx
                        (*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c),param_1,param_2,param_3
                        );
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_SetRealDataCallBackEx",param_1);
  return 4;
}



/* FUNCTION Net_StartVideo ENTRY 1002ac90 */

int Net_StartVideo(uint param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  int iVar2;
  int iVar3;
  
                    /* 0x2ac90  442  Net_StartVideo */
  if (param_1 < 0x20) {
    iVar2 = param_1 * 0x31927c;
    if ((&DAT_1004e500 + iVar2 != (char *)0x0) && ((&DAT_1004e500)[iVar2] != '\0')) {
      EnterCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
      iVar1 = Play_OpenCamera(*(undefined4 *)(&DAT_10367778 + iVar2),param_2,param_3);
      LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
      if (iVar1 == 0) {
        iVar3 = 0;
        do {
          iVar2 = Net_ShowPlateRegion(param_1,1);
          if (iVar2 == 0) break;
          Sleep(100);
          iVar3 = iVar3 + 1;
        } while (iVar3 < 3);
      }
      else {
        EnterCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
        Play_CloseCamera(*(undefined4 *)(&DAT_10367778 + iVar2));
        LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
        iVar2 = 0;
      }
      Log("%s:tHandle=%d, StreamType=%d, ShowPlateRegion ShowPlateRegion eCode=%d, eCode=%d\n",
          "Net_StartVideo",param_1,param_2,iVar2,iVar1);
      return iVar1;
    }
  }
  Log("%s: invalid tHandle=%d, StreamType=%d, eCode=%d\n","Net_StartVideo",param_1,param_2,4);
  return 4;
}



/* FUNCTION Net_StopVideo ENTRY 1002b990 */

undefined4 Net_StopVideo(uint param_1)

{
  undefined4 uVar1;
  
                    /* 0x2b990  447  Net_StopVideo */
  Log("%s handle:%d\n","Net_StopVideo",param_1);
  if (param_1 < 0x20) {
    if ((&DAT_1004e500 + param_1 * 0x31927c != (char *)0x0) &&
       ((&DAT_1004e500)[param_1 * 0x31927c] == '\x01')) {
      EnterCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
      uVar1 = Play_CloseCamera(*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c));
      LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
      return uVar1;
    }
  }
  Log("%s invalid parameter\n","Net_StopVideo");
  return 6;
}



/* FUNCTION Net_Init ENTRY 10026610 */

int Net_Init(void)

{
  int iVar1;
  int iVar2;
  
                    /* 0x26610  100  Net_Init */
  if (DAT_1004dc18 == 1) {
    Log("Net_Init already start\n");
    return 3;
  }
  iVar1 = Play_Init();
  if (iVar1 != 0) {
    Log("%s Play_Init fail\n","Net_Init");
    return iVar1;
  }
  memset(&DAT_1004e500,0,0x6324f80);
  iVar2 = 0;
  iVar1 = 0x20;
  do {
    FUN_10024ff0(iVar2);
    iVar2 = iVar2 + 1;
    iVar1 = iVar1 + -1;
  } while (iVar1 != 0);
  DAT_1004dc18 = 1;
  InitializeCriticalSection((LPCRITICAL_SECTION)&DAT_16373480);
  InitializeCriticalSection((LPCRITICAL_SECTION)&DAT_1004e4e0);
  InitializeCriticalSection((LPCRITICAL_SECTION)&DAT_163734a0);
  if (DAT_1004dc1c == 0) {
    DAT_1004dc1c = _beginthreadex((void *)0x0,0,(_StartAddress *)&LAB_10024e40,(void *)0x0,0,
                                  &DAT_1004dc20);
  }
  FUN_10024c10();
  Log("%s:CUR=%X, SdkVersion=%s, eCode=%d\n","Net_Init",1,"SDK_3.2.3.6 build_20221129_1800",0);
  return 0;
}



/* FUNCTION Net_GetFrameData ENTRY 1002b320 */

undefined4 Net_GetFrameData(uint param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4)

{
  undefined4 uVar1;
  
                    /* 0x2b320  77  Net_GetFrameData */
  if (param_1 < 0x20) {
    if ((&DAT_1004e500 + param_1 * 0x31927c != (char *)0x0) &&
       ((&DAT_1004e500)[param_1 * 0x31927c] != '\0')) {
      uVar1 = Play_GetFrameData(*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c),param_2,param_3,
                                param_4);
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_GetFrameData",param_1);
  return 4;
}



/* FUNCTION Net_FindDevice ENTRY 10025f20 */

void Net_FindDevice(code *param_1,undefined4 param_2)

{
  short *psVar1;
  void *_Memory;
  wchar_t *pwVar2;
  HMODULE hModule;
  FARPROC pFVar3;
  int iVar4;
  undefined4 *puVar5;
  undefined4 *puVar6;
  void *pvVar7;
  undefined1 local_210 [4];
  WCHAR local_20c;
  undefined1 local_20a [518];
  uint local_4;
  
                    /* 0x25f20  64  Net_FindDevice */
  local_4 = DAT_10047000 ^ (uint)local_210;
  local_210 = (undefined1  [4])0x64;
  local_20c = L'\0';
  memset(local_20a,0,0x206);
  DAT_1004dc30 = param_1;
  _Memory = malloc(0x9790);
  GetModuleFileNameW(DAT_1004dc40,&local_20c,0x104);
  pwVar2 = wcsrchr(&local_20c,L'\\');
  pwVar2[1] = L'\0';
  puVar6 = (undefined4 *)(local_210 + 2);
  do {
    psVar1 = (short *)((int)puVar6 + 2);
    puVar6 = (undefined4 *)((int)puVar6 + 2);
  } while (*psVar1 != 0);
  puVar5 = &DAT_1003ef04;
  for (iVar4 = 10; iVar4 != 0; iVar4 = iVar4 + -1) {
    *puVar6 = *puVar5;
    puVar5 = puVar5 + 1;
    puVar6 = puVar6 + 1;
  }
  hModule = LoadLibraryW(&local_20c);
  if (hModule != (HMODULE)0x0) {
    pFVar3 = GetProcAddress(hModule,"GetDevList");
    if (pFVar3 == (FARPROC)0x0) {
      FreeLibrary(hModule);
    }
    else {
      (*pFVar3)(_Memory,local_210);
      FreeLibrary(hModule);
      if ((local_210 != (undefined1  [4])0x0) && (iVar4 = 0, pvVar7 = _Memory, 0 < (int)local_210))
      {
        do {
          (*DAT_1004dc30)(pvVar7,param_2);
          iVar4 = iVar4 + 1;
          pvVar7 = (void *)((int)pvVar7 + 0x184);
        } while (iVar4 < (int)local_210);
      }
      if (_Memory != (void *)0x0) {
        free(_Memory);
      }
    }
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_FindDeviceEx ENTRY 10026060 */

void Net_FindDeviceEx(undefined4 param_1,undefined4 param_2)

{
  short *psVar1;
  wchar_t *pwVar2;
  HMODULE hModule;
  FARPROC pFVar3;
  FARPROC pFVar4;
  int iVar5;
  undefined4 *puVar6;
  undefined4 *puVar7;
  undefined4 local_214;
  undefined1 local_210 [4];
  WCHAR local_20c;
  undefined1 local_20a [518];
  uint local_4;
  
                    /* 0x26060  65  Net_FindDeviceEx */
  local_4 = DAT_10047000 ^ (uint)&local_214;
  local_214 = param_1;
  local_210 = (undefined1  [4])param_2;
  local_20c = L'\0';
  memset(local_20a,0,0x206);
  GetModuleFileNameW(DAT_1004dc40,&local_20c,0x104);
  pwVar2 = wcsrchr(&local_20c,L'\\');
  pwVar2[1] = L'\0';
  puVar7 = (undefined4 *)(local_210 + 2);
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar6 = &DAT_1003ef04;
  for (iVar5 = 10; iVar5 != 0; iVar5 = iVar5 + -1) {
    *puVar7 = *puVar6;
    puVar6 = puVar6 + 1;
    puVar7 = puVar7 + 1;
  }
  hModule = LoadLibraryW(&local_20c);
  if (hModule != (HMODULE)0x0) {
    pFVar3 = GetProcAddress(hModule,"GetDevList");
    if ((pFVar3 == (FARPROC)0x0) ||
       (pFVar4 = GetProcAddress(hModule,"ShowDevList"), pFVar4 == (FARPROC)0x0)) {
      FreeLibrary(hModule);
    }
    else {
      (*pFVar4)(local_214,local_210);
      (*pFVar3)(0,0);
      FreeLibrary(hModule);
    }
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_FindDeviceMac ENTRY 10026180 */

void Net_FindDeviceMac(code *param_1,undefined4 param_2)

{
  short *psVar1;
  void *_Memory;
  wchar_t *pwVar2;
  HMODULE hModule;
  FARPROC pFVar3;
  int iVar4;
  undefined4 *puVar5;
  byte *pbVar6;
  undefined4 *puVar7;
  int local_228;
  void *local_224;
  char local_220 [18];
  undefined4 uStack_20e;
  undefined1 local_20a [518];
  uint local_4;
  
                    /* 0x26180  67  Net_FindDeviceMac */
  local_4 = DAT_10047000 ^ (uint)&local_228;
  local_220[4] = '\0';
  local_220[5] = '\0';
  local_220[6] = '\0';
  local_220[7] = '\0';
  local_220[8] = '\0';
  local_220[9] = '\0';
  local_220[10] = '\0';
  local_220[0xb] = '\0';
  local_220[0xc] = '\0';
  local_220[0xd] = '\0';
  local_220[0xe] = '\0';
  local_220[0xf] = '\0';
  local_220[0x10] = 0;
  local_220[0x11] = 0;
  local_228 = 100;
  local_220[0] = '\0';
  local_220[1] = '\0';
  local_220[2] = '\0';
  local_220[3] = '\0';
  uStack_20e._2_2_ = 0;
  memset(local_20a,0,0x206);
  DAT_1004dc34 = param_1;
  _Memory = malloc(0x9790);
  local_224 = _Memory;
  GetModuleFileNameW(DAT_1004dc40,(LPWSTR)((int)&uStack_20e + 2),0x104);
  pwVar2 = wcsrchr((wchar_t *)((int)&uStack_20e + 2),L'\\');
  pwVar2[1] = L'\0';
  puVar7 = &uStack_20e;
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar5 = &DAT_1003ef04;
  for (iVar4 = 10; iVar4 != 0; iVar4 = iVar4 + -1) {
    *puVar7 = *puVar5;
    puVar5 = puVar5 + 1;
    puVar7 = puVar7 + 1;
  }
  hModule = LoadLibraryW((LPCWSTR)((int)&uStack_20e + 2));
  if (hModule != (HMODULE)0x0) {
    pFVar3 = GetProcAddress(hModule,"GetDevList");
    if (pFVar3 == (FARPROC)0x0) {
      FreeLibrary(hModule);
    }
    else {
      (*pFVar3)(_Memory,&local_228);
      FreeLibrary(hModule);
      if ((local_228 != 0) && (iVar4 = 0, 0 < local_228)) {
        pbVar6 = (byte *)((int)_Memory + 0x180);
        do {
          local_220[0] = '\0';
          local_220[1] = '\0';
          local_220[2] = '\0';
          local_220[3] = '\0';
          local_220[4] = '\0';
          local_220[5] = '\0';
          local_220[6] = '\0';
          local_220[7] = '\0';
          local_220[8] = '\0';
          local_220[9] = '\0';
          local_220[10] = '\0';
          local_220[0xb] = '\0';
          local_220[0xc] = '\0';
          local_220[0xd] = '\0';
          local_220[0xe] = '\0';
          local_220[0xf] = '\0';
          local_220[0x10] = 0;
          local_220[0x11] = 0;
          sprintf_s(local_220,0x12,"%02X:%02X:%02X:%02X:%02X:%02X",(uint)pbVar6[-4],(uint)pbVar6[-3]
                    ,(uint)pbVar6[-2],(uint)pbVar6[-1],(uint)*pbVar6,(uint)pbVar6[1]);
          (*DAT_1004dc34)(local_220,param_2);
          iVar4 = iVar4 + 1;
          pbVar6 = pbVar6 + 0x184;
          _Memory = local_224;
        } while (iVar4 < local_228);
      }
      if (_Memory != (void *)0x0) {
        free(_Memory);
      }
    }
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_FindDeviceIp ENTRY 10026340 */

void Net_FindDeviceIp(code *param_1,undefined4 param_2)

{
  short *psVar1;
  uint uVar2;
  void *_Memory;
  wchar_t *pwVar3;
  HMODULE hModule;
  FARPROC pFVar4;
  int iVar5;
  undefined4 *puVar6;
  undefined4 *puVar7;
  uint *puVar8;
  int local_228;
  void *local_224;
  char local_220 [18];
  undefined4 uStack_20e;
  undefined1 local_20a [518];
  uint local_4;
  
                    /* 0x26340  66  Net_FindDeviceIp */
  local_4 = DAT_10047000 ^ (uint)&local_228;
  local_220[4] = '\0';
  local_220[5] = '\0';
  local_220[6] = '\0';
  local_220[7] = '\0';
  local_220[8] = '\0';
  local_220[9] = '\0';
  local_220[10] = '\0';
  local_220[0xb] = '\0';
  local_220[0xc] = '\0';
  local_220[0xd] = '\0';
  local_220[0xe] = '\0';
  local_220[0xf] = '\0';
  local_220[0x10] = 0;
  local_220[0x11] = 0;
  local_228 = 100;
  local_220[0] = '\0';
  local_220[1] = '\0';
  local_220[2] = '\0';
  local_220[3] = '\0';
  uStack_20e._2_2_ = 0;
  memset(local_20a,0,0x206);
  DAT_1004dc38 = param_1;
  _Memory = malloc(0x9790);
  local_224 = _Memory;
  GetModuleFileNameW(DAT_1004dc40,(LPWSTR)((int)&uStack_20e + 2),0x104);
  pwVar3 = wcsrchr((wchar_t *)((int)&uStack_20e + 2),L'\\');
  pwVar3[1] = L'\0';
  puVar7 = &uStack_20e;
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar6 = &DAT_1003ef04;
  for (iVar5 = 10; iVar5 != 0; iVar5 = iVar5 + -1) {
    *puVar7 = *puVar6;
    puVar6 = puVar6 + 1;
    puVar7 = puVar7 + 1;
  }
  hModule = LoadLibraryW((LPCWSTR)((int)&uStack_20e + 2));
  if (hModule != (HMODULE)0x0) {
    pFVar4 = GetProcAddress(hModule,"GetDevList");
    if (pFVar4 == (FARPROC)0x0) {
      FreeLibrary(hModule);
    }
    else {
      (*pFVar4)(_Memory,&local_228);
      FreeLibrary(hModule);
      if ((local_228 != 0) && (iVar5 = 0, 0 < local_228)) {
        puVar8 = (uint *)((int)_Memory + 0x154);
        do {
          local_220[0] = '\0';
          local_220[1] = '\0';
          local_220[2] = '\0';
          local_220[3] = '\0';
          local_220[4] = '\0';
          local_220[5] = '\0';
          local_220[6] = '\0';
          local_220[7] = '\0';
          local_220[8] = '\0';
          local_220[9] = '\0';
          local_220[10] = '\0';
          local_220[0xb] = '\0';
          local_220[0xc] = '\0';
          local_220[0xd] = '\0';
          local_220[0xe] = '\0';
          local_220[0xf] = '\0';
          local_220[0x10] = 0;
          local_220[0x11] = 0;
          uVar2 = *puVar8;
          sprintf_s(local_220,0x12,"%d.%d.%d.%d",uVar2 & 0xff,uVar2 >> 8 & 0xff,uVar2 >> 0x10 & 0xff
                    ,uVar2 >> 0x18);
          (*DAT_1004dc38)(local_220,param_2);
          iVar5 = iVar5 + 1;
          puVar8 = puVar8 + 0x61;
          _Memory = local_224;
        } while (iVar5 < local_228);
      }
      if (_Memory != (void *)0x0) {
        free(_Memory);
      }
    }
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_AddCamera ENTRY 100267e0 */

int Net_AddCamera(char *param_1)

{
  int iVar1;
  int iVar2;
  undefined *puVar3;
  
                    /* 0x267e0  3  Net_AddCamera */
  EnterCriticalSection((LPCRITICAL_SECTION)&DAT_1004e4e0);
  iVar1 = Play_AddCamera(param_1);
  if (iVar1 == -1) {
    Log("%s: Play_AddCamera %s fail, niHandle=%d\n","Net_AddCamera",param_1,0xffffffff);
    LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_1004e4e0);
    return -1;
  }
  iVar2 = FUN_10025230();
  if (iVar2 == 0) {
    iVar1 = -1;
    Log("%s DCAllocManageItem fail\n","Net_AddCamera");
    puVar3 = &DAT_1003c710;
  }
  else {
    *(int *)(iVar2 + 0x319278) = iVar1;
    iVar1 = *(int *)(iVar2 + 4);
    strncpy((char *)(iVar2 + 8),param_1,0x10);
    if (iVar1 == -1) {
      puVar3 = &DAT_1003c710;
    }
    else {
      puVar3 = &DAT_1003c70c;
    }
  }
  Log("%s:ip=%s %s, niHandle=%d\n","Net_AddCamera",param_1,puVar3,iVar1);
  LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_1004e4e0);
  return iVar1;
}



/* FUNCTION Net_DelCamera ENTRY 10026980 */

int Net_DelCamera(uint param_1)

{
  int iVar1;
  char *pcVar2;
  
                    /* 0x26980  29  Net_DelCamera */
  if (0x1f < param_1) {
    Log("%s: invalid tHandle=%d, eCode=%d\n","Net_DelCamera",param_1,1);
    return 1;
  }
  pcVar2 = &DAT_1004e500 + param_1 * 0x31927c;
  if (pcVar2 == (char *)0x0) {
    Log("%s:tHandle=%d ptItem = NULL\n","Net_DelCamera",param_1);
  }
  else {
    iVar1 = Play_DelCamera(*(undefined4 *)(&DAT_10367778 + param_1 * 0x31927c));
    if (iVar1 != 0) {
      Log("%s Play_DelCamera fail, eCode=%d\n","Net_DelCamera",iVar1);
      return iVar1;
    }
    if (*pcVar2 != '\0') {
      FUN_10025370();
      if ((&DAT_1004e55c)[param_1 * 0xc649f] != 0) {
        OSAL_MemFree(0,(&DAT_1004e55c)[param_1 * 0xc649f],0);
        (&DAT_1004e55c)[param_1 * 0xc649f] = 0;
      }
      *pcVar2 = '\0';
    }
  }
  Log("%s:tHandle=%d, eCode=%d\n","Net_DelCamera",param_1,0);
  return 0;
}



/* FUNCTION Net_ConnCamera ENTRY 10026a60 */

void Net_ConnCamera(uint param_1,uint param_2,uint param_3)

{
  char *_Source;
  undefined *puVar1;
  undefined4 uVar2;
  int iVar3;
  char *pcVar4;
  int iVar5;
  undefined4 uStack_23c;
  undefined4 uStack_238;
  undefined4 uStack_234;
  undefined4 uStack_230;
  undefined4 uStack_22c;
  undefined4 uStack_228;
  undefined4 uStack_224;
  undefined4 uStack_220;
  undefined1 local_218 [524];
  uint local_c;
  
                    /* 0x26a60  22  Net_ConnCamera */
  local_c = DAT_10047000 ^ (uint)&uStack_23c;
  pcVar4 = (char *)0x0;
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    pcVar4 = &DAT_1004e500 + param_1 * 0x31927c;
  }
  _Source = pcVar4 + 8;
  strncpy(pcVar4 + 0x3190b4,_Source,0x20);
  *(short *)(pcVar4 + 0x1c) = (short)param_2;
  if (*pcVar4 == '\0') {
    Log("%s handle not enable\n","Net_ConnCamera");
    iVar5 = 4;
LAB_10026af6:
    Net_DisConnCamera(*(undefined4 *)(pcVar4 + 4));
    if (iVar5 != 0) goto LAB_10026b2f;
LAB_10026b03:
    Net_RegOffLineClient(param_1);
    memset(local_218,0,0x204);
    Net_QuerySysVersion(param_1,local_218);
    if (iVar5 != 0) goto LAB_10026b2f;
  }
  else {
    if (pcVar4[0x18] != '\0') {
      Log("%s ip:%s already start contrl connect\n","Net_ConnCamera",_Source);
      iVar5 = 3;
      goto LAB_10026af6;
    }
    iVar5 = FUN_10002a40(param_2,param_3);
    if (iVar5 != -2) {
      if (iVar5 == -3) {
        Log("[redacted]","[redacted]");
        iVar5 = 0x12;
        goto LAB_10026af6;
      }
      if (iVar5 == -1) {
        Log("%s DCCConn fail\n","Net_ConnCamera");
        iVar5 = 2;
        goto LAB_10026af6;
      }
      uVar2 = Ordinal_11(_Source);
      iVar3 = FUN_10002620(iVar5,uVar2);
      if (iVar3 == -1) {
        DCClose(iVar5);
        iVar5 = 2;
        Log("%s DCCDevPortNego fail\n","Net_ConnCamera");
        goto LAB_10026af6;
      }
      pcVar4[1] = '\x02';
      *(int *)(pcVar4 + 0x28) = iVar3;
      *(int *)(pcVar4 + 0x20) = iVar5;
      pcVar4[0x18] = '\x01';
      pcVar4[0x24] = '\x02';
      pcVar4[0x30] = '\0';
      pcVar4[0x31] = '\0';
      pcVar4[0x32] = '\0';
      pcVar4[0x33] = '\0';
      pcVar4[0x34] = '\0';
      pcVar4[0x35] = '\0';
      pcVar4[0x36] = '\0';
      pcVar4[0x37] = '\0';
      pcVar4[0x48] = '\0';
      pcVar4[0x49] = '\0';
      pcVar4[0x4a] = '\0';
      pcVar4[0x4b] = '\0';
      iVar5 = -1;
      uStack_23c = 0;
      uStack_238 = 0;
      uStack_234 = 0;
      uStack_230 = 0;
      uStack_22c = 0;
      uStack_228 = 0;
      uStack_224 = 0;
      uStack_220 = 0;
      iVar3 = CommQue_Create(8,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026af6;
      *(int *)(pcVar4 + 0x3c) = iVar3;
      iVar3 = CommQue_Create(8,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026af6;
      *(int *)(pcVar4 + 0x40) = iVar3;
      iVar3 = CommQue_Create(10,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026af6;
      *(int *)(pcVar4 + 0x44) = iVar3;
      iVar3 = TSK_create(FUN_1000b370,&uStack_23c,pcVar4);
      if (iVar3 == 0) goto LAB_10026af6;
      *(int *)(pcVar4 + 0x38) = iVar3;
      iVar3 = TSK_create(FUN_1000bc40,&uStack_23c,pcVar4);
      if (iVar3 == 0) goto LAB_10026af6;
      *(int *)(pcVar4 + 0x4c) = iVar3;
      iVar5 = 0;
      goto LAB_10026b03;
    }
    Log("%s DCCConn Beyond MAX Client Num  fail\n","Net_ConnCamera");
    iVar5 = 0xd;
LAB_10026b2f:
    Net_DisConnCamera(*(undefined4 *)(pcVar4 + 4));
    if (iVar5 != 0) {
      puVar1 = &DAT_1003c710;
      goto LAB_10026cf4;
    }
  }
  puVar1 = &DAT_1003c70c;
LAB_10026cf4:
  Log("%s:tHandle=%d,Port=%d,Timeout=%d %s, eCode=%d\n","Net_ConnCamera",param_1,param_2 & 0xffff,
      param_3 & 0xffff,puVar1,iVar5);
  FUN_10037e16();
  return;
}



/* FUNCTION Net_ConnCamera2 ENTRY 10026d30 */

void Net_ConnCamera2(uint param_1,uint param_2,uint param_3)

{
  char *_Source;
  undefined *puVar1;
  undefined4 uVar2;
  int iVar3;
  char *pcVar4;
  int iVar5;
  undefined4 uStack_33c;
  undefined4 uStack_338;
  undefined4 uStack_334;
  undefined4 uStack_330;
  undefined4 uStack_32c;
  undefined4 uStack_328;
  undefined4 uStack_324;
  undefined4 uStack_320;
  undefined1 local_318 [256];
  undefined1 local_218 [524];
  uint local_c;
  
                    /* 0x26d30  21  Net_ConnCamera2 */
  local_c = DAT_10047000 ^ (uint)&uStack_33c;
  pcVar4 = (char *)0x0;
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    pcVar4 = &DAT_1004e500 + param_1 * 0x31927c;
  }
  _Source = pcVar4 + 8;
  strncpy(pcVar4 + 0x3190b4,_Source,0x20);
  *(short *)(pcVar4 + 0x1c) = (short)param_2;
  if (*pcVar4 == '\0') {
    Log("%s handle not enable\n","Net_ConnCamera2");
    iVar5 = 4;
LAB_10026dca:
    Net_DisConnCamera(*(undefined4 *)(pcVar4 + 4));
    if (iVar5 != 0) goto LAB_10026e22;
LAB_10026dd7:
    memset(local_218,0,0x204);
    Net_QuerySysVersion(param_1,local_218);
    memset(local_318,0,0xfc);
    Net_QueryVideoDetectSetup(param_1,local_318);
    if (iVar5 != 0) goto LAB_10026e22;
  }
  else {
    if (pcVar4[0x18] != '\0') {
      Log("%s ip:%s already start contrl connect\n","Net_ConnCamera2",_Source);
      iVar5 = 3;
      goto LAB_10026dca;
    }
    iVar5 = FUN_10002a40(param_2,param_3);
    if (iVar5 != -2) {
      if (iVar5 == -3) {
        Log("[redacted]","[redacted]");
        iVar5 = 0x12;
        goto LAB_10026dca;
      }
      if (iVar5 == -1) {
        Log("%s DCCConn fail\n","Net_ConnCamera2");
        iVar5 = 2;
        goto LAB_10026dca;
      }
      uVar2 = Ordinal_11(_Source);
      iVar3 = FUN_10002620(iVar5,uVar2);
      if (iVar3 == -1) {
        DCClose(iVar5);
        iVar5 = 2;
        Log("%s DCCDevPortNego fail\n","Net_ConnCamera2");
        goto LAB_10026dca;
      }
      pcVar4[1] = '\x02';
      *(int *)(pcVar4 + 0x28) = iVar3;
      *(int *)(pcVar4 + 0x20) = iVar5;
      pcVar4[0x18] = '\x01';
      pcVar4[0x24] = '\x02';
      pcVar4[0x30] = '\0';
      pcVar4[0x31] = '\0';
      pcVar4[0x32] = '\0';
      pcVar4[0x33] = '\0';
      pcVar4[0x34] = '\0';
      pcVar4[0x35] = '\0';
      pcVar4[0x36] = '\0';
      pcVar4[0x37] = '\0';
      pcVar4[0x48] = '\0';
      pcVar4[0x49] = '\0';
      pcVar4[0x4a] = '\0';
      pcVar4[0x4b] = '\0';
      iVar5 = -1;
      uStack_33c = 0;
      uStack_338 = 0;
      uStack_334 = 0;
      uStack_330 = 0;
      uStack_32c = 0;
      uStack_328 = 0;
      uStack_324 = 0;
      uStack_320 = 0;
      iVar3 = CommQue_Create(8,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026dca;
      *(int *)(pcVar4 + 0x3c) = iVar3;
      iVar3 = CommQue_Create(8,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026dca;
      *(int *)(pcVar4 + 0x40) = iVar3;
      iVar3 = CommQue_Create(10,0x5a0,0);
      if (iVar3 == 0) goto LAB_10026dca;
      *(int *)(pcVar4 + 0x44) = iVar3;
      iVar3 = TSK_create(FUN_1000b370,&uStack_33c,pcVar4);
      if (iVar3 == 0) goto LAB_10026dca;
      *(int *)(pcVar4 + 0x38) = iVar3;
      iVar3 = TSK_create(FUN_1000bc40,&uStack_33c,pcVar4);
      if (iVar3 == 0) goto LAB_10026dca;
      *(int *)(pcVar4 + 0x4c) = iVar3;
      iVar5 = 0;
      goto LAB_10026dd7;
    }
    Log("%s DCCConn Beyond MAX Client Num  fail\n","Net_ConnCamera2");
    iVar5 = 0xd;
LAB_10026e22:
    Net_DisConnCamera(*(undefined4 *)(pcVar4 + 4));
    if (iVar5 != 0) {
      puVar1 = &DAT_1003c710;
      goto LAB_10026fe7;
    }
  }
  puVar1 = &DAT_1003c70c;
LAB_10026fe7:
  Log("%s:tHandle=%d,Port=%d,Timeout=%d %s, eCode=%d\n","Net_ConnCamera2",param_1,param_2 & 0xffff,
      param_3 & 0xffff,puVar1,iVar5);
  FUN_10037e16();
  return;
}



/* FUNCTION Net_ConnCameraTest ENTRY 10027030 */

int Net_ConnCameraTest(uint param_1,uint param_2,uint param_3)

{
  int iVar1;
  undefined4 uVar2;
  int iVar3;
  undefined *puVar4;
  int iVar5;
  char *pcVar6;
  int iVar7;
  undefined4 uStack_2c;
  undefined4 uStack_28;
  undefined4 uStack_24;
  undefined4 uStack_20;
  undefined4 uStack_1c;
  undefined4 uStack_18;
  undefined4 uStack_14;
  undefined4 uStack_10;
  undefined4 uStack_c;
  
                    /* 0x27030  25  Net_ConnCameraTest */
  iVar5 = 0;
  pcVar6 = (char *)0x0;
  iVar7 = 0;
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    pcVar6 = &DAT_1004e500 + param_1 * 0x31927c;
  }
  strncpy(pcVar6 + 0x3190b4,pcVar6 + 8,0x20);
  *(short *)(pcVar6 + 0x1c) = (short)param_2;
  do {
    iVar7 = iVar7 + 1;
    if (*pcVar6 == '\0') {
      Log("%s handle not enable\n","Net_ConnCameraTest");
      iVar5 = 4;
    }
    else if (pcVar6[0x18] == '\0') {
      iVar1 = FUN_10002a40(param_2,param_3);
      if (iVar1 == -2) {
        Log("%s DCCConn Beyond MAX Client Num  fail\n","Net_ConnCameraTest");
        iVar5 = 0xd;
        goto LAB_1002726e;
      }
      if (iVar1 == -3) {
        Log("[redacted]","[redacted]");
        iVar5 = 0x12;
      }
      else if (iVar1 == -1) {
        Log("%s DCCConn fail\n","Net_ConnCameraTest");
        iVar5 = 2;
      }
      else {
        uVar2 = Ordinal_11(pcVar6 + 8);
        iVar3 = FUN_10002620(iVar1,uVar2);
        if (iVar3 == -1) {
          DCClose(iVar1);
          iVar5 = 2;
          Log("%s DCCDevPortNego fail\n","Net_ConnCameraTest");
        }
        else {
          if (iVar5 == 0xd) break;
          if (iVar5 == 0) {
            pcVar6[1] = '\x02';
            *(int *)(pcVar6 + 0x28) = iVar3;
            *(int *)(pcVar6 + 0x20) = iVar1;
            pcVar6[0x18] = '\x01';
            pcVar6[0x24] = '\x02';
            pcVar6[0x30] = '\0';
            pcVar6[0x31] = '\0';
            pcVar6[0x32] = '\0';
            pcVar6[0x33] = '\0';
            pcVar6[0x34] = '\0';
            pcVar6[0x35] = '\0';
            pcVar6[0x36] = '\0';
            pcVar6[0x37] = '\0';
            pcVar6[0x48] = '\0';
            pcVar6[0x49] = '\0';
            pcVar6[0x4a] = '\0';
            pcVar6[0x4b] = '\0';
            iVar5 = -1;
            uStack_2c = 0;
            uStack_28 = 0;
            uStack_24 = 0;
            uStack_20 = 0;
            uStack_1c = 0;
            uStack_18 = 0;
            uStack_14 = 0;
            uStack_10 = 0;
            uStack_c = 0;
            iVar1 = CommQue_Create(8,0x5a0,0);
            if (iVar1 != 0) {
              *(int *)(pcVar6 + 0x3c) = iVar1;
              iVar1 = CommQue_Create(8,0x5a0,0);
              if (iVar1 != 0) {
                *(int *)(pcVar6 + 0x40) = iVar1;
                iVar1 = CommQue_Create(10,0x5a0,0);
                if (iVar1 != 0) {
                  *(int *)(pcVar6 + 0x44) = iVar1;
                  iVar1 = TSK_create(FUN_1000b370,&uStack_2c,pcVar6);
                  if (iVar1 != 0) {
                    *(int *)(pcVar6 + 0x38) = iVar1;
                    iVar1 = TSK_create(FUN_1000bc40,&uStack_2c,pcVar6);
                    if (iVar1 != 0) {
                      *(int *)(pcVar6 + 0x4c) = iVar1;
                      iVar5 = 0;
                      goto LAB_100272c9;
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    else {
      Log("%s ip:%s already start contrl connect\n","Net_ConnCameraTest",pcVar6 + 8);
      iVar5 = 3;
    }
    Net_DisConnCamera(*(undefined4 *)(pcVar6 + 4));
    if (iVar5 == 0) goto LAB_100272c9;
  } while (iVar7 < 2);
  if (iVar5 == 0) {
LAB_100272c9:
    puVar4 = &DAT_1003c70c;
  }
  else {
LAB_1002726e:
    Net_DisConnCamera(*(undefined4 *)(pcVar6 + 4));
    puVar4 = &DAT_1003c710;
  }
  Log("%s:tHandle=%d,Port=%d,Timeout=%d %s, eCode=%d\n","Net_ConnCameraTest",param_1,
      param_2 & 0xffff,param_3 & 0xffff,puVar4,iVar5);
  return iVar5;
}



/* FUNCTION Net_ConnCameraEx ENTRY 100272d0 */

void Net_ConnCameraEx(uint param_1,uint param_2,uint param_3,char *param_4,char *param_5)

{
  char *pcVar1;
  undefined4 uVar2;
  int iVar3;
  undefined4 uVar4;
  undefined *puVar5;
  char *pcVar6;
  int iVar7;
  char *local_29c;
  undefined4 local_298;
  int local_294;
  char *local_290;
  int local_28c;
  char *local_288;
  undefined4 local_284;
  undefined4 local_280;
  undefined4 local_27c;
  undefined4 local_278;
  undefined4 local_274;
  undefined4 local_270;
  undefined4 local_26c;
  undefined4 local_268;
  undefined4 local_264;
  char local_260 [32];
  char local_240 [40];
  undefined1 local_218 [524];
  uint local_c;
  
                    /* 0x272d0  24  Net_ConnCameraEx */
  local_c = DAT_10047000 ^ (uint)&local_29c;
  local_298 = 0xffffffff;
  local_28c = -1;
  local_288 = param_4;
  local_290 = param_5;
  local_29c = (char *)0x0;
  local_294 = 0;
  memset(local_260,0,0x44);
  if (param_4 != (char *)0x0) {
    strncpy(local_260,param_4,0x20);
  }
  if (param_5 != (char *)0x0) {
    strncpy(local_240,param_5,0x24);
  }
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    local_29c = &DAT_1004e500 + param_1 * 0x31927c;
  }
  pcVar6 = local_29c;
  strncpy(local_29c + 0x3190b4,local_29c + 8,0x20);
  *(short *)(pcVar6 + 0x1c) = (short)param_2;
  do {
    local_294 = local_294 + 1;
    if (*pcVar6 != '\0') {
      if (pcVar6[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCameraEx",pcVar6 + 8);
        iVar7 = 3;
        goto LAB_100276ad;
      }
      iVar7 = FUN_10002c00(param_2,param_3,param_4,local_290,&local_298);
      uVar2 = local_298;
      if (iVar7 == 0) {
        strncpy(local_29c + 0x3190d4,local_260,0x20);
        strncpy(local_29c + 0x3190f4,local_240,0x24);
LAB_100274cf:
        uVar4 = Ordinal_11(local_29c + 8);
        local_28c = FUN_10002620(uVar2,uVar4);
        if (local_28c == -1) {
          DCClose(uVar2);
          local_298 = 0xffffffff;
          iVar7 = 1000;
          Log("%s DCCDevPortNego fail\n","Net_ConnCameraEx");
          goto LAB_100276ad;
        }
      }
      else if (iVar7 == 6) goto LAB_100274cf;
      if (iVar7 == 0xd) goto LAB_1002764b;
      if ((iVar7 == 0) || (iVar7 == 6)) {
        local_29c[1] = '\x02';
        *(int *)(pcVar6 + 0x28) = local_28c;
        *(short *)(pcVar6 + 0x1c) = (short)param_2;
        *(undefined4 *)(pcVar6 + 0x20) = uVar2;
        pcVar6[0x18] = '\x01';
        pcVar6[0x24] = '\x02';
        pcVar6[0x30] = '\0';
        pcVar6[0x31] = '\0';
        pcVar6[0x32] = '\0';
        pcVar6[0x33] = '\0';
        pcVar6[0x34] = '\0';
        pcVar6[0x35] = '\0';
        pcVar6[0x36] = '\0';
        pcVar6[0x37] = '\0';
        pcVar6[0x48] = '\0';
        pcVar6[0x49] = '\0';
        pcVar6[0x4a] = '\0';
        pcVar6[0x4b] = '\0';
        local_284 = 0;
        local_280 = 0;
        local_27c = 0;
        local_278 = 0;
        local_274 = 0;
        local_270 = 0;
        local_26c = 0;
        local_268 = 0;
        local_264 = 0;
        iVar3 = CommQue_Create(8,0x5a0,0);
        if (iVar3 == 0) {
          iVar7 = 0x3e9;
        }
        else {
          *(int *)(pcVar6 + 0x3c) = iVar3;
          iVar3 = CommQue_Create(8,0x5a0,0);
          if (iVar3 == 0) {
            iVar7 = 0x3ea;
          }
          else {
            *(int *)(pcVar6 + 0x40) = iVar3;
            iVar3 = CommQue_Create(10,0x5a0,0);
            pcVar1 = local_29c;
            if (iVar3 == 0) {
              iVar7 = 0x3eb;
            }
            else {
              *(int *)(pcVar6 + 0x44) = iVar3;
              iVar3 = TSK_create(FUN_1000b370,&local_284,local_29c);
              if (iVar3 == 0) {
                iVar7 = 0x3ec;
              }
              else {
                *(int *)(pcVar6 + 0x38) = iVar3;
                iVar3 = TSK_create(FUN_1000bc40,&local_284,pcVar1);
                if (iVar3 == 0) {
                  iVar7 = 0x3ed;
                }
                else {
                  *(int *)(pcVar6 + 0x4c) = iVar3;
                  if (iVar7 != 6) goto LAB_100276a5;
                  iVar7 = FUN_100142d0(pcVar6 + 0x18);
                  if (iVar7 == 0) {
                    strncpy(pcVar1 + 0x3190d4,local_260,0x20);
                    strncpy(pcVar1 + 0x3190f4,local_240,0x24);
                    goto LAB_1002761b;
                  }
                }
              }
            }
          }
        }
        goto LAB_100276ad;
      }
LAB_100276a5:
      if (iVar7 != 0) goto LAB_100276ad;
LAB_1002761b:
      memset(local_218,0,0x204);
      Net_QuerySysVersion(param_1,local_218);
      break;
    }
    Log("%s handle not enable\n","Net_ConnCameraEx");
    iVar7 = 4;
LAB_100276ad:
    pcVar6 = local_29c;
    Net_DisConnCamera(*(undefined4 *)(local_29c + 4));
    if (iVar7 == 0) goto LAB_1002761b;
    param_4 = local_288;
  } while (local_294 < 2);
  if (iVar7 == 0) {
    puVar5 = &DAT_1003c70c;
  }
  else {
LAB_1002764b:
    Net_DisConnCamera(*(undefined4 *)(local_29c + 4));
    puVar5 = &DAT_1003c710;
  }
  Log("[redacted]","[redacted]",
      param_1,param_2 & 0xffff,param_3 & 0xffff,local_288,local_290,puVar5,iVar7);
  FUN_10037e16();
  return;
}



/* FUNCTION Net_ConnCameraEtcp ENTRY 100276e0 */

void Net_ConnCameraEtcp(uint param_1,uint param_2,uint param_3,char *param_4,char *param_5,
                       byte param_6)

{
  char *pcVar1;
  undefined4 uVar2;
  undefined4 uVar3;
  undefined *puVar4;
  int iVar5;
  char *pcVar6;
  int iVar7;
  char *local_94;
  uint local_90;
  int local_8c;
  undefined4 local_88;
  char *local_84;
  char *local_80;
  undefined4 local_7c;
  undefined4 local_78;
  undefined4 local_74;
  undefined4 local_70;
  undefined4 local_6c;
  undefined4 local_68;
  undefined4 local_64;
  undefined4 local_60;
  undefined4 local_5c;
  char local_58 [32];
  char local_38 [44];
  uint local_c;
  
                    /* 0x276e0  23  Net_ConnCameraEtcp */
  local_c = DAT_10047000 ^ (uint)&local_94;
  local_88 = 0xffffffff;
  local_90 = 0xffffffff;
  local_80 = param_4;
  local_84 = param_5;
  local_94 = (char *)0x0;
  local_8c = 0;
  memset(local_58,0,0x44);
  if (param_4 != (char *)0x0) {
    strncpy(local_58,param_4,0x20);
  }
  if (param_5 != (char *)0x0) {
    strncpy(local_38,param_5,0x24);
  }
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    local_94 = &DAT_1004e500 + param_1 * 0x31927c;
  }
  pcVar6 = local_94;
  strncpy(local_94 + 0x3190b4,local_94 + 8,0x20);
  *(short *)(pcVar6 + 0x1c) = (short)param_2;
  do {
    local_8c = local_8c + 1;
    if (*pcVar6 != '\0') {
      if (pcVar6[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCameraEtcp",pcVar6 + 8);
        iVar7 = 3;
        goto LAB_10027b0d;
      }
      iVar7 = FUN_10002c00(param_2,param_3,param_4,local_84,&local_88);
      uVar2 = local_88;
      if (iVar7 == 0) {
        strncpy(local_94 + 0x3190d4,local_58,0x20);
        strncpy(local_94 + 0x3190f4,local_38,0x24);
LAB_100278df:
        uVar3 = Ordinal_11(local_94 + 8);
        local_90 = FUN_10002620(uVar2,uVar3);
        if (local_90 == 0xffffffff) {
          DCClose(uVar2);
          local_88 = 0xffffffff;
          iVar7 = 1000;
          Log("%s DCCDevPortNego fail\n","Net_ConnCameraEtcp");
          goto LAB_10027b0d;
        }
      }
      else if (iVar7 == 6) goto LAB_100278df;
      if (iVar7 == 0xd) goto LAB_10027a56;
      if ((iVar7 == 0) || (iVar7 == 6)) {
        local_94[1] = '\x02';
        *(uint *)(pcVar6 + 0x28) = local_90;
        *(short *)(pcVar6 + 0x1c) = (short)param_2;
        *(undefined4 *)(pcVar6 + 0x20) = uVar2;
        pcVar6[0x18] = '\x01';
        pcVar6[0x24] = '\x02';
        pcVar6[0x30] = '\0';
        pcVar6[0x31] = '\0';
        pcVar6[0x32] = '\0';
        pcVar6[0x33] = '\0';
        pcVar6[0x34] = '\0';
        pcVar6[0x35] = '\0';
        pcVar6[0x36] = '\0';
        pcVar6[0x37] = '\0';
        pcVar6[0x48] = '\0';
        pcVar6[0x49] = '\0';
        pcVar6[0x4a] = '\0';
        pcVar6[0x4b] = '\0';
        local_7c = 0;
        local_78 = 0;
        local_74 = 0;
        local_70 = 0;
        local_6c = 0;
        local_68 = 0;
        local_64 = 0;
        local_60 = 0;
        local_5c = 0;
        iVar5 = CommQue_Create(8,0x5a0,0);
        if (iVar5 == 0) {
          iVar7 = 0x3e9;
        }
        else {
          *(int *)(pcVar6 + 0x3c) = iVar5;
          iVar5 = CommQue_Create(8,0x5a0,0);
          if (iVar5 == 0) {
            iVar7 = 0x3ea;
          }
          else {
            *(int *)(pcVar6 + 0x40) = iVar5;
            iVar5 = CommQue_Create(10,0x5a0,0);
            pcVar1 = local_94;
            if (iVar5 == 0) {
              iVar7 = 0x3eb;
            }
            else {
              *(int *)(pcVar6 + 0x44) = iVar5;
              iVar5 = TSK_create(FUN_1000b370,&local_7c,local_94);
              if (iVar5 == 0) {
                iVar7 = 0x3ec;
              }
              else {
                *(int *)(pcVar6 + 0x38) = iVar5;
                iVar5 = TSK_create(FUN_1000bc40,&local_7c,pcVar1);
                if (iVar5 == 0) {
                  iVar7 = 0x3ed;
                }
                else {
                  *(int *)(pcVar6 + 0x4c) = iVar5;
                  if (iVar7 != 6) goto LAB_10027b05;
                  iVar7 = FUN_100142d0(pcVar6 + 0x18);
                  if (iVar7 == 0) {
                    strncpy(pcVar1 + 0x3190d4,local_58,0x20);
                    strncpy(pcVar1 + 0x3190f4,local_38,0x24);
                    goto LAB_10027a2b;
                  }
                }
              }
            }
          }
        }
        goto LAB_10027b0d;
      }
LAB_10027b05:
      if (iVar7 != 0) goto LAB_10027b0d;
LAB_10027a2b:
      Net_RegOffLineClient(param_1);
      local_90 = (uint)param_6;
      Net_DetectModeSetup(param_1,&local_90);
      pcVar6 = local_94;
      break;
    }
    Log("%s handle not enable\n","Net_ConnCameraEtcp");
    iVar7 = 4;
LAB_10027b0d:
    pcVar6 = local_94;
    Net_DisConnCamera(*(undefined4 *)(local_94 + 4));
    if (iVar7 == 0) goto LAB_10027a2b;
    param_4 = local_80;
  } while (local_8c < 2);
  if (iVar7 != 0) {
LAB_10027a56:
    pcVar6 = local_94;
    Net_DisConnCamera(*(undefined4 *)(local_94 + 4));
  }
  iVar5 = (iVar7 != 0) + 2;
  if ((DAT_1004dc2c != 0) && (DAT_1004dc20 != 0)) {
    Log("%s %s, ucCtrlConnState=%d\n","Net_ConnCameraEtcp",pcVar6 + 8,iVar5);
    PostThreadMessageW(DAT_1004dc20,0x4c8,*(WPARAM *)(pcVar6 + 4),iVar5);
  }
  puVar4 = &DAT_1003c70c;
  if (iVar7 != 0) {
    puVar4 = &DAT_1003c710;
  }
  Log("[redacted]","[redacted]"
      ,param_1,param_2 & 0xffff,param_3 & 0xffff,local_80,local_84,puVar4,iVar7);
  FUN_10037e16();
  return;
}



/* FUNCTION Net_DisConnCamera ENTRY 10027b40 */

undefined4 Net_DisConnCamera(uint param_1)

{
  int iVar1;
  
                    /* 0x27b40  40  Net_DisConnCamera */
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x31927c;
    if (&DAT_1004e500 + iVar1 != (char *)0x0) {
      if ((&DAT_1004e500)[iVar1] != '\0') {
        if ((&DAT_1004e501)[iVar1] == '\x02') {
          FUN_10002eb0();
          (&DAT_1004e501)[iVar1] = 3;
        }
        FUN_10025370();
      }
      Log("%s:tHandle=%d, eCode=%d\n","Net_DisConnCamera",param_1,0);
      return 0;
    }
  }
  Log("%s invalid handle:%d\n","Net_DisConnCamera",param_1);
  return 6;
}



/* FUNCTION Net_GateSetup ENTRY 10029370 */

undefined4 Net_GateSetup(undefined4 param_1,undefined1 *param_2)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x29370  72  Net_GateSetup */
  if (param_2 == (undefined1 *)0x0) {
    Log("%s parameter invalid\n","Net_GateSetup");
    return 6;
  }
  iVar1 = FUN_100255c0();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_GateSetup",0);
    return 0;
  }
  uVar2 = FUN_10008d60();
  Log("%s:State=%d, eCode=%d, tHandle=%d\n","Net_GateSetup",*param_2,uVar2,param_1);
  return uVar2;
}



/* FUNCTION Net_GateSetupEx ENTRY 10029410 */

undefined4 Net_GateSetupEx(undefined4 param_1,undefined1 *param_2)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x29410  73  Net_GateSetupEx */
  if (param_2 == (undefined1 *)0x0) {
    Log("%s parameter invalid\n","Net_GateSetupEx");
    return 6;
  }
  iVar1 = FUN_100255c0();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_GateSetupEx",0);
    return 0;
  }
  uVar2 = FUN_10008e80();
  Log("%s:State=%d, index=%d, eCode=%d, tHandle=%d\n","Net_GateSetupEx",*param_2,param_2[1],uVar2,
      param_1);
  return uVar2;
}



/* FUNCTION Net_QueryConnState ENTRY 1002a9c0 */

char Net_QueryConnState(uint param_1)

{
  char cVar1;
  int iVar2;
  
                    /* 0x2a9c0  185  Net_QueryConnState */
  if (param_1 < 0x20) {
    iVar2 = param_1 * 0x31927c;
    if ((&DAT_1004e500 + iVar2 != (char *)0x0) && ((&DAT_1004e500)[iVar2] != '\0')) {
      if ((&DAT_1004e518)[iVar2] == '\0') {
        return '\f';
      }
      cVar1 = (&DAT_1004e501)[iVar2];
      if (cVar1 == '\x02') {
        return '\0';
      }
      if (cVar1 == '\0') {
        return '\x02';
      }
      return cVar1;
    }
  }
  return '\x04';
}



/* FUNCTION Net_ImageSnap ENTRY 1002aa60 */

int Net_ImageSnap(uint param_1,int param_2)

{
  int iVar1;
  code *pcVar2;
  char *pcVar3;
  
                    /* 0x2aa60  90  Net_ImageSnap */
  pcVar2 = Log_exref;
  iVar1 = 0;
  if (param_2 == 0) {
    Log("%s parameter invalid\n","Net_ImageSnap");
    iVar1 = 6;
    goto LAB_1002ab1c;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x31927c;
    if ((&DAT_1004e500)[iVar1] == '\0') {
      iVar1 = 4;
      Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConn",param_1,4);
      goto LAB_1002aaee;
    }
    if (((&DAT_1004e518)[iVar1] == '\0') || ((&DAT_1004e501)[iVar1] != '\x02')) {
      Log("%s: connect state not valid, eCode=%d\n","DCMValidCtrlConn",2);
      iVar1 = 2;
      pcVar3 = "%s DCMValidCtrlConn fail, eCode=%d\n";
    }
    else {
      iVar1 = FUN_1000a1d0();
      pcVar2 = Log_exref;
      if (iVar1 == 0) goto LAB_1002ab1c;
      pcVar3 = "%s fail, eCode=%d\n";
    }
  }
  else {
LAB_1002aaee:
    pcVar3 = "%s DCMValidCtrlConn fail, eCode=%d\n";
  }
  (*pcVar2)(pcVar3,"Net_ImageSnap",iVar1);
LAB_1002ab1c:
  (*pcVar2)("%s tHandle=%d eCode=%d\n","Net_ImageSnap",param_1,iVar1);
  return iVar1;
}



/* FUNCTION Net_SaveImageToJpeg ENTRY 10025690 */

void Net_SaveImageToJpeg(uint param_1,char *param_2)

{
  int iVar1;
  FILE *_File;
  int iVar2;
  undefined4 uVar3;
  longlong lVar4;
  size_t local_74;
  undefined4 local_70;
  void *local_6c;
  int local_68;
  int local_64;
  char *local_60;
  int local_5c;
  undefined1 local_58 [76];
  uint local_c;
  
                    /* 0x25690  369  Net_SaveImageToJpeg */
  local_c = DAT_10047000 ^ (uint)&local_74;
  iVar2 = 0;
  local_60 = param_2;
  local_74 = 0;
  local_5c = 0;
  lVar4 = FUN_10033e00();
  if ((lVar4 != -1) && (lVar4 = FUN_100385e0(lVar4,0x800,0), lVar4 == 0)) {
    Log("%s DiskFreeSize < 2M!\n","Net_SaveImageToJpeg");
    FUN_10037e16();
    return;
  }
  if (param_2 == (char *)0x0) {
    FUN_10037e16();
    return;
  }
  iVar1 = FUN_100255c0();
  local_64 = iVar1;
  if (iVar1 != 0) {
    local_74 = 0;
    local_70 = 0;
    if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
      *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 0;
    }
    else {
      iVar2 = 4;
    }
    Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar2);
    if ((iVar2 == 0) && (iVar2 = Net_ImageSnap(param_1,&local_74), iVar2 == 0)) {
      local_74 = 0x300000;
      local_70 = 0x19000;
      local_6c = (void *)(iVar1 + 0xb4);
      local_68 = iVar1 + 0x3000b4;
      iVar2 = Net_GetImage(param_1,0,local_58,&local_74);
      while ((iVar2 != 0 && (local_5c = local_5c + 1, local_5c < 0x29))) {
        Sleep(0x32);
        local_74 = 0x300000;
        local_70 = 0x19000;
        local_6c = (void *)(iVar1 + 0xb4);
        local_68 = iVar1 + 0x3000b4;
        iVar2 = Net_GetImage(param_1,0,local_58,&local_74);
      }
      _File = fopen(local_60,"wb");
      iVar1 = local_64;
      if (_File != (FILE *)0x0) {
        fwrite(local_6c,1,local_74,_File);
        fflush(_File);
        fclose(_File);
        iVar1 = local_64;
      }
    }
    uVar3 = 0;
    if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
      *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 1;
    }
    else {
      uVar3 = 4;
    }
    Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,1,uVar3);
    memset((void *)(iVar1 + 0xb4),0,0x300000);
    memset((void *)(iVar1 + 0x3000b4),0,0x19000);
    Log("%s:tHandle=%d, PathNmme=%s, eCode=%d\n","Net_SaveImageToJpeg",param_1,local_60,uVar3);
    FUN_10037e16();
    return;
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SaveImageToJpeg",local_74);
  FUN_10037e16();
  return;
}



/* FUNCTION _Net_SaveImageToJpegEx@12 ENTRY 10025930 */

void _Net_SaveImageToJpegEx_12(uint param_1,byte param_2,char *param_3)

{
  int iVar1;
  FILE *_File;
  int iVar2;
  undefined4 uVar3;
  longlong lVar4;
  size_t local_74;
  uint local_70;
  void *local_6c;
  int local_68;
  int local_64;
  char *local_60;
  int local_5c;
  undefined1 local_58 [57];
  byte local_1f;
  uint local_c;
  
                    /* 0x25930  370  _Net_SaveImageToJpegEx@12 */
  local_c = DAT_10047000 ^ (uint)&local_74;
  iVar2 = 0;
  local_60 = param_3;
  local_74 = 0;
  local_5c = 0;
  lVar4 = FUN_10033e00();
  if ((lVar4 != -1) && (lVar4 = FUN_100385e0(lVar4,0x800,0), lVar4 == 0)) {
    Log("%s DiskFreeSize < 2M!\n","Net_SaveImageToJpegEx");
    FUN_10037e16();
    return;
  }
  if (param_3 == (char *)0x0) {
    FUN_10037e16();
    return;
  }
  iVar1 = FUN_100255c0();
  local_64 = iVar1;
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SaveImageToJpegEx",local_74);
    FUN_10037e16();
    return;
  }
  local_74 = 0;
  local_70 = (uint)param_2;
  if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
    *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 0;
  }
  else {
    iVar2 = 4;
  }
  Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar2);
  if ((iVar2 == 0) && (iVar2 = Net_ImageSnap(param_1,&local_74), iVar2 == 0)) {
    while( true ) {
      while( true ) {
        local_74 = 0x300000;
        local_70 = 0x19000;
        local_6c = (void *)(iVar1 + 0xb4);
        local_68 = iVar1 + 0x3000b4;
        iVar2 = Net_GetImage(param_1,0,local_58,&local_74);
        if (iVar2 != 0) break;
        if (((param_2 != 0) && (param_2 != 2)) || (local_1f == param_2)) goto LAB_10025ab4;
      }
      local_5c = local_5c + 1;
      if (0x28 < local_5c) break;
      Sleep(0x32);
    }
LAB_10025ab4:
    _File = fopen(local_60,"wb");
    iVar1 = local_64;
    if (_File != (FILE *)0x0) {
      fwrite(local_6c,1,local_74,_File);
      fflush(_File);
      fclose(_File);
      iVar1 = local_64;
    }
  }
  uVar3 = 0;
  if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
    *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 1;
  }
  else {
    uVar3 = 4;
  }
  Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,1,uVar3);
  memset((void *)(iVar1 + 0xb4),0,0x300000);
  memset((void *)(iVar1 + 0x3000b4),0,0x19000);
  Log("%s:tHandle=%d, PathNmme=%s, eCode=%d\n","Net_SaveImageToJpegEx",param_1,local_60,uVar3);
  FUN_10037e16();
  return;
}



/* FUNCTION _Net_SaveChannelImageToJpeg@12 ENTRY 10025bb0 */

void _Net_SaveChannelImageToJpeg_12(uint param_1,byte param_2,char *param_3)

{
  int iVar1;
  FILE *_File;
  undefined4 uVar2;
  int iVar3;
  longlong lVar4;
  size_t local_74;
  undefined4 local_70;
  void *local_6c;
  int local_68;
  int local_64;
  char *local_60;
  int local_5c;
  undefined1 local_58 [76];
  uint local_c;
  
                    /* 0x25bb0  367  _Net_SaveChannelImageToJpeg@12 */
  local_c = DAT_10047000 ^ (uint)&local_74;
  iVar3 = 0;
  local_60 = param_3;
  local_74 = 0;
  local_5c = 0;
  if (param_2 < 4) {
    lVar4 = FUN_10033e00();
    if ((lVar4 != -1) && (lVar4 = FUN_100385e0(lVar4,0x800,0), lVar4 == 0)) {
      Log("%s DiskFreeSize < 2M!\n","Net_SaveChannelImageToJpeg");
      FUN_10037e16();
      return;
    }
    if (param_3 != (char *)0x0) {
      iVar1 = FUN_100255c0();
      local_64 = iVar1;
      if (iVar1 == 0) {
        Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SaveChannelImageToJpeg",local_74);
        FUN_10037e16();
        return;
      }
      local_74 = 0;
      local_70 = 0;
      if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
        *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 0;
      }
      else {
        iVar3 = 4;
      }
      Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar3);
      if (iVar3 == 0) {
        local_70 = CONCAT31(local_70._1_3_,param_2);
        iVar3 = Net_ImageSnap(param_1,&local_74);
        if (iVar3 == 0) {
          local_74 = 0x300000;
          local_70 = 0x19000;
          local_6c = (void *)(iVar1 + 0xb4);
          local_68 = iVar1 + 0x3000b4;
          iVar3 = Net_GetImage(param_1,0,local_58,&local_74);
          while ((iVar3 != 0 && (local_5c = local_5c + 1, local_5c < 0x29))) {
            Sleep(0x32);
            local_74 = 0x300000;
            local_70 = 0x19000;
            local_6c = (void *)(iVar1 + 0xb4);
            local_68 = iVar1 + 0x3000b4;
            iVar3 = Net_GetImage(param_1,0,local_58,&local_74);
          }
          _File = fopen(local_60,"wb");
          iVar1 = local_64;
          if (_File != (FILE *)0x0) {
            fwrite(local_6c,1,local_74,_File);
            fflush(_File);
            fclose(_File);
            iVar1 = local_64;
          }
        }
      }
      uVar2 = Net_SetSnapMode(param_1,1);
      memset((void *)(iVar1 + 0xb4),0,0x300000);
      memset((void *)(iVar1 + 0x3000b4),0,0x19000);
      Log("%s:tHandle=%d, PathNmme=%s, eCode=%d\n","Net_SaveChannelImageToJpeg",param_1,local_60,
          uVar2);
      FUN_10037e16();
      return;
    }
  }
  else {
    Log("%s ucChannel:%d Invalid fail, eCode=%d\n","Net_SaveChannelImageToJpeg",param_2,6);
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_GetJpgBufferEx ENTRY 1002b110 */

void Net_GetJpgBufferEx(uint param_1,undefined4 *param_2,size_t *param_3)

{
  size_t _Size;
  int iVar1;
  void *_Dst;
  int iVar2;
  undefined4 uVar3;
  undefined1 auStack_7c [4];
  size_t local_78;
  undefined4 local_74;
  void *local_70;
  int local_6c;
  int local_68;
  size_t *local_64;
  int local_60;
  undefined4 *local_5c;
  undefined1 local_58 [76];
  uint local_c;
  
                    /* 0x2b110  80  Net_GetJpgBufferEx */
  local_c = DAT_10047000 ^ (uint)auStack_7c;
  iVar2 = 0;
  local_5c = param_2;
  local_64 = param_3;
  local_78 = 0;
  local_68 = 0;
  if (param_3 != (size_t *)0x0) {
    iVar1 = FUN_100255c0();
    local_60 = iVar1;
    if (iVar1 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_GetJpgBufferEx",local_78);
    }
    else {
      local_78 = 0;
      local_74 = 0;
      if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
        *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 0;
      }
      else {
        iVar2 = 4;
      }
      Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar2);
      if ((iVar2 == 0) && (iVar2 = Net_ImageSnap(param_1,&local_78), iVar2 == 0)) {
        local_78 = 0x300000;
        local_74 = 0x19000;
        local_70 = (void *)(iVar1 + 0xb4);
        local_6c = iVar1 + 0x3000b4;
        iVar2 = Net_GetImage(param_1,0,local_58,&local_78);
        _Size = local_78;
        while ((local_78 = _Size, iVar2 != 0 && (local_68 = local_68 + 1, local_68 < 0x29))) {
          Sleep(0x32);
          local_78 = 0x300000;
          local_74 = 0x19000;
          local_70 = (void *)(iVar1 + 0xb4);
          local_6c = iVar1 + 0x3000b4;
          iVar2 = Net_GetImage(param_1,0,local_58,&local_78);
          _Size = local_78;
        }
        *local_64 = _Size;
        _Dst = malloc(_Size);
        *local_5c = _Dst;
        memcpy(_Dst,local_70,_Size);
        iVar1 = local_60;
      }
      uVar3 = 0;
      if ((param_1 < 0x20) && (param_1 * 0x31927c != -0x1004e500)) {
        *(undefined4 *)(&DAT_1004e52c + param_1 * 0x31927c) = 1;
      }
      else {
        uVar3 = 4;
      }
      Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,1,uVar3);
      memset((void *)(iVar1 + 0xb4),0,0x300000);
      memset((void *)(iVar1 + 0x3000b4),0,0x19000);
    }
    FUN_10037e16();
    return;
  }
  FUN_10037e16();
  return;
}



/* FUNCTION Net_RegImageRecv ENTRY 1002ba50 */

undefined4 Net_RegImageRecv(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x2ba50  345  Net_RegImageRecv */
  uVar1 = 0;
  if (param_1 == 0) {
    uVar1 = 6;
  }
  else {
    DAT_1004dc24 = param_1;
  }
  Log("%s eCode=%d\n","Net_RegImageRecv",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegImageRecv2 ENTRY 1002ba90 */

undefined4 Net_RegImageRecv2(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x2ba90  344  Net_RegImageRecv2 */
  uVar1 = 0;
  if (param_1 == 0) {
    uVar1 = 6;
  }
  else {
    DAT_1004dc28 = param_1;
  }
  Log("%s eCode=%d\n","Net_RegImageRecv2",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegImageRecvEx ENTRY 1002bad0 */

undefined4 Net_RegImageRecvEx(uint param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x2bad0  347  Net_RegImageRecvEx */
  uVar2 = 0;
  if (param_2 == 0) {
    uVar2 = 6;
LAB_1002bb3b:
    Log("%s eCode=%d\n","Net_RegImageRecvEx",uVar2);
    return uVar2;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x31927c;
    if ((&DAT_1004e500)[iVar1] != '\0') {
      *(int *)(&DAT_1004e560 + iVar1) = param_2;
      *(undefined4 *)(&DAT_1004e564 + iVar1) = param_3;
      goto LAB_1002bb3b;
    }
    uVar2 = 4;
    Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConnEx",param_1,4);
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegImageRecvEx",uVar2);
  return uVar2;
}



/* FUNCTION Net_RegImageRecvEx2 ENTRY 1002bb60 */

undefined4 Net_RegImageRecvEx2(uint param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x2bb60  346  Net_RegImageRecvEx2 */
  uVar2 = 0;
  if (param_2 == 0) {
    uVar2 = 6;
LAB_1002bbcb:
    Log("%s eCode=%d\n","Net_RegImageRecvEx2",uVar2);
    return uVar2;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x31927c;
    if ((&DAT_1004e500)[iVar1] != '\0') {
      *(int *)(&DAT_1004e568 + iVar1) = param_2;
      *(undefined4 *)(&DAT_1004e56c + iVar1) = param_3;
      goto LAB_1002bbcb;
    }
    uVar2 = 4;
    Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConnEx",param_1,4);
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegImageRecvEx2",uVar2);
  return uVar2;
}



/* FUNCTION Net_RegOffLineImageRecvEx ENTRY 1002bc70 */

int Net_RegOffLineImageRecvEx(undefined4 param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined *puVar2;
  code *pcVar3;
  char *pcVar4;
  
                    /* 0x2bc70  350  Net_RegOffLineImageRecvEx */
  if (param_2 == 0) {
    iVar1 = FUN_100255c0();
    pcVar3 = Log_exref;
    if (iVar1 == 0) {
      iVar1 = 0;
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_StopGetOffLineData",0);
    }
    else {
      iVar1 = FUN_100131d0();
    }
    puVar2 = &DAT_1003c70c;
    if (iVar1 != 0) {
      puVar2 = &DAT_1003c710;
    }
    pcVar4 = "%s Net_StopGetOffLineData %s, eCode=%d\n";
  }
  else {
    iVar1 = FUN_100255c0();
    if (iVar1 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLineImageRecvEx",0);
      return 0;
    }
    *(int *)(iVar1 + 0x70) = param_2;
    *(undefined4 *)(iVar1 + 0x74) = param_3;
    iVar1 = FUN_1002f6d0(param_1);
    puVar2 = &DAT_1003c70c;
    if (iVar1 != 0) {
      puVar2 = &DAT_1003c710;
    }
    pcVar4 = "%s Net_StartGetOffLineData %s, eCode=%d\n";
    pcVar3 = Log_exref;
  }
  (*pcVar3)(pcVar4,"Net_RegOffLineImageRecvEx",puVar2,iVar1);
  (*pcVar3)("%s eCode=%d\n","Net_RegOffLineImageRecvEx",iVar1);
  return iVar1;
}



/* FUNCTION Net_RegOffLinePayRecord ENTRY 1002bea0 */

undefined4 Net_RegOffLinePayRecord(undefined4 param_1,int param_2,undefined4 param_3)

{
  void *_ArgList;
  HANDLE hObject;
  undefined4 uVar1;
  int iVar2;
  int iVar3;
  byte *pbVar4;
  byte *pbVar5;
  bool bVar6;
  bool bVar7;
  
                    /* 0x2bea0  351  Net_RegOffLinePayRecord */
  if (param_2 == 0) {
    uVar1 = 0;
  }
  else {
    _ArgList = (void *)FUN_100255c0();
    if (_ArgList == (void *)0x0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLinePayRecord",0);
      return 0;
    }
    *(int *)((int)_ArgList + 0x88) = param_2;
    *(undefined4 *)((int)_ArgList + 0x8c) = param_3;
    iVar2 = 6;
    bVar6 = false;
    iVar3 = 0;
    bVar7 = true;
    pbVar4 = (byte *)((int)_ArgList + 0x319139);
    pbVar5 = &DAT_1004015c;
    do {
      if (iVar2 == 0) break;
      iVar2 = iVar2 + -1;
      bVar6 = *pbVar4 < *pbVar5;
      bVar7 = *pbVar4 == *pbVar5;
      pbVar4 = pbVar4 + 1;
      pbVar5 = pbVar5 + 1;
    } while (bVar7);
    if (!bVar7) {
      iVar3 = (1 - (uint)bVar6) - (uint)(bVar6 != 0);
    }
    if (iVar3 < 0) {
      uVar1 = FUN_1002f880();
    }
    else {
      hObject = (HANDLE)_beginthreadex((void *)0x0,0,FUN_1002bd70,_ArgList,0,(uint *)0x0);
      CloseHandle(hObject);
      uVar1 = 0;
    }
  }
  Log("%s eCode=%d\n","Net_RegOffLinePayRecord",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegReportMessEx ENTRY 1002c130 */

undefined4 Net_RegReportMessEx(uint param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x2c130  352  Net_RegReportMessEx */
  uVar2 = 0;
  if (param_2 == 0) {
    return 6;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x31927c;
    if ((&DAT_1004e500)[iVar1] != '\0') {
      *(int *)(&DAT_1004e580 + iVar1) = param_2;
      *(undefined4 *)(&DAT_1004e584 + iVar1) = param_3;
      return 0;
    }
    uVar2 = 4;
    Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConnEx",param_1,4);
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegReportMessEx",uVar2);
  return uVar2;
}



/* FUNCTION Net_SetSynTimePeriod ENTRY 1002c250 */

undefined4 Net_SetSynTimePeriod(undefined2 param_1)

{
                    /* 0x2c250  418  Net_SetSynTimePeriod */
  DAT_1004dc3c = param_1;
  return 0;
}



/* FUNCTION Net_TransRS485HexDataEx ENTRY 1002dc10 */

void Net_TransRS485HexDataEx(undefined4 param_1,undefined4 param_2,int param_3,int param_4)

{
  int iVar1;
  undefined4 uVar2;
  int iVar3;
  char *pcVar4;
  int iVar5;
  undefined3 local_414;
  undefined4 local_410;
  undefined1 local_40c [4];
  int local_408;
  undefined1 local_404 [1024];
  uint local_4;
  
                    /* 0x2dc10  458  Net_TransRS485HexDataEx */
  local_4 = DAT_10047000 ^ (uint)&local_414;
  iVar5 = 0;
  local_410 = 0;
  local_414 = 0;
  local_404[0] = 0;
  memset(local_404 + 1,0,0x3ff);
  iVar3 = 0;
  if (param_3 == 0) {
    Log("%s parameter invalid\n","Net_TransRS485HexDataEx");
  }
  else {
    local_408 = FUN_100255c0();
    if (local_408 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_TransRS485HexDataEx",local_410);
    }
    else {
      if (0 < param_4) {
        pcVar4 = (char *)(param_3 + 2);
        do {
          if (0xbff < iVar5) break;
          if ((*pcVar4 != '\0') && (*pcVar4 != ' ')) {
            Log("%s DCMValidCtrlConn fail, pRs485Data[2]!=0 && pRs485Data[2]!=\' \'\n",
                "Net_TransRS485HexDataEx");
            goto LAB_1002dd48;
          }
          local_414 = CONCAT12(local_414._2_1_,*(undefined2 *)(pcVar4 + -2));
          iVar1 = sscanf((char *)&local_414,"%x",local_40c);
          if (iVar1 != 1) {
            Log("%s DCMValidCtrlConn fail, 1 != sscanf(strHex, %x, &uc)\n","Net_TransRS485HexDataEx"
               );
            goto LAB_1002dd48;
          }
          local_404[iVar3] = local_40c[0];
          iVar5 = iVar5 + 3;
          iVar3 = iVar3 + 1;
          pcVar4 = pcVar4 + 3;
        } while (iVar5 < param_4);
      }
      uVar2 = FUN_1000df70(param_2);
      Log("%s eCode=%d\n","Net_TransRS485HexDataEx",uVar2);
    }
  }
LAB_1002dd48:
  FUN_10037e16();
  return;
}



/* FUNCTION Net_RegOffLineClient ENTRY 1002f430 */

undefined4 Net_RegOffLineClient(undefined4 param_1)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x2f430  348  Net_RegOffLineClient */
  iVar1 = FUN_100255c0();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLineClient",0);
    return 0;
  }
  uVar2 = FUN_10012e00();
  *(undefined1 *)(iVar1 + 0x319138) = 1;
  Log("%s:tHandle=%d, eCode=%d\n","Net_RegOffLineClient",param_1,uVar2);
  return uVar2;
}



/* FUNCTION _Net_RegOffLineClientEx@8 ENTRY 1002f4b0 */

int _Net_RegOffLineClientEx_8(undefined4 param_1,char *param_2)

{
  int iVar1;
  int iVar2;
  
                    /* 0x2f4b0  349  _Net_RegOffLineClientEx@8 */
  if ((param_2 == (char *)0x0) && (1 < bRam00000000)) {
    Log("%s parameter invalid\n","Net_RegOffLineClientEx");
    return 6;
  }
  iVar1 = FUN_100255c0();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLineClientEx",0);
    return 0;
  }
  if ((*param_2 == '\0') && (*(char *)(iVar1 + 0x319138) == '\x01')) {
    iVar2 = FUN_10012e70(param_2);
    if (iVar2 == 0) {
      *(undefined1 *)(iVar1 + 0x319138) = 0;
    }
  }
  else if ((*param_2 == '\x01') && (*(char *)(iVar1 + 0x319138) == '\0')) {
    iVar2 = FUN_10012e00();
    if (iVar2 == 0) {
      *(undefined1 *)(iVar1 + 0x319138) = 1;
    }
  }
  else {
    iVar2 = 0;
  }
  Log("%s:tHandle=%d,ucRegState=%d, eCode=%d\n","Net_RegOffLineClientEx",param_1,*param_2,iVar2);
  return iVar2;
}



/* FUNCTION Net_SetPushTargetSetup ENTRY 10032db0 */

undefined4 Net_SetPushTargetSetup(void)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x32db0  411  Net_SetPushTargetSetup */
  iVar1 = FUN_100255c0();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SetPushTargetSetup",0);
    return 0;
  }
  uVar2 = FUN_10017f10(iVar1 + 0x18);
  return uVar2;
}


