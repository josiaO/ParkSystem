
/* FUNCTION Net_UNinit ENTRY 1001afe0 */

void Net_UNinit(void)

{
  int iVar1;
  int *piVar2;
  
                    /* 0x1afe0  301  Net_UNinit */
  if (DAT_10034d14 == 0) {
    Log("%s SDK not Init\n","Net_UNinit");
    return;
  }
  piVar2 = &DAT_10034ddc;
  iVar1 = 0x20;
  do {
    if (piVar2 == (int *)0x5c) {
      Log("%s invalid parameter\n","DCReleaseManageItem");
    }
    else if ((char)piVar2[-0x17] != '\0') {
      FUN_1001a1f0();
      if (*piVar2 != 0) {
        OSAL_MemFree(0,*piVar2,0);
        *piVar2 = 0;
      }
      *(undefined1 *)(piVar2 + -0x17) = 0;
    }
    OSAL_DestroyMutex(piVar2 + -3);
    OSAL_DestroyMutex(piVar2 + -2);
    piVar2 = piVar2 + 0x46499;
    iVar1 = iVar1 + -1;
  } while (iVar1 != 0);
  DAT_10034d14 = 0;
  DeleteCriticalSection((LPCRITICAL_SECTION)&DAT_12359a00);
  Play_UnInit();
  Log(&DAT_1002e0d8,"Net_UNinit");
  return;
}



/* FUNCTION Net_SetRealDataCallBack ENTRY 1001ed90 */

undefined4 Net_SetRealDataCallBack(uint param_1,undefined4 param_2)

{
  undefined4 uVar1;
  
                    /* 0x1ed90  261  Net_SetRealDataCallBack */
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] != '\0')) {
      uVar1 = Play_SetRealDataCallBack
                        (*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264),param_1,param_2);
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_SetRealDataCallBack",param_1);
  return 4;
}



/* FUNCTION Net_GetJpgBuffer ENTRY 1001f030 */

undefined4 Net_GetJpgBuffer(uint param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x1f030  62  Net_GetJpgBuffer */
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] != '\0')) {
      uVar1 = Play_GetJpgBuffer(*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264),param_2,param_3)
      ;
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_GetJpgBuffer",param_1);
  return 4;
}



/* FUNCTION Net_SetRealDataCallBackEx ENTRY 1001edf0 */

undefined4 Net_SetRealDataCallBackEx(uint param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x1edf0  262  Net_SetRealDataCallBackEx */
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] != '\0')) {
      uVar1 = Play_SetRealDataCallBackEx
                        (*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264),param_1,param_2,param_3
                        );
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_SetRealDataCallBackEx",param_1);
  return 4;
}



/* FUNCTION Net_StartVideo ENTRY 1001ed00 */

int Net_StartVideo(uint param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  
                    /* 0x1ed00  285  Net_StartVideo */
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] != '\0')) {
      iVar1 = Play_OpenCamera(*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264),param_2,param_3);
      if (iVar1 == 0) {
        Net_ShowPlateRegion(param_1,1);
      }
      Log("%s:tHandle=%d, StreamType=%d, eCode=%d\n","Net_StartVideo",param_1,param_2,iVar1);
      return iVar1;
    }
  }
  Log("%s: invalid tHandle=%d, eCode=%d\n","Net_StartVideo",param_1,4);
  return 4;
}



/* FUNCTION Net_StopVideo ENTRY 1001f920 */

undefined4 Net_StopVideo(uint param_1)

{
  undefined4 uVar1;
  
                    /* 0x1f920  287  Net_StopVideo */
  Log("%s handle:%d\n","Net_StopVideo",param_1);
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] == '\x01')) {
      uVar1 = Play_CloseCamera(*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264));
      return uVar1;
    }
  }
  Log("%s invalid parameter\n","Net_StopVideo");
  return 6;
}



/* FUNCTION Net_Init ENTRY 1001af00 */

int Net_Init(void)

{
  int iVar1;
  int iVar2;
  
                    /* 0x1af00  79  Net_Init */
  if (DAT_10034d14 == 1) {
    Log("Net_Init already start\n");
    return 3;
  }
  iVar1 = Play_Init();
  if (iVar1 != 0) {
    Log("%s Play_Init fail\n","Net_Init");
    return iVar1;
  }
  memset(&DAT_10034d80,0,0x2324c80);
  iVar2 = 0;
  iVar1 = 0x20;
  do {
    FUN_10019eb0(iVar2);
    iVar2 = iVar2 + 1;
    iVar1 = iVar1 + -1;
  } while (iVar1 != 0);
  DAT_10034d14 = 1;
  InitializeCriticalSection((LPCRITICAL_SECTION)&DAT_12359a00);
  if (DAT_10034d18 == 0) {
    DAT_10034d18 = _beginthreadex((void *)0x0,0,FUN_10019d50,(void *)0x0,0,&DAT_10034d1c);
  }
  Log("%s:SdkVersion=%s, eCode=%d\n","Net_Init","SDK_3.2.2.5 build-1710231600",0);
  return 0;
}



/* FUNCTION Net_GetFrameData ENTRY 1001f2a0 */

undefined4 Net_GetFrameData(uint param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4)

{
  undefined4 uVar1;
  
                    /* 0x1f2a0  60  Net_GetFrameData */
  if (param_1 < 0x20) {
    if ((&DAT_10034d80 + param_1 * 0x119264 != (char *)0x0) &&
       ((&DAT_10034d80)[param_1 * 0x119264] != '\0')) {
      uVar1 = Play_GetFrameData(*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264),param_2,param_3,
                                param_4);
      return uVar1;
    }
  }
  Log("%s invalid handle:%d\n","Net_GetFrameData",param_1);
  return 4;
}



/* FUNCTION Net_FindDevice ENTRY 1001a810 */

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
  
                    /* 0x1a810  50  Net_FindDevice */
  local_4 = DAT_10034000 ^ (uint)local_210;
  local_210 = (undefined1  [4])0x64;
  local_20c = L'\0';
  memset(local_20a,0,0x206);
  DAT_10034d2c = param_1;
  _Memory = malloc(0x9790);
  GetModuleFileNameW(DAT_10034d3c,&local_20c,0x104);
  pwVar2 = wcsrchr(&local_20c,L'\\');
  pwVar2[1] = L'\0';
  puVar6 = (undefined4 *)(local_210 + 2);
  do {
    psVar1 = (short *)((int)puVar6 + 2);
    puVar6 = (undefined4 *)((int)puVar6 + 2);
  } while (*psVar1 != 0);
  puVar5 = &DAT_1002e014;
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
          (*DAT_10034d2c)(pvVar7,param_2);
          iVar4 = iVar4 + 1;
          pvVar7 = (void *)((int)pvVar7 + 0x184);
        } while (iVar4 < (int)local_210);
      }
      if (_Memory != (void *)0x0) {
        free(_Memory);
      }
    }
  }
  FUN_10027126();
  return;
}



/* FUNCTION Net_FindDeviceEx ENTRY 1001a950 */

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
  
                    /* 0x1a950  51  Net_FindDeviceEx */
  local_4 = DAT_10034000 ^ (uint)&local_214;
  local_214 = param_1;
  local_210 = (undefined1  [4])param_2;
  local_20c = L'\0';
  memset(local_20a,0,0x206);
  GetModuleFileNameW(DAT_10034d3c,&local_20c,0x104);
  pwVar2 = wcsrchr(&local_20c,L'\\');
  pwVar2[1] = L'\0';
  puVar7 = (undefined4 *)(local_210 + 2);
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar6 = &DAT_1002e014;
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
  FUN_10027126();
  return;
}



/* FUNCTION Net_FindDeviceMac ENTRY 1001aa70 */

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
  
                    /* 0x1aa70  53  Net_FindDeviceMac */
  local_4 = DAT_10034000 ^ (uint)&local_228;
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
  DAT_10034d30 = param_1;
  _Memory = malloc(0x9790);
  local_224 = _Memory;
  GetModuleFileNameW(DAT_10034d3c,(LPWSTR)((int)&uStack_20e + 2),0x104);
  pwVar2 = wcsrchr((wchar_t *)((int)&uStack_20e + 2),L'\\');
  pwVar2[1] = L'\0';
  puVar7 = &uStack_20e;
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar5 = &DAT_1002e014;
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
          (*DAT_10034d30)(local_220,param_2);
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
  FUN_10027126();
  return;
}



/* FUNCTION Net_FindDeviceIp ENTRY 1001ac30 */

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
  
                    /* 0x1ac30  52  Net_FindDeviceIp */
  local_4 = DAT_10034000 ^ (uint)&local_228;
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
  DAT_10034d34 = param_1;
  _Memory = malloc(0x9790);
  local_224 = _Memory;
  GetModuleFileNameW(DAT_10034d3c,(LPWSTR)((int)&uStack_20e + 2),0x104);
  pwVar3 = wcsrchr((wchar_t *)((int)&uStack_20e + 2),L'\\');
  pwVar3[1] = L'\0';
  puVar7 = &uStack_20e;
  do {
    psVar1 = (short *)((int)puVar7 + 2);
    puVar7 = (undefined4 *)((int)puVar7 + 2);
  } while (*psVar1 != 0);
  puVar6 = &DAT_1002e014;
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
          (*DAT_10034d34)(local_220,param_2);
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
  FUN_10027126();
  return;
}



/* FUNCTION Net_AddCamera ENTRY 1001b0b0 */

int Net_AddCamera(char *param_1)

