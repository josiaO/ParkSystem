/* PROGRAM NetSDK.dll BASE 10000000 */

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


