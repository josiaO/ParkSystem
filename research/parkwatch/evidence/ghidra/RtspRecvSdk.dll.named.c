/* PROGRAM RtspRecvSdk.dll BASE 10000000 */

/* FUNCTION Rtsp_Init ENTRY 10004de0 */

undefined4 Rtsp_Init(void)

{
  int iVar1;
  int iVar2;
  
                    /* 0x4de0  7  Rtsp_Init */
  if (DAT_100091e8 == 1) {
    Log("Rtsp_Init already start\n");
    return 3;
  }
  iVar1 = FUN_100011d0();
  if (iVar1 != 0) {
    Log("Rtsp_Init DCVideoInit fail\n");
    return 0xffffffff;
  }
  memset(&DAT_10008368,0,0xe80);
  iVar2 = 0;
  iVar1 = 0x20;
  do {
    FUN_10004c80(iVar2);
    iVar2 = iVar2 + 1;
    iVar1 = iVar1 + -1;
  } while (iVar1 != 0);
  DAT_100091e8 = 1;
  return 0;
}



/* FUNCTION Rtsp_StartVideo ENTRY 100050f0 */

int Rtsp_StartVideo(uint param_1,undefined4 param_2,undefined1 param_3)

{
  int iVar1;
  int iVar2;
  int iVar3;
  char *pcVar4;
  undefined4 local_3c;
  code *local_38;
  code *local_34;
  undefined4 local_30;
  undefined4 local_2c;
  undefined4 local_28;
  undefined4 local_24;
  undefined4 local_20;
  undefined4 local_1c;
  undefined4 local_18;
  undefined4 local_14;
  undefined4 local_10;
  undefined4 local_c;
  
                    /* 0x50f0  10  Rtsp_StartVideo */
  local_3c = 0;
  local_30 = 0;
  local_38 = OSAL_MemAlloc_exref;
  local_34 = OSAL_MemFree_exref;
  if (param_1 < 0x20) {
    iVar3 = param_1 * 0x74;
    pcVar4 = &DAT_10008368 + iVar3;
    if ((pcVar4 != (char *)0x0) && (*pcVar4 != '\0')) {
      if ((&DAT_100083bc)[iVar3] == '\x01') {
        Log("Rtsp_StartVideo video connect already enable\n");
        return 3;
      }
      iVar1 = FUN_10003c60(param_2);
      if (iVar1 == 0) {
        (&DAT_1000836a)[iVar3] = 2;
        (&DAT_1000836b)[iVar3] = 0;
        (&DAT_100083bc)[iVar3] = 1;
        (&DAT_100083bd)[iVar3] = param_3;
        (&DAT_100083c4)[param_1 * 0x1d] = 0;
        iVar2 = rngQue_Create(10,0xc8000,&local_3c);
        (&DAT_100083cc)[param_1 * 0x1d] = iVar2;
        if (iVar2 == 0) {
          Log("Rtsp_StartVideo call CommQue_Create fail\n");
          Rtsp_StopVideo(param_1);
          return -1;
        }
        local_2c = 0;
        local_28 = 0;
        local_24 = 0;
        local_20 = 0;
        local_1c = 0;
        local_18 = 0;
        local_14 = 0;
        local_10 = 0;
        local_c = 0;
        iVar2 = TSK_create(FUN_10004250,&local_2c,pcVar4);
        (&DAT_100083c8)[param_1 * 0x1d] = iVar2;
        if (iVar2 == 0) {
          Log("Rtsp_StartVideo call TSK_create fail\n");
          Rtsp_StopVideo(param_1);
          return -1;
        }
        Log("Rtsp_StartVideo start video :%s success\n",iVar3 + 0x10008370);
      }
      return iVar1;
    }
  }
  Log("Rtsp_StartVideo invalid handle:%d\n",param_1);
  return 4;
}