{
  int iVar1;
  int iVar2;
  undefined *puVar3;
  
                    /* 0x1b0b0  3  Net_AddCamera */
  iVar1 = Play_AddCamera(param_1);
  if (iVar1 == -1) {
    Log("%s: Play_AddCamera %s fail, niHandle=%d\n","Net_AddCamera",param_1,0xffffffff);
    return -1;
  }
  iVar2 = FUN_1001a0d0();
  if (iVar2 == 0) {
    iVar1 = -1;
    Log("%s DCAllocManageItem fail\n","Net_AddCamera");
    puVar3 = &DAT_1002c5b0;
  }
  else {
    *(int *)(iVar2 + 0x119260) = iVar1;
    iVar1 = *(int *)(iVar2 + 4);
    strncpy((char *)(iVar2 + 8),param_1,0x10);
    if (iVar1 == -1) {
      puVar3 = &DAT_1002c5b0;
    }
    else {
      puVar3 = &DAT_1002c5ac;
    }
  }
  Log("%s:ip=%s %s, niHandle=%d\n","Net_AddCamera",param_1,puVar3,iVar1);
  return iVar1;
}



/* FUNCTION Net_DelCamera ENTRY 1001b200 */

int Net_DelCamera(uint param_1)

{
  int iVar1;
  
                    /* 0x1b200  22  Net_DelCamera */
  if (0x1f < param_1) {
    Log("%s: invalid tHandle=%d, eCode=%d\n","Net_DelCamera",param_1,1);
    return 1;
  }
  iVar1 = Play_DelCamera(*(undefined4 *)(&DAT_1014dfe0 + param_1 * 0x119264));
  if (iVar1 != 0) {
    Log("%s Play_DelCamera fail, eCode=%d\n","Net_DelCamera",iVar1);
    return iVar1;
  }
  if ((&DAT_10034d80)[param_1 * 0x119264] != '\0') {
    FUN_1001a1f0();
    if ((&DAT_10034ddc)[param_1 * 0x46499] != 0) {
      OSAL_MemFree(0,(&DAT_10034ddc)[param_1 * 0x46499],0);
      (&DAT_10034ddc)[param_1 * 0x46499] = 0;
    }
    (&DAT_10034d80)[param_1 * 0x119264] = '\0';
  }
  Log("%s:tHandle=%d, eCode=%d\n","Net_DelCamera",param_1,0);
  return 0;
}



/* FUNCTION Net_ConnCamera ENTRY 1001b2c0 */

void Net_ConnCamera(uint param_1,uint param_2,uint param_3)

