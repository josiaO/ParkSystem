
/* FUNCTION FUN_1008e6f0 ENTRY 1008e6f0 */

void FUN_1008e6f0(undefined4 param_1)

{
  int iVar1;
  int unaff_EBX;
  undefined4 *puVar2;
  undefined4 *puVar3;
  undefined4 local_edc;
  undefined4 local_ed8;
  undefined4 local_ed4;
  undefined4 local_ed0;
  undefined4 local_ecc;
  undefined4 local_ec8 [52];
  undefined4 local_df8 [136];
  undefined4 local_bd8 [226];
  undefined4 local_850 [192];
  undefined4 local_550 [339];
  uint local_4;
  
  local_4 = DAT_10174ab0 ^ (uint)&local_edc;
  local_ed8 = *(undefined4 *)(unaff_EBX + 0x1d78);
  local_ed0 = *(undefined4 *)(unaff_EBX + 0x1d80);
  puVar2 = (undefined4 *)(unaff_EBX + 0x1b5c);
  puVar3 = local_df8;
  for (iVar1 = 0x87; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  local_ed4 = *(undefined4 *)(unaff_EBX + 0x1d7c);
  puVar2 = (undefined4 *)(unaff_EBX + 0x1d88);
  puVar3 = local_ec8;
  for (iVar1 = 0x33; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  local_edc = *(undefined4 *)(unaff_EBX + 0x1e54);
  puVar2 = (undefined4 *)(unaff_EBX + 0x1e58);
  puVar3 = local_550;
  for (iVar1 = 0x152; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  puVar2 = (undefined4 *)(unaff_EBX + 0x23a0);
  puVar3 = local_bd8;
  for (iVar1 = 0xe1; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  puVar2 = (undefined4 *)(unaff_EBX + 0x2724);
  puVar3 = local_850;
  for (iVar1 = 0xc0; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar3 = *puVar2;
    puVar2 = puVar2 + 1;
    puVar3 = puVar3 + 1;
  }
  local_ecc = *(undefined4 *)(unaff_EBX + 0x1d84);
  if (*(int *)(unaff_EBX + 0x2a24) != 5) {
    Net_SetHttpPushSetup(param_1,local_df8);
  }
  if (*(int *)(unaff_EBX + 0x2a28) != 5) {
    Net_SetHttpSetupExt(param_1,&local_ed8);
  }
  if (*(int *)(unaff_EBX + 0x2a2c) != 5) {
    Net_SetCloudParam(param_1,local_ec8);
  }
  if (*(int *)(unaff_EBX + 0x2a30) != 5) {
    Net_ImageQualitySetup(param_1,&local_edc);
  }
  if (*(int *)(unaff_EBX + 0x2a34) != 5) {
    _Net_DevPlatform_8(param_1,local_550);
  }
  if (*(int *)(unaff_EBX + 0x2a38) != 5) {
    _Net_PushCloudParam_8(param_1,local_bd8);
  }
  if (*(int *)(unaff_EBX + 0x2a3c) != 5) {
    _Net_JGWParam_8(param_1,local_850);
  }
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10073930 ENTRY 10073930 */

/* WARNING: Function: __alloca_probe_16 replaced with injection: alloca_probe */

void __fastcall FUN_10073930(int param_1)

{
  LPCWSTR pWVar1;
  UINT CodePage;
  uint uVar2;
  LRESULT LVar3;
  undefined4 uVar4;
  int iVar5;
  int iVar6;
  byte *pbVar7;
  byte *pbVar8;
  byte *pbVar9;
  undefined *puVar10;
  uint local_25c;
  LPCWSTR local_238;
  byte local_234 [2];
  undefined2 uStack_232;
  undefined4 local_230;
  undefined4 local_22c;
  undefined4 local_228;
  undefined2 local_224;
  undefined1 local_222;
  undefined2 local_220;
  undefined2 local_21e;
  undefined1 local_1f7;
  undefined1 local_1f6;
  undefined1 local_1f5;
  undefined1 local_1f4 [80];
  undefined1 local_1a4;
  undefined1 local_1a3;
  undefined1 local_1a2;
  undefined1 local_1a1;
  undefined1 local_1a0;
  undefined1 local_19f;
  undefined1 local_19e;
  undefined1 local_19c;
  undefined1 local_19b [126];
  undefined1 local_11d;
  undefined1 local_11c;
  undefined1 local_11b;
  undefined1 local_11a;
  undefined1 local_119 [65];
  undefined1 local_d8 [64];
  undefined1 local_98;
  undefined1 local_97 [63];
  undefined1 local_58 [68];
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_1012f25b;
  local_10 = ExceptionList;
  local_25c = DAT_10174ab0 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  pbVar9 = (byte *)(param_1 + 0x9c);
  pbVar8 = pbVar9;
  pbVar7 = local_234;
  local_14 = local_25c;
  for (iVar6 = 0x87; iVar6 != 0; iVar6 = iVar6 + -1) {
    *(int *)pbVar7 = *(int *)pbVar8;
    pbVar8 = pbVar8 + 4;
    pbVar7 = pbVar7 + 4;
  }
  CodePage = (*(code *)PTR_FUN_10175f80)();
  FUN_10004eb0(&PTR_1013b7d8);
  local_8 = 0;
  local_234[0] = (**(code **)(*(int *)(param_1 + 0x830) + 0x140))();
  FUN_100d5220(&local_238);
  pWVar1 = local_238;
  if (*(int *)(local_238 + -6) == 0) {
    puVar10 = &DAT_10149108;
    goto LAB_10074091;
  }
  iVar6 = lstrlenW(local_238);
  if (iVar6 + 1 < 0x40000000) {
    if (&stack0x00000000 == (undefined1 *)0x25c) goto LAB_10073a38;
    local_25c = local_25c & 0xffffff00;
    iVar6 = WideCharToMultiByte(CodePage,0,pWVar1,-1,(LPSTR)&local_25c,(iVar6 + 1) * 2,(LPCSTR)0x0,
                                (LPBOOL)0x0);
    uVar2 = -(uint)(iVar6 != 0) & (uint)&local_25c;
  }
  else {
LAB_10073a38:
    uVar2 = 0;
  }
  FUN_100f79a0(local_58,uVar2,0x3f);
  iVar6 = FUN_10095ae0();
  pWVar1 = local_238;
  if (iVar6 == 0) {
    local_230 = 0;
    local_22c = 0;
    local_228 = 0;
    local_224 = 0;
    local_222 = 0;
  }
  else {
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        if (&stack0x00000000 != (undefined1 *)0x25c) {
          local_25c = local_25c & 0xffffff00;
          iVar6 = WideCharToMultiByte(CodePage,0,pWVar1,-1,(LPSTR)&local_25c,(iVar6 + 1) * 2,
                                      (LPCSTR)0x0,(LPBOOL)0x0);
          FUN_100f79a0(&local_230,-(uint)(iVar6 != 0) & (uint)&local_25c,0xf);
          goto LAB_10073aff;
        }
      }
    }
    FUN_100f79a0(&local_230,0,0xf);
  }
LAB_10073aff:
  FUN_100d5220(&local_238);
  iVar6 = thunk_FUN_100f7ac4(local_238);
  if (0xfffe < iVar6 - 1U) {
    puVar10 = &DAT_1014911c;
    goto LAB_10074091;
  }
  uStack_232 = (undefined2)iVar6;
  FUN_100d5220(&local_238);
  uVar2 = thunk_FUN_100f7ac4(local_238);
  if (5 < uVar2) {
    puVar10 = &DAT_10149144;
    goto LAB_10074091;
  }
  local_1f5 = (undefined1)uVar2;
  LVar3 = SendMessageW(*(HWND *)(param_1 + 0x2798),0x147,0,0);
  switch(LVar3) {
  case 0:
    local_1f7 = 0;
    break;
  case 1:
    local_1a1 = 1;
    local_1f7 = 0;
    goto LAB_10073c03;
  case 2:
    local_1a1 = 0;
    local_19f = 1;
    local_1f7 = 0;
    goto LAB_10073c0a;
  case 3:
    local_1a1 = 0;
    local_19f = 0;
    local_11d = 1;
    local_1f7 = 0;
    goto switchD_10073b85_default;
  case 4:
    local_1f7 = 4;
    break;
  case 5:
    local_1f7 = 5;
    break;
  case 6:
    local_1f7 = 6;
    break;
  case 7:
    local_1f7 = 7;
    break;
  default:
    goto switchD_10073b85_default;
  }
  local_1a1 = 0;
LAB_10073c03:
  local_19f = 0;
LAB_10073c0a:
  local_11d = 0;
switchD_10073b85_default:
  local_1a3 = (**(code **)(*(int *)(param_1 + 0x2260) + 0x140))();
  local_1f6 = (**(code **)(*(int *)(param_1 + 0x2d08) + 0x140))();
  local_1a4 = (**(code **)(*(int *)(param_1 + 0xaf0) + 0x140))();
  FUN_100d5220(&local_238);
  iVar6 = thunk_FUN_100f7ac4(local_238);
  if (iVar6 - 1U < 0xffff) {
    local_220 = (undefined2)iVar6;
    FUN_100d5220(&local_238);
    local_1a2 = thunk_FUN_100f7ac4(local_238);
    FUN_100d5220(&local_238);
    pWVar1 = local_238;
    uVar4 = 0;
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        uVar4 = FUN_100024f0(&local_25c,pWVar1,(iVar6 + 1) * 2,CodePage);
      }
      else {
        uVar4 = 0;
      }
    }
    FUN_100f79a0(local_1f4,uVar4,0x4f);
    FUN_100d5220(&local_238);
    local_21e = thunk_FUN_100f7ac4(local_238);
    local_19c = (**(code **)(*(int *)(param_1 + 0xda8) + 0x140))();
    FUN_100d5220(&local_238);
    pWVar1 = local_238;
    uVar4 = 0;
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        uVar4 = FUN_100024f0(&local_25c,pWVar1,(iVar6 + 1) * 2,CodePage);
      }
      else {
        uVar4 = 0;
      }
    }
    FUN_100f79a0(local_19b,uVar4,0x7d);
    local_11c = (**(code **)(*(int *)(param_1 + 0x1010) + 0x140))();
    local_11b = (**(code **)(*(int *)(param_1 + 0x1220) + 0x140))();
    local_11a = (**(code **)(*(int *)(param_1 + 0x1430) + 0x140))();
    FUN_100d5220(&local_238);
    pWVar1 = local_238;
    uVar4 = 0;
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        uVar4 = FUN_100024f0(&local_25c,pWVar1,(iVar6 + 1) * 2,CodePage);
      }
      else {
        uVar4 = 0;
      }
    }
    FUN_100f79a0(local_119,uVar4,0x40);
    FUN_100d5220(&local_238);
    pWVar1 = local_238;
    uVar4 = 0;
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        uVar4 = FUN_100024f0(&local_25c,pWVar1,(iVar6 + 1) * 2,CodePage);
      }
      else {
        uVar4 = 0;
      }
    }
    FUN_100f79a0(local_d8,uVar4,0x3f);
    local_98 = (**(code **)(*(int *)(param_1 + 0x1698) + 0x140))();
    FUN_100d5220(&local_238);
    pWVar1 = local_238;
    uVar4 = 0;
    if (local_238 != (LPCWSTR)0x0) {
      iVar6 = lstrlenW(local_238);
      if (iVar6 + 1 < 0x40000000) {
        uVar4 = FUN_100024f0(&local_25c,pWVar1,(iVar6 + 1) * 2,CodePage);
      }
      else {
        uVar4 = 0;
      }
    }
    FUN_100f79a0(local_97,uVar4,0x3e);
    LVar3 = SendMessageW(*(HWND *)(param_1 + 0x2118),0x147,0,0);
    local_234[1] = (char)LVar3;
    LVar3 = SendMessageW(*(HWND *)(param_1 + 0x253c),0x147,0,0);
    local_1a0 = (char)LVar3;
    local_19e = (**(code **)(*(int *)(param_1 + 0x2890) + 0x140))();
    uVar2 = 0x21c;
    pbVar8 = local_234;
    pbVar7 = pbVar9;
    do {
      if (*(int *)pbVar8 != *(int *)pbVar7) goto LAB_10073fb8;
      uVar2 = uVar2 - 4;
      pbVar7 = pbVar7 + 4;
      pbVar8 = pbVar8 + 4;
    } while (3 < uVar2);
    if (uVar2 == 0) {
LAB_10074015:
      iVar5 = 0;
    }
    else {
LAB_10073fb8:
      iVar6 = (uint)*pbVar8 - (uint)*pbVar7;
      if (iVar6 == 0) {
        if (uVar2 == 1) goto LAB_10074015;
        iVar6 = (uint)pbVar8[1] - (uint)pbVar7[1];
        if (iVar6 == 0) {
          if (uVar2 == 2) goto LAB_10074015;
          iVar6 = (uint)pbVar8[2] - (uint)pbVar7[2];
          if (iVar6 == 0) {
            if ((uVar2 == 3) || (iVar6 = (uint)pbVar8[3] - (uint)pbVar7[3], iVar6 == 0))
            goto LAB_10074015;
          }
        }
      }
      iVar5 = 1;
      if (iVar6 < 1) {
        iVar5 = -1;
      }
    }
    if (iVar5 != 0) {
      iVar6 = FUN_10011f00();
      if ((*(int *)(iVar6 + 0x28) != -1) &&
         (iVar6 = Net_SetHttpPushSetup(*(int *)(iVar6 + 0x28),local_234), iVar6 == 0)) {
        pbVar8 = local_234;
        for (iVar6 = 0x87; iVar6 != 0; iVar6 = iVar6 + -1) {
          *(int *)pbVar9 = *(int *)pbVar8;
          pbVar8 = pbVar8 + 4;
          pbVar9 = pbVar9 + 4;
        }
        goto LAB_100740a4;
      }
    }
    pWVar1 = local_238 + -2;
    LOCK();
    iVar6 = *(int *)pWVar1;
    *(int *)pWVar1 = *(int *)pWVar1 + -1;
    UNLOCK();
  }
  else {
    puVar10 = &DAT_10149168;
LAB_10074091:
    FUN_10041b70(param_1,puVar10);
LAB_100740a4:
    pWVar1 = local_238 + -2;
    LOCK();
    iVar6 = *(int *)pWVar1;
    *(int *)pWVar1 = *(int *)pWVar1 + -1;
    UNLOCK();
  }
  local_8 = 0xffffffff;
  if (iVar6 == 1 || iVar6 + -1 < 0) {
    (**(code **)(**(int **)(local_238 + -8) + 4))(local_238 + -8);
  }
  ExceptionList = local_10;
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10099d40 ENTRY 10099d40 */

void FUN_10099d40(void)

