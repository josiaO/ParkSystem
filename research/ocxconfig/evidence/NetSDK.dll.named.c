/* PROGRAM NetSDK.dll BASE 10000000 */

/* FUNCTION FUN_10002620 ENTRY 10002620 */

void FUN_10002620(int param_1)

{
  int iVar1;
  int iVar2;
  undefined4 uVar3;
  undefined1 auStack_b94 [4];
  int local_b90;
  undefined4 local_b8c;
  undefined4 local_b88;
  undefined4 local_b84;
  undefined4 local_b80;
  undefined4 local_b7c;
  undefined4 local_b78;
  undefined4 local_b74;
  undefined4 local_b70;
  undefined4 local_b6c;
  undefined4 local_b68;
  undefined2 local_b5e;
  byte local_b5c;
  undefined1 local_b5b;
  ushort uStack_b5a;
  int local_b58 [355];
  undefined1 local_5cc [14];
  short sStack_5be;
  undefined2 uStack_5ba;
  undefined4 uStack_5b4;
  char local_28 [32];
  uint local_8;
  
  local_8 = DAT_10047000 ^ (uint)auStack_b94;
  local_b90 = 0;
  local_b7c = 1;
  local_28[0] = '\0';
  local_28[1] = '\0';
  local_28[2] = '\0';
  local_28[3] = '\0';
  local_28[4] = '\0';
  local_28[5] = '\0';
  local_28[6] = '\0';
  local_28[7] = '\0';
  local_28[8] = '\0';
  local_28[9] = '\0';
  local_28[10] = '\0';
  local_28[0xb] = '\0';
  local_28[0xc] = '\0';
  local_28[0xd] = '\0';
  local_28[0xe] = '\0';
  local_28[0xf] = '\0';
  local_28[0x10] = '\0';
  local_28[0x11] = '\0';
  local_28[0x12] = '\0';
  local_28[0x13] = '\0';
  local_28[0x14] = '\0';
  local_28[0x15] = '\0';
  local_28[0x16] = '\0';
  local_28[0x17] = '\0';
  local_28[0x18] = '\0';
  local_28[0x19] = '\0';
  local_28[0x1a] = '\0';
  local_28[0x1b] = '\0';
  local_28[0x1c] = '\0';
  local_28[0x1d] = '\0';
  local_28[0x1e] = '\0';
  local_28[0x1f] = 0;
  local_b80 = 0;
  if (param_1 < 0) {
    Log();
  }
  else {
    local_b8c = 0;
    local_b88 = 0;
    local_b84 = 0;
    local_b78 = 0;
    local_b74 = 0;
    local_b70 = 0;
    memset(&local_b6c,0,0x5a0);
    memset(local_5cc,0,0x5a0);
    local_b6c = 1;
    local_b68 = 0xf0001;
    local_b5e = 8;
    local_b5c = 0;
    local_b5b = 1;
    iVar1 = DCGetLocalIP(param_1,local_b58);
    if (iVar1 == 0) {
      iVar1 = DCSocket();
      if (iVar1 == -1) {
        Log();
      }
      else {
        do {
          uStack_b5a = DAT_10047014;
          iVar2 = DCBind();
          if (iVar2 == 0) {
            DAT_10047014 = DAT_10047014 + 1;
            if (51999 < DAT_10047014) {
              DAT_10047014 = 50000;
            }
            if (((uStack_b5a != 0) && (local_b58[0] != -1)) && (local_b5c < 3)) {
              FUN_100208b0();
              iVar2 = FUN_10001b70();
              Log();
              if ((iVar2 == 0) && (sStack_5be == 0x10)) {
                if (&stack0x00000000 != (undefined1 *)0x5bc) {
                  uStack_5ba = CONCAT11((undefined1)uStack_5ba,uStack_5ba._1_1_);
                  uStack_5b4 = CONCAT22(uStack_5b4._2_2_,
                                        CONCAT11((undefined1)uStack_5b4,uStack_5b4._1_1_));
                }
                sprintf_s(local_28,0x20,"%d.%d.%d.%d");
                iVar2 = DCConnect(iVar1,local_28,uStack_5b4,3);
                if (iVar2 != 0) {
                  Log("%s call DCConnect IP=%s port=%d, niRet=%d\n");
                  DCClose(iVar1);
                  goto LAB_10002a19;
                }
                DCRecvTimeOutSet();
                iVar2 = Ordinal_21(iVar1);
                if (iVar2 == -1) {
                  uVar3 = DCError();
                  Log("%s set setsockopt SO_KEEPALIVE fail, niRet=%d, error=%d\n","DCCDevPortNego",
                      0xffffffff,uVar3);
                }
                iVar1 = WSAIoctl(iVar1,0x98000004,&stack0xfffff460,0xc,&local_b8c,0xc,auStack_b94,0,
                                 0);
                if (iVar1 == 0) goto LAB_10002a19;
                Ordinal_111();
              }
            }
            break;
          }
          Log();
          DAT_10047014 = DAT_10047014 + 1;
          if (51999 < DAT_10047014) {
            DAT_10047014 = 50000;
          }
          local_b90 = local_b90 + 1;
        } while (local_b90 < 10);
        Log();
        DCClose();
      }
    }
    else {
      Log("%s call DCGetLocalIP fail, niCtlFd=%d, niClientIp=%d, niRet=%d\n");
    }
  }
LAB_10002a19:
  FUN_10037e16();
  return;
}



