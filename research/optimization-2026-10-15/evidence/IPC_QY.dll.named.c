/* PROGRAM IPC_QY.dll BASE 10000000 */

/* FUNCTION CAM_StartStream ENTRY 10005230 */

undefined4 CAM_StartStream(int param_1,undefined4 param_2,undefined4 param_3)

{
  undefined4 uVar1;
  
                    /* 0x5230  13  CAM_StartStream */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  uVar1 = FUN_10005bb0(param_1,param_3);
  return uVar1;
}



/* FUNCTION CAM_SetCaptureCallback ENTRY 10005270 */

undefined4 CAM_SetCaptureCallback(int param_1,undefined4 param_2,undefined4 param_3)

{
                    /* 0x5270  12  CAM_SetCaptureCallback */
  if (param_1 == 0) {
    return 0xfffffffe;
  }
  *(undefined4 *)(param_1 + 0x56c) = param_2;
  *(undefined4 *)(param_1 + 0x570) = param_3;
  return 0;
}



/* FUNCTION FUN_100063c0 ENTRY 100063c0 */

void __thiscall
FUN_100063c0(int param_1,void *param_2,size_t param_3,undefined4 *param_4,uint *param_5)

{
  char cVar1;
  int iVar2;
  uint *puVar3;
  undefined4 *puVar4;
  uint *puVar5;
  uint local_204 [4];
  uint local_1f4;
  uint local_1f0;
  uint local_1ec;
  void *local_1e8;
  size_t local_1e4;
  undefined4 local_1e0;
  undefined4 local_1dc [113];
  _SYSTEMTIME local_18;
  uint local_8;
  
  local_8 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  FUN_10006590(param_1,"OuterCapture Begin");
  if (*(int *)(param_1 + 0x56c) != 0) {
    memset(local_204,0,0x1ec);
    GetLocalTime(&local_18);
    if (param_5 != (uint *)0x0) {
      local_18._0_4_ = *param_5;
      local_18._4_4_ = param_5[1];
      local_18._8_4_ = param_5[2];
      local_18._12_4_ = param_5[3];
    }
    local_204[0] = local_18._0_4_ & 0xffff;
    local_204[1] = (uint)local_18._0_4_ >> 0x10;
    local_204[2] = (uint)local_18._4_4_ >> 0x10;
    local_1f4 = (uint)local_18._8_4_ >> 0x10;
    local_204[3] = local_18._8_4_ & 0xffff;
    cVar1 = *(char *)(param_1 + 0x59c);
    local_1f0 = local_18._12_4_ & 0xffff;
    local_1ec = (uint)local_18._12_4_ >> 0x10;
    local_1e8 = param_2;
    local_1e4 = param_3;
    local_1e0 = 1;
    puVar4 = local_1dc;
    for (iVar2 = 0x50; iVar2 != 0; iVar2 = iVar2 + -1) {
      *puVar4 = *param_4;
      param_4 = param_4 + 1;
      puVar4 = puVar4 + 1;
    }
    if (cVar1 == '\0') {
      FUN_10006590(param_1,&DAT_1000b004);
      (**(code **)(param_1 + 0x56c))(param_1,local_204,*(undefined4 *)(param_1 + 0x570));
      FUN_10006590(param_1,&DAT_1000b014);
    }
    else {
      puVar3 = local_204;
      puVar5 = (uint *)(param_1 + 0x5a0);
      for (iVar2 = 0x7b; iVar2 != 0; iVar2 = iVar2 + -1) {
        *puVar5 = *puVar3;
        puVar3 = puVar3 + 1;
        puVar5 = puVar5 + 1;
      }
      FUN_100065f0(param_3);
      memcpy(*(void **)(param_1 + 0x58c),param_2,param_3);
      local_1e8 = *(void **)(param_1 + 0x58c);
      SetEvent(*(HANDLE *)(param_1 + 0x598));
      FUN_10006570(param_1,"CallCaptureCbFun FOR CaptureTo");
      *(undefined1 *)(param_1 + 0x59c) = 0;
    }
  }
  FUN_10006590(param_1,"OuterCapture End");
  FUN_1000810a();
  return;
}



/* FUNCTION FUN_10006d40 ENTRY 10006d40 */

void __thiscall
FUN_10006d40(undefined4 param_1,undefined4 param_2,undefined4 param_3,int param_4,int *param_5,
            char param_6)