{
  int *piVar1;
  code *pcVar2;
  uint uVar3;
  byte *pbVar4;
  int iVar5;
  int iVar6;
  byte *pbVar7;
  int unaff_EBX;
  undefined4 *puVar8;
  int iStack_50;
  undefined1 uStack_4c;
  undefined1 uStack_4b;
  undefined1 uStack_4a;
  undefined1 uStack_49;
  undefined4 uStack_48;
  byte local_44 [32];
  undefined2 uStack_24;
  undefined1 uStack_22;
  undefined1 uStack_21;
  undefined1 uStack_20;
  undefined1 uStack_1f;
  undefined1 uStack_1e;
  uint local_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 uStack_c;
  
  uStack_c = 0xffffffff;
  puStack_10 = &LAB_1012ebc8;
  local_14 = ExceptionList;
  local_1c = DAT_10174ab0 ^ (uint)&iStack_50;
  ExceptionList = &local_14;
  pcVar2 = *(code **)(*(int *)(unaff_EBX + 200) + 0x140);
  puVar8 = (undefined4 *)(unaff_EBX + 0x9c);
  pbVar4 = local_44;
  for (iVar6 = 10; iVar6 != 0; iVar6 = iVar6 + -1) {
    *(undefined4 *)pbVar4 = *puVar8;
    puVar8 = puVar8 + 1;
    pbVar4 = pbVar4 + 4;
  }
  uStack_1f = (*pcVar2)(DAT_10174ab0 ^ (uint)&stack0xffffffa8);
  uStack_1e = (**(code **)(*(int *)(unaff_EBX + 0x2d8) + 0x140))();
  FUN_10004eb0(&PTR_1013b7d8);
  uStack_c = 0;
  FUN_100d5220(&iStack_50);
  uVar3 = thunk_FUN_100f7ac4(iStack_50);
  if (uVar3 < 0x100) {
    uStack_21 = (undefined1)uVar3;
    FUN_100d5220(&iStack_50);
    uVar3 = thunk_FUN_100f7ac4(iStack_50);
    if (uVar3 < 0x100) {
      uStack_20 = (undefined1)uVar3;
      FUN_100d5220(&iStack_50);
      uVar3 = thunk_FUN_100f7ac4(iStack_50);
      if (uVar3 < 0x100) {
        uStack_22 = (undefined1)uVar3;
        FUN_100d5220(&iStack_50);
        iVar6 = thunk_FUN_100f7ac4(iStack_50);
        if (iVar6 - 1U < 0xffff) {
          uStack_24 = (undefined2)iVar6;
          iVar6 = FUN_10027720();
          if (iVar6 == 0) {
            uStack_4c = 0;
            uStack_4a = 0;
            uStack_4b = 0;
            uStack_49 = 0;
            FUN_100dac33(&uStack_4c,&uStack_4a,&uStack_4b,&uStack_49);
            FUN_100f9df8(local_44,0x20,"%d.%d.%d.%d",uStack_4c,uStack_4a,uStack_4b,uStack_49);
            uVar3 = 0x28;
            pbVar4 = (byte *)(unaff_EBX + 0x9c);
            pbVar7 = local_44;
            do {
              if (*(int *)pbVar7 != *(int *)pbVar4) goto LAB_10099f2d;
              uVar3 = uVar3 - 4;
              pbVar4 = pbVar4 + 4;
              pbVar7 = pbVar7 + 4;
            } while (3 < uVar3);
            if (uVar3 == 0) {
LAB_10099f8a:
              iVar5 = 0;
            }
            else {
LAB_10099f2d:
              iVar6 = (uint)*pbVar7 - (uint)*pbVar4;
              if (iVar6 == 0) {
                if (uVar3 == 1) goto LAB_10099f8a;
                iVar6 = (uint)pbVar7[1] - (uint)pbVar4[1];
                if (iVar6 == 0) {
                  if (uVar3 == 2) goto LAB_10099f8a;
                  iVar6 = (uint)pbVar7[2] - (uint)pbVar4[2];
                  if (iVar6 == 0) {
                    if ((uVar3 == 3) || (iVar6 = (uint)pbVar7[3] - (uint)pbVar4[3], iVar6 == 0))
                    goto LAB_10099f8a;
                  }
                }
              }
              iVar5 = 1;
              if (iVar6 < 1) {
                iVar5 = -1;
              }
            }
            if (iVar5 == 0) {
              FUN_10041b70();
              FUN_100027a0();
            }
            else {
              iVar6 = FUN_10011f00();
              uStack_48 = 1;
              if ((*(int *)(iVar6 + 0x28) == -1) ||
                 (iVar6 = Net_SetPushTargetSetup(*(int *)(iVar6 + 0x28),local_44), iVar6 != 0)) {
                uStack_48 = 0;
              }
              else {
                pbVar4 = local_44;
                puVar8 = (undefined4 *)(unaff_EBX + 0x9c);
                for (iVar6 = 10; iVar6 != 0; iVar6 = iVar6 + -1) {
                  *puVar8 = *(undefined4 *)pbVar4;
                  pbVar4 = pbVar4 + 4;
                  puVar8 = puVar8 + 1;
                }
              }
              FUN_10041b70();
              FUN_100027a0();
            }
            goto LAB_1009a08c;
          }
        }
      }
      FUN_10041b70();
      FUN_100027a0();
      goto LAB_1009a08c;
    }
    FUN_10041b70();
    piVar1 = (int *)(iStack_50 + -4);
    LOCK();
    iVar6 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
  }
  else {
    FUN_10041b70();
    piVar1 = (int *)(iStack_50 + -4);
    LOCK();
    iVar6 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
  }
  uStack_c = 0xffffffff;
  if (iVar6 == 1 || iVar6 + -1 < 0) {
    (**(code **)(**(int **)(iStack_50 + -0x10) + 4))((undefined4 *)(iStack_50 + -0x10));
  }
LAB_1009a08c:
  ExceptionList = local_14;
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10091080 ENTRY 10091080 */

void FUN_10091080(undefined4 param_1)

{
  int iVar1;
  int iVar2;
  int unaff_EBX;
  undefined4 *puVar3;
  undefined4 *puVar4;
  undefined1 auStack_dfc [4];
  undefined4 local_df8;
  undefined4 uStack_df4;
  undefined4 local_df0;
  undefined4 local_dec;
  undefined4 uStack_de8;
  undefined4 uStack_de4;
  undefined4 uStack_de0;
  undefined4 uStack_ddc;
  undefined4 uStack_dd8;
  undefined4 auStack_dd4 [10];
  undefined4 auStack_dac [15];
  undefined4 auStack_d70 [34];
  undefined4 auStack_ce8 [70];
  undefined4 auStack_bd0 [82];
  undefined4 auStack_a88 [128];
  undefined4 auStack_888 [202];
  undefined4 auStack_560 [343];
  uint local_4;
  
  local_4 = DAT_10174ab0 ^ (uint)auStack_dfc;
  local_df0 = *(undefined4 *)(unaff_EBX + 0x2dfc);
  local_dec = *(undefined4 *)(unaff_EBX + 0x2e00);
  if (*(int *)(unaff_EBX + 0x3bdc) != 5) {
    Net_ParkGatePulseSetup(param_1,&local_df0);
  }
  local_df8 = *(undefined4 *)(unaff_EBX + 0x2e04);
  if (*(int *)(unaff_EBX + 0x3be0) != 5) {
    Net_SetScreenSetup(param_1,&local_df8);
  }
  puVar3 = (undefined4 *)(unaff_EBX + 0x2e08);
  puVar4 = auStack_888;
  for (iVar1 = 0xc9; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (*(int *)(unaff_EBX + 0x3be4) != 5) {
    Net_SLedSetup(param_1,auStack_888);
  }
  uStack_df4 = *(undefined4 *)(unaff_EBX + 0x312c);
  if (*(int *)(unaff_EBX + 0x3be8) != 5) {
    Net_ParkNumSetup(param_1,&uStack_df4);
  }
  uStack_de8 = *(undefined4 *)(unaff_EBX + 0x3130);
  uStack_de4 = *(undefined4 *)(unaff_EBX + 0x3134);
  if (*(int *)(unaff_EBX + 0x3bec) != 5) {
    Net_SetXWCarinParam(param_1,&uStack_de8);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3bec);
  puVar3 = (undefined4 *)(unaff_EBX + 0x3138);
  puVar4 = auStack_a88;
  for (iVar2 = 0x80; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    Net_SJLedSetup(param_1,auStack_a88);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3bec);
  puVar3 = (undefined4 *)(unaff_EBX + 0x3338);
  puVar4 = auStack_ce8;
  for (iVar2 = 0x45; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    Net_DevInfoSetup(param_1,auStack_ce8);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3bf8);
  puVar3 = (undefined4 *)(unaff_EBX + 0x344c);
  puVar4 = auStack_560;
  for (iVar2 = 0x155; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    Net_LedSetup(param_1,auStack_560);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3bfc);
  puVar3 = (undefined4 *)(unaff_EBX + 0x39a0);
  puVar4 = auStack_bd0;
  for (iVar2 = 0x52; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    _Net_SLedSetup_WS_8(param_1,auStack_bd0);
  }
  puVar3 = (undefined4 *)(unaff_EBX + 0x39a0);
  puVar4 = auStack_dac;
  for (iVar1 = 0xf; iVar1 != 0; iVar1 = iVar1 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (*(int *)(unaff_EBX + 0x3c00) != 5) {
    Net_SLedSetupExt(param_1,auStack_dac);
  }
  uStack_de0 = *(undefined4 *)(unaff_EBX + 0x3b24);
  uStack_ddc = *(undefined4 *)(unaff_EBX + 0x3b28);
  uStack_dd8 = *(undefined4 *)(unaff_EBX + 0x3b2c);
  if (*(int *)(unaff_EBX + 0x3c04) != 5) {
    Net_SLedTfgSetup(param_1,&uStack_de0);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3c08);
  puVar3 = (undefined4 *)(unaff_EBX + 0x3b30);
  puVar4 = auStack_d70;
  for (iVar2 = 0x21; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    Net_LedDcSetup(param_1,auStack_d70);
  }
  iVar1 = *(int *)(unaff_EBX + 0x3c0c);
  puVar3 = (undefined4 *)(unaff_EBX + 0x3bb4);
  puVar4 = auStack_dd4;
  for (iVar2 = 10; iVar2 != 0; iVar2 = iVar2 + -1) {
    *puVar4 = *puVar3;
    puVar3 = puVar3 + 1;
    puVar4 = puVar4 + 1;
  }
  if (iVar1 != 5) {
    Net_SetPushTargetSetup(param_1,auStack_dd4);
  }
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10090870 ENTRY 10090870 */

/* WARNING: Function: __alloca_probe_16 replaced with injection: alloca_probe */

void FUN_10090870(int param_1,LPCWSTR param_2)

{
  LPCWSTR pWVar1;
  undefined4 uVar2;
  int iVar3;
  int iVar4;
  
  uVar2 = (*(code *)PTR_FUN_10175f80)();
  if (param_2 == (LPCWSTR)0x0) {
    uVar2 = 0;
  }
  else {
    iVar3 = lstrlenW(param_2);
    if (iVar3 + 1 < 0x40000000) {
      uVar2 = FUN_100024f0(&stack0xffffffec,param_2,(iVar3 + 1) * 2,uVar2);
    }
    else {
      uVar2 = 0;
    }
  }
  iVar3 = Net_AddCamera(uVar2);
  if (-1 < iVar3) {
    *(int *)(param_1 + 0x4c98) = iVar3;
    iVar4 = Net_ConnCamera(iVar3,30000,3);
    if (iVar4 != 0) {
      Net_DelCamera(iVar3);
    }
  }
  pWVar1 = param_2 + -2;
  LOCK();
  iVar3 = *(int *)pWVar1;
  *(int *)pWVar1 = *(int *)pWVar1 + -1;
  UNLOCK();
  if (iVar3 == 1 || iVar3 + -1 < 0) {
    (**(code **)(**(int **)(param_2 + -8) + 4))(param_2 + -8);
  }
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10080c40 ENTRY 10080c40 */

void __thiscall FUN_10080c40(int param_1,int param_2)

{
  int iVar1;
  int iVar2;
  undefined4 *puVar3;
  undefined4 *puVar4;
  undefined1 auStack_138 [4];
  undefined4 local_134;
  LPCRITICAL_SECTION local_130;
  _SYSTEMTIME _Stack_12c;
  WORD WStack_11c;
  undefined1 uStack_11a;
  undefined1 uStack_119;
  undefined1 uStack_118;
  undefined1 uStack_117;
  undefined1 uStack_116;
  undefined1 auStack_110 [2];
  undefined4 auStack_10e [66];
  uint local_4;
  
  local_4 = DAT_10174ab0 ^ (uint)auStack_138;
  local_130 = (LPCRITICAL_SECTION)(param_1 + 0x348);
  EnterCriticalSection(local_130);
  local_134 = 1;
  if (*(ushort *)(param_1 + 0x13c) == 0xffffffff) {
    local_134 = 0;
    goto LAB_10080d6c;
  }
  iVar1 = Net_AddCamera(param_2);
  if (iVar1 == -1) {
LAB_10080d51:
    local_134 = 0;
  }
  else {
    iVar2 = Net_ConnCamera(iVar1,30000,5);
    if (iVar2 != 0) goto LAB_10080d51;
    if (*(int *)(param_1 + 0x240) != 0) {
      iVar2 = Net_QueryTimeSetup(iVar1,&WStack_11c);
      if (iVar2 == 0) {
        GetLocalTime(&_Stack_12c);
        WStack_11c = _Stack_12c.wYear;
        uStack_118 = (undefined1)_Stack_12c.wHour;
        uStack_11a = (undefined1)_Stack_12c.wMonth;
        uStack_119 = (undefined1)_Stack_12c.wDay;
        uStack_117 = (undefined1)_Stack_12c.wMinute;
        uStack_116 = (undefined1)_Stack_12c.wSecond;
        Net_TimeSetup(iVar1,&WStack_11c);
      }
    }
    puVar3 = (undefined4 *)(param_1 + 0x13c);
    puVar4 = (undefined4 *)auStack_110;
    for (iVar2 = 0x40; iVar2 != 0; iVar2 = iVar2 + -1) {
      *puVar4 = *puVar3;
      puVar3 = puVar3 + 1;
      puVar4 = puVar4 + 1;
    }
    *(undefined2 *)puVar4 = *(undefined2 *)puVar3;
    puVar3 = (undefined4 *)(param_2 + 0x40);
    puVar4 = (undefined4 *)(auStack_110 + 2);
    for (iVar2 = 0x40; iVar2 != 0; iVar2 = iVar2 + -1) {
      *puVar4 = *puVar3;
      puVar3 = puVar3 + 1;
      puVar4 = puVar4 + 1;
    }
    iVar2 = Net_FileUpdate(iVar1,auStack_110);
    if (iVar2 != 0) goto LAB_10080d51;
  }
  if (iVar1 != -1) {
    Net_DisConnCamera(iVar1);
    Net_DelCamera(iVar1);
  }
LAB_10080d6c:
  LeaveCriticalSection(local_130);
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10080da0 ENTRY 10080da0 */

undefined4 FUN_10080da0(undefined4 param_1)

{
  LPCRITICAL_SECTION lpCriticalSection;
  int in_EAX;
  int iVar1;
  int iVar2;
  undefined4 uVar3;
  
  lpCriticalSection = (LPCRITICAL_SECTION)(in_EAX + 0x348);
  EnterCriticalSection(lpCriticalSection);
  uVar3 = 1;
  if (*(ushort *)(in_EAX + 0x13c) == 0xffffffff) {
    LeaveCriticalSection(lpCriticalSection);
    return 0;
  }
  iVar1 = Net_AddCamera(param_1);
  if (iVar1 != -1) {
    iVar2 = Net_ConnCamera(iVar1,30000,5);
    if (iVar2 == 0) {
      iVar2 = Net_BlackWhiteListSend(iVar1,in_EAX + 0x38);
      if (iVar2 == 0) goto LAB_10080e0a;
    }
  }
  uVar3 = 0;
LAB_10080e0a:
  if (iVar1 != -1) {
    Net_DisConnCamera(iVar1);
    Net_DelCamera(iVar1);
  }
  LeaveCriticalSection(lpCriticalSection);
  return uVar3;
}



/* FUNCTION FUN_100b4fb0 ENTRY 100b4fb0 */

undefined4 __thiscall FUN_100b4fb0(int param_1,undefined4 param_2,uint *param_3)

{
  int iVar1;
  ushort uVar2;
  uint uVar3;
  uint *puVar4;
  undefined4 *puVar5;
  LRESULT LVar6;
  ushort *puVar7;
  int iVar8;
  ushort *puVar9;
  int iVar10;
  WPARAM wParam;
  bool bVar11;
  HWND hWnd;
  ushort *local_34;
  ushort *puStack_30;
  uint local_2c;
  uint *local_28;
  LRESULT local_24;
  uint *local_20;
  int local_1c;
  void *local_14;
  undefined1 *puStack_10;
  uint local_c;
  
  local_c = 0xffffffff;
  puStack_10 = &LAB_101309d0;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  if (param_3 != (uint *)0x0) {
    local_1c = param_1;
    SendMessageW(*(HWND *)(param_1 + 0x263c),0x14b,0,0);
    FUN_100bb460(*(undefined4 *)(*(int *)(param_1 + 0x324) + 4));
    *(int *)(*(int *)(param_1 + 0x324) + 4) = *(int *)(param_1 + 0x324);
    *(undefined4 *)(param_1 + 0x328) = 0;
    *(undefined4 *)*(undefined4 *)(param_1 + 0x324) = *(undefined4 *)(param_1 + 0x324);
    *(int *)(*(int *)(param_1 + 0x324) + 8) = *(int *)(param_1 + 0x324);
    iVar8 = param_1 + 0x32c;
    FUN_100bb6a0(*(undefined4 *)(*(int *)(param_1 + 0x330) + 4));
    *(int *)(*(int *)(param_1 + 0x330) + 4) = *(int *)(param_1 + 0x330);
    *(undefined4 *)(param_1 + 0x334) = 0;
    *(undefined4 *)*(undefined4 *)(param_1 + 0x330) = *(undefined4 *)(param_1 + 0x330);
    *(int *)(*(int *)(param_1 + 0x330) + 8) = *(int *)(param_1 + 0x330);
    FUN_10004eb0(&PTR_1013b7d8);
    local_c = 0;
    local_2c = 0;
    if (*param_3 != 0) {
      local_20 = param_3 + 0x21;
      local_28 = param_3 + 1;
      do {
        if (0x1f < local_2c) break;
        uVar3 = *local_28;
        FUN_10002530(&local_34,L"%d.%d.%d.%d",uVar3 & 0xff,uVar3 >> 8 & 0xff,uVar3 >> 0x10 & 0xff,
                     uVar3 >> 0x18);
        local_24 = SendMessageW(*(HWND *)(param_1 + 0x263c),0x143,0,(LPARAM)local_34);
        puVar5 = (undefined4 *)FUN_100bb0b0();
        *puVar5 = 0;
        FUN_100bb140(iVar8);
        puVar4 = local_20;
        iVar1 = (int)local_20 + 1;
        do {
          uVar3 = *local_20;
          local_20 = (uint *)((int)local_20 + 1);
        } while ((char)uVar3 != '\0');
        iVar10 = (int)local_20 - iVar1;
        local_20 = (uint *)iVar1;
        FUN_10009100(puVar4,iVar10);
        local_28 = local_28 + 1;
        local_20 = puVar4 + 8;
        local_2c = local_2c + 1;
        param_1 = local_1c;
      } while (local_2c < *param_3);
    }
    Net_FindDevice(FUN_100b4d40,param_1);
    uVar3 = *(uint *)(param_1 + 0xc0);
    FUN_10002530(&local_34,L"%d.%d.%d.%d",uVar3 & 0xff,uVar3 >> 8 & 0xff,uVar3 >> 0x10 & 0xff,
                 uVar3 >> 0x18);
    FUN_10004eb0(&PTR_1013b7d8);
    local_c = CONCAT31(local_c._1_3_,1);
    FUN_100d83f6(puStack_30);
    wParam = 0;
    LVar6 = SendMessageW(*(HWND *)(param_1 + 0x263c),0x146,0,0);
    if (0 < LVar6) {
      do {
        FUN_100d76a9(wParam,&puStack_30);
        puVar7 = puStack_30;
        puVar9 = local_34;
        if (local_34 == (ushort *)0x0) {
                    /* WARNING: Subroutine does not return */
          FUN_100025f0(0x80004005);
        }
        do {
          uVar2 = *puVar7;
          bVar11 = uVar2 < *puVar9;
          if (uVar2 != *puVar9) {
LAB_100b521b:
            iVar8 = (1 - (uint)bVar11) - (uint)(bVar11 != 0);
            goto LAB_100b5220;
          }
          if (uVar2 == 0) break;
          uVar2 = puVar7[1];
          bVar11 = uVar2 < puVar9[1];
          if (uVar2 != puVar9[1]) goto LAB_100b521b;
          puVar7 = puVar7 + 2;
          puVar9 = puVar9 + 2;
        } while (uVar2 != 0);
        iVar8 = 0;
LAB_100b5220:
        if (iVar8 == 0) {
          hWnd = *(HWND *)(param_1 + 0x263c);
          goto LAB_100b525a;
        }
        wParam = wParam + 1;
        LVar6 = SendMessageW(*(HWND *)(param_1 + 0x263c),0x146,0,0);
      } while ((int)wParam < LVar6);
    }
    hWnd = *(HWND *)(param_1 + 0x263c);
    wParam = 0;
LAB_100b525a:
    SendMessageW(hWnd,0x14e,wParam,0);
    SendMessageW(*(HWND *)(param_1 + 0x263c),0x14f,1,0);
    thunk_FUN_100f998b(param_3);
    local_c = local_c & 0xffffff00;
    puVar7 = puStack_30 + -2;
    LOCK();
    iVar8 = *(int *)puVar7;
    *(int *)puVar7 = *(int *)puVar7 + -1;
    UNLOCK();
    if (iVar8 + -1 < 1) {
      (**(code **)(**(int **)(puStack_30 + -8) + 4))(puStack_30 + -8);
    }
    local_c = 0xffffffff;
    puVar7 = local_34 + -2;
    LOCK();
    iVar8 = *(int *)puVar7;
    *(int *)puVar7 = *(int *)puVar7 + -1;
    UNLOCK();
    if (iVar8 == 1 || iVar8 + -1 < 0) {
      (**(code **)(**(int **)(local_34 + -8) + 4))(local_34 + -8);
    }
  }
  ExceptionList = local_14;
  return 0;
}



/* FUNCTION FUN_100b6800 ENTRY 100b6800 */

/* WARNING: Function: __alloca_probe_16 replaced with injection: alloca_probe */

void __fastcall FUN_100b6800(int param_1)

{
  LPCWSTR pWVar1;
  char cVar2;
  int *piVar3;
  LRESULT LVar4;
  char *pcVar5;
  uint uVar6;
  int iVar7;
  int iVar8;
  byte *pbVar9;
  byte *pbVar10;
  HWND pHVar11;
  LPARAM LVar12;
  uint local_8c;
  undefined4 local_70;
  byte *local_6c;
  undefined4 local_68;
  undefined4 local_64;
  undefined4 local_60;
  undefined1 *local_5c;
  int local_58;
  int local_54;
  int local_50;
  uint local_4c;
  undefined *local_48;
  undefined4 local_44;
  LPCWSTR local_40;
  byte local_3c [36];
  int local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  int local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_1012e5b0;
  local_10 = ExceptionList;
  local_8c = DAT_10174ab0 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_6c = (byte *)(param_1 + 0x9c);
  pbVar10 = local_6c;
  pbVar9 = local_3c;
  local_14 = local_8c;
  for (iVar8 = 10; iVar8 != 0; iVar8 = iVar8 + -1) {
    *(int *)pbVar9 = *(int *)pbVar10;
    pbVar10 = pbVar10 + 4;
    pbVar9 = pbVar9 + 4;
  }
  local_64 = 1;
  local_58 = param_1;
  FUN_10004eb0();
  local_8 = 0;
  FUN_100d5220();
  iVar8 = FUN_10095ae0();
  if (iVar8 == 0) {
    FUN_10041b70();
  }
  else {
    local_60 = 0;
    local_70 = 0;
    local_68 = 0;
    iVar8 = FUN_100f7e99(local_40,L"%d.%d.%d.%d",&local_68,&local_70);
    if (iVar8 == 4) {
      local_44 = CONCAT13((undefined1)local_68,CONCAT12((undefined1)local_70,(ushort)(byte)local_60)
                         );
      local_18 = local_44;
      local_3c[0] = (**(code **)(*(int *)(param_1 + 0x23b8) + 0x140))();
      local_5c = (undefined1 *)(*(code *)PTR_FUN_10175f80)();
      piVar3 = (int *)FUN_100d8606();
      if (piVar3 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
        FUN_100025f0();
      }
      local_54 = (**(code **)(*piVar3 + 0xc))();
      local_54 = local_54 + 0x10;
      iVar8 = 0;
      local_8 = CONCAT31(local_8._1_3_,1);
      LVar4 = SendMessageW(*(HWND *)(param_1 + 0x263c),0x146,0,0);
      if (0 < LVar4) {
        do {
          FUN_100d76a9();
          cVar2 = FUN_10004910();
          if (cVar2 != '\0') {
            local_48 = (undefined *)SendMessageW(*(HWND *)(param_1 + 0x263c),0x147,0,0);
            pcVar5 = (char *)FUN_100bb0b0();
            local_3c[2] = *pcVar5;
            param_1 = local_58;
            goto LAB_100b69ca;
          }
          iVar8 = iVar8 + 1;
          LVar4 = SendMessageW(*(HWND *)(param_1 + 0x263c),0x146,0,0);
        } while (iVar8 < LVar4);
      }
      local_3c[2] = '\x01';
LAB_100b69ca:
      piVar3 = (int *)FUN_100d8606();
      if (piVar3 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
        FUN_100025f0();
      }
      local_50 = (**(code **)(*piVar3 + 0xc))();
      local_50 = local_50 + 0x10;
      local_8._0_1_ = 2;
      FUN_100d5220();
      uVar6 = thunk_FUN_100f7ac4();
      if (uVar6 < 0x7d1) {
        local_3c[3] = ((char)((int)uVar6 / 10) + (char)((int)uVar6 >> 0x1f)) -
                      (char)((longlong)(int)uVar6 * 0x66666667 >> 0x3f);
        uVar6 = 0x28;
        pbVar10 = local_3c;
        pbVar9 = local_6c;
        do {
          if (*(int *)pbVar10 != *(int *)pbVar9) goto LAB_100b6a58;
          uVar6 = uVar6 - 4;
          pbVar9 = pbVar9 + 4;
          pbVar10 = pbVar10 + 4;
        } while (3 < uVar6);
        if (uVar6 == 0) {
LAB_100b6ab5:
          iVar7 = 0;
        }
        else {
LAB_100b6a58:
          iVar8 = (uint)*pbVar10 - (uint)*pbVar9;
          if (iVar8 == 0) {
            if (uVar6 == 1) goto LAB_100b6ab5;
            iVar8 = (uint)pbVar10[1] - (uint)pbVar9[1];
            if (iVar8 == 0) {
              if (uVar6 == 2) goto LAB_100b6ab5;
              iVar8 = (uint)pbVar10[2] - (uint)pbVar9[2];
              if (iVar8 == 0) {
                if ((uVar6 == 3) || (iVar8 = (uint)pbVar10[3] - (uint)pbVar9[3], iVar8 == 0))
                goto LAB_100b6ab5;
              }
            }
          }
          iVar7 = 1;
          if (iVar8 < 1) {
            iVar7 = -1;
          }
        }
        if (iVar7 == 0) {
          local_8._0_1_ = 1;
          piVar3 = (int *)(local_50 + -4);
          LOCK();
          iVar8 = *piVar3;
          *piVar3 = *piVar3 + -1;
          UNLOCK();
          if (iVar8 == 1 || iVar8 + -1 < 0) {
            (**(code **)(**(int **)(local_50 + -0x10) + 4))();
          }
          local_8 = (uint)local_8._1_3_ << 8;
          piVar3 = (int *)(local_54 + -4);
          LOCK();
          iVar8 = *piVar3;
          *piVar3 = *piVar3 + -1;
          UNLOCK();
          if (iVar8 + -1 < 1) {
            (**(code **)(**(int **)(local_54 + -0x10) + 4))();
          }
          local_8 = 0xffffffff;
          pWVar1 = local_40 + -2;
          LOCK();
          iVar8 = *(int *)pWVar1;
          *(int *)pWVar1 = *(int *)pWVar1 + -1;
          UNLOCK();
          if (iVar8 == 1 || iVar8 + -1 < 0) {
            (**(code **)(**(int **)(local_40 + -8) + 4))();
          }
          goto LAB_100b706e;
        }
        iVar8 = FUN_10011f00();
        local_4c = 1;
        if ((*(int *)(iVar8 + 0x28) == -1) || (iVar8 = Net_SetAssCamera(), iVar8 != 0)) {
          local_4c = 0;
          local_48 = &DAT_10151e60;
        }
        else {
          local_48 = &DAT_10151e5c;
        }
        pWVar1 = local_40;
        if (local_40 == (LPCWSTR)0x0) {
          uVar6 = 0;
        }
        else {
          iVar8 = lstrlenW(local_40);
          if (iVar8 + 1 < 0x40000000) {
            if (&stack0x00000000 != (undefined1 *)0x8c) {
              local_8c = local_8c & 0xffffff00;
              iVar8 = WideCharToMultiByte((UINT)local_5c,0,pWVar1,-1,(LPSTR)&local_8c,
                                          (iVar8 + 1) * 2,(LPCSTR)0x0,(LPBOOL)0x0);
              uVar6 = -(uint)(iVar8 != 0) & (uint)&local_8c;
              goto LAB_100b6bbf;
            }
          }
          uVar6 = 0;
        }
LAB_100b6bbf:
        Net_Log("SetAssCamera:ip=%s, ucEnable=%d, ucType=%d, %s\n",uVar6,local_3c[2]);
        if (local_4c == 0) {
          local_64 = 0;
        }
        else {
          pHVar11 = *(HWND *)(param_1 + 0x2850);
          pbVar10 = local_3c;
          pbVar9 = local_6c;
          for (iVar8 = 10; iVar8 != 0; iVar8 = iVar8 + -1) {
            *(int *)pbVar9 = *(int *)pbVar10;
            pbVar10 = pbVar10 + 4;
            pbVar9 = pbVar9 + 4;
          }
          SendMessageW(pHVar11,0x465,0,*(LPARAM *)(param_1 + 0xc0));
          if ((byte)(local_44._3_1_ - 1U) < 0x7e) {
            pHVar11 = *(HWND *)(param_1 + 0x28a4);
            LVar12 = -0x1000000;
          }
          else if ((byte)(local_44._3_1_ + 0x80U) < 0x40) {
            pHVar11 = *(HWND *)(param_1 + 0x28a4);
            LVar12 = -0x10000;
          }
          else {
            pHVar11 = *(HWND *)(param_1 + 0x28a4);
            LVar12 = -0x100;
          }
          SendMessageW(pHVar11,0x465,0,LVar12);
          local_4c = 0;
          local_48 = (undefined *)0x0;
          SendMessageW(*(HWND *)(param_1 + 0x2850),0x466,0,(LPARAM)&local_4c);
          SendMessageW(*(HWND *)(param_1 + 0x28a4),0x466,0,(LPARAM)&local_48);
          local_4c = (local_4c & 0xff0000 | local_4c >> 0x10) >> 8 |
                     (local_4c << 0x10 | local_4c & 0xff00) << 8;
          local_48 = (undefined *)
                     (((uint)local_48 & 0xff0000 | (uint)local_48 >> 0x10) >> 8 |
                     ((int)local_48 << 0x10 | (uint)local_48 & 0xff00) << 8);
          uVar6 = (uint)local_48 & local_4c;
          SendMessageW(*(HWND *)(param_1 + 0x28f8),0x465,0,
                       (uVar6 & 0xff0000 | 0x100) >> 8 | (uVar6 << 0x10 | uVar6 & 0xff00) << 8);
          if (local_3c[2] == '\0') {
            if (local_3c[0] == 1) {
              FUN_10011f00();
              iVar8 = FUN_100165c0();
              if ((iVar8 != 0) &&
                 (((iVar8 = FUN_10011f00(), *(int *)(iVar8 + 0x2c) == -1 ||
                   (iVar8 = Net_QueryVideoState(), iVar8 != 0)) ||
                  (*(int *)(param_1 + 0x38b0) != local_18)))) {
                *(uint *)(param_1 + 0x338) = (uint)*(byte *)(param_1 + 0x9e);
                local_5c = &stack0xffffff6c;
                FUN_10004d20(local_40 + -8);
                local_8._0_1_ = 3;
                FUN_10011f00();
                local_8._0_1_ = 2;
                FUN_100138f0();
                FUN_10011f00();
                FUN_10014190();
                FUN_10011f00();
                iVar8 = FUN_10013ec0();
                if (iVar8 != 0) {
                  FUN_100b79f0();
                  param_1 = local_58;
                }
              }
            }
            else {
LAB_100b6f34:
              FUN_10011f00();
              FUN_10014190();
              FUN_100c7160();
            }
          }
          else {
            if (local_3c[0] != 1) goto LAB_100b6f34;
            iVar8 = FUN_10011f00();
            if ((((*(int *)(iVar8 + 0x2c) == -1) || (iVar8 = Net_QueryConnState(), iVar8 != 0)) ||
                (iVar8 = FUN_10011f00(), *(int *)(iVar8 + 0x2c) == -1)) ||
               ((iVar8 = Net_QueryVideoState(), iVar8 != 0 ||
                (*(int *)(param_1 + 0x38b0) != local_18)))) {
              *(uint *)(param_1 + 0x338) = (uint)*(byte *)(param_1 + 0x9e);
              local_5c = &stack0xffffff6c;
              FUN_10004d20(local_40 + -8);
              local_8._0_1_ = 4;
              FUN_10011f00();
              local_8 = CONCAT31(local_8._1_3_,2);
              FUN_100138f0();
              FUN_10011f00();
              FUN_10014190();
              FUN_10011f00();
              iVar8 = FUN_10013ec0();
              if (iVar8 != 0) {
                FUN_100b79f0();
                param_1 = local_58;
              }
              iVar8 = FUN_10011f00();
              *(uint *)(param_1 + 0x1390) = (uint)(*(int *)(iVar8 + 0x144) != 0);
              FUN_10011f00();
              FUN_10013af0();
              local_8 = CONCAT31(local_8._1_3_,5);
              cVar2 = FUN_1000fa30();
              if (((cVar2 == '\0') && (cVar2 = FUN_1000fa30(), cVar2 == '\0')) &&
                 (cVar2 = FUN_1000fa30(), cVar2 == '\0')) {
                *(undefined4 *)(param_1 + 0x42c8) = 1;
                *(undefined4 *)(param_1 + 0x15b0) = 1;
              }
              else {
                *(undefined4 *)(param_1 + 0x42c8) = 0;
                *(undefined4 *)(param_1 + 0x15b0) = 0;
              }
              FUN_100b8560();
              local_8._0_1_ = 2;
              piVar3 = (int *)(local_44 + -4);
              LOCK();
              iVar8 = *piVar3;
              *piVar3 = *piVar3 + -1;
              UNLOCK();
              if (iVar8 == 1 || iVar8 + -1 < 0) {
                (**(code **)(**(int **)(local_44 + -0x10) + 4))();
              }
            }
          }
          *(int *)(param_1 + 0x38b0) = local_18;
          LVar12 = 3;
          if (*(char *)(param_1 + 0x9e) == '\0') {
            LVar12 = 1;
          }
          PostMessageW(*(HWND *)(param_1 + 0x20),0x5b8,0,LVar12);
        }
        local_8._0_1_ = 1;
        piVar3 = (int *)(local_50 + -4);
        LOCK();
        iVar8 = *piVar3;
        *piVar3 = *piVar3 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(local_50 + -0x10) + 4))();
        }
        local_8 = (uint)local_8._1_3_ << 8;
        piVar3 = (int *)(local_54 + -4);
        LOCK();
        iVar8 = *piVar3;
        *piVar3 = *piVar3 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(local_54 + -0x10) + 4))();
        }
        local_8 = 0xffffffff;
        pWVar1 = local_40 + -2;
        LOCK();
        iVar8 = *(int *)pWVar1;
        *(int *)pWVar1 = *(int *)pWVar1 + -1;
        UNLOCK();
        if (iVar8 == 1 || iVar8 + -1 < 0) {
          (**(code **)(**(int **)(local_40 + -8) + 4))();
        }
        goto LAB_100b706e;
      }
      FUN_10041b70();
      local_8._0_1_ = 1;
      piVar3 = (int *)(local_50 + -4);
      LOCK();
      iVar8 = *piVar3;
      *piVar3 = *piVar3 + -1;
      UNLOCK();
      if (iVar8 + -1 < 1) {
        (**(code **)(**(int **)(local_50 + -0x10) + 4))();
      }
      local_8 = (uint)local_8._1_3_ << 8;
      piVar3 = (int *)(local_54 + -4);
      LOCK();
      iVar8 = *piVar3;
      *piVar3 = *piVar3 + -1;
      UNLOCK();
      if (iVar8 + -1 < 1) {
        (**(code **)(**(int **)(local_54 + -0x10) + 4))();
      }
    }
    else {
      FUN_10041b70();
    }
  }
  local_8 = 0xffffffff;
  pWVar1 = local_40 + -2;
  LOCK();
  iVar8 = *(int *)pWVar1;
  *(int *)pWVar1 = *(int *)pWVar1 + -1;
  UNLOCK();
  if (iVar8 == 1 || iVar8 + -1 < 0) {
    (**(code **)(**(int **)(local_40 + -8) + 4))();
  }
LAB_100b706e:
  ExceptionList = local_10;
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_100b6480 ENTRY 100b6480 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

int FUN_100b6480(void)

{
  int *piVar1;
  char *pcVar2;
  char cVar3;
  int iVar4;
  LPARAM lParam;
  int unaff_EDI;
  WPARAM WStack_28;
  int iVar5;
  int iStack_20;
  undefined1 *puStack_1c;
  void *local_14;
  undefined1 *puStack_10;
  uint uStack_c;
  
  uStack_c = 0xffffffff;
  puStack_10 = &LAB_1012e600;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  pcVar2 = (char *)(unaff_EDI + 0x9c);
  pcVar2[0] = '\0';
  pcVar2[1] = '\0';
  pcVar2[2] = '\0';
  pcVar2[3] = '\0';
  *(undefined4 *)(unaff_EDI + 0xa0) = 0;
  *(undefined4 *)(unaff_EDI + 0xa4) = 0;
  *(undefined4 *)(unaff_EDI + 0xa8) = 0;
  *(undefined4 *)(unaff_EDI + 0xac) = 0;
  *(undefined4 *)(unaff_EDI + 0xb0) = 0;
  *(undefined4 *)(unaff_EDI + 0xb4) = 0;
  *(undefined4 *)(unaff_EDI + 0xb8) = 0;
  *(undefined4 *)(unaff_EDI + 0xbc) = 0;
  *(undefined4 *)(unaff_EDI + 0xc0) = 0;
  iVar4 = FUN_10011f00();
  iVar5 = 1;
  if ((*(int *)(iVar4 + 0x28) == -1) || (iVar4 = Net_QueryAssCamera(), iVar4 != 0)) {
    iVar5 = 0;
  }
  iVar4 = FUN_10011f00();
  WStack_28 = 1;
  if (*(int *)(iVar4 + 0x28) == -1) {
LAB_100b652b:
    WStack_28 = 0;
  }
  else {
    _DAT_1017b0f0 = 0;
    iVar4 = Net_QueryAssCameraStatus();
    if ((iVar4 != 0) || (DAT_1017b0f0 == '\0')) goto LAB_100b652b;
  }
  if (iVar5 == 0) {
    ExceptionList = local_14;
    return 0;
  }
  lParam = 3;
  if (*(char *)(unaff_EDI + 0x9e) == '\0') {
    lParam = 0;
  }
  PostMessageW(*(HWND *)(unaff_EDI + 0x20),0x5b8,0,lParam);
  PostMessageW(*(HWND *)(unaff_EDI + 0x20),0x5a4,WStack_28,1);
  puStack_1c = *(undefined1 **)(unaff_EDI + 0xc0);
  FUN_10004eb0();
  uStack_c = 0;
  FUN_10002530(&iStack_20,L"%d.%d.%d.%d",(uint)puStack_1c >> 0x18,(uint)puStack_1c >> 0x10 & 0xff);
  if (*(char *)(unaff_EDI + 0x9e) == '\0') {
    if (*pcVar2 == '\x01') {
      if (WStack_28 != 0) {
        FUN_10011f00();
        iVar4 = FUN_10016590();
        if ((iVar4 == 0) || (*(int *)(unaff_EDI + 0x38b0) != *(int *)(unaff_EDI + 0xc0))) {
          puStack_1c = &stack0xffffffc4;
          *(uint *)(unaff_EDI + 0x338) = (uint)*(byte *)(unaff_EDI + 0x9e);
          FUN_10004d00(&iStack_20);
          uStack_c._0_1_ = 1;
          FUN_10011f00();
          uStack_c = (uint)uStack_c._1_3_ << 8;
          FUN_100138f0();
          FUN_10011f00();
          FUN_10014190();
          FUN_10011f00();
          FUN_10013ec0();
        }
      }
      goto LAB_100b67b0;
    }
  }
  else if (*pcVar2 == '\x01') {
    iVar4 = FUN_10011f00();
    if ((*(int *)(iVar4 + 0x2c) != -1) && (iVar4 = Net_QueryConnState(), iVar4 == 0)) {
      FUN_10011f00();
      iVar4 = FUN_10016590();
      if ((iVar4 != 0) && (*(int *)(unaff_EDI + 0x38b0) == *(int *)(unaff_EDI + 0xc0)))
      goto LAB_100b67b0;
    }
    *(uint *)(unaff_EDI + 0x338) = (uint)*(byte *)(unaff_EDI + 0x9e);
    puStack_1c = &stack0xffffffc4;
    FUN_10004d20(iStack_20 + -0x10);
    uStack_c._0_1_ = 2;
    FUN_10011f00();
    uStack_c._0_1_ = 0;
    FUN_100138f0();
    FUN_10011f00();
    FUN_10014190();
    FUN_10011f00();
    FUN_10013ec0();
    iVar4 = FUN_10011f00();
    *(uint *)(unaff_EDI + 0x1390) = (uint)(*(int *)(iVar4 + 0x144) != 0);
    FUN_10011f00();
    FUN_10013af0();
    uStack_c = CONCAT31(uStack_c._1_3_,3);
    cVar3 = FUN_1000fa30();
    if (((cVar3 == '\0') && (cVar3 = FUN_1000fa30(), cVar3 == '\0')) &&
       (cVar3 = FUN_1000fa30(), cVar3 == '\0')) {
      *(undefined4 *)(unaff_EDI + 0x42c8) = 1;
      *(undefined4 *)(unaff_EDI + 0x15b0) = 1;
    }
    else {
      *(undefined4 *)(unaff_EDI + 0x42c8) = 0;
      *(undefined4 *)(unaff_EDI + 0x15b0) = 0;
    }
    FUN_100b8560();
    uStack_c = uStack_c & 0xffffff00;
    piVar1 = (int *)(WStack_28 - 4);
    LOCK();
    iVar4 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
    if (iVar4 == 1 || iVar4 + -1 < 0) {
      (**(code **)(**(int **)(WStack_28 - 0x10) + 4))();
    }
    goto LAB_100b67b0;
  }
  FUN_10011f00();
  FUN_10014190();
  FUN_100c7160();
LAB_100b67b0:
  uStack_c = 0xffffffff;
  *(undefined4 *)(unaff_EDI + 0x38b0) = *(undefined4 *)(unaff_EDI + 0xc0);
  piVar1 = (int *)(iStack_20 + -4);
  LOCK();
  iVar4 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar4 == 1 || iVar4 + -1 < 0) {
    (**(code **)(**(int **)(iStack_20 + -0x10) + 4))();
  }
  ExceptionList = local_14;
  return iVar5;
}