{
  int iVar1;
  int iVar2;
  undefined *puVar3;
  int iVar4;
  char *pcVar5;
  undefined1 auStack_244 [4];
  int local_240;
  undefined4 local_23c;
  undefined4 local_238;
  undefined4 local_234;
  undefined4 local_230;
  undefined4 local_22c;
  undefined4 local_228;
  undefined4 local_224;
  undefined4 local_220;
  undefined4 local_21c;
  undefined1 local_218 [128];
  undefined1 local_198 [80];
  undefined1 local_148 [48];
  undefined1 local_118 [268];
  uint local_c;
  
                    /* 0x1b2c0  18  Net_ConnCamera */
  local_c = DAT_10034000 ^ (uint)auStack_244;
  iVar4 = 0;
  pcVar5 = (char *)0x0;
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    pcVar5 = &DAT_10034d80 + param_1 * 0x119264;
  }
  strncpy(pcVar5 + 0x1190ac,pcVar5 + 8,0x20);
  local_240 = 0;
  do {
    local_240 = local_240 + 1;
    if (*pcVar5 != '\0') {
      if (pcVar5[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCamera",pcVar5 + 8);
        iVar4 = 3;
        goto LAB_1001b4e5;
      }
      iVar2 = FUN_10002660(param_2,param_3);
      if (iVar2 == -2) {
        Log("%s DCCConn Beyond MAX Client Num  fail\n","Net_ConnCamera");
        iVar4 = 0xd;
        goto LAB_1001b589;
      }
      if (iVar2 == -3) {
        Log("[redacted]","[redacted]");
        iVar4 = 0x12;
        goto LAB_1001b4e5;
      }
      if (iVar2 == -1) {
        Log("%s DCCConn fail\n","Net_ConnCamera");
        iVar4 = 2;
        goto LAB_1001b4e5;
      }
      iVar1 = FUN_10002270(iVar2);
      if (iVar1 == -1) {
        DCClose(iVar2);
        iVar4 = 2;
        Log("%s DCCDevPortNego fail\n","Net_ConnCamera");
        goto LAB_1001b4e5;
      }
      if (iVar4 == 0xd) goto LAB_1001b589;
      if (iVar4 != 0) goto LAB_1001b4e5;
      pcVar5[1] = '\x02';
      *(int *)(pcVar5 + 0x28) = iVar1;
      *(int *)(pcVar5 + 0x20) = iVar2;
      pcVar5[0x18] = '\x01';
      pcVar5[0x24] = '\x02';
      pcVar5[0x30] = '\0';
      pcVar5[0x31] = '\0';
      pcVar5[0x32] = '\0';
      pcVar5[0x33] = '\0';
      pcVar5[0x34] = '\0';
      pcVar5[0x35] = '\0';
      pcVar5[0x36] = '\0';
      pcVar5[0x37] = '\0';
      pcVar5[0x48] = '\0';
      pcVar5[0x49] = '\0';
      pcVar5[0x4a] = '\0';
      pcVar5[0x4b] = '\0';
      iVar4 = -1;
      local_23c = 0;
      local_238 = 0;
      local_234 = 0;
      local_230 = 0;
      local_22c = 0;
      local_228 = 0;
      local_224 = 0;
      local_220 = 0;
      local_21c = 0;
      iVar2 = CommQue_Create(8,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b4e5;
      *(int *)(pcVar5 + 0x3c) = iVar2;
      iVar2 = CommQue_Create(8,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b4e5;
      *(int *)(pcVar5 + 0x40) = iVar2;
      iVar2 = CommQue_Create(10,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b4e5;
      *(int *)(pcVar5 + 0x44) = iVar2;
      iVar2 = TSK_create(FUN_1000a030,&local_23c,pcVar5);
      if (iVar2 == 0) goto LAB_1001b4e5;
      *(int *)(pcVar5 + 0x38) = iVar2;
      iVar2 = TSK_create(FUN_1000a870,&local_23c,pcVar5);
      if (iVar2 == 0) goto LAB_1001b4e5;
      *(int *)(pcVar5 + 0x4c) = iVar2;
      iVar4 = 0;
LAB_1001b523:
      Net_RegOffLineClient(param_1);
      memset(local_218,0,0x204);
      iVar2 = Net_QuerySysVersion(param_1,local_218);
      if (iVar2 == 0) {
        Log("AppVersion: %s \n",local_198);
        Log("ProtocolVersion: %s \n",local_148);
        Log("HardwareVersion: %s \n",local_118);
      }
      break;
    }
    Log("%s handle not enable\n","Net_ConnCamera");
    iVar4 = 4;
LAB_1001b4e5:
    Net_DisConnCamera(*(undefined4 *)(pcVar5 + 4));
    if (iVar4 == 0) goto LAB_1001b523;
  } while (local_240 < 2);
  if (iVar4 == 0) {
    puVar3 = &DAT_1002c5ac;
  }
  else {
LAB_1001b589:
    Net_DisConnCamera(*(undefined4 *)(pcVar5 + 4));
    Net_DelCamera(*(undefined4 *)(pcVar5 + 4));
    puVar3 = &DAT_1002c5b0;
  }
  Log("%s:tHandle=%d,Port=%d,Timeout=%d %s, eCode=%d\n","Net_ConnCamera",param_1,param_2 & 0xffff,
      param_3 & 0xffff,puVar3,iVar4);
  FUN_10027126();
  return;
}



/* FUNCTION Net_ConnCamera2 ENTRY 1001b5f0 */

void Net_ConnCamera2(uint param_1,uint param_2,uint param_3)

{
  int iVar1;
  int iVar2;
  undefined *puVar3;
  int iVar4;
  char *pcVar5;
  undefined1 auStack_244 [4];
  int local_240;
  undefined4 local_23c;
  undefined4 local_238;
  undefined4 local_234;
  undefined4 local_230;
  undefined4 local_22c;
  undefined4 local_228;
  undefined4 local_224;
  undefined4 local_220;
  undefined4 local_21c;
  undefined1 local_218 [128];
  undefined1 local_198 [80];
  undefined1 local_148 [48];
  undefined1 local_118 [268];
  uint local_c;
  
                    /* 0x1b5f0  17  Net_ConnCamera2 */
  local_c = DAT_10034000 ^ (uint)auStack_244;
  iVar4 = 0;
  pcVar5 = (char *)0x0;
  if ((short)param_2 == 0) {
    param_2 = 30000;
  }
  if ((short)param_3 == 0) {
    param_3 = 3;
  }
  if (param_1 < 0x20) {
    pcVar5 = &DAT_10034d80 + param_1 * 0x119264;
  }
  strncpy(pcVar5 + 0x1190ac,pcVar5 + 8,0x20);
  local_240 = 0;
  do {
    local_240 = local_240 + 1;
    if (*pcVar5 != '\0') {
      if (pcVar5[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCamera2",pcVar5 + 8);
        iVar4 = 3;
        goto LAB_1001b815;
      }
      iVar2 = FUN_10002660(param_2,param_3);
      if (iVar2 == -2) {
        Log("%s DCCConn Beyond MAX Client Num  fail\n","Net_ConnCamera2");
        iVar4 = 0xd;
        goto LAB_1001b8b0;
      }
      if (iVar2 == -3) {
        Log("[redacted]","[redacted]");
        iVar4 = 0x12;
        goto LAB_1001b815;
      }
      if (iVar2 == -1) {
        Log("%s DCCConn fail\n","Net_ConnCamera2");
        iVar4 = 2;
        goto LAB_1001b815;
      }
      iVar1 = FUN_10002270(iVar2);
      if (iVar1 == -1) {
        DCClose(iVar2);
        iVar4 = 2;
        Log("%s DCCDevPortNego fail\n","Net_ConnCamera2");
        goto LAB_1001b815;
      }
      if (iVar4 == 0xd) goto LAB_1001b8b0;
      if (iVar4 != 0) goto LAB_1001b815;
      pcVar5[1] = '\x02';
      *(int *)(pcVar5 + 0x28) = iVar1;
      *(int *)(pcVar5 + 0x20) = iVar2;
      pcVar5[0x18] = '\x01';
      pcVar5[0x24] = '\x02';
      pcVar5[0x30] = '\0';
      pcVar5[0x31] = '\0';
      pcVar5[0x32] = '\0';
      pcVar5[0x33] = '\0';
      pcVar5[0x34] = '\0';
      pcVar5[0x35] = '\0';
      pcVar5[0x36] = '\0';
      pcVar5[0x37] = '\0';
      pcVar5[0x48] = '\0';
      pcVar5[0x49] = '\0';
      pcVar5[0x4a] = '\0';
      pcVar5[0x4b] = '\0';
      iVar4 = -1;
      local_23c = 0;
      local_238 = 0;
      local_234 = 0;
      local_230 = 0;
      local_22c = 0;
      local_228 = 0;
      local_224 = 0;
      local_220 = 0;
      local_21c = 0;
      iVar2 = CommQue_Create(8,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b815;
      *(int *)(pcVar5 + 0x3c) = iVar2;
      iVar2 = CommQue_Create(8,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b815;
      *(int *)(pcVar5 + 0x40) = iVar2;
      iVar2 = CommQue_Create(10,0x5a0,0);
      if (iVar2 == 0) goto LAB_1001b815;
      *(int *)(pcVar5 + 0x44) = iVar2;
      iVar2 = TSK_create(FUN_1000a030,&local_23c,pcVar5);
      if (iVar2 == 0) goto LAB_1001b815;
      *(int *)(pcVar5 + 0x38) = iVar2;
      iVar2 = TSK_create(FUN_1000a870,&local_23c,pcVar5);
      if (iVar2 == 0) goto LAB_1001b815;
      *(int *)(pcVar5 + 0x4c) = iVar2;
      iVar4 = 0;
LAB_1001b850:
      memset(local_218,0,0x204);
      iVar2 = Net_QuerySysVersion(param_1,local_218);
      if (iVar2 == 0) {
        Log("AppVersion: %s \n",local_198);
        Log("ProtocolVersion: %s \n",local_148);
        Log("HardwareVersion: %s \n",local_118);
      }
      break;
    }
    Log("%s handle not enable\n","Net_ConnCamera2");
    iVar4 = 4;
LAB_1001b815:
    Net_DisConnCamera(*(undefined4 *)(pcVar5 + 4));
    if (iVar4 == 0) goto LAB_1001b850;
  } while (local_240 < 2);
  if (iVar4 == 0) {
    puVar3 = &DAT_1002c5ac;
  }
  else {
LAB_1001b8b0:
    Net_DisConnCamera(*(undefined4 *)(pcVar5 + 4));
    Net_DelCamera(*(undefined4 *)(pcVar5 + 4));
    puVar3 = &DAT_1002c5b0;
  }
  Log("%s:tHandle=%d,Port=%d,Timeout=%d %s, eCode=%d\n","Net_ConnCamera2",param_1,param_2 & 0xffff,
      param_3 & 0xffff,puVar3,iVar4);
  FUN_10027126();
  return;
}



/* FUNCTION Net_ConnCameraEx ENTRY 1001b910 */

void Net_ConnCameraEx(uint param_1,uint param_2,uint param_3,char *param_4,char *param_5)

{
  char *pcVar1;
  undefined4 uVar2;
  int iVar3;
  undefined *puVar4;
  int iVar5;
  char *pcVar6;
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
  undefined1 local_218 [128];
  undefined1 local_198 [80];
  undefined1 local_148 [48];
  undefined1 local_118 [268];
  uint local_c;
  
                    /* 0x1b910  20  Net_ConnCameraEx */
  local_c = DAT_10034000 ^ (uint)&local_29c;
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
    local_29c = &DAT_10034d80 + param_1 * 0x119264;
  }
  pcVar6 = local_29c;
  strncpy(local_29c + 0x1190ac,local_29c + 8,0x20);
  do {
    local_294 = local_294 + 1;
    if (*pcVar6 != '\0') {
      if (pcVar6[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCameraEx",pcVar6 + 8);
        iVar5 = 3;
        goto LAB_1001bd26;
      }
      iVar5 = FUN_100027b0(param_2,param_3,param_4,local_290,&local_298);
      uVar2 = local_298;
      if (iVar5 == 0) {
        strncpy(local_29c + 0x1190cc,local_260,0x20);
        strncpy(local_29c + 0x1190ec,local_240,0x24);
LAB_1001bafe:
        local_28c = FUN_10002270(uVar2);
        if (local_28c == -1) {
          DCClose(uVar2);
          local_298 = 0xffffffff;
          iVar5 = 1000;
          Log("%s DCCDevPortNego fail\n","Net_ConnCameraEx");
          goto LAB_1001bd26;
        }
      }
      else if (iVar5 == 6) goto LAB_1001bafe;
      if (iVar5 == 0xd) goto LAB_1001bcbb;
      if ((iVar5 == 0) || (iVar5 == 6)) {
        local_29c[1] = '\x02';
        *(int *)(pcVar6 + 0x28) = local_28c;
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
        *(short *)(pcVar6 + 0x1c) = (short)param_2;
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
          iVar5 = 0x3e9;
        }
        else {
          *(int *)(pcVar6 + 0x3c) = iVar3;
          iVar3 = CommQue_Create(8,0x5a0,0);
          if (iVar3 == 0) {
            iVar5 = 0x3ea;
          }
          else {
            *(int *)(pcVar6 + 0x40) = iVar3;
            iVar3 = CommQue_Create(10,0x5a0,0);
            pcVar1 = local_29c;
            if (iVar3 == 0) {
              iVar5 = 0x3eb;
            }
            else {
              *(int *)(pcVar6 + 0x44) = iVar3;
              iVar3 = TSK_create(FUN_1000a030,&local_284,local_29c);
              if (iVar3 == 0) {
                iVar5 = 0x3ec;
              }
              else {
                *(int *)(pcVar6 + 0x38) = iVar3;
                iVar3 = TSK_create(FUN_1000a870,&local_284,pcVar1);
                if (iVar3 == 0) {
                  iVar5 = 0x3ed;
                }
                else {
                  *(int *)(pcVar6 + 0x4c) = iVar3;
                  if (iVar5 != 6) goto LAB_1001bd1e;
                  iVar5 = FUN_10012670(pcVar6 + 0x18);
                  Log("%s DCCUserLoginSetup eCode=%d\n","Net_ConnCameraEx",iVar5);
                  if (iVar5 == 0) {
                    strncpy(pcVar1 + 0x1190cc,local_260,0x20);
                    strncpy(pcVar1 + 0x1190ec,local_240,0x24);
                    goto LAB_1001bc51;
                  }
                }
              }
            }
          }
        }
        goto LAB_1001bd26;
      }
LAB_1001bd1e:
      if (iVar5 != 0) goto LAB_1001bd26;
LAB_1001bc51:
      memset(local_218,0,0x204);
      iVar3 = Net_QuerySysVersion(param_1,local_218);
      if (iVar3 == 0) {
        Log("AppVersion: %s \n",local_198);
        Log("ProtocolVersion: %s \n",local_148);
        Log("HardwareVersion: %s \n",local_118);
      }
      break;
    }
    Log("%s handle not enable\n","Net_ConnCameraEx");
    iVar5 = 4;
LAB_1001bd26:
    pcVar6 = local_29c;
    Net_DisConnCamera(*(undefined4 *)(local_29c + 4));
    if (iVar5 == 0) goto LAB_1001bc51;
    param_4 = local_288;
  } while (local_294 < 2);
  if (iVar5 == 0) {
    puVar4 = &DAT_1002c5ac;
  }
  else {
LAB_1001bcbb:
    pcVar6 = local_29c;
    Net_DisConnCamera(*(undefined4 *)(local_29c + 4));
    Net_DelCamera(*(undefined4 *)(pcVar6 + 4));
    puVar4 = &DAT_1002c5b0;
  }
  Log("[redacted]","[redacted]",
      param_1,param_2 & 0xffff,param_3 & 0xffff,local_288,local_290,puVar4,iVar5);
  FUN_10027126();
  return;
}



/* FUNCTION Net_ConnCameraEtcp ENTRY 1001bd60 */

void Net_ConnCameraEtcp(uint param_1,uint param_2,uint param_3,char *param_4,char *param_5,
                       byte param_6)

{
  char *pcVar1;
  undefined4 uVar2;
  int iVar3;
  undefined *puVar4;
  int iVar5;
  char *pcVar6;
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
  
                    /* 0x1bd60  19  Net_ConnCameraEtcp */
  local_c = DAT_10034000 ^ (uint)&local_94;
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
    local_94 = &DAT_10034d80 + param_1 * 0x119264;
  }
  pcVar6 = local_94;
  strncpy(local_94 + 0x1190ac,local_94 + 8,0x20);
  do {
    local_8c = local_8c + 1;
    if (*pcVar6 != '\0') {
      if (pcVar6[0x18] != '\0') {
        Log("%s ip:%s already start contrl connect\n","Net_ConnCameraEtcp",pcVar6 + 8);
        iVar5 = 3;
        goto LAB_1001c137;
      }
      iVar5 = FUN_100027b0(param_2,param_3,param_4,local_84,&local_88);
      uVar2 = local_88;
      if (iVar5 == 0) {
        strncpy(local_94 + 0x1190cc,local_58,0x20);
        strncpy(local_94 + 0x1190ec,local_38,0x24);
LAB_1001bf4e:
        local_90 = FUN_10002270(uVar2);
        if (local_90 == 0xffffffff) {
          DCClose(uVar2);
          local_88 = 0xffffffff;
          iVar5 = 1000;
          Log("%s DCCDevPortNego fail\n","Net_ConnCameraEtcp");
          goto LAB_1001c137;
        }
      }
      else if (iVar5 == 6) goto LAB_1001bf4e;
      if (iVar5 == 0xd) goto LAB_1001c0cc;
      if ((iVar5 == 0) || (iVar5 == 6)) {
        local_94[1] = '\x02';
        *(uint *)(pcVar6 + 0x28) = local_90;
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
        *(short *)(pcVar6 + 0x1c) = (short)param_2;
        local_7c = 0;
        local_78 = 0;
        local_74 = 0;
        local_70 = 0;
        local_6c = 0;
        local_68 = 0;
        local_64 = 0;
        local_60 = 0;
        local_5c = 0;
        iVar3 = CommQue_Create(8,0x5a0,0);
        if (iVar3 == 0) {
          iVar5 = 0x3e9;
        }
        else {
          *(int *)(pcVar6 + 0x3c) = iVar3;
          iVar3 = CommQue_Create(8,0x5a0,0);
          if (iVar3 == 0) {
            iVar5 = 0x3ea;
          }
          else {
            *(int *)(pcVar6 + 0x40) = iVar3;
            iVar3 = CommQue_Create(10,0x5a0,0);
            pcVar1 = local_94;
            if (iVar3 == 0) {
              iVar5 = 0x3eb;
            }
            else {
              *(int *)(pcVar6 + 0x44) = iVar3;
              iVar3 = TSK_create(FUN_1000a030,&local_7c,local_94);
              if (iVar3 == 0) {
                iVar5 = 0x3ec;
              }
              else {
                *(int *)(pcVar6 + 0x38) = iVar3;
                iVar3 = TSK_create(FUN_1000a870,&local_7c,pcVar1);
                if (iVar3 == 0) {
                  iVar5 = 0x3ed;
                }
                else {
                  *(int *)(pcVar6 + 0x4c) = iVar3;
                  if (iVar5 != 6) goto LAB_1001c12f;
                  iVar5 = FUN_10012670(pcVar6 + 0x18);
                  Log("%s DCCUserLoginSetup eCode=%d\n","Net_ConnCameraEtcp",iVar5);
                  if (iVar5 == 0) {
                    strncpy(pcVar1 + 0x1190cc,local_58,0x20);
                    strncpy(pcVar1 + 0x1190ec,local_38,0x24);
                    goto LAB_1001c0a1;
                  }
                }
              }
            }
          }
        }
        goto LAB_1001c137;
      }
LAB_1001c12f:
      if (iVar5 != 0) goto LAB_1001c137;
LAB_1001c0a1:
      Net_RegOffLineClient(param_1);
      local_90 = (uint)param_6;
      Net_DetectModeSetup(param_1,&local_90);
      break;
    }
    Log("%s handle not enable\n","Net_ConnCameraEtcp");
    iVar5 = 4;
LAB_1001c137:
    pcVar6 = local_94;
    Net_DisConnCamera(*(undefined4 *)(local_94 + 4));
    if (iVar5 == 0) goto LAB_1001c0a1;
    param_4 = local_80;
  } while (local_8c < 2);
  if (iVar5 == 0) {
    puVar4 = &DAT_1002c5ac;
  }
  else {
LAB_1001c0cc:
    pcVar6 = local_94;
    Net_DisConnCamera(*(undefined4 *)(local_94 + 4));
    Net_DelCamera(*(undefined4 *)(pcVar6 + 4));
    puVar4 = &DAT_1002c5b0;
  }
  Log("[redacted]","[redacted]"
      ,param_1,param_2 & 0xffff,param_3 & 0xffff,local_80,local_84,puVar4,iVar5);
  FUN_10027126();
  return;
}



/* FUNCTION Net_DisConnCamera ENTRY 1001c170 */

undefined4 Net_DisConnCamera(uint param_1)

{
  int iVar1;
  
                    /* 0x1c170  28  Net_DisConnCamera */
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x119264;
    if (&DAT_10034d80 + iVar1 != (char *)0x0) {
      if ((&DAT_10034d80)[iVar1] != '\0') {
        if ((&DAT_10034d81)[iVar1] == '\x02') {
          FUN_100029e0();
          (&DAT_10034d81)[iVar1] = 3;
        }
        FUN_1001a1f0();
      }
      Log("%s:tHandle=%d, eCode=%d\n","Net_DisConnCamera",param_1,0);
      return 0;
    }
  }
  Log("%s invalid handle:%d\n","Net_DisConnCamera",param_1);
  return 6;
}



/* FUNCTION Net_GateSetup ENTRY 1001d610 */

undefined4 Net_GateSetup(undefined4 param_1,undefined1 *param_2)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x1d610  56  Net_GateSetup */
  if (param_2 == (undefined1 *)0x0) {
    Log("%s parameter invalid\n","Net_GateSetup");
    return 6;
  }
  iVar1 = FUN_1001a410();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_GateSetup",0);
    return 0;
  }
  uVar2 = FUN_10008310();
  Log("%s:State=%d, eCode=%d\n","Net_GateSetup",*param_2,uVar2);
  return uVar2;
}



/* FUNCTION Net_QueryConnState ENTRY 1001ea30 */

char Net_QueryConnState(uint param_1)

{
  char cVar1;
  int iVar2;
  
                    /* 0x1ea30  118  Net_QueryConnState */
  if (param_1 < 0x20) {
    iVar2 = param_1 * 0x119264;
    if ((&DAT_10034d80 + iVar2 != (char *)0x0) && ((&DAT_10034d80)[iVar2] != '\0')) {
      if ((&DAT_10034d98)[iVar2] == '\0') {
        return '\f';
      }
      cVar1 = (&DAT_10034d81)[iVar2];
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



/* FUNCTION Net_ImageSnap ENTRY 1001ead0 */

int Net_ImageSnap(uint param_1,int param_2)

{
  int iVar1;
  code *pcVar2;
  char *pcVar3;
  
                    /* 0x1ead0  71  Net_ImageSnap */
  pcVar2 = Log_exref;
  iVar1 = 0;
  if (param_2 == 0) {
    Log("%s parameter invalid\n","Net_ImageSnap");
    iVar1 = 6;
    goto LAB_1001eb8b;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x119264;
    if ((&DAT_10034d80)[iVar1] == '\0') {
      iVar1 = 4;
      Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConn",param_1,4);
      goto LAB_1001eb5d;
    }
    if (((&DAT_10034d98)[iVar1] == '\0') || ((&DAT_10034d81)[iVar1] != '\x02')) {
      Log("%s: connect state not valid, eCode=%d\n","DCMValidCtrlConn",2);
      iVar1 = 2;
      pcVar3 = "%s DCMValidCtrlConn fail, eCode=%d\n";
    }
    else {
      iVar1 = FUN_10009580();
      pcVar2 = Log_exref;
      if (iVar1 == 0) goto LAB_1001eb8b;
      pcVar3 = "%s fail, eCode=%d\n";
    }
  }
  else {
LAB_1001eb5d:
    pcVar3 = "%s DCMValidCtrlConn fail, eCode=%d\n";
  }
  (*pcVar2)(pcVar3,"Net_ImageSnap",iVar1);
LAB_1001eb8b:
  (*pcVar2)("%s eCode=%d\n","Net_ImageSnap",iVar1);
  return iVar1;
}



/* FUNCTION Net_SaveImageToJpeg ENTRY 1001a4e0 */

void Net_SaveImageToJpeg(uint param_1,char *param_2)

{
  int iVar1;
  FILE *_File;
  int iVar2;
  undefined4 uVar3;
  size_t local_74;
  undefined4 local_70;
  void *local_6c;
  int local_68;
  int local_64;
  char *local_60;
  int local_5c;
  undefined1 local_58 [76];
  uint local_c;
  
                    /* 0x1a4e0  228  Net_SaveImageToJpeg */
  local_c = DAT_10034000 ^ (uint)&local_74;
  iVar2 = 0;
  local_60 = param_2;
  local_74 = 0;
  local_5c = 0;
  if (param_2 == (char *)0x0) {
    FUN_10027126();
    return;
  }
  iVar1 = FUN_1001a410();
  local_64 = iVar1;
  if (iVar1 != 0) {
    local_74 = 0;
    local_70 = 0;
    if ((param_1 < 0x20) && (param_1 * 0x119264 != -0x10034d80)) {
      *(undefined4 *)(&DAT_10034dac + param_1 * 0x119264) = 0;
    }
    else {
      iVar2 = 4;
    }
    Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar2);
    if ((iVar2 == 0) && (iVar2 = Net_ImageSnap(param_1,&local_74), iVar2 == 0)) {
      local_74 = 0x100000;
      local_70 = 0x19000;
      local_6c = (void *)(iVar1 + 0xac);
      local_68 = iVar1 + 0x1000ac;
      iVar2 = Net_GetImage(param_1,0,local_58,&local_74);
      while ((iVar2 != 0 && (local_5c = local_5c + 1, local_5c < 0x29))) {
        Sleep(0x32);
        local_74 = 0x100000;
        local_70 = 0x19000;
        local_6c = (void *)(iVar1 + 0xac);
        local_68 = iVar1 + 0x1000ac;
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
    if ((param_1 < 0x20) && (param_1 * 0x119264 != -0x10034d80)) {
      *(undefined4 *)(&DAT_10034dac + param_1 * 0x119264) = 1;
    }
    else {
      uVar3 = 4;
    }
    Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,1,uVar3);
    memset((void *)(iVar1 + 0xac),0,0x100000);
    memset((void *)(iVar1 + 0x1000ac),0,0x19000);
    Log("%s:tHandle=%d, PathNmme=%s, eCode=%d\n","Net_SaveImageToJpeg",param_1,local_60,uVar3);
    FUN_10027126();
    return;
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SaveImageToJpeg",local_74);
  FUN_10027126();
  return;
}



/* FUNCTION Net_GetJpgBufferEx ENTRY 1001f090 */

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
  
                    /* 0x1f090  63  Net_GetJpgBufferEx */
  local_c = DAT_10034000 ^ (uint)auStack_7c;
  iVar2 = 0;
  local_5c = param_2;
  local_64 = param_3;
  local_78 = 0;
  local_68 = 0;
  if (param_3 != (size_t *)0x0) {
    iVar1 = FUN_1001a410();
    local_60 = iVar1;
    if (iVar1 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_GetJpgBufferEx",local_78);
    }
    else {
      local_78 = 0;
      local_74 = 0;
      if ((param_1 < 0x20) && (param_1 * 0x119264 != -0x10034d80)) {
        *(undefined4 *)(&DAT_10034dac + param_1 * 0x119264) = 0;
      }
      else {
        iVar2 = 4;
      }
      Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,0,iVar2);
      if ((iVar2 == 0) && (iVar2 = Net_ImageSnap(param_1,&local_78), iVar2 == 0)) {
        local_78 = 0x100000;
        local_74 = 0x19000;
        local_70 = (void *)(iVar1 + 0xac);
        local_6c = iVar1 + 0x1000ac;
        iVar2 = Net_GetImage(param_1,0,local_58,&local_78);
        _Size = local_78;
        while ((local_78 = _Size, iVar2 != 0 && (local_68 = local_68 + 1, local_68 < 0x29))) {
          Sleep(0x32);
          local_78 = 0x100000;
          local_74 = 0x19000;
          local_70 = (void *)(iVar1 + 0xac);
          local_6c = iVar1 + 0x1000ac;
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
      if ((param_1 < 0x20) && (param_1 * 0x119264 != -0x10034d80)) {
        *(undefined4 *)(&DAT_10034dac + param_1 * 0x119264) = 1;
      }
      else {
        uVar3 = 4;
      }
      Log("%s:tHandle=%d, SnapMode=%d, eCode=%d\n","Net_SetSnapMode",param_1,1,uVar3);
      memset((void *)(iVar1 + 0xac),0,0x100000);
      memset((void *)(iVar1 + 0x1000ac),0,0x19000);
    }
    FUN_10027126();
    return;
  }
  FUN_10027126();
  return;
}



/* FUNCTION Net_RegImageRecv ENTRY 1001f9d0 */

undefined4 Net_RegImageRecv(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x1f9d0  214  Net_RegImageRecv */
  uVar1 = 0;
  if (param_1 == 0) {
    uVar1 = 6;
  }
  else {
    DAT_10034d20 = param_1;
  }
  Log("%s eCode=%d\n","Net_RegImageRecv",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegImageRecv2 ENTRY 1001fa10 */

undefined4 Net_RegImageRecv2(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x1fa10  213  Net_RegImageRecv2 */
  uVar1 = 0;
  if (param_1 == 0) {
    uVar1 = 6;
  }
  else {
    DAT_10034d24 = param_1;
  }
  Log("%s eCode=%d\n","Net_RegImageRecv2",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegImageRecvEx ENTRY 1001fa50 */

undefined4 Net_RegImageRecvEx(undefined4 param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x1fa50  215  Net_RegImageRecvEx */
  if (param_2 == 0) {
    uVar2 = 6;
  }
  else {
    iVar1 = FUN_1001a410();
    if (iVar1 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegImageRecvEx",0);
      return 0;
    }
    *(int *)(iVar1 + 0x60) = param_2;
    uVar2 = 0;
    *(undefined4 *)(iVar1 + 100) = param_3;
  }
  Log("%s eCode=%d\n","Net_RegImageRecvEx",uVar2);
  return uVar2;
}



/* FUNCTION Net_RegOffLineImageRecvEx ENTRY 1001fad0 */

int Net_RegOffLineImageRecvEx(undefined4 param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined *puVar2;
  code *pcVar3;
  char *pcVar4;
  
                    /* 0x1fad0  217  Net_RegOffLineImageRecvEx */
  if (param_2 == 0) {
    iVar1 = FUN_1001a410();
    pcVar3 = Log_exref;
    if (iVar1 == 0) {
      iVar1 = 0;
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_StopGetOffLineData",0);
    }
    else {
      iVar1 = FUN_10011570();
    }
    puVar2 = &DAT_1002c5ac;
    if (iVar1 != 0) {
      puVar2 = &DAT_1002c5b0;
    }
    pcVar4 = "%s Net_StopGetOffLineData %s, eCode=%d\n";
  }
  else {
    iVar1 = FUN_1001a410();
    if (iVar1 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLineImageRecvEx",0);
      return 0;
    }
    *(int *)(iVar1 + 0x68) = param_2;
    *(undefined4 *)(iVar1 + 0x6c) = param_3;
    iVar1 = FUN_10022f40(param_1);
    puVar2 = &DAT_1002c5ac;
    if (iVar1 != 0) {
      puVar2 = &DAT_1002c5b0;
    }
    pcVar4 = "%s Net_StartGetOffLineData %s, eCode=%d\n";
    pcVar3 = Log_exref;
  }
  (*pcVar3)(pcVar4,"Net_RegOffLineImageRecvEx",puVar2,iVar1);
  (*pcVar3)("%s eCode=%d\n","Net_RegOffLineImageRecvEx",iVar1);
  return iVar1;
}



/* FUNCTION Net_RegOffLinePayRecord ENTRY 1001fd00 */

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
  
                    /* 0x1fd00  218  Net_RegOffLinePayRecord */
  if (param_2 == 0) {
    uVar1 = 0;
  }
  else {
    _ArgList = (void *)FUN_1001a410();
    if (_ArgList == (void *)0x0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLinePayRecord",0);
      return 0;
    }
    *(int *)((int)_ArgList + 0x80) = param_2;
    *(undefined4 *)((int)_ArgList + 0x84) = param_3;
    iVar2 = 6;
    bVar6 = false;
    iVar3 = 0;
    bVar7 = true;
    pbVar4 = (byte *)((int)_ArgList + 0x119131);
    pbVar5 = &DAT_1002efac;
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
      uVar1 = FUN_100230f0();
    }
    else {
      hObject = (HANDLE)_beginthreadex((void *)0x0,0,FUN_1001fbd0,_ArgList,0,(uint *)0x0);
      CloseHandle(hObject);
      uVar1 = 0;
    }
  }
  Log("%s eCode=%d\n","Net_RegOffLinePayRecord",uVar1);
  return uVar1;
}



/* FUNCTION Net_RegReportMessEx ENTRY 1001ff90 */

undefined4 Net_RegReportMessEx(uint param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x1ff90  219  Net_RegReportMessEx */
  uVar2 = 0;
  if (param_2 == 0) {
    return 6;
  }
  if (param_1 < 0x20) {
    iVar1 = param_1 * 0x119264;
    if ((&DAT_10034d80)[iVar1] != '\0') {
      *(int *)(&DAT_10034df8 + iVar1) = param_2;
      *(undefined4 *)(&DAT_10034dfc + iVar1) = param_3;
      return 0;
    }
    uVar2 = 4;
    Log("%s: handle=%d not enable, eCode=%d\n","DCMValidCtrlConnEx",param_1,4);
  }
  Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegReportMessEx",uVar2);
  return uVar2;
}



/* FUNCTION Net_SetSynTimePeriod ENTRY 10020090 */

undefined4 Net_SetSynTimePeriod(undefined2 param_1)

{
                    /* 0x20090  267  Net_SetSynTimePeriod */
  DAT_10034d38 = param_1;
  return 0;
}



/* FUNCTION Net_TransRS485HexDataEx ENTRY 10021890 */

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
  
                    /* 0x21890  296  Net_TransRS485HexDataEx */
  local_4 = DAT_10034000 ^ (uint)&local_414;
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
    local_408 = FUN_1001a410();
    if (local_408 == 0) {
      Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_TransRS485HexDataEx",local_410);
    }
    else {
      if (0 < param_4) {
        pcVar4 = (char *)(param_3 + 2);
        do {
          if (0xbff < iVar5) break;
          if ((*pcVar4 != '\0') && (*pcVar4 != ' ')) goto LAB_100219c4;
          local_414 = CONCAT12(local_414._2_1_,*(undefined2 *)(pcVar4 + -2));
          iVar1 = sscanf((char *)&local_414,"%x",local_40c);
          if (iVar1 != 1) goto LAB_100219c4;
          local_404[iVar3] = local_40c[0];
          iVar5 = iVar5 + 3;
          iVar3 = iVar3 + 1;
          pcVar4 = pcVar4 + 3;
        } while (iVar5 < param_4);
      }
      uVar2 = FUN_1000cae0(param_2);
      Log("%s eCode=%d\n","Net_TransRS485HexDataEx",uVar2);
    }
  }
LAB_100219c4:
  FUN_10027126();
  return;
}



/* FUNCTION Net_RegOffLineClient ENTRY 10022d90 */

undefined4 Net_RegOffLineClient(undefined4 param_1)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x22d90  216  Net_RegOffLineClient */
  iVar1 = FUN_1001a410();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_RegOffLineClient",0);
    return 0;
  }
  uVar2 = FUN_10011220();
  *(undefined1 *)(iVar1 + 0x119130) = 1;
  Log("%s:tHandle=%d, eCode=%d\n","Net_RegOffLineClient",param_1,uVar2);
  return uVar2;
}



/* FUNCTION Net_SetPushTargetSetup ENTRY 10025fc0 */

undefined4 Net_SetPushTargetSetup(void)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x25fc0  260  Net_SetPushTargetSetup */
  iVar1 = FUN_1001a410();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SetPushTargetSetup",0);
    return 0;
  }
  uVar2 = FUN_10015ce0(iVar1 + 0x18);
  return uVar2;
}



/* FUNCTION Net_SetHttpPushSetup ENTRY 10026060 */

undefined4 Net_SetHttpPushSetup(void)

{
  int iVar1;
  undefined4 uVar2;
  
                    /* 0x26060  249  Net_SetHttpPushSetup */
  iVar1 = FUN_1001a410();
  if (iVar1 == 0) {
    Log("%s DCMValidCtrlConn fail, eCode=%d\n","Net_SetHttpPushSetup",0);
    return 0;
  }
  uVar2 = FUN_10015ea0(iVar1 + 0x18);
  return uVar2;
}



/* FUNCTION FUN_1001a1f0 ENTRY 1001a1f0 */

void FUN_1001a1f0(void)

{
  int iVar1;
  char *unaff_ESI;
  
  if (*unaff_ESI != '\0') {
    unaff_ESI[0x1c] = '\x01';
    unaff_ESI[0x1d] = '\0';
    unaff_ESI[0x1e] = '\0';
    unaff_ESI[0x1f] = '\0';
    unaff_ESI[0x18] = '\x01';
    unaff_ESI[0x19] = '\0';
    unaff_ESI[0x1a] = '\0';
    unaff_ESI[0x1b] = '\0';
    unaff_ESI[0x30] = '\x01';
    unaff_ESI[0x31] = '\0';
    unaff_ESI[0x32] = '\0';
    unaff_ESI[0x33] = '\0';
    if (*(int *)(unaff_ESI + 0x20) != 0) {
      TSK_delete(*(int *)(unaff_ESI + 0x20));
      unaff_ESI[0x20] = '\0';
      unaff_ESI[0x21] = '\0';
      unaff_ESI[0x22] = '\0';
      unaff_ESI[0x23] = '\0';
    }
    if (*(int *)(unaff_ESI + 0x34) != 0) {
      TSK_delete(*(int *)(unaff_ESI + 0x34));
      unaff_ESI[0x34] = '\0';
      unaff_ESI[0x35] = '\0';
      unaff_ESI[0x36] = '\0';
      unaff_ESI[0x37] = '\0';
    }
    if (*(int *)(unaff_ESI + 0x24) != 0) {
      CommQue_Delete(*(int *)(unaff_ESI + 0x24));
      unaff_ESI[0x24] = '\0';
      unaff_ESI[0x25] = '\0';
      unaff_ESI[0x26] = '\0';
      unaff_ESI[0x27] = '\0';
    }
    if (*(int *)(unaff_ESI + 0x28) != 0) {
      CommQue_Delete(*(int *)(unaff_ESI + 0x28));
      unaff_ESI[0x28] = '\0';
      unaff_ESI[0x29] = '\0';
      unaff_ESI[0x2a] = '\0';
      unaff_ESI[0x2b] = '\0';
    }
    if (*(int *)(unaff_ESI + 0x2c) != 0) {
      CommQue_Delete(*(int *)(unaff_ESI + 0x2c));
      unaff_ESI[0x2c] = '\0';
      unaff_ESI[0x2d] = '\0';
      unaff_ESI[0x2e] = '\0';
      unaff_ESI[0x2f] = '\0';
    }
    DCClose(*(undefined4 *)(unaff_ESI + 0x10));
    unaff_ESI[0x10] = -1;
    unaff_ESI[0x11] = -1;
    unaff_ESI[0x12] = -1;
    unaff_ESI[0x13] = -1;
    DCClose(*(undefined4 *)(unaff_ESI + 8));
    unaff_ESI[8] = -1;
    unaff_ESI[9] = -1;
    unaff_ESI[10] = -1;
    unaff_ESI[0xb] = -1;
    unaff_ESI[0x40] = '\0';
    unaff_ESI[0x41] = '\0';
    unaff_ESI[0x42] = '\0';
    unaff_ESI[0x43] = '\0';
    if (*(int *)(unaff_ESI + 0x44) != 0) {
      iVar1 = 0;
      do {
        *(undefined4 *)(iVar1 + *(int *)(unaff_ESI + 0x44)) = 0;
        *(undefined4 *)(iVar1 + 4 + *(int *)(unaff_ESI + 0x44)) = 0;
        *(undefined4 *)(iVar1 + 8 + *(int *)(unaff_ESI + 0x44)) = 0;
        iVar1 = iVar1 + 0x119010;
      } while (iVar1 < 0x34b030);
    }
    unaff_ESI[0x14] = '\x01';
    unaff_ESI[0x15] = '\0';
    unaff_ESI[0x16] = '\0';
    unaff_ESI[0x17] = '\0';
    *unaff_ESI = '\0';
    unaff_ESI[0x48] = '\0';
    unaff_ESI[0x49] = '\0';
    unaff_ESI[0x4a] = '\0';
    unaff_ESI[0x4b] = '\0';
    unaff_ESI[0x4c] = '\0';
    unaff_ESI[0x4d] = '\0';
    unaff_ESI[0x4e] = '\0';
    unaff_ESI[0x4f] = '\0';
    unaff_ESI[0x50] = '\0';
    unaff_ESI[0x51] = '\0';
    unaff_ESI[0x52] = '\0';
    unaff_ESI[0x53] = '\0';
    unaff_ESI[0x54] = '\0';
    unaff_ESI[0x55] = '\0';
    unaff_ESI[0x56] = '\0';
    unaff_ESI[0x57] = '\0';
    unaff_ESI[0x68] = '\0';
    unaff_ESI[0x69] = '\0';
    unaff_ESI[0x6a] = '\0';
    unaff_ESI[0x6b] = '\0';
    unaff_ESI[0x6c] = '\0';
    unaff_ESI[0x6d] = '\0';
    unaff_ESI[0x6e] = '\0';
    unaff_ESI[0x6f] = '\0';
    unaff_ESI[0x58] = '\0';
    unaff_ESI[0x59] = '\0';
    unaff_ESI[0x5a] = '\0';
    unaff_ESI[0x5b] = '\0';
    unaff_ESI[0x5c] = '\0';
    unaff_ESI[0x5d] = '\0';
    unaff_ESI[0x5e] = '\0';
    unaff_ESI[0x5f] = '\0';
    unaff_ESI[0x60] = '\0';
    unaff_ESI[0x61] = '\0';
    unaff_ESI[0x62] = '\0';
    unaff_ESI[99] = '\0';
    unaff_ESI[100] = '\0';
    unaff_ESI[0x65] = '\0';
    unaff_ESI[0x66] = '\0';
    unaff_ESI[0x67] = '\0';
    unaff_ESI[0x70] = '\0';
    unaff_ESI[0x71] = '\0';
    unaff_ESI[0x72] = '\0';
    unaff_ESI[0x73] = '\0';
    unaff_ESI[0x74] = '\0';
    unaff_ESI[0x75] = '\0';
    unaff_ESI[0x76] = '\0';
    unaff_ESI[0x77] = '\0';
    unaff_ESI[0x7c] = '\0';
    unaff_ESI[0x7d] = '\0';
    unaff_ESI[0x7e] = '\0';
    unaff_ESI[0x7f] = '\0';
    unaff_ESI[0x80] = '\0';
    unaff_ESI[0x81] = '\0';
    unaff_ESI[0x82] = '\0';
    unaff_ESI[0x83] = '\0';
    unaff_ESI[0x119118] = '\0';
    unaff_ESI[0x119094] = '\0';
    unaff_ESI[0x119095] = '\0';
    unaff_ESI[0x119096] = '\0';
    unaff_ESI[0x119097] = '\0';
    unaff_ESI[0x119098] = '\0';
    unaff_ESI[0x119099] = '\0';
    unaff_ESI[0x11909a] = '\0';
    unaff_ESI[0x11909b] = '\0';
    unaff_ESI[0x11909c] = '\0';
    unaff_ESI[0x11909d] = '\0';
    unaff_ESI[0x11909e] = '\0';
    unaff_ESI[0x11909f] = '\0';
    unaff_ESI[0x1190a0] = '\0';
    unaff_ESI[0x1190a1] = '\0';
    unaff_ESI[0x1190a2] = '\0';
    unaff_ESI[0x1190a3] = '\0';
    unaff_ESI[0x1190a4] = '\0';
    unaff_ESI[0x1190a5] = '\0';
    unaff_ESI[0x1190a6] = '\0';
    unaff_ESI[0x1190a7] = '\0';
    unaff_ESI[0x1190a8] = '\0';
    unaff_ESI[0x1190a9] = '\0';
    unaff_ESI[0x1190aa] = '\0';
    unaff_ESI[0x1190ab] = '\0';
    unaff_ESI[0x1190ac] = '\0';
    unaff_ESI[0x1190ad] = '\0';
    unaff_ESI[0x1190ae] = '\0';
    unaff_ESI[0x1190af] = '\0';
    unaff_ESI[0x1190b0] = '\0';
    unaff_ESI[0x1190b1] = '\0';
    unaff_ESI[0x1190b2] = '\0';
    unaff_ESI[0x1190b3] = '\0';
    unaff_ESI[0x1190b4] = '\0';
    unaff_ESI[0x1190b5] = '\0';
    unaff_ESI[0x1190b6] = '\0';
    unaff_ESI[0x1190b7] = '\0';
    unaff_ESI[0x1190b8] = '\0';
    unaff_ESI[0x1190b9] = '\0';
    unaff_ESI[0x1190ba] = '\0';
    unaff_ESI[0x1190bb] = '\0';
    unaff_ESI[0x1190bc] = '\0';
    unaff_ESI[0x1190bd] = '\0';
    unaff_ESI[0x1190be] = '\0';
    unaff_ESI[0x1190bf] = '\0';
    unaff_ESI[0x1190c0] = '\0';
    unaff_ESI[0x1190c1] = '\0';
    unaff_ESI[0x1190c2] = '\0';
    unaff_ESI[0x1190c3] = '\0';
    unaff_ESI[0x1190c4] = '\0';
    unaff_ESI[0x1190c5] = '\0';
    unaff_ESI[0x1190c6] = '\0';
    unaff_ESI[0x1190c7] = '\0';
    unaff_ESI[0x1190c8] = '\0';
    unaff_ESI[0x1190c9] = '\0';
    unaff_ESI[0x1190ca] = '\0';
    unaff_ESI[0x1190cb] = '\0';
    unaff_ESI[0x1190cc] = '\0';
    unaff_ESI[0x1190cd] = '\0';
    unaff_ESI[0x1190ce] = '\0';
    unaff_ESI[0x1190cf] = '\0';
    unaff_ESI[0x1190d0] = '\0';
    unaff_ESI[0x1190d1] = '\0';
    unaff_ESI[0x1190d2] = '\0';
    unaff_ESI[0x1190d3] = '\0';
    unaff_ESI[0x1190d4] = '\0';
    unaff_ESI[0x1190d5] = '\0';
    unaff_ESI[0x1190d6] = '\0';
    unaff_ESI[0x1190d7] = '\0';
    unaff_ESI[0x1190d8] = '\0';
    unaff_ESI[0x1190d9] = '\0';
    unaff_ESI[0x1190da] = '\0';
    unaff_ESI[0x1190db] = '\0';
    unaff_ESI[0x1190dc] = '\0';
    unaff_ESI[0x1190dd] = '\0';
    unaff_ESI[0x1190de] = '\0';
    unaff_ESI[0x1190df] = '\0';
    unaff_ESI[0x1190e0] = '\0';
    unaff_ESI[0x1190e1] = '\0';
    unaff_ESI[0x1190e2] = '\0';
    unaff_ESI[0x1190e3] = '\0';
    unaff_ESI[0x1190e4] = '\0';
    unaff_ESI[0x1190e5] = '\0';
    unaff_ESI[0x1190e6] = '\0';
    unaff_ESI[0x1190e7] = '\0';
    unaff_ESI[0x1190e8] = '\0';
    unaff_ESI[0x1190e9] = '\0';
    unaff_ESI[0x1190ea] = '\0';
    unaff_ESI[0x1190eb] = '\0';
    unaff_ESI[0x1190ec] = '\0';
    unaff_ESI[0x1190ed] = '\0';
    unaff_ESI[0x1190ee] = '\0';
    unaff_ESI[0x1190ef] = '\0';
    unaff_ESI[0x1190f0] = '\0';
    unaff_ESI[0x1190f1] = '\0';
    unaff_ESI[0x1190f2] = '\0';
    unaff_ESI[0x1190f3] = '\0';
    unaff_ESI[0x1190f4] = '\0';
    unaff_ESI[0x1190f5] = '\0';
    unaff_ESI[0x1190f6] = '\0';
    unaff_ESI[0x1190f7] = '\0';
    unaff_ESI[0x1190f8] = '\0';
    unaff_ESI[0x1190f9] = '\0';
    unaff_ESI[0x1190fa] = '\0';
    unaff_ESI[0x1190fb] = '\0';
    unaff_ESI[0x1190fc] = '\0';
    unaff_ESI[0x1190fd] = '\0';
    unaff_ESI[0x1190fe] = '\0';
    unaff_ESI[0x1190ff] = '\0';
    unaff_ESI[0x119100] = '\0';
    unaff_ESI[0x119101] = '\0';
    unaff_ESI[0x119102] = '\0';
    unaff_ESI[0x119103] = '\0';
    unaff_ESI[0x119104] = '\0';
    unaff_ESI[0x119105] = '\0';
    unaff_ESI[0x119106] = '\0';
    unaff_ESI[0x119107] = '\0';
    unaff_ESI[0x119108] = '\0';
    unaff_ESI[0x119109] = '\0';
    unaff_ESI[0x11910a] = '\0';
    unaff_ESI[0x11910b] = '\0';
    unaff_ESI[0x11910c] = '\0';
    unaff_ESI[0x11910d] = '\0';
    unaff_ESI[0x11910e] = '\0';
    unaff_ESI[0x11910f] = '\0';
    unaff_ESI[0x119110] = '\0';
    unaff_ESI[0x119111] = '\0';
    unaff_ESI[0x119112] = '\0';
    unaff_ESI[0x119113] = '\0';
    unaff_ESI[0x119114] = '\0';
    unaff_ESI[0x119115] = '\0';
    unaff_ESI[0x119116] = '\0';
    unaff_ESI[0x119117] = '\0';
    unaff_ESI[0x119119] = '\0';
    unaff_ESI[0x11911a] = '\0';
    unaff_ESI[0x11911b] = '\0';
    unaff_ESI[0x11911c] = '\0';
    unaff_ESI[0x11911d] = '\0';
    unaff_ESI[0x11911e] = '\0';
    unaff_ESI[0x11911f] = '\0';
    unaff_ESI[0x119120] = '\0';
    unaff_ESI[0x119121] = '\0';
    unaff_ESI[0x119122] = '\0';
    unaff_ESI[0x119123] = '\0';
    unaff_ESI[0x119124] = '\0';
    unaff_ESI[0x119125] = '\0';
    unaff_ESI[0x119126] = '\0';
    unaff_ESI[0x119127] = '\0';
    unaff_ESI[0x119128] = '\0';
    unaff_ESI[0x119129] = '\0';
    unaff_ESI[0x11912a] = '\0';
    unaff_ESI[0x11912b] = '\0';
    unaff_ESI[0x11912c] = '\0';
    unaff_ESI[0x11912d] = '\0';
    unaff_ESI[0x11912e] = '\0';
    unaff_ESI[0x11912f] = '\0';
    unaff_ESI[0x119130] = '\0';
    unaff_ESI[0x119131] = '\0';
    unaff_ESI[0x119132] = '\0';
    unaff_ESI[0x119133] = '\0';
    unaff_ESI[0x119134] = '\0';
    unaff_ESI[0x119135] = '\0';
    unaff_ESI[0x119136] = '\0';
    unaff_ESI[0x119137] = '\0';
    unaff_ESI[0x119138] = '\0';
    memset(unaff_ESI + 0x119140,0,0x108);
    unaff_ESI[0x11913c] = '\0';
    unaff_ESI[0x11913d] = '\0';
    unaff_ESI[0x11913e] = '\0';
    unaff_ESI[0x11913f] = '\0';
  }
  return;
}



/* FUNCTION FUN_10019eb0 ENTRY 10019eb0 */

undefined4 FUN_10019eb0(undefined4 param_1)

{
  undefined1 *unaff_ESI;
  
  if (unaff_ESI == (undefined1 *)0x0) {
    Log("%s invalid parameter\n","DCResetManageItem");
    return 6;
  }
  *(undefined4 *)(unaff_ESI + 4) = param_1;
  *unaff_ESI = 0;
  unaff_ESI[1] = 0;
  unaff_ESI[8] = 0;
  unaff_ESI[0x18] = 0;
  *(undefined2 *)(unaff_ESI + 0x1a) = 5;
  *(undefined2 *)(unaff_ESI + 0x1c) = 30000;
  unaff_ESI[0x24] = 0;
  *(undefined4 *)(unaff_ESI + 0x38) = 0;
  *(undefined4 *)(unaff_ESI + 0x4c) = 0;
  *(undefined4 *)(unaff_ESI + 0x3c) = 0;
  *(undefined4 *)(unaff_ESI + 0x40) = 0;
  *(undefined4 *)(unaff_ESI + 0x44) = 0;
  *(undefined4 *)(unaff_ESI + 0x58) = 0;
  *(undefined4 *)(unaff_ESI + 0x70) = 0;
  *(undefined4 *)(unaff_ESI + 0x74) = 0;
  *(undefined4 *)(unaff_ESI + 0x78) = 0;
  *(undefined4 *)(unaff_ESI + 0x7c) = 0;
  *(undefined4 *)(unaff_ESI + 0x60) = 0;
  *(undefined4 *)(unaff_ESI + 100) = 0;
  *(undefined4 *)(unaff_ESI + 0x68) = 0;
  *(undefined4 *)(unaff_ESI + 0x6c) = 0;
  *(undefined4 *)(unaff_ESI + 0x80) = 0;
  *(undefined4 *)(unaff_ESI + 0x84) = 0;
  *(undefined4 *)(unaff_ESI + 0x88) = 0;
  *(undefined4 *)(unaff_ESI + 0x8c) = 0;
  *(undefined4 *)(unaff_ESI + 0x94) = 0;
  *(undefined4 *)(unaff_ESI + 0x98) = 0;
  unaff_ESI[0x19] = 3;
  *(undefined2 *)(unaff_ESI + 0x1e) = 3;
  *(undefined4 *)(unaff_ESI + 0x20) = 0xffffffff;
  *(undefined4 *)(unaff_ESI + 0x28) = 0xffffffff;
  *(undefined4 *)(unaff_ESI + 0x2c) = 1;
  *(undefined4 *)(unaff_ESI + 0x30) = 1;
  *(undefined4 *)(unaff_ESI + 0x34) = 1;
  *(undefined4 *)(unaff_ESI + 0x48) = 1;
  *(undefined4 *)(unaff_ESI + 0x1190ac) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190b0) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190b4) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190b8) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190bc) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190c0) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190c4) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190c8) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190cc) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190d0) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190d4) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190d8) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190dc) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190e0) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190e4) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190e8) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190ec) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190f0) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190f4) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190f8) = 0;
  *(undefined4 *)(unaff_ESI + 0x1190fc) = 0;
  *(undefined4 *)(unaff_ESI + 0x119100) = 0;
  *(undefined4 *)(unaff_ESI + 0x119104) = 0;
  *(undefined4 *)(unaff_ESI + 0x119108) = 0;
  *(undefined4 *)(unaff_ESI + 0x11910c) = 0;
  *(undefined4 *)(unaff_ESI + 0x119110) = 0;
  *(undefined4 *)(unaff_ESI + 0x119114) = 0;
  *(undefined4 *)(unaff_ESI + 0x119118) = 0;
  *(undefined4 *)(unaff_ESI + 0x11911c) = 0;
  *(undefined4 *)(unaff_ESI + 0x119120) = 0;
  *(undefined4 *)(unaff_ESI + 0x119124) = 0;
  *(undefined4 *)(unaff_ESI + 0x119128) = 0;
  *(undefined4 *)(unaff_ESI + 0x11912c) = 0;
  *(undefined4 *)(unaff_ESI + 0x119131) = 0;
  *(undefined4 *)(unaff_ESI + 0x119135) = 0;
  *(undefined4 *)(unaff_ESI + 0x119139) = 0;
  *(undefined4 *)(unaff_ESI + 0x11913d) = 0;
  *(undefined4 *)(unaff_ESI + 0x119141) = 0;
  *(undefined4 *)(unaff_ESI + 0x119145) = 0;
  *(undefined4 *)(unaff_ESI + 0x119149) = 0;
  *(undefined4 *)(unaff_ESI + 0x11914d) = 0;
  memset(unaff_ESI + 0xac,0,0x100000);
  memset(unaff_ESI + 0x1000ac,0,0x19000);
  memset(unaff_ESI + 0x119158,0,0x108);
  *(undefined4 *)(unaff_ESI + 0x119154) = 0;
  unaff_ESI[0x119130] = 0;
  OSAL_CreateMutex(unaff_ESI + 0x50);
  OSAL_CreateMutex(unaff_ESI + 0x54);
  *(undefined4 *)(unaff_ESI + 0x5c) = 0;
  return 0;
}



