/* PROGRAM CommModule.dll BASE 10000000 */

/* FUNCTION DCSocket ENTRY 10001730 */

undefined4 DCSocket(int param_1)

{
  undefined4 uVar1;
  
                    /* 0x1730  25  DCSocket */
  if (param_1 == 0) {
    uVar1 = 2;
  }
  else {
    uVar1 = 1;
  }
  uVar1 = Ordinal_23(2,uVar1,0);
  return uVar1;
}



/* FUNCTION DCConnect ENTRY 10001860 */

void DCConnect(undefined4 *param_1,char *param_2,uint param_3,ushort param_4)

{
  undefined2 uVar1;
  int iVar2;
  undefined4 uVar3;
  char *pcStack_260;
  undefined4 *puStack_25c;
  char *pcStack_258;
  uint uStack_254;
  undefined4 uStack_244;
  undefined4 local_240;
  undefined4 local_23c;
  undefined4 local_238;
  undefined4 local_234;
  undefined4 uStack_148;
  undefined4 *puStack_144;
  undefined1 auStack_3c [12];
  undefined1 auStack_30 [16];
  undefined4 uStack_20;
  undefined4 local_1c;
  undefined4 local_18;
  undefined4 local_14;
  undefined4 local_10;
  uint local_c;
  
                    /* 0x1860  14  DCConnect */
  local_c = DAT_10006000 ^ (uint)&uStack_244;
  local_240 = 0;
  local_23c = 0;
  local_238 = 0;
  local_234 = 0;
  if (param_1 == (undefined4 *)0xffffffff) {
LAB_10001a7d:
    if (param_2 != (char *)0x0) goto LAB_10001a86;
  }
  else if (param_2 != (char *)0x0) {
    if ((short)param_3 != 0) {
      uStack_254 = param_3;
      local_18 = 0;
      local_14 = 0;
      local_10 = 0;
      local_1c = 2;
      pcStack_258 = (char *)0x100018df;
      uVar1 = Ordinal_9();
      pcStack_258 = param_2;
      uStack_20 = CONCAT22(uVar1,(undefined2)uStack_20);
      puStack_25c = (undefined4 *)0x100018ee;
      uStack_20 = Ordinal_11();
      puStack_25c = &uStack_244;
      pcStack_260 = (char *)0x8004667e;
      uStack_244 = 1;
      Ordinal_10(param_1);
      iVar2 = Ordinal_4(param_1,auStack_30,uStack_254);
      if (iVar2 == 0) {
        Log("%s connect ok, server ip=%s, server port=%d\n","DCConnect",param_2,param_3 & 0xffff);
      }
      else {
        iVar2 = Ordinal_111();
        if ((iVar2 == 0x2734) || (iVar2 = Ordinal_111(), iVar2 == 0x2733)) {
          pcStack_258 = (char *)(uint)param_4;
          uStack_148 = 1;
          puStack_144 = param_1;
          iVar2 = Ordinal_18((int)param_1 + 1,&uStack_148,&stack0xfffffdb0,0,&pcStack_258);
          if (iVar2 == 0) {
            uVar3 = Ordinal_111();
            Log("%s fail select connect timeout, server ip=%s, server port=%d, error=%d\n",
                "DCConnect",param_2,param_3 & 0xffff,uVar3);
          }
          else if ((0 < iVar2) && (iVar2 = Ordinal_151(param_1,&stack0xfffffdb0), iVar2 != 0)) {
            pcStack_260 = (char *)0x10;
            iVar2 = Ordinal_5(param_1,auStack_3c,&pcStack_260);
            if (iVar2 < 0) {
              uVar3 = Ordinal_111();
              Log("%s fail, niRet=%d, call getpeername, server ip=%s, server port=%d, error=%d\n",
                  "DCConnect",iVar2,param_2,param_3 & 0xffff,uVar3);
            }
          }
        }
        else {
          uVar3 = Ordinal_111();
          Log("%s connect  fail, server ip=%s, server port=%d, error=%d\n","DCConnect",param_2,
              param_3 & 0xffff,uVar3);
        }
      }
      puStack_25c = (undefined4 *)0x0;
      Ordinal_10(param_1,0x8004667e,&puStack_25c);
      FUN_10003782();
      return;
    }
    goto LAB_10001a7d;
  }
  param_2 = "is null";
LAB_10001a86:
  uStack_254 = param_3 & 0xffff;
  puStack_25c = param_1;
  pcStack_260 = "DCConnect";
  pcStack_258 = param_2;
  Log("%s parameter invalid, niFd=%d, szServerIp=%s, usServerPort=%d\n");
  FUN_10003782();
  return;
}



/* FUNCTION DCSend ENTRY 10001b10 */

undefined4 DCSend(int param_1,int param_2,int param_3)

{
  int iVar1;
  int iVar2;
  
                    /* 0x1b10  23  DCSend */
  iVar2 = 0;
  if (((param_1 != -1) && (param_2 != 0)) && (0 < param_3)) {
    do {
      while (iVar1 = Ordinal_19(param_1,iVar2 + param_2,param_3 - iVar2,0), 0 < iVar1) {
        iVar2 = iVar2 + iVar1;
        if (iVar2 == param_3) goto LAB_10001b5e;
      }
      iVar1 = Ordinal_111();
    } while (iVar1 == 0x2714);
LAB_10001b5e:
    if (iVar2 == param_3) {
      return 0;
    }
  }
  return 0xffffffff;
}



/* FUNCTION DCRecv ENTRY 10001b80 */

int DCRecv(int param_1,int param_2,int param_3)

{
  int iVar1;
  int iVar2;
  int iVar3;
  
                    /* 0x1b80  20  DCRecv */
  iVar1 = -1;
  iVar3 = 0;
  if (((param_1 != -1) && (param_2 != 0)) && (0 < param_3)) {
    while( true ) {
      iVar1 = Ordinal_16(param_1,param_2,param_3,0);
      if (0 < iVar1) break;
      if (iVar1 == 0) {
        return -1;
      }
      iVar2 = Ordinal_111();
      if (iVar2 != 0x2714) {
        iVar2 = Ordinal_111();
        if (iVar2 == 0x2733) {
          return 0;
        }
        iVar2 = Ordinal_111();
        if (iVar2 != 0x274c) {
          return iVar1;
        }
        Sleep(10);
      }
      iVar3 = iVar3 + 1;
      if (9 < iVar3) {
        return iVar1;
      }
    }
  }
  return iVar1;
}