/* FUNCTION FUN_10016110 ENTRY 10016110 */

undefined4 FUN_10016110(byte param_1)

{
  int iVar1;
  int unaff_ESI;
  undefined4 local_8;
  uint local_4;
  
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    local_8 = 0;
    local_4 = (uint)param_1;
    iVar1 = Net_ImageSnap(*(int *)(unaff_ESI + 0x28),&local_8);
    if (iVar1 == 0) {
      *(undefined4 *)(unaff_ESI + 0xd4) = 1;
      FUN_10002610(&PTR_1013b7d8,0);
      return 1;
    }
    *(undefined4 *)(unaff_ESI + 0xd4) = 0;
  }
  return 0;
}



/* FUNCTION FUN_10016630 ENTRY 10016630 */

undefined4 FUN_10016630(void)

{
  undefined4 uVar1;
  int iVar2;
  undefined4 uVar3;
  int unaff_ESI;
  uint uVar4;
  
  uVar3 = 1;
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    uVar1 = 0;
    if (*(int *)(unaff_ESI + 0x104) != 0) {
      uVar1 = *(undefined4 *)(*(int *)(unaff_ESI + 0x104) + 0x20);
    }
    iVar2 = Net_StartVideo(*(int *)(unaff_ESI + 0x28),*(undefined4 *)(unaff_ESI + 0x118),uVar1);
    if (iVar2 == 0) {
      iVar2 = Net_ShowPlateRegion(*(undefined4 *)(unaff_ESI + 0x28),0);
      if (iVar2 == 0) {
        uVar4 = 0;
        while( true ) {
          iVar2 = *(int *)(unaff_ESI + 0x1c);
          if ((iVar2 == 0) || ((uint)(*(int *)(unaff_ESI + 0x20) - iVar2 >> 2) <= uVar4))
          goto LAB_100166c1;
          if ((iVar2 == 0) || ((uint)(*(int *)(unaff_ESI + 0x20) - iVar2 >> 2) <= uVar4)) {
            FUN_100f8677();
          }
          iVar2 = Net_AddPlayWindow(*(undefined4 *)(unaff_ESI + 0x28),
                                    *(undefined4 *)(*(int *)(unaff_ESI + 0x1c) + uVar4 * 4));
          if (iVar2 != 0) break;
          uVar4 = uVar4 + 1;
        }
        uVar3 = 0;
LAB_100166c1:
        *(undefined4 *)(unaff_ESI + 0xe0) = 1;
        *(undefined4 *)(unaff_ESI + 0x128) = 0;
        return uVar3;
      }
    }
  }
  return 0;
}



