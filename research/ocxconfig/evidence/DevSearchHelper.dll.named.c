/* PROGRAM DevSearchHelper.dll BASE 10000000 */

/* FUNCTION GetDevList ENTRY 100018a0 */

void GetDevList(int param_1,DWORD *param_2)

{
  uint uVar1;
  uint uVar2;
  int iVar3;
  int iVar4;
  DWORD DVar5;
  DWORD DVar6;
  undefined4 *puVar7;
  byte *pbVar8;
  uint uVar9;
  byte *pbVar10;
  uint uVar11;
  undefined4 *puVar12;
  undefined4 *puVar13;
  char *_Format;
  undefined1 auStack_78c [4];
  uint local_788;
  DWORD *local_784;
  uint uStack_780;
  DWORD DStack_77c;
  int local_778;
  int local_774;
  void *local_76c;
  int local_768;
  uint uStack_75c;
  undefined1 auStack_758 [16];
  undefined4 auStack_748 [2];
  undefined2 uStack_740;
  undefined4 uStack_6fc;
  char acStack_6f8 [64];
  char acStack_6b8 [64];
  char acStack_678 [64];
  char acStack_638 [68];
  undefined4 uStack_5f4;
  undefined4 uStack_5f0;
  undefined4 uStack_5ec;
  undefined4 uStack_5e8;
  undefined4 uStack_5e4;
  char acStack_5e0 [17];
  undefined1 uStack_5cf;
  undefined1 uStack_5ce;
  undefined4 uStack_5cc;
  undefined2 uStack_5c8;
  undefined4 uStack_5c4;
  undefined1 local_5c0 [4];
  undefined4 uStack_5bc;
  undefined2 uStack_5b2;
  char acStack_530 [96];
  undefined1 uStack_4d0;
  undefined1 uStack_4cf;
  char acStack_470 [64];
  char acStack_430 [132];
  undefined4 uStack_3ac;
  undefined4 uStack_3a8;
  undefined4 uStack_3a4;
  undefined4 uStack_3a0;
  undefined4 uStack_39c;
  char acStack_398 [16];
  undefined4 uStack_388;
  undefined2 uStack_384;
  uint local_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 local_c;
  
                    /* 0x18a0  1  GetDevList */
  uVar11 = DAT_10006600;
  local_c = 0xffffffff;
  puStack_10 = &LAB_10003f6b;
  local_14 = ExceptionList;
  local_1c = DAT_1000601c ^ (uint)auStack_78c;
  uVar2 = DAT_1000601c ^ (uint)&stack0xfffff868;
  ExceptionList = &local_14;
  local_778 = param_1;
  local_784 = param_2;
  if (DAT_10006600 < DAT_100065fc) {
    _invalid_parameter_noinfo();
  }
  uVar9 = DAT_100065fc;
  if (DAT_10006600 < DAT_100065fc) {
    _invalid_parameter_noinfo();
  }
  if (uVar9 != uVar11) {
    DAT_10006600 = FUN_10002b10(uVar9,uVar2);
  }
  memset(local_5c0,0,0x5a0);
  FUN_100014e0();
  local_c = 0;
  if (local_76c == (void *)0x0) {
    iVar3 = 0;
  }
  else {
    iVar3 = local_768 - (int)local_76c >> 2;
  }
  printf("GetSockets count = %d\n",iVar3);
  local_788 = 0;
  while( true ) {
    if ((local_76c == (void *)0x0) || ((uint)(local_768 - (int)local_76c >> 2) <= local_788))
    goto LAB_10001dec;
    iVar3 = *(int *)((int)local_76c + local_788 * 4);
    local_774 = iVar3;
    if (iVar3 == -1) break;
    memset(local_5c0,0,0x5a0);
    uStack_5c4 = Ordinal_8(2);
    uStack_5bc = Ordinal_8(0x2001f013);
    uStack_5b2 = 0;
    iVar4 = FUN_10001370(0x5a0);
    if (iVar4 != 0) {
      _Format = "BroadCastSend fail \n";
      goto LAB_10001ddf;
    }
    memset(local_5c0,0,0x5a0);
    DVar5 = GetTickCount();
    DStack_77c = DVar5;
    printf("fd=%d \n",iVar3);
    DVar6 = GetTickCount();
    if (DVar6 - DVar5 < 0xbb9) {
LAB_10001a60:
      iVar3 = FUN_10001470(auStack_758);
      if ((iVar3 == 0x240) &&
         (iVar3 = Ordinal_8(uStack_5bc), uVar11 = DAT_100065fc, iVar3 == 0x3001f013)) {
        uStack_780 = 0xffffffff;
        uVar2 = DAT_10006600;
        if (DAT_10006600 < DAT_100065fc) {
          _invalid_parameter_noinfo();
          uVar2 = DAT_10006600;
        }
        do {
          uVar9 = uVar2;
          uStack_75c = uVar11;
          if (uVar2 < DAT_100065fc) {
            _invalid_parameter_noinfo();
            uVar9 = DAT_10006600;
          }
          if (uVar11 == uVar2) {
            memset(auStack_748,0,0x184);
            uStack_5ce = uStack_4cf;
            uStack_5cf = uStack_4d0;
            strncpy(acStack_678,acStack_530,0x40);
            strncpy(acStack_6f8,acStack_470,0x40);
            strncpy(acStack_638,"NOT DSP",0x40);
            strncpy(acStack_6b8,acStack_430,0x40);
            auStack_748[1] = uStack_388;
            uStack_5cc = uStack_388;
            uStack_6fc = uStack_3a8;
            uStack_5f0 = uStack_3a8;
            uStack_740 = uStack_384;
            uStack_5c8 = uStack_384;
            uStack_5ec = uStack_3a4;
            uStack_5e8 = uStack_3a0;
            uStack_5f4 = uStack_3ac;
            uStack_5e4 = uStack_39c;
            strncpy(acStack_5e0,acStack_398,0x10);
            FUN_10002160();
            if ((DAT_100065c4 != 0) && (puVar7 = malloc(0x184), puVar7 != (undefined4 *)0x0)) {
              memset(puVar7,0,0x184);
              puVar12 = auStack_748;
              puVar13 = puVar7;
              for (iVar3 = 0x61; iVar3 != 0; iVar3 = iVar3 + -1) {
                *puVar13 = *puVar12;
                puVar12 = puVar12 + 1;
                puVar13 = puVar13 + 1;
              }
              PostThreadMessageW(DAT_100065c4,0x4c8,0,(LPARAM)puVar7);
            }
            break;
          }
          uStack_780 = uStack_780 + 1;
          uVar2 = 6;
          pbVar10 = (byte *)&uStack_388;
          if (uVar9 <= uVar11) {
            _invalid_parameter_noinfo();
            uVar9 = DAT_10006600;
          }
          uVar1 = uStack_780;
          pbVar8 = (byte *)(uVar11 + 4);
          do {
            if (*(int *)pbVar8 != *(int *)pbVar10) goto LAB_10001b1e;
            uVar2 = uVar2 - 4;
            pbVar10 = pbVar10 + 4;
            pbVar8 = pbVar8 + 4;
          } while (3 < uVar2);
          if (uVar2 == 0) {
LAB_10001b83:
            iVar4 = 0;
          }
          else {
LAB_10001b1e:
            iVar3 = (uint)*pbVar8 - (uint)*pbVar10;
            uVar11 = uStack_75c;
            if (iVar3 == 0) {
              if (uVar2 == 1) goto LAB_10001b83;
              iVar3 = (uint)pbVar8[1] - (uint)pbVar10[1];
              if (iVar3 == 0) {
                if (uVar2 == 2) goto LAB_10001b83;
                iVar3 = (uint)pbVar8[2] - (uint)pbVar10[2];
                if (iVar3 == 0) {
                  if ((uVar2 == 3) || (iVar3 = (uint)pbVar8[3] - (uint)pbVar10[3], iVar3 == 0))
                  goto LAB_10001b83;
                }
              }
            }
            iVar4 = 1;
            if (iVar3 < 1) {
              iVar4 = -1;
            }
          }
          if (iVar4 == 0) goto LAB_10001ba4;
          if (uVar9 <= uVar11) {
            _invalid_parameter_noinfo();
            uVar9 = DAT_10006600;
          }
          uVar11 = uVar11 + 0x184;
          uVar2 = uVar9;
        } while( true );
      }
      goto LAB_10001da5;
    }
LAB_10001dbe:
    Ordinal_3(iVar3);
    local_788 = local_788 + 1;
  }
  _Format = "BroadCastOpen fail \n";
LAB_10001ddf:
  printf(_Format);
LAB_10001dec:
  if (((local_778 == 0) || (local_784 == (DWORD *)0x0)) ||
     (DStack_77c = *local_784, DStack_77c == 0)) {
    Sleep(100);
  }
  else if ((DAT_100065fc == 0) ||
          (DVar5 = (int)(DAT_10006600 - DAT_100065fc) / 0x184, (int)DVar5 < 1)) {
    *local_784 = 0;
  }
  else {
    DVar6 = DStack_77c;
    if ((int)DVar5 <= (int)DStack_77c) {
      *local_784 = DVar5;
      DVar6 = DVar5;
    }
    local_784 = (DWORD *)0x0;
    if (0 < (int)DVar6) {
      local_788 = 0;
      do {
        uVar11 = local_788;
        if ((DAT_100065fc == 0) ||
           ((DWORD *)((int)(DAT_10006600 - DAT_100065fc) / 0x184) <= local_784)) {
          _invalid_parameter_noinfo();
        }
        local_788 = local_788 + 0x184;
        local_784 = (DWORD *)((int)local_784 + 1);
        puVar7 = (undefined4 *)(DAT_100065fc + uVar11);
        puVar12 = (undefined4 *)(uVar11 + local_778);
        for (iVar3 = 0x61; iVar3 != 0; iVar3 = iVar3 + -1) {
          *puVar12 = *puVar7;
          puVar7 = puVar7 + 1;
          puVar12 = puVar12 + 1;
        }
      } while ((int)local_784 < (int)DVar6);
    }
  }
  if (local_76c != (void *)0x0) {
    operator_delete(local_76c);
  }
  ExceptionList = local_14;
  FUN_10003576();
  return;
LAB_10001ba4:
  if ((DAT_100065fc == 0) || ((uint)((int)(uVar9 - DAT_100065fc) / 0x184) <= uStack_780)) {
    _invalid_parameter_noinfo();
  }
  iVar3 = uVar1 * 0x184;
  *(undefined1 *)(iVar3 + 0x17a + DAT_100065fc) = uStack_4cf;
  if ((DAT_100065fc == 0) || ((uint)((int)(DAT_10006600 - DAT_100065fc) / 0x184) <= uVar1)) {
    _invalid_parameter_noinfo();
  }
  *(undefined1 *)(iVar3 + 0x179 + DAT_100065fc) = uStack_4d0;
LAB_10001da5:
  DVar5 = GetTickCount();
  iVar3 = local_774;
  if (3000 < DVar5 - DStack_77c) goto LAB_10001dbe;
  goto LAB_10001a60;
}