{
  char cVar1;
  uint uVar2;
  int iVar3;
  undefined4 ****ppppuVar4;
  char *pcVar5;
  char ****ppppcVar6;
  char *pcVar7;
  char local_1cc [32];
  undefined4 local_1ac;
  char local_1a8 [128];
  undefined4 local_128;
  uint local_124;
  uint local_120;
  uint local_11c;
  uint local_118;
  uint local_114;
  char ***local_8c [4];
  undefined4 local_7c;
  uint local_78;
  undefined4 local_74 [2];
  _SYSTEMTIME local_6c;
  undefined1 local_5c [24];
  uint local_44 [4];
  undefined4 local_34;
  uint local_30;
  undefined4 ***local_2c [4];
  undefined4 local_1c;
  uint local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  uint local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009933;
  local_10 = ExceptionList;
  uVar2 = DAT_1000f014 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_18 = 0xf;
  local_1c = 0;
  local_2c[0] = (undefined4 ***)((uint)local_2c[0] & 0xffffff00);
  local_14 = uVar2;
  FUN_100028b0("ProcessPlate",0xc);
  local_8 = 0;
  if (param_6 != '\0') {
    FUN_10002220("_Offline",8);
  }
  if (param_4 == 0) {
    ppppuVar4 = local_2c;
    if (0xf < local_18) {
      ppppuVar4 = (undefined4 ****)local_2c[0];
    }
    FUN_100065d0(param_1,"%s: ptImageInfo == NULL",ppppuVar4);
  }
  else if (param_5 == (int *)0x0) {
    ppppuVar4 = local_2c;
    if (0xf < local_18) {
      ppppuVar4 = (undefined4 ****)local_2c[0];
    }
    FUN_100065d0(param_1,"%s: ptPicInfo == NULL",ppppuVar4);
  }
  else {
    ppppuVar4 = local_2c;
    if (0xf < local_18) {
      ppppuVar4 = (undefined4 ****)local_2c[0];
    }
    FUN_10006590(param_1,"%s Begin",ppppuVar4,uVar2);
    memset(local_1cc,0,0x140);
    pcVar5 = (char *)(param_4 + 8);
    do {
      cVar1 = *pcVar5;
      pcVar5 = pcVar5 + 1;
    } while (cVar1 != '\0');
    if (pcVar5 != (char *)(param_4 + 9)) {
      FUN_100029b0((char *)(param_4 + 8));
      local_8 = CONCAT31(local_8._1_3_,1);
      pcVar5 = (char *)FUN_100077b0(local_44,local_74);
      if (0xf < *(uint *)(pcVar5 + 0x14)) {
        pcVar5 = *(char **)pcVar5;
      }
      pcVar7 = local_1cc;
      do {
        cVar1 = *pcVar5;
        pcVar5 = pcVar5 + 1;
        *pcVar7 = cVar1;
        pcVar7 = pcVar7 + 1;
      } while (cVar1 != '\0');
      if (0xf < local_30) {
        FUN_10002a10(local_44[0],local_30 + 1);
      }
      local_30 = 0xf;
      local_34 = 0;
      local_44[0] = local_44[0] & 0xffffff00;
      if (0xf < (uint)local_6c._12_4_) {
        FUN_10002a10(local_74[0],local_6c._12_4_ + 1);
      }
    }
    local_78 = 0xf;
    local_7c = 0;
    local_8c[0] = (char ***)((uint)local_8c[0] & 0xffffff00);
    local_8 = CONCAT31(local_8._1_3_,2);
    local_1ac = FUN_10007970(*(undefined1 *)(param_4 + 7),local_8c);
    pcVar5 = local_1a8;
    ppppcVar6 = local_8c;
    if (0xf < local_78) {
      ppppcVar6 = (char ****)local_8c[0];
    }
    do {
      cVar1 = *(char *)ppppcVar6;
      *pcVar5 = cVar1;
      pcVar5 = pcVar5 + 1;
      ppppcVar6 = (char ****)((int)ppppcVar6 + 1);
    } while (cVar1 != '\0');
    local_128 = FUN_10007a40(*(undefined1 *)(param_4 + 0x20));
    local_124 = (uint)*(byte *)(param_4 + 0x40);
    local_120 = (uint)*(ushort *)(param_4 + 0x18);
    local_11c = (uint)*(ushort *)(param_4 + 0x1a);
    local_118 = (uint)*(ushort *)(param_4 + 0x1c);
    local_114 = (uint)*(ushort *)(param_4 + 0x1e);
    if (*param_5 == 0) {
      ppppuVar4 = local_2c;
      if (0xf < local_18) {
        ppppuVar4 = (undefined4 ****)local_2c[0];
      }
      FUN_100065d0(param_1,"%s End",ppppuVar4);
    }
    else {
      GetLocalTime(&local_6c);
      pcVar5 = (char *)(param_4 + 0x26);
      do {
        cVar1 = *pcVar5;
        pcVar5 = pcVar5 + 1;
      } while (cVar1 != '\0');
      if ((int)pcVar5 - (param_4 + 0x27) == 0x11) {
        FUN_100029b0((char *)(param_4 + 0x26));
        local_8._0_1_ = 3;
        pcVar5 = (char *)FUN_10001b50(local_5c,0,4);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wYear = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,4,2);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wMonth = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,6,2);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wDay = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,8,2);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wHour = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,10,2);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wMinute = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,0xc,2);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wSecond = (WORD)iVar3;
        FUN_10002ad0();
        pcVar5 = (char *)FUN_10001b50(local_5c,0xe,3);
        if (0xf < *(uint *)(pcVar5 + 0x14)) {
          pcVar5 = *(char **)pcVar5;
        }
        iVar3 = atoi(pcVar5);
        local_6c.wMilliseconds = (short)iVar3;
        FUN_10002ad0();
        local_8 = CONCAT31(local_8._1_3_,2);
        FUN_10002ad0();
      }
      FUN_100063c0(param_5[2],*param_5,local_1cc,&local_6c);
    }
    local_8 = local_8 & 0xffffff00;
    if (0xf < local_78) {
      FUN_10002a10(local_8c[0],local_78 + 1);
    }
    ppppuVar4 = local_2c;
    if (0xf < local_18) {
      ppppuVar4 = (undefined4 ****)local_2c[0];
    }
    FUN_10006590(param_1,"%s End",ppppuVar4);
  }
  if (0xf < local_18) {
    FUN_10002a10(local_2c[0],local_18 + 1);
  }
  ExceptionList = local_10;
  FUN_1000810a();
  return;
}