/* FUNCTION FUN_100144d0 ENTRY 100144d0 */

undefined4 FUN_100144d0(void)

{
  undefined4 uVar1;
  int iVar2;
  int unaff_ESI;
  
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    if (*(int *)(unaff_ESI + 0xdc) != 0) {
      return 1;
    }
    *(undefined4 *)(unaff_ESI + 0xe0) = 0;
    uVar1 = 0;
    if (*(int *)(unaff_ESI + 0x104) != 0) {
      uVar1 = *(undefined4 *)(*(int *)(unaff_ESI + 0x104) + 0x20);
    }
    iVar2 = Net_StartVideo(*(int *)(unaff_ESI + 0x28),*(undefined4 *)(unaff_ESI + 0x118),uVar1);
    if (iVar2 == 0) {
      *(undefined4 *)(unaff_ESI + 0xe0) = 1;
      iVar2 = Net_ShowPlateRegion(*(undefined4 *)(unaff_ESI + 0x28),0);
      if (iVar2 == 0) {
        *(undefined4 *)(unaff_ESI + 0xdc) = 1;
        return 1;
      }
    }
  }
  return 0;
}



/* FUNCTION FUN_10013ec0 ENTRY 10013ec0 */

/* WARNING: Function: __alloca_probe_16 replaced with injection: alloca_probe */

void __fastcall FUN_10013ec0(int param_1)

{
  short sVar1;
  LPCWSTR lpString;
  UINT UVar2;
  int iVar3;
  short *psVar4;
  short *psVar5;
  undefined1 local_20c [120];
  undefined1 local_194 [136];
  CHAR local_10c [64];
  CHAR local_cc [196];
  uint local_8;
  
  local_8 = DAT_10174ab0 ^ (uint)local_194;
  if (*(int *)(param_1 + 0x2c) != -1) goto LAB_1001416a;
  UVar2 = (*(code *)PTR_FUN_10175f80)();
  lpString = *(LPCWSTR *)(param_1 + 0x48);
  if (*(int *)(param_1 + 0x30) == 0) {
    if (lpString != (LPCWSTR)0x0) {
      iVar3 = lstrlenW(lpString);
      if (iVar3 + 1 < 0x40000000) {
        if (&stack0x00000000 != (undefined1 *)0x220) {
          WideCharToMultiByte(UVar2,0,lpString,-1,&stack0xfffffde0,(iVar3 + 1) * 2,(LPCSTR)0x0,
                              (LPBOOL)0x0);
          iVar3 = Net_AddAssCamera();
          goto LAB_10013fb4;
        }
      }
    }
    iVar3 = Net_AddAssCamera();
  }
  else {
    if (lpString != (LPCWSTR)0x0) {
      iVar3 = lstrlenW(lpString);
      if (iVar3 + 1 < 0x40000000) {
        if (&stack0x00000000 != (undefined1 *)0x220) {
          WideCharToMultiByte(UVar2,0,lpString,-1,&stack0xfffffde0,(iVar3 + 1) * 2,(LPCSTR)0x0,
                              (LPBOOL)0x0);
        }
      }
    }
    iVar3 = Net_AddCamera();
  }
LAB_10013fb4:
  *(int *)(param_1 + 0x2c) = iVar3;
  if (iVar3 == -1) goto LAB_1001416a;
  if (*(int *)(param_1 + 0x30) == 1) {
    iVar3 = Net_ConnCamera2(iVar3,30000,5);
    if (iVar3 != 0) {
      Net_DisConnCamera(*(undefined4 *)(param_1 + 0x2c));
      Net_DelCamera(*(undefined4 *)(param_1 + 0x2c));
      *(undefined4 *)(param_1 + 0x2c) = 0xffffffff;
      goto LAB_1001416a;
    }
    FUN_100fcb30(local_20c,0,0x204);
    iVar3 = Net_QuerySysVersion(*(undefined4 *)(param_1 + 0x2c),local_20c);
    if (iVar3 != 0) goto LAB_10014146;
    UVar2 = (*(code *)PTR_FUN_10175f80)();
    iVar3 = lstrlenA(local_cc);
    if (iVar3 + 1 < 0x40000000) {
      if (&stack0x00000000 == (undefined1 *)0x228) goto LAB_10014078;
      iVar3 = MultiByteToWideChar(UVar2,0,local_cc,-1,(LPWSTR)&stack0xfffffdd8,iVar3 + 1);
      psVar4 = (short *)(-(uint)(iVar3 != 0) & (uint)&stack0xfffffdd8);
    }
    else {
LAB_10014078:
      psVar4 = (short *)0x0;
    }
    if (psVar4 == (short *)0x0) {
      iVar3 = 0;
    }
    else {
      psVar5 = psVar4;
      do {
        sVar1 = *psVar5;
        psVar5 = psVar5 + 1;
      } while (sVar1 != 0);
      iVar3 = (int)psVar5 - (int)(psVar4 + 1) >> 1;
    }
    FUN_10002610(psVar4,iVar3);
    iVar3 = lstrlenA(local_10c);
    if (iVar3 + 1 < 0x40000000) {
      if (&stack0x00000000 == (undefined1 *)0x228) goto LAB_100140f2;
      iVar3 = MultiByteToWideChar(UVar2,0,local_10c,-1,(LPWSTR)&stack0xfffffdd8,iVar3 + 1);
      psVar4 = (short *)(-(uint)(iVar3 != 0) & (uint)&stack0xfffffdd8);
    }
    else {
LAB_100140f2:
      psVar4 = (short *)0x0;
    }
    if (psVar4 == (short *)0x0) {
      iVar3 = 0;
    }
    else {
      psVar5 = psVar4;
      do {
        sVar1 = *psVar5;
        psVar5 = psVar5 + 1;
      } while (sVar1 != 0);
      iVar3 = (int)psVar5 - (int)(psVar4 + 1) >> 1;
    }
    FUN_10002610(psVar4,iVar3);
    iVar3 = thunk_FUN_100f7ac4(*(undefined4 *)(param_1 + 0xb8));
    *(uint *)(param_1 + 0x144) = (uint)(299 < iVar3);
    *(uint *)(param_1 + 0x14c) = (uint)(299 < iVar3);
  }
LAB_10014146:
  if (*(int *)(param_1 + 0x17c) != 0) {
    PostMessageW(*(HWND *)(*(int *)(param_1 + 0x17c) + 0x20),0x5a2,1,*(LPARAM *)(param_1 + 0x2c));
  }
LAB_1001416a:
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10013bb0 ENTRY 10013bb0 */

/* WARNING: Function: __alloca_probe_16 replaced with injection: alloca_probe */

void __fastcall FUN_10013bb0(int param_1)

{
  char *pcVar1;
  LPCWSTR pWVar2;
  UINT CodePage;
  int iVar3;
  uint uVar4;
  LPARAM lParam;
  HWND hWnd;
  WPARAM local_14;
  
  if (*(int *)(param_1 + 0x28) != -1) goto LAB_10013ea3;
  CodePage = (*(code *)PTR_FUN_10175f80)();
  pWVar2 = *(LPCWSTR *)(param_1 + 0x44);
  if (pWVar2 != (LPCWSTR)0x0) {
    iVar3 = lstrlenW(pWVar2);
    if (iVar3 + 1 < 0x40000000) {
      if (&stack0x00000000 != (undefined1 *)0x24) {
        WideCharToMultiByte(CodePage,0,pWVar2,-1,&stack0xffffffdc,(iVar3 + 1) * 2,(LPCSTR)0x0,
                            (LPBOOL)0x0);
      }
    }
  }
  iVar3 = Net_AddCamera();
  *(int *)(param_1 + 0x28) = iVar3;
  if (iVar3 == -1) {
    FUN_100f7705();
    return;
  }
  iVar3 = Net_RegReportMessEx();
  if (iVar3 != 0) goto LAB_10013ea3;
  if (*(int *)(param_1 + 0xd8) == 0) {
    pWVar2 = *(LPCWSTR *)(param_1 + 0x40);
    if (pWVar2 == (LPCWSTR)0x0) {
      local_14 = 0;
    }
    else {
      iVar3 = lstrlenW(pWVar2);
      if (iVar3 + 1 < 0x40000000) {
        if (&stack0x00000000 != (undefined1 *)0x34) {
          iVar3 = WideCharToMultiByte(CodePage,0,pWVar2,-1,&stack0xffffffcc,(iVar3 + 1) * 2,
                                      (LPCSTR)0x0,(LPBOOL)0x0);
          local_14 = -(uint)(iVar3 != 0) & (uint)&stack0xffffffcc;
          goto LAB_10013cc8;
        }
      }
      local_14 = 0;
    }
LAB_10013cc8:
    pWVar2 = *(LPCWSTR *)(param_1 + 0x3c);
    if (pWVar2 == (LPCWSTR)0x0) {
LAB_10013d13:
      uVar4 = 0;
    }
    else {
      iVar3 = lstrlenW(pWVar2);
      if (0x3fffffff < iVar3 + 1) goto LAB_10013d13;
      if (&stack0x00000000 == (undefined1 *)0x34) goto LAB_10013d13;
      iVar3 = WideCharToMultiByte(CodePage,0,pWVar2,-1,&stack0xffffffcc,(iVar3 + 1) * 2,(LPCSTR)0x0,
                                  (LPBOOL)0x0);
      uVar4 = -(uint)(iVar3 != 0) & (uint)&stack0xffffffcc;
    }
    iVar3 = Net_ConnCameraEx(*(undefined4 *)(param_1 + 0x28),*(undefined2 *)(param_1 + 0x34),3,uVar4
                             ,local_14);
    if (iVar3 != 0) {
      Net_DisConnCamera(*(undefined4 *)(param_1 + 0x28));
      Net_DelCamera(*(undefined4 *)(param_1 + 0x28));
      *(undefined4 *)(param_1 + 0x28) = 0xffffffff;
      goto LAB_10013ea3;
    }
    *(undefined4 *)(param_1 + 0xd8) = 1;
    pcVar1 = (char *)(param_1 + 0x198);
    if (*(int *)(param_1 + 0x28) == -1) {
LAB_10013e02:
      iVar3 = FUN_10011f00();
      if (*(int *)(iVar3 + 0x110) != 0) {
        hWnd = *(HWND *)(*(int *)(iVar3 + 0x110) + 0x20);
        lParam = 0;
        local_14 = 0;
LAB_10013e1e:
        PostMessageW(hWnd,0x590,local_14,lParam);
      }
    }
    else {
      FUN_100fcb30(pcVar1,0,800);
      iVar3 = Net_FuntionListRsp(*(undefined4 *)(param_1 + 0x28),pcVar1);
      if (iVar3 != 0) goto LAB_10013e02;
      lParam = 0;
      local_14 = 0;
      if (*(char *)(param_1 + 0x1b8) != '\0') {
        local_14 = *(WPARAM *)(param_1 + 0x1bc);
      }
      if (*pcVar1 != '\0') {
        uVar4 = *(uint *)(param_1 + 0x19c);
        if ((uVar4 & 0x20000) == 0) {
          if ((uVar4 & 0x8000) == 0) {
            if ((uVar4 & 0x10000) == 0) {
              if ((uVar4 & 0x200) != 0) {
                lParam = 1;
              }
            }
            else {
              lParam = 2;
            }
          }
          else {
            lParam = 3;
          }
        }
        else {
          lParam = 4;
        }
      }
      iVar3 = FUN_10011f00();
      if (*(int *)(iVar3 + 0x110) != 0) {
        hWnd = *(HWND *)(*(int *)(iVar3 + 0x110) + 0x20);
        goto LAB_10013e1e;
      }
    }
    FUN_100144d0();
  }
  Net_RegImageRecvEx2(*(undefined4 *)(param_1 + 0x28),FUN_10010620,param_1);
  Net_BlackWhiteListSendReportMess(*(undefined4 *)(param_1 + 0x28),FUN_10011150,0);
  Net_RegFileUpdateProgress(*(undefined4 *)(param_1 + 0x28),&LAB_100112b0,0);
  if (*(int *)(param_1 + 0xd8) != 0) {
    if (*(int *)(param_1 + 0xe8) != 0) {
      PostMessageW(*(HWND *)(*(int *)(param_1 + 0xe8) + 0x20),0x465,0,0);
    }
    if (*(int *)(param_1 + 0xe4) != 0) {
      PostMessageW(*(HWND *)(*(int *)(param_1 + 0xe4) + 0x20),0x5c2,1,0);
    }
  }
LAB_10013ea3:
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10012090 ENTRY 10012090 */

void FUN_10012090(void)

{
  int iVar1;
  int unaff_ESI;
  
  if ((*(int *)(unaff_ESI + 0x28) != -1) &&
     (iVar1 = Net_StopRecord(*(int *)(unaff_ESI + 0x28)), iVar1 == 0)) {
    *(undefined4 *)(unaff_ESI + 0xcc) = 0;
  }
  if ((*(int *)(unaff_ESI + 0x2c) != -1) &&
     (iVar1 = Net_StopRecord(*(int *)(unaff_ESI + 0x2c)), iVar1 == 0)) {
    *(undefined4 *)(unaff_ESI + 0xd0) = 0;
  }
  if (*(HANDLE *)(unaff_ESI + 0x11c) != (HANDLE)0x0) {
    TerminateThread(*(HANDLE *)(unaff_ESI + 0x11c),0);
    CloseHandle(*(HANDLE *)(unaff_ESI + 0x11c));
    *(undefined4 *)(unaff_ESI + 0x11c) = 0;
  }
  if (*(HANDLE *)(unaff_ESI + 0x120) != (HANDLE)0x0) {
    TerminateThread(*(HANDLE *)(unaff_ESI + 0x120),0);
    CloseHandle(*(HANDLE *)(unaff_ESI + 0x120));
    *(undefined4 *)(unaff_ESI + 0x120) = 0;
  }
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    Net_StopVideo(*(int *)(unaff_ESI + 0x28));
  }
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    Net_DisConnCamera(*(int *)(unaff_ESI + 0x28));
    Net_DelCamera(*(undefined4 *)(unaff_ESI + 0x28));
    *(undefined4 *)(unaff_ESI + 0x28) = 0xffffffff;
    *(undefined4 *)(unaff_ESI + 0xdc) = 0;
    *(undefined4 *)(unaff_ESI + 0xd8) = 0;
  }
  if ((*(int *)(unaff_ESI + 0x2c) != -1) &&
     (iVar1 = Net_StopVideo(*(int *)(unaff_ESI + 0x2c)), iVar1 == 0)) {
    if ((*(int *)(unaff_ESI + 0x30) == 1) &&
       (iVar1 = Net_DisConnCamera(*(undefined4 *)(unaff_ESI + 0x2c)), iVar1 != 0)) {
      return;
    }
    iVar1 = Net_DelCamera(*(undefined4 *)(unaff_ESI + 0x2c));
    if (iVar1 == 0) {
      *(undefined4 *)(unaff_ESI + 0x2c) = 0xffffffff;
    }
  }
  return;
}



/* FUNCTION FUN_1008fc90 ENTRY 1008fc90 */

void __fastcall FUN_1008fc90(int param_1)