/* FUNCTION FUN_10027126 ENTRY 10027126 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __fastcall FUN_10027126(int param_1,undefined4 param_2)

{
  undefined4 in_EAX;
  HANDLE hProcess;
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
  byte in_AF;
  byte in_TF;
  byte in_IF;
  byte in_NT;
  byte in_AC;
  byte in_VIF;
  byte in_VIP;
  byte in_ID;
  undefined4 unaff_retaddr;
  UINT uExitCode;
  int local_32c;
  undefined4 local_328;
  
  if (param_1 == DAT_10034000) {
    return;
  }
  _DAT_10034b00 =
       (uint)(in_NT & 1) * 0x4000 | (uint)SBORROW4((int)&stack0xfffffffc,0x328) * 0x800 |
       (uint)(in_IF & 1) * 0x200 | (uint)(in_TF & 1) * 0x100 | (uint)((int)&local_32c < 0) * 0x80 |
       (uint)(&stack0x00000000 == (undefined1 *)0x32c) * 0x40 | (uint)(in_AF & 1) * 0x10 |
       (uint)((POPCOUNT((uint)&local_32c & 0xff) & 1U) == 0) * 4 |
       (uint)(&stack0xfffffffc < (undefined1 *)0x328) | (uint)(in_ID & 1) * 0x200000 |
       (uint)(in_VIP & 1) * 0x100000 | (uint)(in_VIF & 1) * 0x80000 | (uint)(in_AC & 1) * 0x40000;
  _DAT_10034b04 = &stack0x00000004;
  _DAT_10034a40 = 0x10001;
  _DAT_100349e8 = 0xc0000409;
  _DAT_100349ec = 1;
  local_32c = DAT_10034000;
  local_328 = DAT_10034004;
  _DAT_100349f4 = unaff_retaddr;
  _DAT_10034acc = in_GS;
  _DAT_10034ad0 = in_FS;
  _DAT_10034ad4 = in_ES;
  _DAT_10034ad8 = in_DS;
  _DAT_10034adc = unaff_EDI;
  _DAT_10034ae0 = unaff_ESI;
  _DAT_10034ae4 = unaff_EBX;
  _DAT_10034ae8 = param_2;
  _DAT_10034aec = param_1;
  _DAT_10034af0 = in_EAX;
  _DAT_10034af4 = unaff_EBP;
  DAT_10034af8 = unaff_retaddr;
  _DAT_10034afc = in_CS;
  _DAT_10034b08 = in_SS;
  DAT_10034a38 = IsDebuggerPresent();
  _crt_debugger_hook(1);
  SetUnhandledExceptionFilter((LPTOP_LEVEL_EXCEPTION_FILTER)0x0);
  UnhandledExceptionFilter((_EXCEPTION_POINTERS *)&PTR_DAT_1002c328);
  if (DAT_10034a38 == 0) {
    _crt_debugger_hook(1);
  }
  uExitCode = 0xc0000409;
  hProcess = GetCurrentProcess();
  TerminateProcess(hProcess,uExitCode);
  return;
}



/* FUNCTION FUN_1001a0d0 ENTRY 1001a0d0 */