/* FUNCTION FUN_10002a40 ENTRY 10002a40 */

void __thiscall FUN_10002a40(int param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  int iVar2;
  int iVar3;
  undefined1 auStack_5c0 [4];
  undefined4 uStack_5bc;
  undefined4 uStack_5b8;
  int iStack_5b4;
  undefined4 uStack_5b0;
  int iStack_5a8;
  int iStack_59c;
  uint local_8;
  
  local_8 = DAT_10047000 ^ (uint)auStack_5c0;
  if (param_1 == 0) {
    Log("%s invalid parameter: szIp is NULL\n","DCCConn");
    FUN_10037e16();
    return;
  }
  iVar1 = DCSocket(1);
  if (iVar1 == -1) {
    Log("%s DCSocket fail\n","DCCConn");
    goto LAB_10002bd8;
  }
  iVar2 = DCConnect(iVar1,param_1,param_2,param_3);
  if (iVar2 == -1) {
    DCClose(iVar1);
    Log("%s DCConnect Fail niRet=%d\n","DCCConn",0xffffffff);
    FUN_10037e16();
    return;
  }
  Sleep(10);
  iVar3 = DCIsRead(iVar1);
  if (0 < iVar3) {
    FUN_100010b0(iVar1);
    if ((iStack_5a8 == 1) && (iVar2 = iStack_59c, iStack_59c == 1)) {
      DCClose(iVar1);
      FUN_10037e16();
      return;
    }
  }
  if (iVar2 == 0) {
    iVar2 = DCRecvTimeOutSet(iVar1,1);
    if (iVar2 == 0) {
      if (iVar1 < 0) goto LAB_10002bd8;
      uStack_5bc = 0;
      uStack_5b8 = 1;
      uStack_5b0 = 0;
      iStack_5b4 = iVar2;
      iVar2 = FUN_10001980(iVar1);
      if (iVar2 == 6) {
        DCClose(iVar1);
        goto LAB_10002bd8;
      }
      if (iVar2 == 0) goto LAB_10002bd8;
    }
  }
  DCClose(iVar1);
LAB_10002bd8:
  FUN_10037e16();
  return;
}



/* FUNCTION FUN_10002c00 ENTRY 10002c00 */

void __thiscall
FUN_10002c00(int param_1,undefined4 param_2,undefined4 param_3,byte *param_4,byte *param_5,
            int *param_6)