{
  int *piVar1;
  int iVar2;
  LRESULT LVar3;
  int iVar4;
  undefined4 uVar5;
  int iVar6;
  undefined **appuStack_b0 [29];
  int iStack_3c;
  void *pvStack_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 uStack_c;
  
  uStack_c = 0xffffffff;
  puStack_10 = &LAB_10130ae6;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  *(undefined4 *)(param_1 + 0x1b3c) = 0;
  *(undefined4 *)(param_1 + 0x1b40) = 0;
  *(undefined4 *)(param_1 + 0x1b54) = 0;
  *(undefined4 *)(param_1 + 7000) = 0;
  *(undefined4 *)(param_1 + 0x2a24) = 0;
  *(undefined4 *)(param_1 + 0x2a28) = 0;
  *(undefined4 *)(param_1 + 0x2a2c) = 0;
  *(undefined4 *)(param_1 + 0x2a30) = 0;
  *(undefined4 *)(param_1 + 0x2a34) = 0;
  *(undefined4 *)(param_1 + 0x2a38) = 0;
  *(undefined4 *)(param_1 + 0x2a3c) = 0;
  *(undefined4 *)(param_1 + 0x2be0) = 0;
  *(undefined4 *)(param_1 + 0x2be4) = 0;
  *(undefined4 *)(param_1 + 0x2be8) = 0;
  *(undefined4 *)(param_1 + 0x2bec) = 0;
  *(undefined4 *)(param_1 + 0x2bf0) = 0;
  *(undefined4 *)(param_1 + 0x2bf4) = 0;
  *(undefined4 *)(param_1 + 0x2c54) = 0;
  *(undefined4 *)(param_1 + 0x2c58) = 0;
  *(undefined4 *)(param_1 + 0x2c5c) = 0;
  *(undefined4 *)(param_1 + 0x2c60) = 0;
  *(undefined4 *)(param_1 + 0x2c64) = 0;
  *(undefined4 *)(param_1 + 0x2c68) = 0;
  *(undefined4 *)(param_1 + 0x2dd4) = 0;
  *(undefined4 *)(param_1 + 0x2dd8) = 0;
  *(undefined4 *)(param_1 + 0x2ddc) = 0;
  *(undefined4 *)(param_1 + 0x2de0) = 0;
  *(undefined4 *)(param_1 + 0x2de4) = 0;
  *(undefined4 *)(param_1 + 0x2de8) = 0;
  *(undefined4 *)(param_1 + 0x2dec) = 0;
  *(undefined4 *)(param_1 + 0x2df0) = 0;
  *(undefined4 *)(param_1 + 0x2df8) = 0;
  *(undefined4 *)(param_1 + 0x3bf8) = 0;
  *(undefined4 *)(param_1 + 0x3bfc) = 0;
  *(undefined4 *)(param_1 + 0x3c00) = 0;
  *(undefined4 *)(param_1 + 0x3c04) = 0;
  *(undefined4 *)(param_1 + 0x3c08) = 0;
  *(undefined4 *)(param_1 + 0x3c0c) = 0;
  *(undefined4 *)(param_1 + 0x4c98) = 0xffffffff;
  Net_DisConnCamera();
  Net_DelCamera();
  *(undefined4 *)(param_1 + 0x4c98) = 0xffffffff;
  iVar2 = FUN_10011f00();
  if (((*(int *)(iVar2 + 0xdc) == 0) || (*(int *)(iVar2 + 0xd8) == 0)) ||
     (*(int *)(iVar2 + 0x28) == -1)) {
    FUN_10004eb0(&DAT_1013e62c);
    FUN_100abc40(appuStack_b0);
    local_14 = (void *)0x0;
    FUN_100d8024();
    appuStack_b0[0] = CTipDlg::vftable;
    local_14 = (void *)0x1;
    piVar1 = (int *)(iStack_3c + -4);
    LOCK();
    iVar2 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
    if (iVar2 == 1 || iVar2 + -1 < 0) {
      (**(code **)(**(int **)(iStack_3c + -0x10) + 4))();
    }
    local_14 = (void *)0xffffffff;
    FUN_100d790d();
    ExceptionList = pvStack_1c;
    return;
  }
  iVar2 = 0;
  iVar6 = 0;
  LVar3 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
  if (0 < LVar3) {
    do {
      iVar4 = FUN_100dac77();
      if (iVar4 == 1) {
        iVar2 = iVar2 + 1;
      }
      iVar6 = iVar6 + 1;
      LVar3 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
    } while (iVar6 < LVar3);
    if (iVar2 != 0) {
      if (*(HANDLE *)(param_1 + 0x4c94) != (HANDLE)0x0) {
        TerminateThread(*(HANDLE *)(param_1 + 0x4c94),0);
        CloseHandle(*(HANDLE *)(param_1 + 0x4c94));
        *(undefined4 *)(param_1 + 0x4c94) = 0;
      }
      uVar5 = FUN_100f78e4(0,0,&LAB_1008ff40,param_1);
      *(undefined4 *)(param_1 + 0x4c94) = uVar5;
      ExceptionList = pvStack_1c;
      return;
    }
  }
  FUN_10041b70();
  ExceptionList = pvStack_1c;
  return;
}



/* FUNCTION FUN_1008ff60 ENTRY 1008ff60 */

/* WARNING: Heritage AFTER dead removal. Example location: s0xffffff60 : 0x100903b6 */
/* WARNING: Restarted to delay deadcode elimination for space: stack */

undefined4 FUN_1008ff60(int param_1)

{
  int *piVar1;
  ushort uVar2;
  char cVar3;
  LRESULT LVar4;
  int iVar5;
  ushort *puVar6;
  ushort *puVar7;
  int iVar8;
  bool bVar9;
  int *piStackY_ac;
  int in_stack_ffffff60;
  int iStack_7c;
  int iStack_78;
  int iStack_74;
  int iStack_70;
  ushort *puStack_6c;
  int iStack_68;
  int iStack_40;
  ushort *puStack_3c;
  int iStack_30;
  int iStack_2c;
  void *local_14;
  undefined1 *puStack_10;
  int iStack_c;
  
  iStack_c = 0xffffffff;
  puStack_10 = &LAB_10130ab0;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  iVar8 = 0;
  LVar4 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
  if (0 < LVar4) {
    do {
      FUN_100d9afe();
      iVar8 = iVar8 + 1;
      LVar4 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
    } while (iVar8 < LVar4);
  }
  FUN_1008a870();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  iVar8 = (**(code **)(*(int *)(param_1 + 0x3c10) + 0x140))();
  if ((((((iVar8 == 0) || (iVar8 = FUN_1008e1d0(), iVar8 != 0)) &&
        ((iVar8 = (**(code **)(*(int *)(param_1 + 0x3e20) + 0x140))(), iVar8 == 0 ||
         (iVar8 = FUN_1008e380(), iVar8 != 0)))) &&
       ((iVar8 = (**(code **)(*(int *)(param_1 + 0x4030) + 0x140))(), iVar8 == 0 ||
        (iVar8 = FUN_1008e4b0(), iVar8 != 0)))) &&
      ((iVar8 = (**(code **)(*(int *)(param_1 + 0x4240) + 0x140))(), iVar8 == 0 ||
       (iVar8 = FUN_1008e890(), iVar8 != 0)))) &&
     (((iVar8 = (**(code **)(*(int *)(param_1 + 0x4450) + 0x140))(), iVar8 == 0 ||
       (iVar8 = FUN_1008ebe0(), iVar8 != 0)) &&
      ((iVar8 = (**(code **)(*(int *)(param_1 + 0x4660) + 0x140))(), iVar8 == 0 ||
       (iVar8 = FUN_1008ef30(), iVar8 != 0)))))) {
    iVar8 = (**(code **)(*(int *)(param_1 + 0x4870) + 0x140))();
    if ((iVar8 == 0) || (iVar8 = FUN_1008f1b0(), iVar8 != 0)) {
      iVar8 = (**(code **)(*(int *)(param_1 + 0x4a80) + 0x140))();
      if ((iVar8 == 0) || (iVar8 = FUN_10090c60(), iVar8 != 0)) {
        FUN_10004eb0();
        iStack_c = 0;
        FUN_10004eb0();
        iStack_c._0_1_ = 1;
        FUN_10004eb0();
        iStack_c._0_1_ = 2;
        FUN_10004eb0();
        iStack_c._0_1_ = 3;
        FUN_10011f00();
        FUN_10013ad0();
        iStack_c._0_1_ = 4;
        FUN_10011f00();
        FUN_10013ab0();
        iStack_c._0_1_ = 5;
        FUN_10011f00();
        FUN_10013a70();
        iStack_c = CONCAT31(iStack_c._1_3_,6);
        FUN_10004d20(iStack_78 + -0x10);
        cVar3 = FUN_100aecd0();
        if (cVar3 == '\0') {
          FUN_10002610();
        }
        else {
          FUN_10002530();
        }
        iStack_68 = 0;
        LVar4 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
        if (0 < LVar4) {
          do {
            iVar5 = FUN_100dac77();
            iVar8 = in_stack_ffffff60;
            if (iVar5 != 0) {
              FUN_10002610();
              FUN_10002610();
              FUN_10002610();
              FUN_10002610();
              FUN_100da267();
              iStack_c._0_1_ = 7;
              FUN_10004e30();
              iStack_c._0_1_ = 6;
              piVar1 = (int *)(iStack_30 + -4);
              LOCK();
              iVar8 = *piVar1;
              *piVar1 = *piVar1 + -1;
              UNLOCK();
              if (iVar8 == 1 || iVar8 + -1 < 0) {
                (**(code **)(**(int **)(iStack_30 + -0x10) + 4))();
              }
              FUN_100da267();
              iStack_c._0_1_ = 8;
              FUN_10004e30();
              iStack_c._0_1_ = 6;
              piVar1 = (int *)(iStack_2c + -4);
              LOCK();
              iVar8 = *piVar1;
              *piVar1 = *piVar1 + -1;
              UNLOCK();
              if (iVar8 == 1 || iVar8 + -1 < 0) {
                (**(code **)(**(int **)(iStack_2c + -0x10) + 4))();
              }
              FUN_100da267();
              iStack_c._0_1_ = 9;
              FUN_10004e30();
              iStack_c = CONCAT31(iStack_c._1_3_,6);
              LOCK();
              iVar8 = in_stack_ffffff60 + -1;
              UNLOCK();
              if (in_stack_ffffff60 == 1 || in_stack_ffffff60 + -1 < 0) {
                (**(code **)(*piStackY_ac + 4))();
              }
              puVar6 = puStack_6c;
              puVar7 = puStack_3c;
              if (puStack_3c == (ushort *)0x0) {
                    /* WARNING: Subroutine does not return */
                FUN_100025f0();
              }
              do {
                uVar2 = *puVar6;
                bVar9 = uVar2 < *puVar7;
                if (uVar2 != *puVar7) {
LAB_10090406:
                  iVar5 = (1 - (uint)bVar9) - (uint)(bVar9 != 0);
                  goto LAB_1009040b;
                }
                if (uVar2 == 0) break;
                uVar2 = puVar6[1];
                bVar9 = uVar2 < puVar7[1];
                if (uVar2 != puVar7[1]) goto LAB_10090406;
                puVar6 = puVar6 + 2;
                puVar7 = puVar7 + 2;
              } while (uVar2 != 0);
              iVar5 = 0;
LAB_1009040b:
              if ((((iVar5 == 0) && (iStack_78 != 0)) && (-1 < *(int *)(iStack_74 + -0xc))) &&
                 ((iVar5 = FUN_100f8b5d(), iVar5 != 0 && (iVar5 - iStack_74 >> 1 == 0)))) {
                cVar3 = FUN_10004910();
                FUN_100d9afe();
                FUN_10004d20();
                iVar5 = FUN_10090870();
                if (-1 < iVar5) {
                  FUN_100d9afe();
                  iVar5 = (**(code **)(*(int *)(param_1 + 0x3c10) + 0x140))();
                  if ((iVar5 != 0) && (iVar5 = FUN_1008e280(), iVar5 == 0)) {
                    FUN_10036b90();
                  }
                  if (cVar3 == '\0') {
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x3e20) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008e430(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4030) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008e6f0(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4240) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008ea70(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4450) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008edc0(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4660) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008f490(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4870) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_1008f400(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                    iVar5 = (**(code **)(*(int *)(param_1 + 0x4a80) + 0x140))();
                    if ((iVar5 != 0) && (iVar5 = FUN_10091080(), iVar5 == 0)) {
                      FUN_10036b90();
                    }
                  }
                  if (*(int *)(iStack_7c + -0xc) == 0) {
                    FUN_10002610();
                  }
                  else {
                    FUN_1000fe10();
                  }
                  FUN_100d9afe();
                  *(undefined4 *)(param_1 + 0x4c98) = 0xffffffff;
                  Net_DisConnCamera();
                  Net_DelCamera();
                  *(undefined4 *)(param_1 + 0x4c98) = 0xffffffff;
                  goto LAB_100906aa;
                }
              }
              FUN_100d9afe();
            }
LAB_100906aa:
            iStack_68 = iStack_68 + 1;
            LVar4 = SendMessageW(*(HWND *)(param_1 + 0xbc),0x1004,0,0);
            in_stack_ffffff60 = iVar8;
          } while (iStack_68 < LVar4);
        }
        iStack_c._0_1_ = 5;
        piVar1 = (int *)(iStack_40 + -4);
        LOCK();
        iVar8 = *piVar1;
        *piVar1 = *piVar1 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(iStack_40 + -0x10) + 4))();
        }
        iStack_c._0_1_ = 4;
        piVar1 = (int *)(iStack_78 + -4);
        LOCK();
        iVar8 = *piVar1;
        *piVar1 = *piVar1 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(iStack_78 + -0x10) + 4))();
        }
        iStack_c._0_1_ = 3;
        puVar6 = puStack_3c + -2;
        LOCK();
        iVar8 = *(int *)puVar6;
        *(int *)puVar6 = *(int *)puVar6 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(puStack_3c + -8) + 4))();
        }
        iStack_c._0_1_ = 2;
        piVar1 = (int *)(iStack_7c + -4);
        LOCK();
        iVar8 = *piVar1;
        *piVar1 = *piVar1 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(iStack_7c + -0x10) + 4))();
        }
        iStack_c._0_1_ = 1;
        piVar1 = (int *)(iStack_74 + -4);
        LOCK();
        iVar8 = *piVar1;
        *piVar1 = *piVar1 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(iStack_74 + -0x10) + 4))();
        }
        iStack_c = (uint)iStack_c._1_3_ << 8;
        puVar6 = puStack_6c + -2;
        LOCK();
        iVar8 = *(int *)puVar6;
        *(int *)puVar6 = *(int *)puVar6 + -1;
        UNLOCK();
        if (iVar8 + -1 < 1) {
          (**(code **)(**(int **)(puStack_6c + -8) + 4))();
        }
        iStack_c = 0xffffffff;
        piVar1 = (int *)(iStack_70 + -4);
        LOCK();
        iVar8 = *piVar1;
        *piVar1 = *piVar1 + -1;
        UNLOCK();
        if (iVar8 == 1 || iVar8 + -1 < 0) {
          (**(code **)(**(int **)(iStack_70 + -0x10) + 4))();
        }
        goto LAB_10090804;
      }
    }
  }
  FUN_10041b70();
LAB_10090804:
  FUN_1008a870();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  FUN_100d84cc();
  ExceptionList = local_14;
  return 0;
}



/* FUNCTION FUN_10088f50 ENTRY 10088f50 */

void __fastcall FUN_10088f50(undefined4 *param_1)

{
  int *piVar1;
  int iVar2;
  undefined4 uVar3;
  uint uVar4;
  undefined4 *puVar5;
  void *unaff_EBX;
  void *local_c;
  undefined1 *puStack_8;
  undefined4 local_4;
  
  puStack_8 = &LAB_1011d9b8;
  local_c = ExceptionList;
  uVar4 = DAT_10174ab0 ^ (uint)&stack0xffffffe0;
  ExceptionList = &local_c;
  *param_1 = COperatorDlg::vftable;
  local_4 = 0x30;
  if ((int *)param_1[0x366] != (int *)0x0) {
    (**(code **)(*(int *)param_1[0x366] + 4))(1,uVar4);
    param_1[0x366] = 0;
  }
  if ((HANDLE)param_1[0x367] != (HANDLE)0x0) {
    TerminateThread((HANDLE)param_1[0x367],0);
    CloseHandle((HANDLE)param_1[0x367]);
    param_1[0x367] = 0;
  }
  if ((HANDLE)param_1[0x1324] != (HANDLE)0x0) {
    TerminateThread((HANDLE)param_1[0x1324],0);
    CloseHandle((HANDLE)param_1[0x1324]);
    param_1[0x1324] = 0;
  }
  if ((HANDLE)param_1[0x1325] != (HANDLE)0x0) {
    TerminateThread((HANDLE)param_1[0x1325],0);
    CloseHandle((HANDLE)param_1[0x1325]);
    param_1[0x1325] = 0;
  }
  FUN_100d95bc();
  uVar3 = param_1[0x1326];
  param_1[0x1326] = 0xffffffff;
  Net_DisConnCamera(uVar3);
  Net_DelCamera(uVar3);
  param_1[0x1326] = 0xffffffff;
  local_c._0_1_ = 0x2f;
  param_1[0x133d] = CGdiObject::vftable;
  FUN_100d95bc();
  local_c._0_1_ = 0x2e;
  FUN_100d9a2e();
  local_c._0_1_ = 0x2d;
  FUN_1007b2d0();
  local_c._0_1_ = 0x2c;
  FUN_1007b2d0();
  local_c._0_1_ = 0x2b;
  FUN_1007b2d0();
  local_c._0_1_ = 0x2a;
  FUN_1007b2d0();
  local_c._0_1_ = 0x29;
  FUN_1007b2d0();
  local_c._0_1_ = 0x28;
  FUN_1007b2d0();
  local_c._0_1_ = 0x27;
  FUN_1007b2d0();
  local_c._0_1_ = 0x26;
  FUN_1007b2d0();
  local_c._0_1_ = 0x25;
  puVar5 = (undefined4 *)(param_1[0xb7d] + -0x10);
  piVar1 = (int *)(param_1[0xb7d] + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(*(int *)*puVar5 + 4))(puVar5);
  }
  local_c._0_1_ = 0x24;
  FUN_10079540();
  local_c._0_1_ = 0x23;
  FUN_100a7520();
  local_c._0_1_ = 0x22;
  FUN_100d97ea();
  local_c._0_1_ = 0x21;
  FUN_1007be50();
  local_c._0_1_ = 0x20;
  FUN_10079540();
  local_c._0_1_ = 0x1f;
  FUN_1007f9e0();
  local_c._0_1_ = 0x1e;
  FUN_1007b2d0();
  local_c._0_1_ = 0x1d;
  FUN_1007f9e0();
  local_c._0_1_ = 0x1c;
  FUN_100a7520();
  local_c._0_1_ = 0x1b;
  FUN_1007f9e0();
  local_c._0_1_ = 0x1a;
  FUN_100a7520();
  local_c._0_1_ = 0x19;
  FUN_1007f9e0();
  local_c._0_1_ = 0x18;
  FUN_100a7520();
  local_c._0_1_ = 0x17;
  FUN_100a7520();
  local_c = (void *)CONCAT31(local_c._1_3_,0x16);
  FUN_100a7520();
  FUN_100ada80();
  if (param_1[0x3f7] != 0) {
    thunk_FUN_100f998b(param_1[0x3f7]);
  }
  param_1[0x3f7] = 0;
  param_1[0x3f8] = 0;
  param_1[0x3f9] = 0;
  if (param_1[0x3f3] != 0) {
    FUN_10037060();
    thunk_FUN_100f998b(param_1[0x3f3]);
  }
  param_1[0x3f3] = 0;
  param_1[0x3f4] = 0;
  param_1[0x3f5] = 0;
  if (param_1[0x3ef] != 0) {
    FUN_10037060();
    thunk_FUN_100f998b(param_1[0x3ef]);
  }
  param_1[0x3ef] = 0;
  param_1[0x3f0] = 0;
  param_1[0x3f1] = 0;
  local_c._0_1_ = 0x11;
  puVar5 = (undefined4 *)(param_1[0x3ac] + -0x10);
  piVar1 = (int *)(param_1[0x3ac] + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(*(int *)*puVar5 + 4))(puVar5);
  }
  local_c._0_1_ = 0x10;
  puVar5 = (undefined4 *)(param_1[0x3ab] + -0x10);
  piVar1 = (int *)(param_1[0x3ab] + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(*(int *)*puVar5 + 4))(puVar5);
  }
  local_c._0_1_ = 0xf;
  puVar5 = (undefined4 *)(param_1[0x369] + -0x10);
  piVar1 = (int *)(param_1[0x369] + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(*(int *)*puVar5 + 4))(puVar5);
  }
  local_c._0_1_ = 0xe;
  puVar5 = (undefined4 *)(param_1[0x368] + -0x10);
  piVar1 = (int *)(param_1[0x368] + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(*(int *)*puVar5 + 4))(puVar5);
  }
  FUN_10080b80();
  local_c._0_1_ = 0xc;
  FUN_10079540();
  local_c._0_1_ = 0xb;
  FUN_10079540();
  local_c._0_1_ = 10;
  FUN_100d75c9();
  local_c._0_1_ = 9;
  FUN_1007f9e0();
  local_c._0_1_ = 8;
  FUN_10079540();
  local_c._0_1_ = 7;
  FUN_10079540();
  local_c._0_1_ = 6;
  FUN_100d75c9();
  local_c._0_1_ = 5;
  FUN_1007f9e0();
  local_c._0_1_ = 4;
  FUN_10079540();
  local_c._0_1_ = 3;
  FUN_100daba0();
  local_c._0_1_ = 2;
  FUN_1007f9e0();
  local_c._0_1_ = 1;
  FUN_10079540();
  local_c = (void *)((uint)local_c._1_3_ << 8);
  FUN_100d9a2e();
  local_c = (void *)0xffffffff;
  FUN_10008710();
  ExceptionList = unaff_EBX;
  return;
}