/* WARNING: Removing unreachable block (ram,0x1001a1d8) */

char * FUN_1001a0d0(void)

{
  uint uVar1;
  undefined4 *puVar2;
  char *pcVar3;
  
  uVar1 = 0;
  pcVar3 = &DAT_10034d80;
  do {
    if (*pcVar3 == '\0') {
      if (*(int *)(pcVar3 + 0x5c) == 0) {
        puVar2 = (undefined4 *)OSAL_MemAlloc(0,0x34b030,0);
        *(undefined4 **)(pcVar3 + 0x5c) = puVar2;
        if (puVar2 == (undefined4 *)0x0) {
          Log("%s alloc memory fail\n","DCAllocManageItem");
          break;
        }
        *puVar2 = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 4) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 8) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x119010) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x119014) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x119018) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x232020) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x232024) = 0;
        *(undefined4 *)(*(int *)(pcVar3 + 0x5c) + 0x232028) = 0;
      }
      pcVar3[0x119131] = '\0';
      pcVar3[0x119132] = '\0';
      pcVar3[0x119133] = '\0';
      pcVar3[0x119134] = '\0';
      pcVar3[0x119135] = '\0';
      pcVar3[0x119136] = '\0';
      pcVar3[0x119137] = '\0';
      pcVar3[0x119138] = '\0';
      pcVar3[0x119139] = '\0';
      pcVar3[0x11913a] = '\0';
      pcVar3[0x11913b] = '\0';
      pcVar3[0x11913c] = '\0';
      pcVar3[0x11913d] = '\0';
      pcVar3[0x11913e] = '\0';
      pcVar3[0x11913f] = '\0';
      pcVar3[0x119140] = '\0';
      pcVar3[0x119141] = '\0';
      pcVar3[0x119142] = '\0';
      pcVar3[0x119143] = '\0';
      pcVar3[0x119144] = '\0';
      pcVar3[0x119145] = '\0';
      pcVar3[0x119146] = '\0';
      pcVar3[0x119147] = '\0';
      pcVar3[0x119148] = '\0';
      pcVar3[0x119149] = '\0';
      pcVar3[0x11914a] = '\0';
      pcVar3[0x11914b] = '\0';
      pcVar3[0x11914c] = '\0';
      pcVar3[0x11914d] = '\0';
      pcVar3[0x11914e] = '\0';
      pcVar3[0x11914f] = '\0';
      pcVar3[0x119150] = '\0';
      *pcVar3 = '\x01';
      return pcVar3;
    }
    uVar1 = uVar1 + 0x119264;
    pcVar3 = pcVar3 + 0x119264;
  } while (uVar1 < 0x2324c80);
  Log("%s alloc manage item fail\n","DCAllocManageItem");
  return (char *)0x0;
}