{
  int iVar1;
  int iVar2;
  int iVar3;
  undefined4 uVar4;
  int iVar5;
  byte *pbVar6;
  code *pcVar7;
  bool bVar8;
  bool bVar9;
  char *pcVar10;
  int *local_5c0;
  int iStack_5bc;
  undefined4 uStack_5b8;
  int iStack_5b4;
  undefined4 uStack_5b0;
  undefined4 uStack_5ac;
  int iStack_5a4;
  int iStack_598;
  uint local_4;
  
  local_4 = DAT_10047000 ^ (uint)&local_5c0;
  local_5c0 = param_6;
  if (param_1 == 0) {
    Log("%s invalid parameter: szIp is NULL\n","DCCConnEx");
    Log("%s Check szIp is NULL Return -1\n","DCCConnEx");
    goto LAB_10002e90;
  }
  iVar1 = DCSocket(1);
  if (iVar1 == -1) {
    Log("%s DCSocket fail\n","DCCConnEx");
    goto LAB_10002e88;
  }
  iVar2 = DCConnect(iVar1,param_1,param_2,param_3);
  pcVar7 = Log_exref;
  iStack_5bc = iVar2;
  if (iVar2 == -1) {
    DCClose(iVar1);
    Log("%s DCConnect Fail niRet=%d\n","DCCConnEx",0xffffffff);
    goto LAB_10002e90;
  }
  Log("%s DCConnect niRet=%d\n","DCCConnEx",iVar2);
  Sleep(10);
  iVar3 = DCIsRead(iVar1);
  if (0 < iVar3) {
    uVar4 = FUN_100010b0(iVar1);
    Log("%s DCCRecvMsg eCode=%d\n","DCCConnEx",uVar4);
    iVar2 = iStack_5bc;
    if ((iStack_5a4 == 1) && (iStack_5bc = iStack_598, iVar2 = iStack_598, iStack_598 == 1)) {
      *local_5c0 = iVar1;
      DCClose(iVar1);
      Log("%s fail: DC_BEYOND_MAX_CLIENT\n","DCCConnEx");
      goto LAB_10002e90;
    }
  }
  if (iVar2 == 0) {
    iVar2 = DCRecvTimeOutSet(iVar1,1);
    if (iVar2 != 0) {
      pcVar10 = "%s DCRecvTimeOutSet fd:%d Return -1\n";
      goto LAB_10002d7b;
    }
    if (-1 < iVar1) {
      uStack_5b0 = 0;
      uStack_5b8 = 0;
      iStack_5b4 = 1;
      uStack_5ac = 0;
      iVar2 = FUN_10001980(iVar1);
      Log("%s DCCHanelReqMsg, niCtlFd=%d, eCode=%d\n","DCCConnEx",iVar1,iVar2);
      FUN_10020810();
      if (iStack_5b4 != 1) goto LAB_10002e55;
      if (iVar2 == 0) {
        if ((short)uStack_5ac == 0x1001) goto LAB_10002e88;
        if ((short)uStack_5ac != 0) {
LAB_10002e55:
          if (iVar2 == 0) goto LAB_10002e88;
          goto LAB_10002e59;
        }
        iVar5 = 6;
        bVar8 = false;
        iVar3 = 0;
        bVar9 = true;
        pbVar6 = (byte *)"[redacted]";
        do {
          if (iVar5 == 0) break;
          iVar5 = iVar5 + -1;
          bVar8 = *param_4 < *pbVar6;
          bVar9 = *param_4 == *pbVar6;
          param_4 = param_4 + 1;
          pbVar6 = pbVar6 + 1;
        } while (bVar9);
        if (!bVar9) {
          iVar3 = (1 - (uint)bVar8) - (uint)(bVar8 != 0);
        }
        pcVar7 = Log_exref;
        if (iVar3 == 0) {
          iVar5 = 6;
          bVar8 = false;
          iVar3 = 0;
          bVar9 = true;
          pbVar6 = (byte *)"[redacted]";
          do {
            if (iVar5 == 0) break;
            iVar5 = iVar5 + -1;
            bVar8 = *param_5 < *pbVar6;
            bVar9 = *param_5 == *pbVar6;
            param_5 = param_5 + 1;
            pbVar6 = pbVar6 + 1;
          } while (bVar9);
          if (!bVar9) {
            iVar3 = (1 - (uint)bVar8) - (uint)(bVar8 != 0);
          }
          if (iVar3 == 0) goto LAB_10002e55;
        }
      }
      else {
LAB_10002e59:
        if (iVar2 == 6) goto LAB_10002e88;
      }
      (*pcVar7)("%s if ((DC_NO_ERROR != eCode)&&(RESPONSE_CODE_AUTHORITY_LIMIT != eCode)) fd:%d Return -1\n"
                ,"DCCConnEx",iVar1);
      DCClose(iVar1);
      goto LAB_10002e82;
    }
  }
  else {
    pcVar10 = "%s if (0 == niRet) fd:%d Return -1\n";
LAB_10002d7b:
    Log(pcVar10,"DCCConnEx",iVar1);
    DCClose(iVar1);
LAB_10002e82:
    iVar1 = -1;
  }
LAB_10002e88:
  *local_5c0 = iVar1;
LAB_10002e90:
  FUN_10037e16();
  return;
}



/* FUNCTION FUN_10008d60 ENTRY 10008d60 */

void __fastcall FUN_10008d60(undefined4 param_1,char *param_2)

{
  int *piVar1;
  int iVar2;
  int *piVar3;
  int iVar4;
  undefined8 uVar5;
  undefined4 local_5b0;
  undefined4 local_5ac;
  undefined2 local_5a2;
  undefined4 local_5a0 [357];
  uint local_c;
  
  local_c = DAT_10047000 ^ (uint)&local_5b0;
  memset(&local_5b0,0,0x5a0);
  if (*param_2 == '\x01') {
    param_2[1] = '\0';
  }
  else {
    param_2[1] = *param_2 == '\x02';
  }
  local_5a0[0] = *(undefined4 *)param_2;
  local_5b0 = 1;
  local_5ac = 0x15002;
  local_5a2 = 4;
  uVar5 = FUN_100204f0();
  iVar4 = (int)uVar5;
  if (iVar4 == 0) {
    iVar4 = 0;
    if (&stack0x00000000 == (undefined1 *)0x5b0) {
      iVar4 = 6;
    }
    else {
      piVar3 = &DAT_1004c858;
      iVar2 = DAT_1004c858;
      while ((iVar2 != -1 && (iVar2 != 0x15002))) {
        piVar1 = piVar3 + 3;
        piVar3 = piVar3 + 3;
        iVar2 = *piVar1;
      }
      if (*piVar3 != -1) {
        if (piVar3[1] == (int)((ulonglong)uVar5 >> 0x20)) {
          if ((code *)piVar3[2] != (code *)0x0) {
            (*(code *)piVar3[2])(local_5a0);
          }
          iVar4 = 0;
        }
        else {
          iVar4 = 6;
        }
      }
      if (iVar4 == 0) {
        FUN_100022b0(&local_5b0);
        FUN_10037e16();
        return;
      }
    }
  }
  Log("%s parameter valid check fail, eCode=%d\n","DCCGateSetup",iVar4);
  FUN_10037e16();
  return;
}