/* FUNCTION FUN_10014190 ENTRY 10014190 */

undefined4 FUN_10014190(void)

{
  int iVar1;
  int unaff_ESI;
  
  if (*(int *)(unaff_ESI + 0x2c) == -1) {
    return 1;
  }
  iVar1 = Net_StopVideo(*(int *)(unaff_ESI + 0x2c));
  if (iVar1 == 0) {
    if ((*(int *)(unaff_ESI + 0x30) == 1) &&
       (iVar1 = Net_DisConnCamera(*(undefined4 *)(unaff_ESI + 0x2c)), iVar1 != 0)) {
      return 0;
    }
    iVar1 = Net_DelCamera(*(undefined4 *)(unaff_ESI + 0x2c));
    if (iVar1 == 0) {
      *(undefined4 *)(unaff_ESI + 0x2c) = 0xffffffff;
      return 1;
    }
  }
  return 0;
}



/* FUNCTION FUN_10011f90 ENTRY 10011f90 */

void FUN_10011f90(void)

{
  int iVar1;
  int unaff_ESI;
  
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    iVar1 = Net_StopRecord(*(int *)(unaff_ESI + 0x28));
    if (iVar1 == 0) {
      *(undefined4 *)(unaff_ESI + 0xcc) = 0;
    }
  }
  if (*(int *)(unaff_ESI + 0x2c) != -1) {
    iVar1 = Net_StopRecord(*(int *)(unaff_ESI + 0x2c));
    if (iVar1 == 0) {
      *(undefined4 *)(unaff_ESI + 0xd0) = 0;
    }
  }
  if (*(HANDLE *)(unaff_ESI + 0x11c) != (HANDLE)0x0) {
    TerminateThread(*(HANDLE *)(unaff_ESI + 0x11c),0);
    CloseHandle(*(HANDLE *)(unaff_ESI + 0x11c));
    *(undefined4 *)(unaff_ESI + 0x11c) = 0;
  }
  if (*(HANDLE *)(unaff_ESI + 0x120) != (HANDLE)0x0) {
    TerminateThread(*(HANDLE *)(unaff_ESI + 0x120),0);
    CloseHandle(*(HANDLE *)(unaff_ESI + 0x120));
    *(undefined4 *)(unaff_ESI + 0x120) = 0;
  }
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    Net_StopVideo(*(int *)(unaff_ESI + 0x28));
  }
  if (*(int *)(unaff_ESI + 0x28) != -1) {
    Net_DisConnCamera(*(int *)(unaff_ESI + 0x28));
    Net_DelCamera(*(undefined4 *)(unaff_ESI + 0x28));
    *(undefined4 *)(unaff_ESI + 0x28) = 0xffffffff;
    *(undefined4 *)(unaff_ESI + 0xdc) = 0;
    *(undefined4 *)(unaff_ESI + 0xd8) = 0;
  }
  if (*(int *)(unaff_ESI + 0x2c) != -1) {
    iVar1 = Net_StopVideo(*(int *)(unaff_ESI + 0x2c));
    if (iVar1 == 0) {
      if (*(int *)(unaff_ESI + 0x30) == 1) {
        iVar1 = Net_DisConnCamera(*(undefined4 *)(unaff_ESI + 0x2c));
        if (iVar1 != 0) goto LAB_1001207e;
      }
      iVar1 = Net_DelCamera(*(undefined4 *)(unaff_ESI + 0x2c));
      if (iVar1 == 0) {
        *(undefined4 *)(unaff_ESI + 0x2c) = 0xffffffff;
      }
    }
  }
LAB_1001207e:
                    /* WARNING: Could not recover jumptable at 0x10012081. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  Net_UNinit();
  return;
}



/* FUNCTION FUN_100caca0 ENTRY 100caca0 */

undefined4 __fastcall FUN_100caca0(int param_1)

{
  ushort uVar1;
  char cVar2;
  uint uVar3;
  int iVar4;
  int iVar5;
  LRESULT LVar6;
  int *piVar7;
  int iVar8;
  ushort *puVar9;
  ushort *puVar10;
  undefined4 uVar11;
  byte *pbVar12;
  undefined1 uVar13;
  byte *pbVar14;
  bool bVar15;
  ushort **ppuVar16;
  ushort *puStack_50;
  int iStack_4c;
  ushort *puStack_48;
  int iStack_44;
  int local_40;
  int local_3c;
  byte *local_38;
  byte *local_34;
  undefined4 local_30;
  int iStack_2c;
  int iStack_28;
  undefined4 local_24;
  int local_20;
  int local_1c;
  undefined4 local_18;
  int local_14;
  int local_10;
  void *local_c;
  undefined1 *puStack_8;
  undefined4 uStack_4;
  
  uStack_4 = 0xffffffff;
  puStack_8 = &LAB_1012e3d8;
  local_c = ExceptionList;
  uVar3 = DAT_10174ab0 ^ (uint)&stack0xffffffa0;
  ExceptionList = &local_c;
  local_24 = *(int *)(param_1 + 0xbc);
  local_20 = *(int *)(param_1 + 0xc0);
  local_38 = (byte *)(param_1 + 0xbc);
  local_1c = *(int *)(param_1 + 0xc4);
  local_34 = (byte *)(param_1 + 200);
  local_18 = *(int *)local_34;
  local_14 = *(int *)(param_1 + 0xcc);
  local_10 = *(int *)(param_1 + 0xd0);
  local_30 = 1;
  iVar4 = FUN_100d82f4(0x1c7);
  local_3c = iVar4;
  iVar5 = FUN_100d82f4(0x156);
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
  if ((LVar6 == 0) && (*(int *)(param_1 + 0x2918) != 0)) {
    *(undefined4 **)(param_1 + 0xd4) = &local_24;
    piVar7 = (int *)FUN_100d8606(uVar3);
    if (piVar7 == (int *)0x0) {
LAB_100cad77:
                    /* WARNING: Subroutine does not return */
      FUN_100025f0(0x80004005);
    }
    iVar4 = (**(code **)(*piVar7 + 0xc))();
    puStack_50 = (ushort *)(iVar4 + 0x10);
    ppuVar16 = &puStack_50;
    uStack_4 = 0;
    LVar6 = SendMessageW(*(HWND *)(iVar5 + 0x20),0x147,0,0);
    FUN_100d76a9(LVar6,ppuVar16);
    iStack_28 = **(int **)(param_1 + 0x2914);
    iStack_2c = param_1 + 0x2910;
    while( true ) {
      iVar4 = iStack_2c;
      iStack_44 = *(int *)(param_1 + 0x2914);
      if ((iStack_2c == 0) || (iStack_2c != param_1 + 0x2910)) {
        FUN_100f8677();
      }
      if (iStack_28 == iStack_44) goto LAB_100cae47;
      if (iVar4 == 0) {
        FUN_100f8677();
      }
      if (iStack_28 == *(int *)(iVar4 + 4)) {
        FUN_100f8677();
      }
      cVar2 = FUN_10004910(&puStack_50,iStack_28 + 0x10);
      iVar5 = iStack_28;
      if (cVar2 != '\0') break;
      FUN_100bc700();
    }
    if (iStack_28 == *(int *)(iVar4 + 4)) {
      FUN_100f8677();
    }
    *(undefined1 *)(*(int *)(param_1 + 0xd4) + 1) = *(undefined1 *)(iVar5 + 0xc);
LAB_100cae47:
    LVar6 = SendMessageW(*(HWND *)(local_3c + 0x20),0x147,0,0);
    puVar10 = puStack_50;
    if (LVar6 != 0) {
      if (*(int *)(param_1 + 0x2958) != 0) {
        ppuVar16 = &puStack_50;
        LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
        FUN_100d76a9(LVar6,ppuVar16);
        iStack_28 = **(int **)(param_1 + 0x2954);
        iStack_2c = param_1 + 0x2950;
        do {
          iVar5 = iStack_2c;
          iVar4 = *(int *)(param_1 + 0x2954);
          if ((iStack_2c == 0) || (iStack_2c != param_1 + 0x2950)) {
            FUN_100f8677();
          }
          puVar10 = puStack_50;
          if (iStack_28 == iVar4) goto LAB_100cb1cb;
          if (iVar5 == 0) {
            FUN_100f8677();
          }
          if (iStack_28 == *(int *)(iVar5 + 4)) {
            FUN_100f8677();
          }
          iVar4 = iStack_28;
          puVar10 = *(ushort **)(iStack_28 + 0x10);
          puVar9 = puStack_50;
          if (puVar10 == (ushort *)0x0) goto LAB_100cad77;
          do {
            uVar1 = *puVar9;
            bVar15 = uVar1 < *puVar10;
            if (uVar1 != *puVar10) {
LAB_100caf26:
              iVar8 = (1 - (uint)bVar15) - (uint)(bVar15 != 0);
              goto LAB_100caf2b;
            }
            if (uVar1 == 0) break;
            uVar1 = puVar9[1];
            bVar15 = uVar1 < puVar10[1];
            if (uVar1 != puVar10[1]) goto LAB_100caf26;
            puVar10 = puVar10 + 2;
            puVar9 = puVar9 + 2;
          } while (uVar1 != 0);
          iVar8 = 0;
LAB_100caf2b:
          if (iVar8 == 0) goto LAB_100caf46;
          FUN_100bc700();
        } while( true );
      }
      LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
      **(undefined1 **)(param_1 + 0xd4) = (char)LVar6;
      puVar10 = puStack_50;
    }
    goto LAB_100cb1cb;
  }
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
  if ((LVar6 == 1) && (*(int *)(param_1 + 0x2924) != 0)) {
    *(undefined4 **)(param_1 + 0xd4) = &local_18;
    piVar7 = (int *)FUN_100d8606(uVar3);
    if (piVar7 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_100025f0(0x80004005);
    }
    iVar4 = (**(code **)(*piVar7 + 0xc))();
    puStack_48 = (ushort *)(iVar4 + 0x10);
    ppuVar16 = &puStack_48;
    uStack_4 = 1;
    LVar6 = SendMessageW(*(HWND *)(iVar5 + 0x20),0x147,0,0);
    FUN_100d76a9(LVar6,ppuVar16);
    iStack_28 = **(int **)(param_1 + 0x2920);
    iStack_2c = param_1 + 0x291c;
    while( true ) {
      iVar5 = iStack_28;
      iVar4 = iStack_2c;
      iStack_4c = *(int *)(param_1 + 0x2920);
      if ((iStack_2c == 0) || (iStack_2c != param_1 + 0x291c)) {
        FUN_100f8677();
      }
      if (iVar5 == iStack_4c) goto LAB_100cb0a1;
      if (iVar4 == 0) {
        FUN_100f8677();
      }
      if (iVar5 == *(int *)(iVar4 + 4)) {
        FUN_100f8677();
      }
      cVar2 = FUN_10004910(&puStack_48,iVar5 + 0x10);
      if (cVar2 != '\0') break;
      FUN_100bc700();
    }
    if (iVar5 == *(int *)(iVar4 + 4)) {
      FUN_100f8677();
    }
    *(undefined1 *)(*(int *)(param_1 + 0xd4) + 1) = *(undefined1 *)(iVar5 + 0xc);
LAB_100cb0a1:
    if (*(int *)(param_1 + 0x2958) != 0) {
      ppuVar16 = &puStack_48;
      LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
      FUN_100d76a9(LVar6,ppuVar16);
      iStack_28 = **(int **)(param_1 + 0x2954);
      iStack_2c = param_1 + 0x2950;
      do {
        iVar5 = iStack_2c;
        iVar4 = *(int *)(param_1 + 0x2954);
        if ((iStack_2c == 0) || (iStack_2c != param_1 + 0x2950)) {
          FUN_100f8677();
        }
        puVar10 = puStack_48;
        if (iStack_28 == iVar4) goto LAB_100cb1cb;
        if (iVar5 == 0) {
          FUN_100f8677();
        }
        if (iStack_28 == *(int *)(iVar5 + 4)) {
          FUN_100f8677();
        }
        iVar4 = iStack_28;
        puVar10 = *(ushort **)(iStack_28 + 0x10);
        puVar9 = puStack_48;
        if (puVar10 == (ushort *)0x0) goto LAB_100cad77;
        do {
          uVar1 = *puVar9;
          bVar15 = uVar1 < *puVar10;
          if (uVar1 != *puVar10) {
LAB_100cb166:
            iVar8 = (1 - (uint)bVar15) - (uint)(bVar15 != 0);
            goto LAB_100cb16b;
          }
          if (uVar1 == 0) break;
          uVar1 = puVar9[1];
          bVar15 = uVar1 < puVar10[1];
          if (uVar1 != puVar10[1]) goto LAB_100cb166;
          puVar10 = puVar10 + 2;
          puVar9 = puVar9 + 2;
        } while (uVar1 != 0);
        iVar8 = 0;
LAB_100cb16b:
        if (iVar8 == 0) goto LAB_100cb186;
        FUN_100bc700();
      } while( true );
    }
    LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
    **(undefined1 **)(param_1 + 0xd4) = (char)LVar6;
    puVar10 = puStack_48;
    goto LAB_100cb1cb;
  }
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
  if ((LVar6 == 0) || (iVar8 = FUN_10011f00(), *(int *)(iVar8 + 0x4bc) != 0)) {
    *(undefined4 **)(param_1 + 0xd4) = &local_24;
    iVar8 = FUN_10011f00();
    if ((*(int *)(iVar8 + 0x148) == 0) && (iVar8 = FUN_10011f00(), *(int *)(iVar8 + 0x4bc) == 0)) {
      LVar6 = SendMessageW(*(HWND *)(iVar5 + 0x20),0x147,0,0);
      uVar13 = (&DAT_1017609c)[LVar6 * 4];
    }
    else {
      LVar6 = SendMessageW(*(HWND *)(iVar5 + 0x20),0x147,0,0);
      uVar13 = (&DAT_101760a0)[LVar6 * 4];
    }
    *(undefined1 *)(*(int *)(param_1 + 0xd4) + 1) = uVar13;
    LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
    if (LVar6 != 0) {
      LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
      **(undefined1 **)(param_1 + 0xd4) = (char)LVar6;
    }
  }
  else {
    *(undefined4 **)(param_1 + 0xd4) = &local_18;
    LVar6 = SendMessageW(*(HWND *)(iVar5 + 0x20),0x147,0,0);
    *(undefined *)(*(int *)(param_1 + 0xd4) + 1) = (&DAT_1017609c)[LVar6 * 4];
    LVar6 = SendMessageW(*(HWND *)(param_1 + 0x2698),0x147,0,0);
    **(undefined1 **)(param_1 + 0xd4) = (char)LVar6;
  }
  goto LAB_100cb2e3;
LAB_100caf46:
  if (iStack_28 == *(int *)(iVar5 + 4)) {
    FUN_100f8677();
  }
  **(undefined1 **)(param_1 + 0xd4) = *(undefined1 *)(iVar4 + 0xc);
  puVar10 = puStack_50;
  goto LAB_100cb1cb;
LAB_100cb186:
  if (iStack_28 == *(int *)(iVar5 + 4)) {
    FUN_100f8677();
  }
  **(undefined1 **)(param_1 + 0xd4) = *(undefined1 *)(iVar4 + 0xc);
  puVar10 = puStack_48;
LAB_100cb1cb:
  uStack_4 = 0xffffffff;
  puVar9 = puVar10 + -2;
  LOCK();
  iVar4 = *(int *)puVar9;
  *(int *)puVar9 = *(int *)puVar9 + -1;
  UNLOCK();
  if (iVar4 == 1 || iVar4 + -1 < 0) {
    (**(code **)(**(int **)(puVar10 + -8) + 4))(puVar10 + -8);
  }
LAB_100cb2e3:
  FUN_10004eb0(&PTR_1013b7d8);
  uStack_4 = 2;
  iVar4 = FUN_100d82f4(0x1fd);
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x400,0,0);
  *(char *)(*(int *)(param_1 + 0xd4) + 2) = (char)LVar6;
  iVar4 = FUN_100d82f4(0x157);
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
  *(char *)(*(int *)(param_1 + 0xd4) + 3) = (char)LVar6;
  FUN_100d82f4(0x112);
  iVar4 = FUN_100d82f4(0x158);
  LVar6 = SendMessageW(*(HWND *)(local_3c + 0x20),0x147,0,0);
  if ((LVar6 == 0) || (iVar5 = FUN_10011f00(), *(int *)(iVar5 + 0x4bc) != 0)) {
    LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
    if (LVar6 == 0) {
      *(undefined4 *)(*(int *)(param_1 + 0xd4) + 4) = 0x1000;
    }
    else {
      LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
      if (LVar6 == 1) {
        *(undefined4 *)(*(int *)(param_1 + 0xd4) + 4) = 0x2000;
      }
      else {
        FUN_100d5220(&local_40);
        uVar11 = thunk_FUN_100f7ac4(local_40);
        *(undefined4 *)(*(int *)(param_1 + 0xd4) + 4) = uVar11;
        uVar3 = *(uint *)(*(int *)(param_1 + 0xd4) + 4);
        if ((uVar3 < 0x180) || (4000 < uVar3)) {
          FUN_10041b70(param_1,&DAT_10152dd8);
          uVar11 = 3;
          goto LAB_100cb70b;
        }
      }
    }
  }
  else {
    FUN_100d5220(&local_40);
    uVar11 = thunk_FUN_100f7ac4(local_40);
    *(undefined4 *)(*(int *)(param_1 + 0xd4) + 4) = uVar11;
    uVar3 = *(uint *)(*(int *)(param_1 + 0xd4) + 4);
    if ((uVar3 < 0x20) || (2000 < uVar3)) {
      FUN_10041b70(param_1,&DAT_10152e04);
      uVar11 = 3;
      goto LAB_100cb70b;
    }
  }
  iVar4 = FUN_100d82f4(0x159);
  LVar6 = SendMessageW(*(HWND *)(iVar4 + 0x20),0x147,0,0);
  *(char *)(*(int *)(param_1 + 0xd4) + 8) = (char)LVar6 + '\x01';
  LVar6 = SendMessageW(*(HWND *)(param_1 + 0x281c),0x147,0,0);
  *(char *)(*(int *)(param_1 + 0xd4) + 0xb) = (char)LVar6;
  LVar6 = SendMessageW(*(HWND *)(local_3c + 0x20),0x147,0,0);
  if ((LVar6 == 0) || (iVar4 = FUN_10011f00(), *(int *)(iVar4 + 0x4bc) != 0)) {
    uVar3 = 0xc;
    pbVar14 = (byte *)&local_24;
    pbVar12 = local_38;
    do {
      if (*(int *)pbVar14 != *(int *)pbVar12) goto LAB_100cb588;
      uVar3 = uVar3 - 4;
      pbVar12 = pbVar12 + 4;
      pbVar14 = pbVar14 + 4;
    } while (3 < uVar3);
    if (uVar3 != 0) {
LAB_100cb588:
      iVar4 = (uint)*pbVar14 - (uint)*pbVar12;
      if (iVar4 != 0) goto LAB_100cb5d7;
      if (uVar3 != 1) {
        iVar4 = (uint)pbVar14[1] - (uint)pbVar12[1];
        if (iVar4 != 0) goto LAB_100cb5d7;
        if (uVar3 != 2) {
          iVar4 = (uint)pbVar14[2] - (uint)pbVar12[2];
          if (iVar4 != 0) goto LAB_100cb5d7;
          if (uVar3 != 3) {
            iVar4 = (uint)pbVar14[3] - (uint)pbVar12[3];
            goto LAB_100cb5d5;
          }
        }
      }
    }
LAB_100cb5e5:
    iVar5 = 0;
  }
  else {
    uVar3 = 0xc;
    pbVar14 = (byte *)&local_18;
    pbVar12 = local_34;
    do {
      if (*(int *)pbVar14 != *(int *)pbVar12) goto LAB_100cb4fc;
      uVar3 = uVar3 - 4;
      pbVar12 = pbVar12 + 4;
      pbVar14 = pbVar14 + 4;
    } while (3 < uVar3);
    if (uVar3 == 0) goto LAB_100cb5e5;
LAB_100cb4fc:
    iVar4 = (uint)*pbVar14 - (uint)*pbVar12;
    if (iVar4 == 0) {
      if (uVar3 != 1) {
        iVar4 = (uint)pbVar14[1] - (uint)pbVar12[1];
        if (iVar4 != 0) goto LAB_100cb5d7;
        if (uVar3 != 2) {
          iVar4 = (uint)pbVar14[2] - (uint)pbVar12[2];
          if (iVar4 != 0) goto LAB_100cb5d7;
          if (uVar3 != 3) {
            iVar4 = (uint)pbVar14[3] - (uint)pbVar12[3];
LAB_100cb5d5:
            if (iVar4 != 0) goto LAB_100cb5d7;
          }
        }
      }
      goto LAB_100cb5e5;
    }
LAB_100cb5d7:
    iVar5 = 1;
    if (iVar4 < 1) {
      iVar5 = -1;
    }
  }
  if (iVar5 == 0) {
    uVar11 = 2;
  }
  else {
    iVar4 = FUN_10011f00();
    if ((*(int *)(iVar4 + 0x28) != -1) &&
       (iVar5 = Net_StopVideo(*(int *)(iVar4 + 0x28)), iVar5 == 0)) {
      *(undefined4 *)(iVar4 + 0x128) = 1;
    }
    LVar6 = SendMessageW(*(HWND *)(local_3c + 0x20),0x147,0,0);
    uVar11 = *(undefined4 *)(param_1 + 0xd4);
    if (LVar6 == 0) {
      iVar4 = FUN_10011f00();
      bVar15 = true;
      if ((*(int *)(iVar4 + 0x28) == -1) ||
         (iVar4 = Net_VideoCodeSetup(*(int *)(iVar4 + 0x28),uVar11), iVar4 != 0)) {
        bVar15 = false;
      }
      if (bVar15) {
        *(int *)local_38 = local_24;
        *(int *)(local_38 + 4) = local_20;
        *(int *)(local_38 + 8) = local_1c;
      }
    }
    else {
      iVar4 = FUN_10011f00();
      bVar15 = true;
      if ((*(int *)(iVar4 + 0x28) == -1) ||
         (iVar4 = Net_ViceVideoCodeSetup(*(int *)(iVar4 + 0x28),uVar11), iVar4 != 0)) {
        bVar15 = false;
      }
      if (bVar15) {
        *(int *)local_34 = local_18;
        *(int *)(local_34 + 4) = local_14;
        *(int *)(local_34 + 8) = local_10;
      }
    }
    FUN_10011f00();
    FUN_10016630();
    iVar5 = FUN_10011f00();
    iVar4 = *(int *)(iVar5 + 0x28);
    if (iVar4 != -1) {
      if (*(int *)(iVar5 + 0x138) == 0) {
        Net_ShowPlateRegion(iVar4,0);
      }
      else {
        Net_ShowPlateRegion(iVar4,1);
      }
    }
    uVar11 = local_30;
    if (!bVar15) {
      uVar11 = 0;
    }
  }