/* FUNCTION FUN_10002660 ENTRY 10002660 */

void __thiscall FUN_10002660(int param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  int iVar2;
  int iVar3;
  undefined4 local_5bc;
  undefined4 local_5b8;
  undefined4 local_5b4;
  undefined4 local_5b0;
  int local_5a8;
  int local_59c;
  uint local_8;
  
  local_8 = DAT_10034000 ^ (uint)&local_5bc;
  if (param_1 == 0) {
    Log("%s invalid parameter: szIp is NULL\n","DCCConn");
  }
  else {
    iVar1 = DCSocket(1);
    if (iVar1 == -1) {
      Log("%s DCSocket fail\n","DCCConn");
    }
    else {
      iVar3 = DCConnect(iVar1,param_1,param_2,param_3);
      Sleep(10);
      iVar2 = DCIsRead(iVar1);
      if (((0 < iVar2) && (FUN_100010f0(), local_5a8 == 1)) && (iVar3 = local_59c, local_59c == 1))
      {
        DCClose(iVar1);
        goto LAB_10002793;
      }
      if ((iVar3 != 0) || (iVar3 = DCRecvTimeOutSet(iVar1,1), iVar3 != 0)) {
        DCClose(iVar1);
        iVar1 = -1;
      }
    }
    local_5b4 = 0;
    local_5bc = 0;
    local_5b8 = 1;
    local_5b0 = 0;
    iVar3 = FUN_10001680(iVar1);
    if (iVar3 == 6) {
      DCClose(iVar1);
    }
    else if (iVar3 != 0) {
      DCClose(iVar1);
    }
  }
LAB_10002793:
  FUN_10027126();
  return;
}