LAB_100cb70b:
  uStack_4 = 0xffffffff;
  piVar7 = (int *)(local_40 + -4);
  LOCK();
  iVar4 = *piVar7;
  *piVar7 = *piVar7 + -1;
  UNLOCK();
  if (iVar4 == 1 || iVar4 + -1 < 0) {
    (**(code **)(**(int **)(local_40 + -0x10) + 4))((undefined4 *)(local_40 + -0x10));
  }
  ExceptionList = local_c;
  return uVar11;
}



/* FUNCTION FUN_10023160 ENTRY 10023160 */

void FUN_10023160(void)

{
  int *piVar1;
  int iVar2;
  int iVar3;
  undefined **local_138 [29];
  int local_c4;
  undefined **appuStack_a8 [29];
  int iStack_34;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 local_c;
  
  local_c = 0xffffffff;
  puStack_10 = &LAB_101310e2;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  iVar2 = FUN_10011f00();
  if (((*(int *)(iVar2 + 0xdc) == 0) || (*(int *)(iVar2 + 0xd8) == 0)) ||
     (*(int *)(iVar2 + 0x28) == -1)) {
    FUN_10004eb0(&DAT_1013e62c);
    FUN_100abc40(local_138);
    local_c = 0;
    FUN_100d8024();
    local_c = 1;
    piVar1 = (int *)(local_c4 + -4);
    LOCK();
    iVar2 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
  }
  else {
    iVar2 = FUN_10011f00();
    if ((*(int *)(iVar2 + 0x28) != -1) && (iVar2 = Net_ReStoreConfig(), iVar2 == 0)) {
      FUN_10004eb0(&DAT_1013e650);
      FUN_100abc40(appuStack_a8);
      local_c = 4;
      FUN_100d8024();
      FUN_10020330();
      iVar2 = FUN_10011f00();
      if ((*(int *)(iVar2 + 0x28) != -1) && (iVar3 = Net_StopVideo(), iVar3 == 0)) {
        *(undefined4 *)(iVar2 + 0x128) = 1;
      }
      FUN_10011f00();
      FUN_10016630();
      iVar2 = FUN_10011f00();
      if (*(int *)(iVar2 + 0x28) != -1) {
        Net_SetDrawFunCallBack(*(int *)(iVar2 + 0x28));
      }
      appuStack_a8[0] = CTipDlg::vftable;
      local_c = 5;
      piVar1 = (int *)(iStack_34 + -4);
      LOCK();
      iVar2 = *piVar1;
      *piVar1 = *piVar1 + -1;
      UNLOCK();
      if (iVar2 == 1 || iVar2 + -1 < 0) {
        (**(code **)(**(int **)(iStack_34 + -0x10) + 4))();
      }
      goto LAB_10023363;
    }
    FUN_10004eb0(&DAT_1013e63c);
    FUN_100abc40(local_138);
    local_c = 2;
    FUN_100d8024();
    local_c = 3;
    piVar1 = (int *)(local_c4 + -4);
    LOCK();
    iVar2 = *piVar1;
    *piVar1 = *piVar1 + -1;
    UNLOCK();
  }
  local_138[0] = CTipDlg::vftable;
  if (iVar2 + -1 < 1) {
    (**(code **)(**(int **)(local_c4 + -0x10) + 4))();
  }
LAB_10023363:
  local_c = 0xffffffff;
  FUN_100d790d();
  ExceptionList = local_14;
  return;
}



/* FUNCTION FUN_10041a70 ENTRY 10041a70 */

void __fastcall FUN_10041a70(undefined4 param_1)

{
  int iVar1;
  int iVar2;
  
  iVar1 = FUN_10011f00();
  if (*(int *)(iVar1 + 0x28) != -1) {
    iVar2 = Net_StopVideo(*(int *)(iVar1 + 0x28));
    if (iVar2 == 0) {
      *(undefined4 *)(iVar1 + 0x128) = 1;
    }
  }
  iVar1 = FUN_10011f00();
  if (*(int *)(iVar1 + 0x28) != -1) {
    iVar1 = Net_ReStoreConfig(*(int *)(iVar1 + 0x28));
    if (iVar1 == 0) {
      FUN_10041b70(param_1,&DAT_1013e650);
      goto LAB_10041ace;
    }
  }
  FUN_1000ad00(param_1,&DAT_1013e63c);
LAB_10041ace:
  FUN_10011f00();
  FUN_10016630();
  return;
}



/* FUNCTION FUN_10041af0 ENTRY 10041af0 */

void __fastcall FUN_10041af0(undefined4 param_1)

{
  int iVar1;
  int iVar2;
  
  iVar1 = FUN_10011f00();
  if (*(int *)(iVar1 + 0x28) != -1) {
    iVar2 = Net_StopVideo(*(int *)(iVar1 + 0x28));
    if (iVar2 == 0) {
      *(undefined4 *)(iVar1 + 0x128) = 1;
    }
  }
  iVar1 = FUN_10011f00();
  if (*(int *)(iVar1 + 0x28) != -1) {
    iVar1 = Net_SetupRestore(*(int *)(iVar1 + 0x28));
    if (iVar1 == 0) {
      FUN_10041b70(param_1,&DAT_10142404);
      goto LAB_10041b4e;
    }
  }
  FUN_1000ad00(param_1,&DAT_10142418);
LAB_10041b4e:
  FUN_10011f00();
  FUN_10016630();
  return;
}



/* FUNCTION FUN_10011310 ENTRY 10011310 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

LPCRITICAL_SECTION FUN_10011310(LPCRITICAL_SECTION param_1)

{
  HANDLE *ppvVar1;
  WCHAR WVar2;
  LPCWSTR pWVar3;
  char cVar4;
  uint uVar5;
  int *piVar6;
  int iVar7;
  HANDLE pvVar8;
  LPWSTR pWVar9;
  int unaff_EBX;
  void *pvStack_14;
  LPWSTR pWStack_10;
  void *local_c;
  undefined1 *puStack_8;
  undefined4 local_4;
  
  local_4 = 0xffffffff;
  puStack_8 = &LAB_1012d7fa;
  local_c = ExceptionList;
  uVar5 = DAT_10174ab0 ^ (uint)&stack0xffffffdc;
  ExceptionList = &local_c;
  InitializeCriticalSection(param_1);
  param_1[1].LockCount = 0;
  param_1[1].RecursionCount = 0;
  param_1[1].OwningThread = (HANDLE)0x0;
  local_4._0_1_ = 1;
  local_4._1_3_ = 0;
  piVar6 = (int *)FUN_100d8606(uVar5);
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[2].OwningThread = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 2;
  piVar6 = (int *)FUN_100d8606(uVar5);
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[2].LockSemaphore = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 3;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[2].SpinCount = iVar7 + 0x10;
  local_4._0_1_ = 4;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)(iVar7 + 0x10);
  local_4._0_1_ = 5;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].LockCount = iVar7 + 0x10;
  local_4._0_1_ = 6;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].RecursionCount = iVar7 + 0x10;
  local_4._0_1_ = 7;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].OwningThread = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 8;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].LockSemaphore = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 9;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[3].SpinCount = iVar7 + 0x10;
  local_4._0_1_ = 10;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[4].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)(iVar7 + 0x10);
  local_4._0_1_ = 0xb;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[4].LockCount = iVar7 + 0x10;
  local_4._0_1_ = 0xc;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[4].RecursionCount = iVar7 + 0x10;
  local_4._0_1_ = 0xd;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[4].OwningThread = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 0xe;
  ppvVar1 = &param_1[4].LockSemaphore;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  *ppvVar1 = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 0xf;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[7].OwningThread = (HANDLE)(iVar7 + 0x10);
  local_4._0_1_ = 0x10;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[7].LockSemaphore = (HANDLE)(iVar7 + 0x10);
  param_1[8].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[8].LockCount = 0;
  param_1[8].RecursionCount = 0;
  local_4._0_1_ = 0x12;
  piVar6 = (int *)FUN_100d8606();
  if (piVar6 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar7 = (**(code **)(*piVar6 + 0xc))();
  param_1[0x10].LockCount = iVar7 + 0x10;
  local_4._0_1_ = 0x13;
  pvVar8 = (HANDLE)FUN_1001a530();
  param_1[0x10].OwningThread = pvVar8;
  *(undefined1 *)((int)pvVar8 + 0x25) = 1;
  *(HANDLE *)((int)param_1[0x10].OwningThread + 4) = param_1[0x10].OwningThread;
  *(HANDLE *)param_1[0x10].OwningThread = param_1[0x10].OwningThread;
  *(HANDLE *)((int)param_1[0x10].OwningThread + 8) = param_1[0x10].OwningThread;
  param_1[0x10].LockSemaphore = (HANDLE)0x0;
  local_4._0_1_ = 0x14;
  param_1[0x32].OwningThread = (HANDLE)0x0;
  param_1[8].OwningThread = (HANDLE)0x0;
  param_1[8].LockSemaphore = (HANDLE)0x0;
  param_1[8].SpinCount = 0;
  param_1[9].RecursionCount = 0;
  param_1[9].LockCount = 0;
  param_1[9].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[0xb].LockSemaphore = (HANDLE)0x0;
  param_1[9].OwningThread = (HANDLE)0x0;
  param_1[9].LockSemaphore = (HANDLE)0x0;
  param_1[9].SpinCount = 0;
  param_1[10].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[10].LockCount = 0;
  param_1[10].RecursionCount = 0;
  param_1[10].OwningThread = (HANDLE)0x0;
  param_1[10].LockSemaphore = (HANDLE)0x0;
  param_1[0x10].SpinCount = 0;
  param_1[10].SpinCount = 0;
  param_1[0xb].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[0xb].LockCount = 0;
  param_1[0xb].RecursionCount = 0;
  param_1[0xb].OwningThread = (HANDLE)0x0;
  param_1[1].LockSemaphore = (HANDLE)0xffffffff;
  param_1[1].SpinCount = 0xffffffff;
  param_1[2].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[2].LockCount = 30000;
  FUN_10002610(L"admin",5);
  FUN_10002610(L"admin",5);
  FUN_10002610(L"192.168.0.10",0xc);
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10002610(&PTR_1013b7d8,0);
  param_1[0xb].SpinCount = 0;
  param_1[0xc].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[0xc].LockCount = 0;
  param_1[0xc].RecursionCount = 0;
  param_1[0xc].OwningThread = (HANDLE)0x0;
  _DAT_1017ad74 = 0;
  param_1[0xc].LockSemaphore = (HANDLE)0x0;
  param_1[0xc].SpinCount = 0;
  param_1[0xd].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x1;
  param_1[0xd].LockCount = 0;
  param_1[0xd].RecursionCount = 0;
  param_1[0xd].OwningThread = (HANDLE)0x0;
  param_1[0xd].LockSemaphore = (HANDLE)0x0;
  param_1[0xd].SpinCount = 0;
  param_1[0xe].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
  param_1[0xe].LockCount = 0;
  param_1[0xe].RecursionCount = 0;
  param_1[0x32].RecursionCount = 0;
  param_1[0xf].RecursionCount = 0x780;
  param_1[0xf].OwningThread = (HANDLE)0x438;
  param_1[0xf].LockSemaphore = (HANDLE)0x0;
  param_1[0xf].SpinCount = 0;
  param_1[2].RecursionCount = 0;
  param_1[0x10].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0xa;
  FUN_10002610(&PTR_1013b7d8,0);
  FUN_10018310();
  FUN_10002610(L"C:\\Config.ini",0xd);
  param_1[0xe].LockSemaphore = (HANDLE)0x0;
  FUN_10004eb0(&PTR_1013b7d8);
  local_4 = CONCAT31(local_4._1_3_,0x15);
  pWVar3 = *ppvVar1;
  if ((int)(*(int *)(pWStack_10 + -4) - 0x104U | 1U - *(int *)(pWStack_10 + -2)) < 0) {
    FUN_100023e0(0x104);
  }
  GetPrivateProfileStringW(L"Config",L"ShowViceVideo",L"0",pWStack_10,0x104,pWVar3);
  if (pWStack_10 == (LPCWSTR)0x0) {
    iVar7 = 0;
  }
  else {
    pWVar9 = pWStack_10;
    do {
      WVar2 = *pWVar9;
      pWVar9 = pWVar9 + 1;
    } while (WVar2 != L'\0');
    iVar7 = (int)pWVar9 - (int)(pWStack_10 + 1) >> 1;
    if (iVar7 < 0) goto LAB_10011b96;
  }
  if (iVar7 <= *(int *)(pWStack_10 + -4)) {
    *(int *)(pWStack_10 + -6) = iVar7;
    pWStack_10[iVar7] = L'\0';
    WritePrivateProfileStringW(L"Config",L"ShowViceVideo",pWStack_10,*ppvVar1);
    cVar4 = FUN_1000fa30(&pWStack_10,&DAT_1013d0a8);
    pWVar3 = *ppvVar1;
    param_1[0xf].LockCount = 0;
    param_1[0xe].SpinCount = 0;
    param_1[0xe].LockSemaphore = (HANDLE)(uint)(cVar4 != '\0');
    if ((int)(*(int *)(pWStack_10 + -4) - 0x104U | 1U - *(int *)(pWStack_10 + -2)) < 0) {
      FUN_100023e0(0x104);
    }
    GetPrivateProfileStringW(L"Config",L"SavePlateInfo",L"0",pWStack_10,0x104,pWVar3);
    if (pWStack_10 == (LPCWSTR)0x0) {
      iVar7 = 0;
    }
    else {
      pWVar9 = pWStack_10;
      do {
        WVar2 = *pWVar9;
        pWVar9 = pWVar9 + 1;
      } while (WVar2 != L'\0');
      iVar7 = (int)pWVar9 - (int)(pWStack_10 + 1) >> 1;
      if (iVar7 < 0) goto LAB_10011b96;
    }
    if (iVar7 <= *(int *)(pWStack_10 + -4)) {
      *(int *)(pWStack_10 + -6) = iVar7;
      pWStack_10[iVar7] = L'\0';
      WritePrivateProfileStringW(L"Config",L"SavePlateInfo",pWStack_10,*ppvVar1);
      cVar4 = FUN_1000fa30(&pWStack_10,&DAT_1013d0a8);
      param_1[0xe].SpinCount = (uint)(cVar4 != '\0');
      FUN_10002610(&PTR_1013b7d8,0);
      pWVar3 = *ppvVar1;
      param_1[0xf].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)0x0;
      if ((int)(*(int *)(pWStack_10 + -4) - 0x104U | 1U - *(int *)(pWStack_10 + -2)) < 0) {
        FUN_100023e0(0x104);
      }
      GetPrivateProfileStringW(L"Config",L"SavePlateInfoTime",L"0",pWStack_10,0x104,pWVar3);
      if (pWStack_10 == (LPCWSTR)0x0) {
        iVar7 = 0;
      }
      else {
        pWVar9 = pWStack_10;
        do {
          WVar2 = *pWVar9;
          pWVar9 = pWVar9 + 1;
        } while (WVar2 != L'\0');
        iVar7 = (int)pWVar9 - (int)(pWStack_10 + 1) >> 1;
        if (iVar7 < 0) goto LAB_10011b96;
      }
      if (iVar7 <= *(int *)(pWStack_10 + -4)) {
        *(int *)(pWStack_10 + -6) = iVar7;
        pWStack_10[iVar7] = L'\0';
        WritePrivateProfileStringW(L"Config",L"SavePlateInfoTime",pWStack_10,*ppvVar1);
        cVar4 = FUN_1000fa30(&pWStack_10,&DAT_1013d0a8);
        param_1[0xf].DebugInfo = (PRTL_CRITICAL_SECTION_DEBUG)(uint)(cVar4 != '\0');
        FUN_10002610(L"c:\\OcxSave",10);
        FUN_100fcb30(&param_1[4].SpinCount,0,0x40);
        Net_Init();
        Net_RegTalkConnStateCallBack(&LAB_100112e0,param_1);
        param_1[0xe].OwningThread = (HANDLE)0x0;
        FUN_100fcb30(param_1 + 0x11,0,800);
        FUN_10002610(&DAT_1013d104,2);
        local_c = (void *)CONCAT31(local_c._1_3_,0x14);
        piVar6 = (int *)(unaff_EBX + -4);
        LOCK();
        iVar7 = *piVar6;
        *piVar6 = *piVar6 + -1;
        UNLOCK();
        if (iVar7 == 1 || iVar7 + -1 < 0) {
          (**(code **)(**(int **)(unaff_EBX + -0x10) + 4))((undefined4 *)(unaff_EBX + -0x10));
        }
        ExceptionList = pvStack_14;
        return param_1;
      }
    }
  }
LAB_10011b96:
                    /* WARNING: Subroutine does not return */
  FUN_100025f0(0x80070057);
}



/* FUNCTION FUN_100f7705 ENTRY 100f7705 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __fastcall FUN_100f7705(int param_1,undefined4 param_2)

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
  
  if (param_1 == DAT_10174ab0) {
    return;
  }
  _DAT_1017a348 =
       (uint)(in_NT & 1) * 0x4000 | (uint)SBORROW4((int)&stack0xfffffffc,0x328) * 0x800 |
       (uint)(in_IF & 1) * 0x200 | (uint)(in_TF & 1) * 0x100 | (uint)((int)&local_32c < 0) * 0x80 |
       (uint)(&stack0x00000000 == (undefined1 *)0x32c) * 0x40 | (uint)(in_AF & 1) * 0x10 |
       (uint)((POPCOUNT((uint)&local_32c & 0xff) & 1U) == 0) * 4 |
       (uint)(&stack0xfffffffc < (undefined1 *)0x328) | (uint)(in_ID & 1) * 0x200000 |
       (uint)(in_VIP & 1) * 0x100000 | (uint)(in_VIF & 1) * 0x80000 | (uint)(in_AC & 1) * 0x40000;
  _DAT_1017a34c = &stack0x00000004;
  _DAT_1017a288 = 0x10001;
  _DAT_1017a230 = 0xc0000409;
  _DAT_1017a234 = 1;
  local_32c = DAT_10174ab0;
  local_328 = DAT_10174ab4;
  _DAT_1017a23c = unaff_retaddr;
  _DAT_1017a314 = in_GS;
  _DAT_1017a318 = in_FS;
  _DAT_1017a31c = in_ES;
  _DAT_1017a320 = in_DS;
  _DAT_1017a324 = unaff_EDI;
  _DAT_1017a328 = unaff_ESI;
  _DAT_1017a32c = unaff_EBX;
  _DAT_1017a330 = param_2;
  _DAT_1017a334 = param_1;
  _DAT_1017a338 = in_EAX;
  _DAT_1017a33c = unaff_EBP;
  DAT_1017a340 = unaff_retaddr;
  _DAT_1017a344 = in_CS;
  _DAT_1017a350 = in_SS;
  DAT_1017a280 = IsDebuggerPresent();
  FUN_1010520b(1);
  SetUnhandledExceptionFilter((LPTOP_LEVEL_EXCEPTION_FILTER)0x0);
  UnhandledExceptionFilter((_EXCEPTION_POINTERS *)&PTR_DAT_10138afc);
  if (DAT_1017a280 == 0) {
    FUN_1010520b(1);
  }
  uExitCode = 0xc0000409;
  hProcess = GetCurrentProcess();
  TerminateProcess(hProcess,uExitCode);
  return;
}



/* FUNCTION FUN_10117889 ENTRY 10117889 */

void FUN_10117889(void)

{
  undefined1 *Value;
  _OSVERSIONINFOA local_9c;
  uint local_8;
  
  local_8 = DAT_10174ab0 ^ (uint)&stack0xfffffffc;
  local_9c.dwOSVersionInfoSize = 0x94;
  GetVersionExA(&local_9c);
  if ((local_9c.dwPlatformId != 2) || (Value = &LAB_10117885, local_9c.dwMajorVersion < 5)) {
    Value = &LAB_10117820;
  }
  InterlockedExchange((LONG *)&PTR_FUN_10175f80,(LONG)Value);
  (*(code *)PTR_FUN_10175f80)();
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10004eb0 ENTRY 10004eb0 */

int * __thiscall FUN_10004eb0(int *param_1,short *param_2)

{
  short sVar1;
  int *piVar2;
  int iVar3;
  short *psVar4;
  void *local_c;
  undefined1 *puStack_8;
  undefined4 uStack_4;
  
  uStack_4 = 0xffffffff;
  puStack_8 = &LAB_1011b0b8;
  local_c = ExceptionList;
  ExceptionList = &local_c;
  piVar2 = (int *)FUN_100d8606(DAT_10174ab0 ^ (uint)&stack0xffffffe8);
  if (piVar2 == (int *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_100025f0(0x80004005);
  }
  iVar3 = (**(code **)(*piVar2 + 0xc))();
  *param_1 = iVar3 + 0x10;
  uStack_4 = 0;
  if (param_2 == (short *)0x0) {
    iVar3 = 0;
  }
  else {
    if (((uint)param_2 & 0xffff0000) == 0) {
      iVar3 = FUN_100da3f0((uint)param_2 & 0xffff);
      if (iVar3 == 0) {
        ExceptionList = local_c;
        return param_1;
      }
      FUN_10004b40(iVar3,(uint)param_2 & 0xffff);
      ExceptionList = local_c;
      return param_1;
    }
    psVar4 = param_2;
    do {
      sVar1 = *psVar4;
      psVar4 = psVar4 + 1;
    } while (sVar1 != 0);
    iVar3 = (int)psVar4 - (int)(param_2 + 1) >> 1;
  }
  FUN_10002610(param_2,iVar3);
  ExceptionList = local_c;
  return param_1;
}



/* FUNCTION FUN_100d5220 ENTRY 100d5220 */

void __fastcall FUN_100d5220(int param_1)

{
  int iVar1;
  LPWSTR lpString;
  int nMaxCount;
  
  if (*(int *)(param_1 + 0x50) == 0) {
    iVar1 = GetWindowTextLengthW(*(HWND *)(param_1 + 0x20));
    nMaxCount = iVar1 + 1;
    lpString = (LPWSTR)FUN_100d51e3(iVar1);
    GetWindowTextW(*(HWND *)(param_1 + 0x20),lpString,nMaxCount);
    FUN_1001ac00(0xffffffff);
    return;
  }
                    /* WARNING: Could not recover jumptable at 0x100d525f. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  (**(code **)(**(int **)(param_1 + 0x50) + 0x8c))();
  return;
}



/* FUNCTION FUN_100f79a0 ENTRY 100f79a0 */

uint * FUN_100f79a0(uint *param_1,uint *param_2,uint param_3)

{
  uint uVar1;
  uint uVar2;
  char cVar3;
  uint uVar4;
  uint *puVar5;
  
  if (param_3 == 0) {
    return param_1;
  }
  puVar5 = param_1;
  if (((uint)param_2 & 3) != 0) {
    while( true ) {
      uVar4 = *param_2;
      param_2 = (uint *)((int)param_2 + 1);
      *(char *)puVar5 = (char)uVar4;
      puVar5 = (uint *)((int)puVar5 + 1);
      param_3 = param_3 - 1;
      if (param_3 == 0) {
        return param_1;
      }
      if ((char)uVar4 == '\0') break;
      if (((uint)param_2 & 3) == 0) {
        uVar4 = param_3 >> 2;
        goto joined_r0x100f79ec;
      }
    }
    do {
      if (((uint)puVar5 & 3) == 0) {
        uVar4 = param_3 >> 2;
        cVar3 = '\0';
        if (uVar4 == 0) goto LAB_100f7a33;
        goto LAB_100f7aa9;
      }
      *(char *)puVar5 = '\0';
      puVar5 = (uint *)((int)puVar5 + 1);
      param_3 = param_3 - 1;
    } while (param_3 != 0);
    return param_1;
  }
  uVar4 = param_3 >> 2;
  if (uVar4 != 0) {
    do {
      uVar1 = *param_2;
      uVar2 = *param_2;
      param_2 = param_2 + 1;
      if (((uVar1 ^ 0xffffffff ^ uVar1 + 0x7efefeff) & 0x81010100) != 0) {
        if ((char)uVar2 == '\0') {
          *puVar5 = 0;
joined_r0x100f7aa5:
          while( true ) {
            uVar4 = uVar4 - 1;
            puVar5 = puVar5 + 1;
            if (uVar4 == 0) break;
LAB_100f7aa9:
            *puVar5 = 0;
          }
          cVar3 = '\0';
          param_3 = param_3 & 3;
          if (param_3 != 0) goto LAB_100f7a33;
          return param_1;
        }
        if ((char)(uVar2 >> 8) == '\0') {
          *puVar5 = uVar2 & 0xff;
          goto joined_r0x100f7aa5;
        }
        if ((uVar2 & 0xff0000) == 0) {
          *puVar5 = uVar2 & 0xffff;
          goto joined_r0x100f7aa5;
        }
        if ((uVar2 & 0xff000000) == 0) {
          *puVar5 = uVar2;
          goto joined_r0x100f7aa5;
        }
      }
      *puVar5 = uVar2;
      puVar5 = puVar5 + 1;
      uVar4 = uVar4 - 1;
joined_r0x100f79ec:
    } while (uVar4 != 0);
    param_3 = param_3 & 3;
    if (param_3 == 0) {
      return param_1;
    }
  }
  do {
    cVar3 = (char)*param_2;
    param_2 = (uint *)((int)param_2 + 1);
    *(char *)puVar5 = cVar3;
    puVar5 = (uint *)((int)puVar5 + 1);
    if (cVar3 == '\0') {
      while (param_3 = param_3 - 1, param_3 != 0) {
LAB_100f7a33:
        *(char *)puVar5 = cVar3;
        puVar5 = (uint *)((int)puVar5 + 1);
      }
      return param_1;
    }
    param_3 = param_3 - 1;
  } while (param_3 != 0);
  return param_1;
}



/* FUNCTION FUN_10027720 ENTRY 10027720 */

void FUN_10027720(void)

{
  int in_EAX;
  
  SendMessageW(*(HWND *)(in_EAX + 0x20),0x469,0,0);
  return;
}



/* FUNCTION FUN_10041b70 ENTRY 10041b70 */

void FUN_10041b70(void)

{
  int *piVar1;
  int iVar2;
  int local_b0;
  undefined **local_a8 [29];
  int local_34;
  void *local_14;
  undefined1 *puStack_10;
  int local_c;
  
  local_c = 0xffffffff;
  puStack_10 = &LAB_101276f1;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  FUN_10004eb0();
  local_c = 0;
  FUN_10002280();
  FUN_10004d20(local_b0 + -0x10);
  FUN_100abc40(local_a8);
  local_c._0_1_ = 1;
  FUN_100d8024();
  local_a8[0] = CTipDlg::vftable;
  local_c._0_1_ = 2;
  piVar1 = (int *)(local_34 + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(**(int **)(local_34 + -0x10) + 4))();
  }
  local_c = (uint)local_c._1_3_ << 8;
  FUN_100d790d();
  local_c = 0xffffffff;
  piVar1 = (int *)(local_b0 + -4);
  LOCK();
  iVar2 = *piVar1;
  *piVar1 = *piVar1 + -1;
  UNLOCK();
  if (iVar2 == 1 || iVar2 + -1 < 0) {
    (**(code **)(**(int **)(local_b0 + -0x10) + 4))();
  }
  ExceptionList = local_14;
  return;
}



/* FUNCTION FUN_100024f0 ENTRY 100024f0 */

uint FUN_100024f0(LPSTR param_1,LPCWSTR param_2,int param_3,UINT param_4)

{
  int iVar1;
  
  if ((param_1 != (LPSTR)0x0) && (param_2 != (LPCWSTR)0x0)) {
    *param_1 = '\0';
    iVar1 = WideCharToMultiByte(param_4,0,param_2,-1,param_1,param_3,(LPCSTR)0x0,(LPBOOL)0x0);
    return -(uint)(iVar1 != 0) & (uint)param_1;
  }
  return 0;
}



/* FUNCTION FUN_100bb460 ENTRY 100bb460 */

void FUN_100bb460(int *param_1)

{
  char cVar1;
  int *piVar2;
  
  cVar1 = *(char *)((int)param_1 + 0x15);
  while (cVar1 == '\0') {
    FUN_100bb460(param_1[2]);
    piVar2 = (int *)*param_1;
    thunk_FUN_100f998b(param_1);
    param_1 = piVar2;
    cVar1 = *(char *)((int)piVar2 + 0x15);
  }
  return;
}



/* FUNCTION FUN_100bb6a0 ENTRY 100bb6a0 */

void FUN_100bb6a0(int *param_1)

{
  char cVar1;
  int *piVar2;
  
  cVar1 = *(char *)((int)param_1 + 0x2d);
  while (cVar1 == '\0') {
    FUN_100bb6a0(param_1[2]);
    piVar2 = (int *)*param_1;
    if (0xf < (uint)param_1[10]) {
      thunk_FUN_100f998b(param_1[5]);
    }
    param_1[10] = 0xf;
    param_1[9] = 0;
    *(undefined1 *)(param_1 + 5) = 0;
    thunk_FUN_100f998b(param_1);
    param_1 = piVar2;
    cVar1 = *(char *)((int)piVar2 + 0x2d);
  }
  return;
}



/* FUNCTION FUN_10002530 ENTRY 10002530 */

void FUN_10002530(undefined4 param_1,undefined4 param_2)

{
  FUN_10002280(param_2,&stack0x0000000c);
  return;
}



/* FUNCTION FUN_10095ae0 ENTRY 10095ae0 */

void __fastcall FUN_10095ae0(undefined4 param_1)

{
  uint uVar1;
  int iVar2;
  int iVar3;
  uint uVar4;
  undefined4 local_ac;
  undefined4 local_a8;
  int local_a4;
  undefined4 local_a0;
  undefined4 local_9c;
  undefined4 local_98;
  undefined4 local_94;
  undefined4 local_90;
  undefined4 local_8c;
  uint local_88 [3];
  undefined4 local_7c;
  int local_78;
  int local_74;
  short local_60;
  undefined1 local_5e [66];
  uint local_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 local_c;
  
  puStack_10 = &LAB_1011aa23;
  local_14 = ExceptionList;
  local_1c = DAT_10174ab0 ^ (uint)&local_ac;
  ExceptionList = &local_14;
  local_ac = 1;
  local_a4 = 0;
  local_a0 = 0;
  local_9c = 0;
  local_98 = 0;
  local_94 = 0;
  local_90 = 0;
  local_8c = 1;
  local_a8 = 0;
  local_c = 0;
  FUN_100960d0(DAT_10174ab0 ^ (uint)&stack0xffffff48);
  FUN_100968b0(local_88);
  local_c = CONCAT31(local_c._1_3_,1);
  local_60 = 0;
  FUN_100fcb30(local_5e,0,0x3e);
  iVar2 = FUN_100961a0(param_1);
  if ((iVar2 != 0) && (uVar4 = 0, local_88[0] != 0)) {
    do {
      uVar1 = local_88[0];
      FUN_100fcb30(&local_60,0,0x40);
      if (uVar1 <= uVar4) {
                    /* WARNING: Subroutine does not return */
        FUN_100025f0(0x80004005);
      }
      iVar2 = *(int *)(local_78 + uVar4 * 8);
      iVar3 = *(int *)(local_78 + 4 + uVar4 * 8) - iVar2 >> 1;
      FUN_100f9b43(&local_60,iVar2,iVar3);
      if (((local_60 == 0x30) && (1 < iVar3)) ||
         (iVar2 = thunk_FUN_100f7ac4(&local_60), 0xff < iVar2)) {
        local_ac = 0;
        break;
      }
      uVar4 = uVar4 + 1;
    } while (uVar4 < local_88[0]);
  }
  if (local_74 != 0) {
    FUN_100f998b(local_74);
  }
  thunk_FUN_100f998b(local_78);
  local_78 = 0;
  thunk_FUN_100f998b(local_7c);
  local_7c = 0;
  if (local_a4 != 0) {
    FUN_100f998b(local_a4);
  }
  ExceptionList = local_14;
  FUN_100f7705();
  return;
}



/* FUNCTION FUN_10011f00 ENTRY 10011f00 */

void FUN_10011f00(void)

{
  undefined1 auStack_20 [4];
  int local_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 local_c;
  
  local_c = 0xffffffff;
  puStack_10 = &LAB_1012dd7b;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  if (DAT_1017ad70 == 0) {
    local_1c = FUN_100d0d96(0x4c0,DAT_10174ab0 ^ (uint)auStack_20);
    local_c = 0;
    if (local_1c != 0) {
      DAT_1017ad70 = FUN_10011310(local_1c);
      ExceptionList = local_14;
      return;
    }
    DAT_1017ad70 = 0;
  }
  ExceptionList = local_14;
  return;
}



/* FUNCTION FUN_10016590 ENTRY 10016590 */

bool FUN_10016590(void)

{
  int in_EAX;
  int iVar1;
  
  if (*(int *)(in_EAX + 0x2c) == -1) {
    return false;
  }
  iVar1 = Net_QueryVideoState(*(int *)(in_EAX + 0x2c));
  return iVar1 == 0;
}


