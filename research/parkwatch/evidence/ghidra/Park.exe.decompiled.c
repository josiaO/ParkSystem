
/* FUNCTION DV_Capture ENTRY 00897298 */

void __stdcall DV_Capture(void)

{
                    /* WARNING: Could not recover jumptable at 0x00897298. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_Capture();
  return;
}



/* FUNCTION DV_CloseDevice ENTRY 0089729e */

void __stdcall DV_CloseDevice(void)

{
                    /* WARNING: Could not recover jumptable at 0x0089729e. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_CloseDevice();
  return;
}



/* FUNCTION DV_CloseRS485 ENTRY 008972a4 */

void __stdcall DV_CloseRS485(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972a4. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_CloseRS485();
  return;
}



/* FUNCTION DV_Exec ENTRY 008972aa */

void __stdcall DV_Exec(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972aa. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_Exec();
  return;
}



/* FUNCTION DV_InitSDK ENTRY 008972b0 */

void __stdcall DV_InitSDK(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972b0. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_InitSDK();
  return;
}



/* FUNCTION DV_OpenDevice ENTRY 008972b6 */

void __stdcall DV_OpenDevice(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972b6. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_OpenDevice();
  return;
}



/* FUNCTION DV_OpenRS485 ENTRY 008972bc */

void __stdcall DV_OpenRS485(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972bc. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_OpenRS485();
  return;
}



/* FUNCTION DV_ReleaseSDK ENTRY 008972c2 */

void __stdcall DV_ReleaseSDK(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972c2. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_ReleaseSDK();
  return;
}



/* FUNCTION DV_SetCaptureCallback ENTRY 008972c8 */

void __stdcall DV_SetCaptureCallback(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972c8. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_SetCaptureCallback();
  return;
}



/* FUNCTION DV_StartStream ENTRY 008972ce */

void __stdcall DV_StartStream(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972ce. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_StartStream();
  return;
}



/* FUNCTION DV_WriteRS485 ENTRY 008972d4 */

void __stdcall DV_WriteRS485(void)

{
                    /* WARNING: Could not recover jumptable at 0x008972d4. Too many branches */
                    /* WARNING: Treating indirect jump as call */
  DV_WriteRS485();
  return;
}



/* FUNCTION FUN_004a4774 ENTRY 004a4774 */

void FUN_004a4774(int param_1)

{
  if (*(int *)(param_1 + 0x3d24) != 0) {
    DV_Capture();
  }
  return;
}



/* FUNCTION FUN_004a47a0 ENTRY 004a47a0 */

void FUN_004a47a0(int param_1)

{
  if (*(int *)(param_1 + 0x3d28) != 0) {
    DV_Capture();
  }
  return;
}



/* FUNCTION FUN_004a47cc ENTRY 004a47cc */

void FUN_004a47cc(int param_1)

{
  if (*(int *)(param_1 + 0x3d34) != 0) {
    DV_Capture();
  }
  return;
}



/* FUNCTION FUN_004a47f8 ENTRY 004a47f8 */

void FUN_004a47f8(int param_1)

{
  if (*(int *)(param_1 + 0x3d38) != 0) {
    DV_Capture();
  }
  return;
}



/* FUNCTION FUN_0049f3f0 ENTRY 0049f3f0 */

void FUN_0049f3f0(int param_1,undefined4 param_2,undefined1 *param_3)

{
  char cVar1;
  undefined4 *in_FS_OFFSET;
  undefined4 local_28;
  
  FUN_0088747c(&DAT_008e2d44);
  *(undefined1 *)(param_1 + 0x3a94) = 0;
  FUN_005c5a98(*(undefined4 *)(param_1 + 0x400),*(undefined1 *)(param_1 + 0x3a94));
  *(undefined1 *)(param_1 + 0x3a92) = 0;
  FUN_005c5a98(*(undefined4 *)(param_1 + 0x38c),*(undefined1 *)(param_1 + 0x3a92));
  *(undefined1 *)(param_1 + 0x3a93) = 0;
  FUN_005c5a98(*(undefined4 *)(param_1 + 0x530),*(undefined1 *)(param_1 + 0x3a93));
  FUN_007bf4e0(*(undefined4 *)(param_1 + 0x7a4),0);
  FUN_005c5a98(*(undefined4 *)(param_1 + 0x42c),0);
  cVar1 = FUN_0040f0d0(&DAT_00935f34);
  if (cVar1 == '\0') {
    DV_CloseRS485();
    DV_CloseDevice();
    *(undefined4 *)(param_1 + 0x3d24) = 0;
    (**(code **)(**(int **)(param_1 + 0x458) + 0x90))();
  }
  cVar1 = FUN_0040f0d0(&DAT_00935f3c);
  if (cVar1 == '\0') {
    DV_CloseRS485();
    DV_CloseDevice();
    *(undefined4 *)(param_1 + 0x3d28) = 0;
    (**(code **)(**(int **)(param_1 + 0x48c) + 0x90))();
  }
  cVar1 = FUN_0040f0d0(&DAT_00935f38);
  if (cVar1 == '\0') {
    DV_CloseRS485();
    DV_CloseDevice();
    *(undefined4 *)(param_1 + 0x3d34) = 0;
    (**(code **)(**(int **)(param_1 + 0x470) + 0x90))();
  }
  cVar1 = FUN_0040f0d0(&DAT_00935f40);
  if (cVar1 == '\0') {
    DV_CloseRS485();
    DV_CloseDevice();
    *(undefined4 *)(param_1 + 0x3d38) = 0;
    (**(code **)(**(int **)(param_1 + 0x4a8) + 0x90))();
  }
  *param_3 = 2;
  *in_FS_OFFSET = local_28;
  return;
}



/* FUNCTION FUN_004b1b50 ENTRY 004b1b50 */

undefined4 FUN_004b1b50(int param_1)

{
  char cVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  undefined4 *in_FS_OFFSET;
  longdouble in_ST0;
  undefined4 local_4c;
  undefined4 local_28;
  undefined1 local_24 [4];
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined4 local_14;
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  FUN_0088747c(&DAT_008e7650);
  cVar1 = (**(code **)(**(int **)(param_1 + 0x518) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_4c;
  }
  else {
    if (*(int *)(param_1 + 0x3d24) != 0) {
      FUN_00886f3f();
      DV_Exec();
    }
    FUN_004060d8(local_8,&DAT_00935f54);
    FUN_00896b08(local_c,&DAT_008de8aa);
    FUN_0049c7c8();
    FUN_00896cc8(local_c,2);
    FUN_00406118(local_8,2);
    FUN_004a4824(param_1,1);
    FUN_004a5a64(param_1,1);
    FUN_00528d2c();
    *(double *)(param_1 + 0xc70) = (double)in_ST0;
    puVar2 = (undefined4 *)FUN_00896b08(local_10,s_Unknown_Vehicle_No__Entry_Arm_Ra_008de8af);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x464),*puVar2);
    FUN_00896cc8(local_10,2);
    uVar3 = FUN_0040234c(&local_14);
    FUN_008969e4(param_1 + 0xc70,uVar3);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x468),local_14);
    FUN_00896cc8(&local_14,2);
    FUN_00896b08(local_18,s_Unknown_008de8d5);
    FUN_00896cf0(param_1 + 0xbfc,local_18);
    FUN_00896cc8(local_18,2);
    FUN_00896b08(local_1c,s_Unknown_008de8dd);
    FUN_00896cf0(param_1 + 0xc18,local_1c);
    FUN_00896cc8(local_1c,2);
    FUN_00896b08(local_20,s_Unknown_008de8e5);
    FUN_00896cf0(param_1 + 0xc1c,local_20);
    FUN_00896cc8(local_20,2);
    cVar1 = FUN_004a7208(param_1,1);
    if (cVar1 == '\0') {
      FUN_00422c0b();
      FUN_0041fa89();
      FUN_0041ebdf();
      *in_FS_OFFSET = local_4c;
    }
    else {
      uVar3 = FUN_0040234c(&local_28);
      FUN_00896b08(local_24,s_Write_the_InRecord_s_table_error_008de8ed);
      FUN_00896d18(param_1 + 0x7f0,local_24,uVar3);
      FUN_004a45f0(param_1,local_28);
      FUN_00896cc8(&local_28,2);
      uVar3 = FUN_00896cc8(local_24,2);
      *in_FS_OFFSET = local_4c;
      local_4c = uVar3;
    }
  }
  return local_4c;
}



/* FUNCTION FUN_004b1e30 ENTRY 004b1e30 */

undefined4 FUN_004b1e30(int param_1)

{
  char cVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  undefined4 *in_FS_OFFSET;
  longdouble in_ST0;
  undefined4 local_50;
  undefined4 local_2c;
  undefined1 local_28 [4];
  undefined1 local_24 [4];
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined4 local_14;
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  FUN_0088747c(&DAT_008e7748);
  cVar1 = (**(code **)(**(int **)(param_1 + 0x510) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_50;
  }
  else {
    if (*(int *)(param_1 + 0x3d28) != 0) {
      FUN_00886f3f();
      DV_Exec();
    }
    FUN_004060d8(local_8,&DAT_00935f58);
    FUN_00896b08(local_c,&DAT_008de918);
    FUN_0049c7c8();
    FUN_00896cc8(local_c,2);
    FUN_00406118(local_8,2);
    FUN_004a4824(param_1,3);
    FUN_004a5a64(param_1,3);
    FUN_00528d2c();
    *(double *)(param_1 + 0x25c0) = (double)in_ST0;
    puVar2 = (undefined4 *)FUN_00896b08(local_10,s_Unknown_Vehicle_No__Exit_Arm_Rai_008de91d);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x498),*puVar2);
    FUN_00896cc8(local_10,2);
    uVar3 = FUN_0040234c(&local_14);
    FUN_008969e4(param_1 + 0x25c0,uVar3);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x49c),local_14);
    FUN_00896cc8(&local_14,2);
    FUN_00896b08(local_18,s_Unknown_008de942);
    FUN_00896cf0(param_1 + 0x254c,local_18);
    FUN_00896cc8(local_18,2);
    FUN_00896b08(local_1c,s_Unknown_008de94a);
    FUN_00896cf0(param_1 + 0x2568,local_1c);
    FUN_00896cc8(local_1c,2);
    FUN_00896b08(local_20,s_Unknown_008de952);
    FUN_00896cf0(param_1 + 0x256c,local_20);
    FUN_00896cc8(local_20,2);
    FUN_00896b08(local_24,&DAT_008de95a);
    FUN_00896cf0(param_1 + 0x25fc,local_24);
    FUN_00896cc8(local_24,2);
    cVar1 = FUN_004a9650(param_1,1);
    if (cVar1 == '\0') {
      FUN_00422c0b();
      FUN_0041fa89();
      FUN_0041ebdf();
      *in_FS_OFFSET = local_50;
    }
    else {
      uVar3 = FUN_0040234c(&local_2c);
      FUN_00896b08(local_28,s_Write_the_OutRecord_s_table_erro_008de95b);
      FUN_00896d18(param_1 + 0x2140,local_28,uVar3);
      FUN_004a45f0(param_1,local_2c);
      FUN_00896cc8(&local_2c,2);
      uVar3 = FUN_00896cc8(local_28,2);
      *in_FS_OFFSET = local_50;
      local_50 = uVar3;
    }
  }
  return local_50;
}



/* FUNCTION FUN_004b2144 ENTRY 004b2144 */

int FUN_004b2144(int param_1,undefined4 param_2)

{
  char cVar1;
  undefined2 uVar2;
  undefined4 uVar3;
  undefined4 *puVar4;
  undefined4 uVar5;
  undefined4 uVar6;
  int *in_FS_OFFSET;
  longdouble in_ST0;
  undefined4 uVar7;
  undefined4 uVar8;
  undefined4 uVar9;
  undefined4 uVar10;
  undefined4 uVar11;
  undefined4 uVar12;
  undefined4 uVar13;
  undefined4 uVar14;
  undefined4 uVar15;
  undefined4 uVar16;
  undefined4 uVar17;
  undefined1 *puVar18;
  ushort uVar19;
  undefined2 uStack_34e;
  double local_234;
  undefined4 *local_22c;
  undefined4 local_228;
  int local_224;
  int local_220;
  undefined2 local_210;
  int local_204;
  undefined1 local_1fc [4];
  undefined1 local_1f8 [4];
  undefined1 local_1f4 [4];
  undefined1 local_1f0 [4];
  undefined1 local_1ec [4];
  undefined1 local_1e8 [4];
  undefined1 local_1e4 [4];
  undefined1 local_1e0 [4];
  undefined1 local_1dc [4];
  undefined1 local_1d8 [4];
  undefined1 local_1d4 [4];
  undefined1 local_1d0 [4];
  undefined1 local_1cc [4];
  undefined1 local_1c8 [4];
  undefined1 local_1c4 [4];
  undefined1 local_1c0 [4];
  undefined1 local_1bc [4];
  undefined4 local_1b8;
  undefined2 local_1b4 [2];
  undefined1 local_1b0 [4];
  undefined1 local_1ac [4];
  undefined1 local_1a8 [4];
  undefined1 local_1a4 [4];
  undefined1 local_1a0 [4];
  undefined1 local_19c [4];
  undefined1 local_198 [4];
  undefined1 local_194 [4];
  undefined1 local_190 [4];
  undefined1 local_18c [4];
  undefined1 local_188 [4];
  undefined1 local_184 [4];
  undefined1 local_180 [4];
  undefined1 local_17c [4];
  undefined1 local_178 [4];
  undefined1 local_174 [4];
  undefined1 local_170 [4];
  undefined1 local_16c [4];
  undefined1 local_168 [4];
  undefined4 local_164;
  undefined1 local_160 [4];
  undefined1 local_15c [4];
  undefined1 local_158 [4];
  undefined1 local_154 [84];
  undefined1 local_100 [4];
  undefined1 local_fc [40];
  undefined1 local_d4 [4];
  undefined1 local_d0 [40];
  undefined1 local_a8 [4];
  undefined1 local_a4 [80];
  undefined1 local_54 [4];
  undefined1 local_50 [4];
  undefined1 local_4c [4];
  undefined1 local_48 [4];
  undefined1 local_44 [4];
  undefined1 local_40 [4];
  undefined1 local_3c [4];
  undefined1 local_38 [4];
  undefined1 local_34 [4];
  undefined1 local_30 [4];
  undefined1 local_2c [4];
  undefined1 local_28 [4];
  undefined1 local_24 [4];
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined1 local_14 [4];
  undefined4 local_10;
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  local_228 = param_2;
  local_224 = param_1;
  FUN_0088747c(&DAT_008e7bb8);
  cVar1 = (**(code **)(**(int **)(local_224 + 0x72c) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_220;
    return local_220;
  }
  local_210 = 0xc;
  uVar3 = FUN_0040234c(local_8);
  local_204 = local_204 + 1;
  FUN_005e2c30(*(undefined4 *)(local_224 + 0x740),uVar3);
  uVar2 = SUB42(local_8,0);
  uStack_34e = (undefined2)((uint)local_8 >> 0x10);
  uVar3 = FUN_0040234c(local_c);
  local_204 = local_204 + 1;
  FUN_00896f10(CONCAT22(uStack_34e,uVar2),uVar3);
  cVar1 = FUN_0040f0d0(local_c);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_c,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_8,2);
  if (cVar1 != '\0') {
    (**(code **)(**(int **)(local_224 + 0x740) + 0x74))(*(int **)(local_224 + 0x740),1);
    local_22c = (undefined4 *)(*(int *)(local_224 + 0x740) + 0x2ac);
    uVar3 = (**(code **)(*(int *)*local_22c + 0x54))((int *)*local_22c,DAT_00936070);
    (**(code **)(**(int **)(local_224 + 0x740) + 0xf0))(*(int **)(local_224 + 0x740),uVar3);
    FUN_00896cf0(local_224 + 0x2570,&DAT_00936070);
  }
  local_210 = 0x18;
  uVar3 = FUN_0040234c(&local_10);
  local_204 = local_204 + 1;
  FUN_008969e4(local_224 + 0x25c0,uVar3);
  FUN_005e2c68(*(undefined4 *)(local_224 + 0x49c),local_10);
  local_204 = local_204 + -1;
  FUN_00896cc8(&local_10,2);
  if (*(int *)(local_224 + 0x3d28) != 0) {
    FUN_00886f3f();
    DV_Exec();
  }
  local_210 = 0x24;
  FUN_00896b08(local_14,s_Temporary_008de993);
  local_204 = local_204 + 1;
  cVar1 = FUN_00896d9c(local_224 + 0x254c,local_14);
  if ((cVar1 == '\0') || (DAT_00935ec1 != '\x01')) {
    cVar1 = '\0';
  }
  else {
    cVar1 = '\x01';
  }
  local_204 = local_204 + -1;
  FUN_00896cc8(local_14,2);
  if (cVar1 == '\0') {
    local_210 = 0x3c;
    FUN_004060d8(local_20,&DAT_00935f58);
    local_204 = local_204 + 2;
    FUN_00896b08(local_24,&DAT_008de9a2);
    local_204 = local_204 + 1;
    FUN_0049c7c8();
    local_204 = local_204 + -1;
    FUN_00896cc8(local_24,2);
    local_204 = local_204 + -2;
    FUN_00406118(local_20,2);
  }
  else {
    local_210 = 0x30;
    FUN_004060d8(local_18,&DAT_00935f58);
    local_204 = local_204 + 2;
    FUN_00896b08(local_1c,&DAT_008de99d);
    local_204 = local_204 + 1;
    FUN_0049d018();
    local_204 = local_204 + -1;
    FUN_00896cc8(local_1c,2);
    local_204 = local_204 + -2;
    FUN_00406118(local_18,2);
  }
  (**(code **)(**(int **)(local_224 + 0x740) + 0x74))(*(int **)(local_224 + 0x740),0);
  (**(code **)(**(int **)(local_224 + 0x72c) + 0x74))(*(int **)(local_224 + 0x72c),0);
  (**(code **)(**(int **)(local_224 + 0x730) + 0x74))(*(int **)(local_224 + 0x730),0);
  (**(code **)(**(int **)(local_224 + 0x734) + 0x74))(*(int **)(local_224 + 0x734),0);
  if (DAT_00935ebc == '\x01') {
    (**(code **)(**(int **)(local_224 + 0x510) + 0x74))(*(int **)(local_224 + 0x510),1);
  }
  else {
    (**(code **)(**(int **)(local_224 + 0x510) + 0x74))(*(int **)(local_224 + 0x510),0);
  }
  local_210 = 0x48;
  FUN_00896b08(local_28,&DAT_008de9a7);
  local_204 = local_204 + 1;
  cVar1 = FUN_00896d9c(local_224 + 0x254c,local_28);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_28,2);
  if (cVar1 == '\0') {
    local_210 = 0x60;
    FUN_00896c64(local_30,u_Season_008de9ac);
    local_204 = local_204 + 1;
    cVar1 = FUN_00896d9c(local_224 + 0x254c,local_30);
    local_204 = local_204 + -1;
    FUN_00896cc8(local_30,2);
    if (cVar1 == '\0') {
      local_210 = 0x78;
      FUN_00896c64(local_38,u_Cash_008de9ba);
      local_204 = local_204 + 1;
      cVar1 = FUN_00896d9c(local_224 + 0x254c,local_38);
      local_204 = local_204 + -1;
      FUN_00896cc8(local_38,2);
      if (cVar1 == '\0') {
        FUN_00896cf0(local_224 + 0x3d54,&DAT_00935ffc);
        FUN_00896cf0(local_224 + 0x3d50,&DAT_00935ff8);
        local_210 = 0x90;
        uVar2 = FUN_0040234c(local_40);
        local_204 = local_204 + 1;
        FUN_00528d2c();
        local_234 = (double)in_ST0;
        FUN_008969e4(&local_234,uVar2);
        FUN_00896cf0(local_224 + 0x3d58,local_40);
        local_204 = local_204 + -1;
        FUN_00896cc8(local_40,2);
      }
      else {
        FUN_00896cf0(local_224 + 0x3d54,&DAT_00936004);
        FUN_00896cf0(local_224 + 0x3d50,&DAT_00935fe4);
        local_210 = 0x84;
        FUN_0040234c(local_3c);
        local_204 = local_204 + 1;
        FUN_0052839c();
        FUN_00896cf0(local_224 + 0x3d58,local_3c);
        local_204 = local_204 + -1;
        FUN_00896cc8(local_3c,2);
      }
    }
    else {
      FUN_00896cf0(local_224 + 0x3d54,&DAT_00936000);
      FUN_00896cf0(local_224 + 0x3d50,&DAT_00935fe0);
      local_210 = 0x6c;
      uVar3 = FUN_0040234c(local_34);
      local_204 = local_204 + 1;
      FUN_008968ec(local_224 + 0x2550,uVar3);
      FUN_00896cf0(local_224 + 0x3d58,local_34);
      local_204 = local_204 + -1;
      FUN_00896cc8(local_34,2);
    }
  }
  else {
    FUN_00896cf0(local_224 + 0x3d54,&DAT_00936008);
    FUN_00896cf0(local_224 + 0x3d50,&DAT_00935fe0);
    local_210 = 0x54;
    uVar3 = FUN_0040234c(local_2c);
    local_204 = local_204 + 1;
    FUN_008968ec(local_224 + 0x2550,uVar3);
    FUN_00896cf0(local_224 + 0x3d58,local_2c);
    local_204 = local_204 + -1;
    FUN_00896cc8(local_2c,2);
  }
  local_210 = 0x9c;
  uVar3 = FUN_0040234c(local_44);
  local_204 = local_204 + 1;
  FUN_008970d8(&DAT_008de9c4,local_224 + 0x256c,uVar3);
  uVar2 = SUB42(local_44,0);
  uStack_34e = (undefined2)((uint)local_44 >> 0x10);
  uVar3 = FUN_0040234c(local_4c);
  local_204 = local_204 + 1;
  FUN_00896b08(local_48,s__p300__008de9c9);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_48,uVar3);
  uVar2 = SUB42(local_4c,0);
  uStack_34e = (undefined2)((uint)local_4c >> 0x10);
  uVar3 = FUN_0040234c(local_50);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),&DAT_00935ff8,uVar3);
  FUN_00896cf0(local_224 + 0x3d08,local_50);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_50,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_4c,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_48,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_44,2);
  FUN_00422c0b();
  uVar2 = 1;
  local_210 = 0xa8;
  uVar3 = FUN_0040234c(local_54);
  local_204 = local_204 + 1;
  FUN_008970d8(&DAT_008de9d0,local_224 + 0x3d08,uVar3,uVar2);
  FUN_00430398(local_54);
  FUN_00497420();
  local_204 = local_204 + 1;
  FUN_00497630();
  FUN_0041fa89();
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_204 = local_204 + -1;
  FUN_00896cc8(local_54,2);
  FUN_0041ebdf();
  local_210 = 0xb4;
  FUN_00430398(local_224 + 0x3d50);
  FUN_00497420();
  uVar2 = SUB42(local_a4,0);
  uStack_34e = (undefined2)((uint)local_a4 >> 0x10);
  local_204 = local_204 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_a8,uVar3,CONCAT22(uStack_34e,uVar2));
  local_204 = local_204 + 2;
  FUN_00456030(local_224 + 0x3db0,local_a8);
  local_204 = local_204 + -2;
  FUN_00406118(local_a8,2);
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_210 = 0xc0;
  FUN_00430398(local_224 + 0x3d54);
  FUN_00497420();
  uVar2 = SUB42(local_d0,0);
  uStack_34e = (undefined2)((uint)local_d0 >> 0x10);
  local_204 = local_204 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_d4,uVar3,CONCAT22(uStack_34e,uVar2));
  local_204 = local_204 + 2;
  FUN_00456030(local_224 + 0x3db4,local_d4);
  local_204 = local_204 + -2;
  FUN_00406118(local_d4,2);
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_210 = 0xcc;
  FUN_00430398(local_224 + 0x3d58);
  FUN_00497420();
  uVar2 = SUB42(local_fc,0);
  uStack_34e = (undefined2)((uint)local_fc >> 0x10);
  local_204 = local_204 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_100,uVar3,CONCAT22(uStack_34e,uVar2));
  local_204 = local_204 + 2;
  FUN_00456030(local_224 + 0x3db8,local_100);
  local_204 = local_204 + -2;
  FUN_00406118(local_100,2);
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_210 = 0xd8;
  FUN_00430398(local_224 + 0x2568);
  FUN_00497420();
  local_204 = local_204 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_210 = 0xe4;
  FUN_00430398(local_224 + 0x256c);
  FUN_00497420();
  local_204 = local_204 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_204 = local_204 + -1;
  FUN_004974ec();
  local_210 = 0xf0;
  uVar3 = FUN_00455e50(local_154);
  local_204 = local_204 + 2;
  FUN_00455ec8(local_224 + 0x3db0,local_224 + 0x3db4,uVar3);
  FUN_0045df2c(local_154);
  FUN_004206a5();
  local_204 = local_204 + -2;
  FUN_00406118(local_154,2);
  FUN_0045df2c(local_224 + 0x3db8);
  FUN_004206a5();
  FUN_005c5a98(*(undefined4 *)(local_224 + 0x3f8),1);
  local_210 = 0xfc;
  FUN_00896b08(local_158,&DAT_008de9d5);
  local_204 = local_204 + 1;
  FUN_00896cf0(local_224 + 0x25fc,local_158);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_158,2);
  *(undefined4 *)(local_224 + 0x25e8) = 0;
  *(undefined4 *)(local_224 + 0x25ec) = 0;
  local_210 = 0x108;
  puVar4 = (undefined4 *)FUN_00896b08(local_15c,&DAT_008de9d6);
  local_204 = local_204 + 1;
  FUN_005e2c68(*(undefined4 *)(local_224 + 0x748),*puVar4);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_15c,2);
  cVar1 = FUN_004a9650(local_224,0);
  if (cVar1 != '\0') {
    local_210 = 0x114;
    uVar2 = FUN_0040234c(&local_164);
    local_204 = local_204 + 1;
    FUN_00896b08(local_160,s_Write_the_OutRecord_s_table_erro_008de9d8);
    local_204 = local_204 + 1;
    FUN_00896d18(local_224 + 0x2140,local_160,uVar2);
    FUN_004a45f0(local_224,local_164);
    local_204 = local_204 + -1;
    FUN_00896cc8(&local_164,2);
    local_204 = local_204 + -1;
    FUN_00896cc8(local_160,2);
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_224 + 0x2dd4) = uVar3;
    while ((*(int *)(local_224 + 0x2dd4) != *(int *)(local_224 + 0x2dd8) &&
           (cVar1 = FUN_00896d9c(local_224 + 0x2568,
                                 *(int *)(local_224 + 0x2dd4) * 4 + local_224 + 0x2600),
           cVar1 != '\0'))) {
      uVar3 = FUN_0043ee68();
      *(undefined4 *)(local_224 + 0x2dd4) = uVar3;
    }
    *(undefined1 *)(local_224 + 0x2ddc) = 0;
    *in_FS_OFFSET = local_220;
    return local_224;
  }
  cVar1 = FUN_0040f0d0(&DAT_00935fb8);
  if (cVar1 != '\0') goto LAB_004b3305;
  local_210 = 0x120;
  FUN_00896b08(local_168,&DAT_008de9fc);
  local_204 = local_204 + 1;
  cVar1 = FUN_00896d9c(local_224 + 0x254c,local_168);
  if (cVar1 == '\0') {
    FUN_00896b08(local_16c,s_Season_008dea00);
    local_204 = local_204 + 1;
    cVar1 = FUN_00896d9c(local_224 + 0x254c,local_16c);
    uVar19 = (ushort)(cVar1 != '\0');
    local_204 = local_204 + -1;
    FUN_00896cc8(local_16c,2);
    if (uVar19 != 0) goto LAB_004b2f2b;
    cVar1 = '\0';
  }
  else {
LAB_004b2f2b:
    cVar1 = '\x01';
  }
  local_204 = local_204 + -1;
  FUN_00896cc8(local_168,2);
  if (cVar1 == '\0') {
    local_210 = 0x138;
    FUN_00896b08(local_174,&DAT_008dea07);
    local_204 = local_204 + 1;
    cVar1 = FUN_00896d9c(local_224 + 0x254c,local_174);
    local_204 = local_204 + -1;
    FUN_00896cc8(local_174,2);
    if (cVar1 == '\0') {
      local_210 = 0x150;
      FUN_00896b08(local_17c,s_Temporary_008dea0c);
      local_204 = local_204 + 1;
      FUN_00896cf0(local_224 + 0x3d50,local_17c);
      local_204 = local_204 + -1;
      FUN_00896cc8(local_17c,2);
      FUN_00896cf0(local_224 + 0x3d58,&DAT_00935ff8);
    }
    else {
      FUN_00896cf0(local_224 + 0x3d50,&DAT_00936004);
      local_210 = 0x144;
      FUN_0040234c(local_178);
      local_204 = local_204 + 1;
      FUN_0052839c();
      FUN_00896cf0(local_224 + 0x3d58,local_178);
      local_204 = local_204 + -1;
      FUN_00896cc8(local_178,2);
    }
  }
  else {
    FUN_00896cf0(local_224 + 0x3d50,&DAT_00935fe0);
    local_210 = 300;
    uVar3 = FUN_0040234c(local_170);
    local_204 = local_204 + 1;
    FUN_008968ec(local_224 + 0x2550,uVar3);
    FUN_00896cf0(local_224 + 0x3d58,local_170);
    local_204 = local_204 + -1;
    FUN_00896cc8(local_170,2);
  }
  FUN_00896cf0(local_224 + 0x3d54,local_224 + 0x254c);
  local_210 = 0x15c;
  FUN_00896b08(local_180,s_have_a_good_Journey_008dea16);
  local_204 = local_204 + 1;
  FUN_00896cf0(local_224 + 0x3d08,local_180);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_180,2);
  uVar2 = 0;
  uVar17 = 1;
  uVar16 = 1;
  uVar3 = *(undefined4 *)(local_224 + 0x3bc8);
  uVar15 = 1;
  uVar14 = 0;
  uVar13 = 3;
  uVar12 = 1;
  uVar11 = *(undefined4 *)(local_224 + 0x3bc4);
  uVar10 = 1;
  uVar9 = 0x10;
  uVar8 = 0x40;
  uVar7 = 1;
  uVar5 = FUN_00897218(&DAT_00935fb8);
  local_210 = 0x168;
  uVar6 = FUN_0040234c(local_188);
  local_204 = local_204 + 1;
  FUN_00896b08(local_184,&DAT_008dea2a);
  local_204 = local_204 + 1;
  FUN_00896d18(local_224 + 0x3d50,local_184,uVar6,uVar5,uVar7,uVar8,uVar9,uVar10,uVar11,uVar12,
               uVar13,uVar14,uVar15,uVar3,uVar16,uVar17,uVar2);
  uVar3 = FUN_0040234c(local_18c);
  local_204 = local_204 + 1;
  FUN_00896d18(local_188,local_224 + 0x3d54,uVar3);
  uVar3 = FUN_0040234c(local_194);
  local_204 = local_204 + 1;
  FUN_00896b08(local_190,&DAT_008dea2c);
  local_204 = local_204 + 1;
  FUN_00896d18(local_18c,local_190,uVar3);
  uVar3 = FUN_0040234c(local_198);
  local_204 = local_204 + 1;
  FUN_00896d18(local_194,local_224 + 0x3d58,uVar3);
  FUN_00897218(local_198);
  (*DAT_00935d4c)();
  local_204 = local_204 + -1;
  FUN_00896cc8(local_198,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_194,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_190,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_18c,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_188,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_184,2);
LAB_004b3305:
  *(undefined4 *)(local_224 + 0x3bcc) = 0;
  local_210 = 0x180;
  uVar2 = FUN_0040234c(local_19c);
  local_204 = local_204 + 1;
  FUN_00896f9c(local_224 + 0x25a0,4,8,uVar2);
  uVar2 = SUB42(local_19c,0);
  uStack_34e = (undefined2)((uint)local_19c >> 0x10);
  uVar3 = FUN_0040234c(local_1a0);
  local_204 = local_204 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_34e,uVar2),uVar3);
  uVar2 = SUB42(local_1a0,0);
  uStack_34e = (undefined2)((uint)local_1a0 >> 0x10);
  uVar3 = FUN_0040234c(local_1a8);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1a4,&DAT_008dea2e);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_1a4,uVar3);
  uVar2 = SUB42(local_1a8,0);
  uStack_34e = (undefined2)((uint)local_1a8 >> 0x10);
  uVar3 = FUN_0040234c(local_1ac);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_224 + 0x25a0,uVar3);
  uVar2 = SUB42(local_1ac,0);
  uStack_34e = (undefined2)((uint)local_1ac >> 0x10);
  uVar3 = FUN_0040234c(local_1b4);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1b0,&DAT_008dea30);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_1b0,uVar3);
  uVar3 = FUN_0040234c(&local_1b8);
  local_204 = local_204 + 1;
  FUN_00525f2c(local_1b4[0],uVar3);
  FUN_005261f4(local_1b8);
  local_204 = local_204 + -1;
  FUN_00896cc8(&local_1b8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1b4,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1b0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1ac,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1a8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1a4,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1a0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_19c,2);
  local_210 = 0x18c;
  uVar2 = FUN_0040234c(local_1bc);
  local_204 = local_204 + 1;
  FUN_00896f9c(local_224 + 0x25a0,4,8,uVar2);
  uVar2 = SUB42(local_1bc,0);
  uStack_34e = (undefined2)((uint)local_1bc >> 0x10);
  uVar3 = FUN_0040234c(local_1c0);
  local_204 = local_204 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_34e,uVar2),uVar3);
  uVar2 = SUB42(local_1c0,0);
  uStack_34e = (undefined2)((uint)local_1c0 >> 0x10);
  uVar3 = FUN_0040234c(local_1c8);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1c4,&DAT_008dea3c);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_1c4,uVar3);
  uVar2 = SUB42(local_1c8,0);
  uStack_34e = (undefined2)((uint)local_1c8 >> 0x10);
  uVar3 = FUN_0040234c(local_1cc);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_224 + 0x25a0,uVar3);
  uVar2 = SUB42(local_1cc,0);
  uStack_34e = (undefined2)((uint)local_1cc >> 0x10);
  uVar3 = FUN_0040234c(local_1d4);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1d0,&DAT_008dea3e);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_1d0,uVar3);
  uVar3 = FUN_0040234c(local_1d8);
  local_204 = local_204 + 1;
  FUN_00896f9c(local_224 + 0x25a0,4,8,uVar3);
  puVar18 = local_1d8;
  uVar3 = FUN_0040234c(local_1dc);
  local_204 = local_204 + 1;
  FUN_00896d18(&DAT_00935e20,puVar18,uVar3);
  puVar18 = local_1dc;
  uVar3 = FUN_0040234c(local_1e4);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1e0,&DAT_008dea35);
  local_204 = local_204 + 1;
  FUN_00896d18(puVar18,local_1e0,uVar3);
  puVar18 = local_1e4;
  uVar3 = FUN_0040234c(local_1e8);
  local_204 = local_204 + 1;
  FUN_00896d18(puVar18,local_224 + 0x25a0,uVar3);
  puVar18 = local_1e8;
  uVar3 = FUN_0040234c(local_1f0);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1ec,&DAT_008dea37);
  local_204 = local_204 + 1;
  FUN_00896d18(puVar18,local_1ec,uVar3);
  FUN_0043ede8();
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1f0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1ec,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1e8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1e4,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1e0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1dc,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1d8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1d4,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1d0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1cc,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1c8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1c4,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1c0,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1bc,2);
  local_210 = 0x1a4;
  uVar3 = FUN_0040234c(local_1f4);
  local_204 = local_204 + 1;
  FUN_008970d8(s_delete_from_CardIssue_where_Rema_008dea43,local_224 + 0x2568,uVar3);
  uVar2 = SUB42(local_1f4,0);
  uStack_34e = (undefined2)((uint)local_1f4 >> 0x10);
  uVar3 = FUN_0040234c(local_1fc);
  local_204 = local_204 + 1;
  FUN_00896b08(local_1f8,&DAT_008dea84);
  local_204 = local_204 + 1;
  FUN_00896d18(CONCAT22(uStack_34e,uVar2),local_1f8,uVar3);
  FUN_004877f8();
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1fc,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1f8,2);
  local_204 = local_204 + -1;
  FUN_00896cc8(local_1f4,2);
  FUN_004a4e48(local_224);
  uVar3 = FUN_0043ee68();
  *(undefined4 *)(local_224 + 0x2dd4) = uVar3;
  while ((*(int *)(local_224 + 0x2dd4) != *(int *)(local_224 + 0x2dd8) &&
         (cVar1 = FUN_00896d9c(local_224 + 0x2568,
                               *(int *)(local_224 + 0x2dd4) * 4 + local_224 + 0x2600), cVar1 != '\0'
         ))) {
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_224 + 0x2dd4) = uVar3;
  }
  *(undefined1 *)(local_224 + 0x2ddc) = 0;
  *in_FS_OFFSET = local_220;
  return local_224;
}



/* FUNCTION FUN_004b39e8 ENTRY 004b39e8 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

int FUN_004b39e8(int param_1,undefined4 param_2)

{
  char cVar1;
  undefined2 uVar2;
  undefined4 uVar3;
  undefined4 uVar4;
  undefined4 uVar5;
  int *in_FS_OFFSET;
  longdouble in_ST0;
  longdouble lVar6;
  undefined4 uVar7;
  undefined4 uVar8;
  undefined4 uVar9;
  undefined4 uVar10;
  undefined4 uVar11;
  undefined4 uVar12;
  undefined4 uVar13;
  undefined4 uVar14;
  undefined4 uVar15;
  undefined4 uVar16;
  undefined2 uStack_366;
  undefined2 uVar17;
  ushort uVar18;
  undefined2 uStack_362;
  double local_248;
  undefined4 *local_240;
  undefined4 local_23c;
  int local_238;
  int local_234;
  undefined2 local_224;
  int local_218;
  undefined1 local_210 [4];
  undefined1 local_20c [4];
  undefined1 local_208 [4];
  undefined1 local_204 [4];
  undefined1 local_200 [4];
  undefined1 local_1fc [4];
  undefined1 local_1f8 [4];
  undefined1 local_1f4 [4];
  undefined1 local_1f0 [4];
  undefined1 local_1ec [4];
  undefined2 local_1e8 [2];
  undefined1 local_1e4 [4];
  undefined1 local_1e0 [4];
  undefined1 local_1dc [4];
  undefined1 local_1d8 [4];
  undefined1 local_1d4 [4];
  undefined1 local_1d0 [4];
  undefined4 local_1cc;
  undefined2 local_1c8 [2];
  undefined1 local_1c4 [4];
  undefined1 local_1c0 [4];
  undefined1 local_1bc [4];
  undefined1 local_1b8 [4];
  undefined1 local_1b4 [4];
  undefined1 local_1b0 [4];
  undefined1 local_1ac [4];
  undefined1 local_1a8 [4];
  undefined1 local_1a4 [4];
  undefined1 local_1a0 [4];
  undefined1 local_19c [4];
  undefined1 local_198 [4];
  undefined1 local_194 [4];
  undefined1 local_190 [4];
  undefined1 local_18c [4];
  undefined1 local_188 [4];
  undefined1 local_184 [4];
  undefined1 local_180 [4];
  undefined1 local_17c [4];
  undefined4 local_178;
  undefined1 local_174 [4];
  undefined4 local_170;
  undefined1 local_16c [4];
  undefined1 local_168 [4];
  undefined1 local_164 [4];
  undefined1 local_160 [4];
  undefined1 local_15c [4];
  undefined1 local_158 [84];
  undefined1 local_104 [4];
  undefined1 local_100 [40];
  undefined1 local_d8 [4];
  undefined1 local_d4 [40];
  undefined1 local_ac [4];
  undefined1 local_a8 [80];
  undefined1 local_58 [4];
  undefined1 local_54 [4];
  undefined1 local_50 [4];
  undefined1 local_4c [4];
  undefined1 local_48 [4];
  undefined1 local_44 [4];
  undefined1 local_40 [4];
  undefined1 local_3c [4];
  undefined1 local_38 [4];
  undefined1 local_34 [4];
  undefined1 local_30 [4];
  undefined1 local_2c [4];
  undefined1 local_28 [4];
  undefined4 local_24;
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined1 local_14 [4];
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  local_23c = param_2;
  local_238 = param_1;
  FUN_0088747c(&DAT_008e81ac);
  cVar1 = (**(code **)(**(int **)(local_238 + 0x730) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_234;
    return local_234;
  }
  local_224 = 0xc;
  uVar3 = FUN_0040234c(local_8);
  local_218 = local_218 + 1;
  FUN_005e2c30(*(undefined4 *)(local_238 + 0x740),uVar3);
  uVar2 = SUB42(local_8,0);
  uStack_362 = (undefined2)((uint)local_8 >> 0x10);
  uVar3 = FUN_0040234c(local_c);
  local_218 = local_218 + 1;
  FUN_00896f10(CONCAT22(uStack_362,uVar2),uVar3);
  cVar1 = FUN_0040f0d0(local_c);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_c,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_8,2);
  if (cVar1 != '\0') {
    (**(code **)(**(int **)(local_238 + 0x740) + 0x74))(*(int **)(local_238 + 0x740),1);
    local_240 = (undefined4 *)(*(int *)(local_238 + 0x740) + 0x2ac);
    uVar3 = (**(code **)(*(int *)*local_240 + 0x54))((int *)*local_240,DAT_00936070);
    (**(code **)(**(int **)(local_238 + 0x740) + 0xf0))(*(int **)(local_238 + 0x740),uVar3);
    FUN_00896cf0(local_238 + 0x2570,&DAT_00936070);
  }
  if (*(int *)(local_238 + 0x3d28) != 0) {
    FUN_00886f3f();
    DV_Exec();
  }
  local_224 = 0x18;
  FUN_00896b08(local_10,s_Temporary_008dea86);
  local_218 = local_218 + 1;
  cVar1 = FUN_00896d9c(local_238 + 0x254c,local_10);
  if ((cVar1 == '\0') || (DAT_00935ec1 != '\x01')) {
    cVar1 = '\0';
  }
  else {
    cVar1 = '\x01';
  }
  local_218 = local_218 + -1;
  FUN_00896cc8(local_10,2);
  if (cVar1 == '\0') {
    local_224 = 0x30;
    FUN_004060d8(local_1c,&DAT_00935f58);
    local_218 = local_218 + 2;
    FUN_00896b08(local_20,&DAT_008dea95);
    local_218 = local_218 + 1;
    FUN_0049c7c8();
    local_218 = local_218 + -1;
    FUN_00896cc8(local_20,2);
    local_218 = local_218 + -2;
    FUN_00406118(local_1c,2);
  }
  else {
    local_224 = 0x24;
    FUN_004060d8(local_14,&DAT_00935f58);
    local_218 = local_218 + 2;
    FUN_00896b08(local_18,&DAT_008dea90);
    local_218 = local_218 + 1;
    FUN_0049d018();
    local_218 = local_218 + -1;
    FUN_00896cc8(local_18,2);
    local_218 = local_218 + -2;
    FUN_00406118(local_14,2);
  }
  local_224 = 0x3c;
  uVar3 = FUN_0040234c(&local_24);
  local_218 = local_218 + 1;
  FUN_008969e4(local_238 + 0x25c0,uVar3);
  FUN_005e2c68(*(undefined4 *)(local_238 + 0x49c),local_24);
  local_218 = local_218 + -1;
  FUN_00896cc8(&local_24,2);
  *(undefined4 *)(local_238 + 0x3bcc) = 0;
  (**(code **)(**(int **)(local_238 + 0x740) + 0x74))(*(int **)(local_238 + 0x740),0);
  (**(code **)(**(int **)(local_238 + 0x72c) + 0x74))(*(int **)(local_238 + 0x72c),0);
  (**(code **)(**(int **)(local_238 + 0x730) + 0x74))(*(int **)(local_238 + 0x730),0);
  (**(code **)(**(int **)(local_238 + 0x734) + 0x74))(*(int **)(local_238 + 0x734),0);
  if (DAT_00935ebc == '\x01') {
    (**(code **)(**(int **)(local_238 + 0x510) + 0x74))(*(int **)(local_238 + 0x510),1);
  }
  else {
    (**(code **)(**(int **)(local_238 + 0x510) + 0x74))(*(int **)(local_238 + 0x510),0);
  }
  local_224 = 0x48;
  FUN_00896b08(local_28,s_Temporary_008dea9a);
  local_218 = local_218 + 1;
  cVar1 = FUN_00896d9c(local_238 + 0x254c,local_28);
  if (((cVar1 == '\0') || (DAT_00935e94 != '\x01')) ||
     (*(double *)(local_238 + 0x25d8) <= (double)_DAT_004b5444)) {
    cVar1 = '\0';
  }
  else {
    cVar1 = '\x01';
  }
  local_218 = local_218 + -1;
  FUN_00896cc8(local_28,2);
  if (cVar1 != '\0') {
    FUN_004e1e80(local_238);
  }
  local_224 = 0x54;
  FUN_00896b08(local_2c,&DAT_008deaa4);
  local_218 = local_218 + 1;
  cVar1 = FUN_00896d9c(local_238 + 0x254c,local_2c);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_2c,2);
  if (cVar1 == '\0') {
    local_224 = 0x6c;
    FUN_00896c64(local_34,u_Season_008deaa8);
    local_218 = local_218 + 1;
    cVar1 = FUN_00896d9c(local_238 + 0x254c,local_34);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_34,2);
    if (cVar1 == '\0') {
      local_224 = 0x84;
      FUN_00896c64(local_3c,u_Cash_008deab6);
      local_218 = local_218 + 1;
      cVar1 = FUN_00896d9c(local_238 + 0x254c,local_3c);
      local_218 = local_218 + -1;
      FUN_00896cc8(local_3c,2);
      if (cVar1 == '\0') {
        FUN_00896cf0(local_238 + 0x3d54,&DAT_00935ffc);
        FUN_00896cf0(local_238 + 0x3d50,&DAT_00935ff8);
        local_224 = 0x9c;
        uVar2 = FUN_0040234c(local_44);
        local_218 = local_218 + 1;
        FUN_00528d2c();
        local_248 = (double)in_ST0;
        FUN_008969e4(&local_248,uVar2);
        FUN_00896cf0(local_238 + 0x3d58,local_44);
        local_218 = local_218 + -1;
        FUN_00896cc8(local_44,2);
      }
      else {
        FUN_00896cf0(local_238 + 0x3d54,&DAT_00936004);
        FUN_00896cf0(local_238 + 0x3d50,&DAT_00935fe4);
        local_224 = 0x90;
        FUN_0040234c(local_40);
        local_218 = local_218 + 1;
        FUN_0052839c();
        FUN_00896cf0(local_238 + 0x3d58,local_40);
        local_218 = local_218 + -1;
        FUN_00896cc8(local_40,2);
      }
    }
    else {
      FUN_00896cf0(local_238 + 0x3d54,&DAT_00936000);
      FUN_00896cf0(local_238 + 0x3d50,&DAT_00935fe0);
      local_224 = 0x78;
      uVar3 = FUN_0040234c(local_38);
      local_218 = local_218 + 1;
      FUN_008968ec(local_238 + 0x2550,uVar3);
      FUN_00896cf0(local_238 + 0x3d58,local_38);
      local_218 = local_218 + -1;
      FUN_00896cc8(local_38,2);
    }
  }
  else {
    FUN_00896cf0(local_238 + 0x3d54,&DAT_00936008);
    FUN_00896cf0(local_238 + 0x3d50,&DAT_00935fe0);
    local_224 = 0x60;
    uVar3 = FUN_0040234c(local_30);
    local_218 = local_218 + 1;
    FUN_008968ec(local_238 + 0x2550,uVar3);
    FUN_00896cf0(local_238 + 0x3d58,local_30);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_30,2);
  }
  local_224 = 0xa8;
  uVar3 = FUN_0040234c(local_48);
  local_218 = local_218 + 1;
  FUN_008970d8(&DAT_008deac0,local_238 + 0x256c,uVar3);
  uVar17 = SUB42(local_48,0);
  uStack_362 = (undefined2)((uint)local_48 >> 0x10);
  uVar2 = FUN_0040234c(local_50);
  local_218 = local_218 + 1;
  FUN_00896b08(local_4c,s__p300__008deac5);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_4c,uVar2);
  uVar2 = SUB42(local_50,0);
  uStack_362 = (undefined2)((uint)local_50 >> 0x10);
  uVar3 = FUN_0040234c(local_54);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),&DAT_00935ff8,uVar3);
  FUN_00896cf0(local_238 + 0x3d08,local_54);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_54,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_50,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_4c,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_48,2);
  FUN_00422c0b();
  uVar2 = 1;
  local_224 = 0xb4;
  uVar3 = FUN_0040234c(local_58);
  local_218 = local_218 + 1;
  FUN_008970d8(&DAT_008deacc,local_238 + 0x3d08,uVar3,uVar2);
  FUN_00430398(local_58);
  FUN_00497420();
  local_218 = local_218 + 1;
  FUN_00497630();
  FUN_0041fa89();
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_218 = local_218 + -1;
  FUN_00896cc8(local_58,2);
  FUN_0041ebdf();
  local_224 = 0xc0;
  FUN_00430398(local_238 + 0x3d50);
  FUN_00497420();
  uVar2 = SUB42(local_a8,0);
  uStack_362 = (undefined2)((uint)local_a8 >> 0x10);
  local_218 = local_218 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_ac,uVar3,CONCAT22(uStack_362,uVar2));
  local_218 = local_218 + 2;
  FUN_00456030(local_238 + 0x3db0,local_ac);
  local_218 = local_218 + -2;
  FUN_00406118(local_ac,2);
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_224 = 0xcc;
  FUN_00430398(local_238 + 0x3d54);
  FUN_00497420();
  uVar2 = SUB42(local_d4,0);
  uStack_362 = (undefined2)((uint)local_d4 >> 0x10);
  local_218 = local_218 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_d8,uVar3,CONCAT22(uStack_362,uVar2));
  local_218 = local_218 + 2;
  FUN_00456030(local_238 + 0x3db4,local_d8);
  local_218 = local_218 + -2;
  FUN_00406118(local_d8,2);
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_224 = 0xd8;
  FUN_00430398(local_238 + 0x3d58);
  FUN_00497420();
  uVar2 = SUB42(local_100,0);
  uStack_362 = (undefined2)((uint)local_100 >> 0x10);
  local_218 = local_218 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_104,uVar3,CONCAT22(uStack_362,uVar2));
  local_218 = local_218 + 2;
  FUN_00456030(local_238 + 0x3db8,local_104);
  local_218 = local_218 + -2;
  FUN_00406118(local_104,2);
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_224 = 0xe4;
  FUN_00430398(local_238 + 0x2568);
  FUN_00497420();
  local_218 = local_218 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_224 = 0xf0;
  FUN_00430398(local_238 + 0x256c);
  FUN_00497420();
  local_218 = local_218 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_218 = local_218 + -1;
  FUN_004974ec();
  local_224 = 0xfc;
  uVar3 = FUN_00455e50(local_158);
  local_218 = local_218 + 2;
  FUN_00455ec8(local_238 + 0x3db0,local_238 + 0x3db4,uVar3);
  FUN_0045df2c(local_158);
  FUN_004206a5();
  local_218 = local_218 + -2;
  FUN_00406118(local_158,2);
  FUN_0045df2c(local_238 + 0x3db8);
  FUN_004206a5();
  FUN_005c5a98(*(undefined4 *)(local_238 + 0x3f8),1);
  local_224 = 0x108;
  FUN_00896b08(local_15c,&DAT_008dead1);
  local_218 = local_218 + 1;
  cVar1 = FUN_00896d9c(local_238 + 0x254c,local_15c);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_15c,2);
  if (cVar1 != '\0') {
    local_224 = 0x114;
    uVar3 = FUN_0040234c(local_160);
    local_218 = local_218 + 1;
    FUN_008970d8(&DAT_008dead6,local_238 + 0x256c,uVar3);
    uVar17 = SUB42(local_160,0);
    uStack_362 = (undefined2)((uint)local_160 >> 0x10);
    uVar2 = FUN_0040234c(local_168);
    local_218 = local_218 + 1;
    FUN_00896b08(local_164,s_Balance__008deadb);
    local_218 = local_218 + 1;
    FUN_00896d18(CONCAT22(uStack_362,uVar17),local_164,uVar2);
    uVar17 = SUB42(local_168,0);
    uStack_362 = (undefined2)((uint)local_168 >> 0x10);
    lVar6 = (longdouble)*(double *)(local_238 + 0x2558) -
            (longdouble)*(double *)(local_238 + 0x25e8);
    FUN_0040234c(local_16c,local_168,local_238,SUB104(lVar6,0),(int)((unkuint10)lVar6 >> 0x20),
                 (short)((unkuint10)lVar6 >> 0x40));
    local_218 = local_218 + 1;
    FUN_0052839c();
    uVar2 = SUB42(local_16c,0);
    uStack_366 = (undefined2)((uint)local_16c >> 0x10);
    uVar3 = FUN_0040234c(&local_170);
    local_218 = local_218 + 1;
    FUN_00896d18(CONCAT22(uStack_362,uVar17),CONCAT22(uStack_366,uVar2),uVar3);
    FUN_005e2c68(*(undefined4 *)(local_238 + 0x498),local_170);
    local_218 = local_218 + -1;
    FUN_00896cc8(&local_170,2);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_16c,2);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_168,2);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_164,2);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_160,2);
  }
  FUN_00896cf0(local_238 + 0x3cf8,&DAT_00936018);
  FUN_00896cf0(local_238 + 0x25fc,local_238 + 0x3cd4);
  cVar1 = FUN_004a9650(local_238,0);
  if (cVar1 != '\0') {
    local_224 = 0x120;
    uVar2 = FUN_0040234c(&local_178);
    local_218 = local_218 + 1;
    FUN_00896b08(local_174,s_Write_the_OutRecord_s_table_erro_008deae5);
    local_218 = local_218 + 1;
    FUN_00896d18(local_238 + 0x2140,local_174,uVar2);
    FUN_004a45f0(local_238,local_178);
    local_218 = local_218 + -1;
    FUN_00896cc8(&local_178,2);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_174,2);
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_238 + 0x2dd4) = uVar3;
    while ((*(int *)(local_238 + 0x2dd4) != *(int *)(local_238 + 0x2dd8) &&
           (cVar1 = FUN_00896d9c(local_238 + 0x2568,
                                 *(int *)(local_238 + 0x2dd4) * 4 + local_238 + 0x2600),
           cVar1 != '\0'))) {
      uVar3 = FUN_0043ee68();
      *(undefined4 *)(local_238 + 0x2dd4) = uVar3;
    }
    *(undefined1 *)(local_238 + 0x2ddc) = 0;
    *in_FS_OFFSET = local_234;
    return local_238;
  }
  cVar1 = FUN_0040f0d0(&DAT_00935fb8);
  if (cVar1 != '\0') goto LAB_004b4d6d;
  local_224 = 300;
  FUN_00896b08(local_17c,&DAT_008deb09);
  local_218 = local_218 + 1;
  cVar1 = FUN_00896d9c(local_238 + 0x254c,local_17c);
  if (cVar1 == '\0') {
    FUN_00896b08(local_180,s_Season_008deb0d);
    local_218 = local_218 + 1;
    cVar1 = FUN_00896d9c(local_238 + 0x254c,local_180);
    uVar18 = (ushort)(cVar1 != '\0');
    local_218 = local_218 + -1;
    FUN_00896cc8(local_180,2);
    if (uVar18 != 0) goto LAB_004b4993;
    cVar1 = '\0';
  }
  else {
LAB_004b4993:
    cVar1 = '\x01';
  }
  local_218 = local_218 + -1;
  FUN_00896cc8(local_17c,2);
  if (cVar1 == '\0') {
    local_224 = 0x144;
    FUN_00896b08(local_188,&DAT_008deb14);
    local_218 = local_218 + 1;
    cVar1 = FUN_00896d9c(local_238 + 0x254c,local_188);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_188,2);
    if (cVar1 == '\0') {
      local_224 = 0x15c;
      FUN_00896b08(local_190,s_Temporary_008deb19);
      local_218 = local_218 + 1;
      FUN_00896cf0(local_238 + 0x3d50,local_190);
      local_218 = local_218 + -1;
      FUN_00896cc8(local_190,2);
      FUN_00896cf0(local_238 + 0x3d58,&DAT_00935ff8);
    }
    else {
      FUN_00896cf0(local_238 + 0x3d50,&DAT_00936004);
      local_224 = 0x150;
      FUN_0040234c(local_18c);
      local_218 = local_218 + 1;
      FUN_0052839c();
      FUN_00896cf0(local_238 + 0x3d58,local_18c);
      local_218 = local_218 + -1;
      FUN_00896cc8(local_18c,2);
    }
  }
  else {
    FUN_00896cf0(local_238 + 0x3d50,&DAT_00935fe0);
    local_224 = 0x138;
    uVar3 = FUN_0040234c(local_184);
    local_218 = local_218 + 1;
    FUN_008968ec(local_238 + 0x2550,uVar3);
    FUN_00896cf0(local_238 + 0x3d58,local_184);
    local_218 = local_218 + -1;
    FUN_00896cc8(local_184,2);
  }
  FUN_00896cf0(local_238 + 0x3d54,local_238 + 0x254c);
  local_224 = 0x168;
  FUN_00896b08(local_194,s_have_a_good_Journey_008deb23);
  local_218 = local_218 + 1;
  FUN_00896cf0(local_238 + 0x3d08,local_194);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_194,2);
  uVar17 = 0;
  uVar2 = 1;
  uVar16 = 1;
  uVar3 = *(undefined4 *)(local_238 + 0x3bc8);
  uVar15 = 1;
  uVar14 = 0;
  uVar13 = 3;
  uVar12 = 1;
  uVar11 = *(undefined4 *)(local_238 + 0x3bc4);
  uVar10 = 1;
  uVar9 = 0x10;
  uVar8 = 0x40;
  uVar7 = 1;
  uVar4 = FUN_00897218(&DAT_00935fb8);
  local_224 = 0x174;
  uVar5 = FUN_0040234c(local_19c);
  local_218 = local_218 + 1;
  FUN_00896b08(local_198,&DAT_008deb37);
  local_218 = local_218 + 1;
  FUN_00896d18(local_238 + 0x3d50,local_198,uVar5,uVar4,uVar7,uVar8,uVar9,uVar10,uVar11,uVar12,
               uVar13,uVar14,uVar15,uVar3,uVar16,uVar2,uVar17);
  uVar3 = FUN_0040234c(local_1a0);
  local_218 = local_218 + 1;
  FUN_00896d18(local_19c,local_238 + 0x3d54,uVar3);
  uVar3 = FUN_0040234c(local_1a8);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1a4,&DAT_008deb39);
  local_218 = local_218 + 1;
  FUN_00896d18(local_1a0,local_1a4,uVar3);
  uVar3 = FUN_0040234c(local_1ac);
  local_218 = local_218 + 1;
  FUN_00896d18(local_1a8,local_238 + 0x3d58,uVar3);
  FUN_00897218(local_1ac);
  (*DAT_00935d4c)();
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1ac,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1a8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1a4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1a0,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_19c,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_198,2);
LAB_004b4d6d:
  local_224 = 0x18c;
  uVar2 = FUN_0040234c(local_1b0);
  local_218 = local_218 + 1;
  FUN_00896f9c(local_238 + 0x25a0,4,8,uVar2);
  uVar2 = SUB42(local_1b0,0);
  uStack_362 = (undefined2)((uint)local_1b0 >> 0x10);
  uVar3 = FUN_0040234c(local_1b4);
  local_218 = local_218 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_362,uVar2),uVar3);
  uVar17 = SUB42(local_1b4,0);
  uStack_362 = (undefined2)((uint)local_1b4 >> 0x10);
  uVar2 = FUN_0040234c(local_1bc);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1b8,&DAT_008deb3b);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_1b8,uVar2);
  uVar2 = SUB42(local_1bc,0);
  uStack_362 = (undefined2)((uint)local_1bc >> 0x10);
  uVar3 = FUN_0040234c(local_1c0);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),local_238 + 0x25a0,uVar3);
  uVar17 = SUB42(local_1c0,0);
  uStack_362 = (undefined2)((uint)local_1c0 >> 0x10);
  uVar2 = FUN_0040234c(local_1c8);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1c4,&DAT_008deb3d);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_1c4,uVar2);
  uVar3 = FUN_0040234c(&local_1cc);
  local_218 = local_218 + 1;
  FUN_00525f2c(local_1c8[0],uVar3);
  FUN_005261f4(local_1cc);
  local_218 = local_218 + -1;
  FUN_00896cc8(&local_1cc,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1c8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1c4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1c0,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1bc,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1b8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1b4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1b0,2);
  local_224 = 0x198;
  uVar2 = FUN_0040234c(local_1d0);
  local_218 = local_218 + 1;
  FUN_00896f9c(local_238 + 0x25a0,4,8,uVar2);
  uVar2 = SUB42(local_1d0,0);
  uStack_362 = (undefined2)((uint)local_1d0 >> 0x10);
  uVar3 = FUN_0040234c(local_1d4);
  local_218 = local_218 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_362,uVar2),uVar3);
  uVar17 = SUB42(local_1d4,0);
  uStack_362 = (undefined2)((uint)local_1d4 >> 0x10);
  uVar2 = FUN_0040234c(local_1dc);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1d8,&DAT_008deb49);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_1d8,uVar2);
  uVar2 = SUB42(local_1dc,0);
  uStack_362 = (undefined2)((uint)local_1dc >> 0x10);
  uVar3 = FUN_0040234c(local_1e0);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),local_238 + 0x25a0,uVar3);
  uVar17 = SUB42(local_1e0,0);
  uStack_362 = (undefined2)((uint)local_1e0 >> 0x10);
  uVar2 = FUN_0040234c(local_1e8);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1e4,&DAT_008deb4b);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_1e4,uVar2);
  uVar2 = FUN_0040234c(local_1ec);
  local_218 = local_218 + 1;
  FUN_00896f9c(local_238 + 0x25a0,4,8,uVar2);
  uVar2 = SUB42(local_1ec,0);
  uStack_366 = (undefined2)((uint)local_1ec >> 0x10);
  uVar3 = FUN_0040234c(local_1f0);
  local_218 = local_218 + 1;
  FUN_00896d18(&DAT_00935e20,CONCAT22(uStack_366,uVar2),uVar3,local_1e8[0]);
  uVar2 = SUB42(local_1f0,0);
  uStack_366 = (undefined2)((uint)local_1f0 >> 0x10);
  uVar3 = FUN_0040234c(local_1f8);
  local_218 = local_218 + 1;
  FUN_00896b08(local_1f4,&DAT_008deb42);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_366,uVar2),local_1f4,uVar3);
  uVar2 = SUB42(local_1f8,0);
  uStack_366 = (undefined2)((uint)local_1f8 >> 0x10);
  uVar3 = FUN_0040234c(local_1fc);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_366,uVar2),local_238 + 0x25a0,uVar3);
  uVar2 = SUB42(local_1fc,0);
  uStack_366 = (undefined2)((uint)local_1fc >> 0x10);
  uVar3 = FUN_0040234c(local_204);
  local_218 = local_218 + 1;
  FUN_00896b08(local_200,&DAT_008deb44);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_366,uVar2),local_200,uVar3);
  FUN_0043ede8();
  local_218 = local_218 + -1;
  FUN_00896cc8(local_204,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_200,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1fc,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1f8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1f4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1f0,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1ec,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1e8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1e4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1e0,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1dc,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1d8,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1d4,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_1d0,2);
  local_224 = 0x1b0;
  uVar3 = FUN_0040234c(local_208);
  local_218 = local_218 + 1;
  FUN_008970d8(s_delete_from_CardIssue_where_Rema_008deb50,local_238 + 0x2568,uVar3);
  uVar17 = SUB42(local_208,0);
  uStack_362 = (undefined2)((uint)local_208 >> 0x10);
  uVar2 = FUN_0040234c(local_210);
  local_218 = local_218 + 1;
  FUN_00896b08(local_20c,&DAT_008deb91);
  local_218 = local_218 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar17),local_20c,uVar2);
  FUN_004877f8();
  local_218 = local_218 + -1;
  FUN_00896cc8(local_210,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_20c,2);
  local_218 = local_218 + -1;
  FUN_00896cc8(local_208,2);
  FUN_004a4e48(local_238);
  uVar3 = FUN_0043ee68();
  *(undefined4 *)(local_238 + 0x2dd4) = uVar3;
  while ((*(int *)(local_238 + 0x2dd4) != *(int *)(local_238 + 0x2dd8) &&
         (cVar1 = FUN_00896d9c(local_238 + 0x2568,
                               *(int *)(local_238 + 0x2dd4) * 4 + local_238 + 0x2600), cVar1 != '\0'
         ))) {
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_238 + 0x2dd4) = uVar3;
  }
  *(undefined1 *)(local_238 + 0x2ddc) = 0;
  *in_FS_OFFSET = local_234;
  return local_238;
}



/* FUNCTION FUN_004b6180 ENTRY 004b6180 */
/* SKIPPED: function body is too large for this pass */

/* FUNCTION FUN_004cf2ec ENTRY 004cf2ec */

undefined4 FUN_004cf2ec(int param_1)

{
  char cVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  undefined4 *in_FS_OFFSET;
  longdouble in_ST0;
  undefined4 local_4c;
  undefined4 local_28;
  undefined1 local_24 [4];
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined4 local_14;
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  FUN_0088747c(&DAT_008ee584);
  cVar1 = (**(code **)(**(int **)(param_1 + 0x514) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_4c;
  }
  else {
    if (*(int *)(param_1 + 0x3d34) != 0) {
      FUN_00886f3f();
      DV_Exec();
    }
    FUN_004060d8(local_8,&DAT_00935f5c);
    FUN_00896b08(local_c,&DAT_008dfd25);
    FUN_0049c7c8();
    FUN_00896cc8(local_c,2);
    FUN_00406118(local_8,2);
    FUN_004a4824(param_1,2);
    FUN_004a5a64(param_1,2);
    FUN_00528d2c();
    *(double *)(param_1 + 0x1918) = (double)in_ST0;
    puVar2 = (undefined4 *)FUN_00896b08(local_10,s_Unknown_Vehicle_No__Entry_Arm_Ra_008dfd2a);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x47c),*puVar2);
    FUN_00896cc8(local_10,2);
    uVar3 = FUN_0040234c(&local_14);
    FUN_008969e4(param_1 + 0x1918,uVar3);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x480),local_14);
    FUN_00896cc8(&local_14,2);
    FUN_00896b08(local_18,s_Unknown_008dfd50);
    FUN_00896cf0(param_1 + 0x18a4,local_18);
    FUN_00896cc8(local_18,2);
    FUN_00896b08(local_1c,s_Unknown_008dfd58);
    FUN_00896cf0(param_1 + 0x18c0,local_1c);
    FUN_00896cc8(local_1c,2);
    FUN_00896b08(local_20,s_Unknown_008dfd60);
    FUN_00896cf0(param_1 + 0x18c4,local_20);
    FUN_00896cc8(local_20,2);
    cVar1 = FUN_004ac6ac(param_1,1);
    if (cVar1 == '\0') {
      FUN_00422c0b();
      FUN_0041fa89();
      FUN_0041ebdf();
      *in_FS_OFFSET = local_4c;
    }
    else {
      uVar3 = FUN_0040234c(&local_28);
      FUN_00896b08(local_24,s_Write_the_InRecord_s_table_error_008dfd68);
      FUN_00896d18(param_1 + 0x1498,local_24,uVar3);
      FUN_004a45f0(param_1,local_28);
      FUN_00896cc8(&local_28,2);
      uVar3 = FUN_00896cc8(local_24,2);
      *in_FS_OFFSET = local_4c;
      local_4c = uVar3;
    }
  }
  return local_4c;
}



/* FUNCTION FUN_004cf5cc ENTRY 004cf5cc */

undefined4 FUN_004cf5cc(int param_1)

{
  char cVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  undefined4 *in_FS_OFFSET;
  longdouble in_ST0;
  undefined4 local_50;
  undefined4 local_2c;
  undefined1 local_28 [4];
  undefined1 local_24 [4];
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined4 local_14;
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  FUN_0088747c(&DAT_008ee67c);
  cVar1 = (**(code **)(**(int **)(param_1 + 0x50c) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_50;
  }
  else {
    if (*(int *)(param_1 + 0x3d38) != 0) {
      FUN_00886f3f();
      DV_Exec();
    }
    FUN_004060d8(local_8,&DAT_00935f60);
    FUN_00896b08(local_c,&DAT_008dfd93);
    FUN_0049c7c8();
    FUN_00896cc8(local_c,2);
    FUN_00406118(local_8,2);
    FUN_004a4824(param_1,4);
    FUN_004a5a64(param_1,4);
    FUN_00528d2c();
    *(double *)(param_1 + 0x3268) = (double)in_ST0;
    puVar2 = (undefined4 *)FUN_00896b08(local_10,s_Unknown_Vehicle_No__Exit_Arm_Rai_008dfd98);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x4b4),*puVar2);
    FUN_00896cc8(local_10,2);
    uVar3 = FUN_0040234c(&local_14);
    FUN_008969e4(param_1 + 0x3268,uVar3);
    FUN_005e2c68(*(undefined4 *)(param_1 + 0x4b8),local_14);
    FUN_00896cc8(&local_14,2);
    FUN_00896b08(local_18,s_Unknown_008dfdbd);
    FUN_00896cf0(param_1 + 0x31f4,local_18);
    FUN_00896cc8(local_18,2);
    FUN_00896b08(local_1c,s_Unknown_008dfdc5);
    FUN_00896cf0(param_1 + 0x3210,local_1c);
    FUN_00896cc8(local_1c,2);
    FUN_00896b08(local_20,s_Unknown_008dfdcd);
    FUN_00896cf0(param_1 + 0x3214,local_20);
    FUN_00896cc8(local_20,2);
    FUN_00896b08(local_24,&DAT_008dfdd5);
    FUN_00896cf0(param_1 + 0x32a4,local_24);
    FUN_00896cc8(local_24,2);
    cVar1 = FUN_004aeaf4(param_1,1);
    if (cVar1 == '\0') {
      FUN_00422c0b();
      FUN_0041fa89();
      FUN_0041ebdf();
      *in_FS_OFFSET = local_50;
    }
    else {
      uVar3 = FUN_0040234c(&local_2c);
      FUN_00896b08(local_28,s_Write_the_OutRecord_s_table_erro_008dfdd6);
      FUN_00896d18(param_1 + 0x2de8,local_28,uVar3);
      FUN_004a45f0(param_1,local_2c);
      FUN_00896cc8(&local_2c,2);
      uVar3 = FUN_00896cc8(local_28,2);
      *in_FS_OFFSET = local_50;
      local_50 = uVar3;
    }
  }
  return local_50;
}



/* FUNCTION FUN_004cfa70 ENTRY 004cfa70 */
/* SKIPPED: function body is too large for this pass */

/* FUNCTION FUN_004e02e4 ENTRY 004e02e4 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

int FUN_004e02e4(int param_1,undefined4 param_2)

{
  char cVar1;
  undefined2 uVar2;
  undefined4 uVar3;
  undefined4 uVar4;
  undefined4 uVar5;
  int *in_FS_OFFSET;
  longdouble in_ST0;
  longdouble lVar6;
  undefined4 uVar7;
  undefined4 uVar8;
  undefined4 uVar9;
  undefined4 uVar10;
  undefined4 uVar11;
  undefined4 uVar12;
  undefined4 uVar13;
  undefined4 uVar14;
  undefined4 uVar15;
  undefined4 uVar16;
  undefined2 uStack_362;
  undefined2 uVar17;
  ushort uVar18;
  undefined2 uStack_35e;
  double local_244;
  undefined4 *local_23c;
  undefined4 local_238;
  int local_234;
  int local_230;
  undefined2 local_220;
  int local_214;
  undefined1 local_20c [4];
  undefined1 local_208 [4];
  undefined1 local_204 [4];
  undefined1 local_200 [4];
  undefined1 local_1fc [4];
  undefined1 local_1f8 [4];
  undefined1 local_1f4 [4];
  undefined1 local_1f0 [4];
  undefined1 local_1ec [4];
  undefined1 local_1e8 [4];
  undefined1 local_1e4 [4];
  undefined1 local_1e0 [4];
  undefined1 local_1dc [4];
  undefined1 local_1d8 [4];
  undefined1 local_1d4 [4];
  undefined1 local_1d0 [4];
  undefined1 local_1cc [4];
  undefined1 local_1c8 [4];
  undefined1 local_1c4 [4];
  undefined1 local_1c0 [4];
  undefined1 local_1bc [4];
  undefined1 local_1b8 [4];
  undefined1 local_1b4 [4];
  undefined1 local_1b0 [4];
  undefined1 local_1ac [4];
  undefined1 local_1a8 [4];
  undefined1 local_1a4 [4];
  undefined1 local_1a0 [4];
  undefined1 local_19c [4];
  undefined1 local_198 [4];
  undefined4 local_194;
  undefined2 local_190 [2];
  undefined1 local_18c [4];
  undefined1 local_188 [4];
  undefined1 local_184 [4];
  undefined1 local_180 [4];
  undefined1 local_17c [4];
  undefined1 local_178 [4];
  undefined4 local_174;
  undefined1 local_170 [4];
  undefined4 local_16c;
  undefined1 local_168 [4];
  undefined1 local_164 [4];
  undefined1 local_160 [4];
  undefined1 local_15c [4];
  undefined1 local_158 [4];
  undefined1 local_154 [84];
  undefined1 local_100 [4];
  undefined1 local_fc [40];
  undefined1 local_d4 [4];
  undefined1 local_d0 [40];
  undefined1 local_a8 [4];
  undefined1 local_a4 [80];
  undefined1 local_54 [4];
  undefined1 local_50 [4];
  undefined1 local_4c [4];
  undefined1 local_48 [4];
  undefined1 local_44 [4];
  undefined1 local_40 [4];
  undefined1 local_3c [4];
  undefined1 local_38 [4];
  undefined1 local_34 [4];
  undefined1 local_30 [4];
  undefined1 local_2c [4];
  undefined1 local_28 [4];
  undefined4 local_24;
  undefined1 local_20 [4];
  undefined1 local_1c [4];
  undefined1 local_18 [4];
  undefined1 local_14 [4];
  undefined1 local_10 [4];
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  local_238 = param_2;
  local_234 = param_1;
  FUN_0088747c(&DAT_008f22f0);
  cVar1 = (**(code **)(**(int **)(local_234 + 0x760) + 0x5c))();
  if (cVar1 == '\0') {
    *in_FS_OFFSET = local_230;
    return local_230;
  }
  local_220 = 0xc;
  uVar3 = FUN_0040234c(local_8);
  local_214 = local_214 + 1;
  FUN_005e2c30(*(undefined4 *)(local_234 + 0x774),uVar3);
  uVar2 = SUB42(local_8,0);
  uStack_35e = (undefined2)((uint)local_8 >> 0x10);
  uVar3 = FUN_0040234c(local_c);
  local_214 = local_214 + 1;
  FUN_00896f10(CONCAT22(uStack_35e,uVar2),uVar3);
  cVar1 = FUN_0040f0d0(local_c);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_8,2);
  if (cVar1 != '\0') {
    (**(code **)(**(int **)(local_234 + 0x774) + 0x74))(*(int **)(local_234 + 0x774),1);
    local_23c = (undefined4 *)(*(int *)(local_234 + 0x774) + 0x2ac);
    uVar3 = (**(code **)(*(int *)*local_23c + 0x54))((int *)*local_23c,DAT_00936070);
    (**(code **)(**(int **)(local_234 + 0x774) + 0xf0))(*(int **)(local_234 + 0x774),uVar3);
    FUN_00896cf0(local_234 + 0x3218,&DAT_00936070);
  }
  if (*(int *)(local_234 + 0x3d38) != 0) {
    FUN_00886f3f();
    DV_Exec();
  }
  local_220 = 0x18;
  FUN_00896b08(local_10,s_Temporary_008e08bb);
  local_214 = local_214 + 1;
  cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_10);
  if ((cVar1 == '\0') || (DAT_00935ec1 != '\x01')) {
    cVar1 = '\0';
  }
  else {
    cVar1 = '\x01';
  }
  local_214 = local_214 + -1;
  FUN_00896cc8(local_10,2);
  if (cVar1 == '\0') {
    local_220 = 0x30;
    FUN_004060d8(local_1c,&DAT_00935f60);
    local_214 = local_214 + 2;
    FUN_00896b08(local_20,&DAT_008e08ca);
    local_214 = local_214 + 1;
    FUN_0049c7c8();
    local_214 = local_214 + -1;
    FUN_00896cc8(local_20,2);
    local_214 = local_214 + -2;
    FUN_00406118(local_1c,2);
  }
  else {
    local_220 = 0x24;
    FUN_004060d8(local_14,&DAT_00935f60);
    local_214 = local_214 + 2;
    FUN_00896b08(local_18,&DAT_008e08c5);
    local_214 = local_214 + 1;
    FUN_0049d018();
    local_214 = local_214 + -1;
    FUN_00896cc8(local_18,2);
    local_214 = local_214 + -2;
    FUN_00406118(local_14,2);
  }
  local_220 = 0x3c;
  uVar3 = FUN_0040234c(&local_24);
  local_214 = local_214 + 1;
  FUN_008969e4(local_234 + 0x3268,uVar3);
  FUN_005e2c68(*(undefined4 *)(local_234 + 0x4b8),local_24);
  local_214 = local_214 + -1;
  FUN_00896cc8(&local_24,2);
  (**(code **)(**(int **)(local_234 + 0x774) + 0x74))(*(int **)(local_234 + 0x774),0);
  (**(code **)(**(int **)(local_234 + 0x75c) + 0x74))(*(int **)(local_234 + 0x75c),0);
  (**(code **)(**(int **)(local_234 + 0x760) + 0x74))(*(int **)(local_234 + 0x760),0);
  (**(code **)(**(int **)(local_234 + 0x764) + 0x74))(*(int **)(local_234 + 0x764),0);
  if (DAT_00935ebc == '\x01') {
    (**(code **)(**(int **)(local_234 + 0x50c) + 0x74))(*(int **)(local_234 + 0x50c),1);
  }
  else {
    (**(code **)(**(int **)(local_234 + 0x50c) + 0x74))(*(int **)(local_234 + 0x50c),0);
  }
  local_220 = 0x48;
  FUN_00896b08(local_28,s_Temporary_008e08cf);
  local_214 = local_214 + 1;
  cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_28);
  if (((cVar1 == '\0') || (DAT_00935e94 != '\x01')) ||
     (*(double *)(local_234 + 0x3280) <= (double)_DAT_004e1d00)) {
    cVar1 = '\0';
  }
  else {
    cVar1 = '\x01';
  }
  local_214 = local_214 + -1;
  FUN_00896cc8(local_28,2);
  if (cVar1 != '\0') {
    FUN_004e2824(local_234);
  }
  local_220 = 0x54;
  FUN_00896b08(local_2c,&DAT_008e08d9);
  local_214 = local_214 + 1;
  cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_2c);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_2c,2);
  if (cVar1 == '\0') {
    local_220 = 0x6c;
    FUN_00896c64(local_34,u_Season_008e08de);
    local_214 = local_214 + 1;
    cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_34);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_34,2);
    if (cVar1 == '\0') {
      local_220 = 0x84;
      FUN_00896c64(local_3c,u_Cash_008e08ec);
      local_214 = local_214 + 1;
      cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_3c);
      local_214 = local_214 + -1;
      FUN_00896cc8(local_3c,2);
      if (cVar1 == '\0') {
        FUN_00896cf0(local_234 + 0x3d54,&DAT_00935ffc);
        FUN_00896cf0(local_234 + 0x3d50,&DAT_00935ff8);
        local_220 = 0x9c;
        uVar2 = FUN_0040234c(local_44);
        local_214 = local_214 + 1;
        FUN_00528d2c();
        local_244 = (double)in_ST0;
        FUN_008969e4(&local_244,uVar2);
        FUN_00896cf0(local_234 + 0x3d58,local_44);
        local_214 = local_214 + -1;
        FUN_00896cc8(local_44,2);
      }
      else {
        FUN_00896cf0(local_234 + 0x3d54,&DAT_00936004);
        FUN_00896cf0(local_234 + 0x3d50,&DAT_00935fe4);
        local_220 = 0x90;
        FUN_0040234c(local_40);
        local_214 = local_214 + 1;
        FUN_0052839c();
        FUN_00896cf0(local_234 + 0x3d58,local_40);
        local_214 = local_214 + -1;
        FUN_00896cc8(local_40,2);
      }
    }
    else {
      FUN_00896cf0(local_234 + 0x3d54,&DAT_00936000);
      FUN_00896cf0(local_234 + 0x3d50,&DAT_00935fe0);
      local_220 = 0x78;
      uVar3 = FUN_0040234c(local_38);
      local_214 = local_214 + 1;
      FUN_008968ec(local_234 + 0x31f8,uVar3);
      FUN_00896cf0(local_234 + 0x3d58,local_38);
      local_214 = local_214 + -1;
      FUN_00896cc8(local_38,2);
    }
  }
  else {
    FUN_00896cf0(local_234 + 0x3d54,&DAT_00936008);
    FUN_00896cf0(local_234 + 0x3d50,&DAT_00935fe0);
    local_220 = 0x60;
    uVar3 = FUN_0040234c(local_30);
    local_214 = local_214 + 1;
    FUN_008968ec(local_234 + 0x31f8,uVar3);
    FUN_00896cf0(local_234 + 0x3d58,local_30);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_30,2);
  }
  local_220 = 0xa8;
  uVar3 = FUN_0040234c(local_48);
  local_214 = local_214 + 1;
  FUN_008970d8(&DAT_008e08f6,local_234 + 0x3214,uVar3);
  uVar17 = SUB42(local_48,0);
  uStack_35e = (undefined2)((uint)local_48 >> 0x10);
  uVar2 = FUN_0040234c(local_50);
  local_214 = local_214 + 1;
  FUN_00896b08(local_4c,s__p300_Have_a_good_journey_008e08fb);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_4c,uVar2);
  FUN_00896cf0(local_234 + 0x3d08,local_50);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_50,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_4c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_48,2);
  FUN_00422c0b();
  uVar2 = 1;
  local_220 = 0xb4;
  uVar3 = FUN_0040234c(local_54);
  local_214 = local_214 + 1;
  FUN_008970d8(&DAT_008e0915,local_234 + 0x3d08,uVar3,uVar2);
  FUN_00430398(local_54);
  FUN_00497420();
  local_214 = local_214 + 1;
  FUN_00497630();
  FUN_0041fa89();
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_214 = local_214 + -1;
  FUN_00896cc8(local_54,2);
  FUN_0041ebdf();
  local_220 = 0xc0;
  FUN_00430398(local_234 + 0x3d50);
  FUN_00497420();
  uVar2 = SUB42(local_a4,0);
  uStack_35e = (undefined2)((uint)local_a4 >> 0x10);
  local_214 = local_214 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_a8,uVar3,CONCAT22(uStack_35e,uVar2));
  local_214 = local_214 + 2;
  FUN_00456030(local_234 + 0x3db0,local_a8);
  local_214 = local_214 + -2;
  FUN_00406118(local_a8,2);
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_220 = 0xcc;
  FUN_00430398(local_234 + 0x3d54);
  FUN_00497420();
  uVar2 = SUB42(local_d0,0);
  uStack_35e = (undefined2)((uint)local_d0 >> 0x10);
  local_214 = local_214 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_d4,uVar3,CONCAT22(uStack_35e,uVar2));
  local_214 = local_214 + 2;
  FUN_00456030(local_234 + 0x3db4,local_d4);
  local_214 = local_214 + -2;
  FUN_00406118(local_d4,2);
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_220 = 0xd8;
  FUN_00430398(local_234 + 0x3d58);
  FUN_00497420();
  uVar2 = SUB42(local_fc,0);
  uStack_35e = (undefined2)((uint)local_fc >> 0x10);
  local_214 = local_214 + 1;
  uVar3 = FUN_00497630();
  FUN_00455e88(local_100,uVar3,CONCAT22(uStack_35e,uVar2));
  local_214 = local_214 + 2;
  FUN_00456030(local_234 + 0x3db8,local_100);
  local_214 = local_214 + -2;
  FUN_00406118(local_100,2);
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_220 = 0xe4;
  FUN_00430398(local_234 + 0x3210);
  FUN_00497420();
  local_214 = local_214 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_220 = 0xf0;
  FUN_00430398(local_234 + 0x3214);
  FUN_00497420();
  local_214 = local_214 + 1;
  FUN_00497630();
  FUN_004206a5();
  local_214 = local_214 + -1;
  FUN_004974ec();
  local_220 = 0xfc;
  uVar3 = FUN_00455e50(local_154);
  local_214 = local_214 + 2;
  FUN_00455ec8(local_234 + 0x3db0,local_234 + 0x3db4,uVar3);
  FUN_0045df2c(local_154);
  FUN_004206a5();
  local_214 = local_214 + -2;
  FUN_00406118(local_154,2);
  FUN_0045df2c(local_234 + 0x3db8);
  FUN_004206a5();
  FUN_005c5a98(*(undefined4 *)(local_234 + 0x52c),1);
  local_220 = 0x108;
  FUN_00896b08(local_158,&DAT_008e091a);
  local_214 = local_214 + 1;
  cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_158);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_158,2);
  if (cVar1 != '\0') {
    local_220 = 0x114;
    uVar3 = FUN_0040234c(local_15c);
    local_214 = local_214 + 1;
    FUN_008970d8(&DAT_008e091f,local_234 + 0x3214,uVar3);
    uVar17 = SUB42(local_15c,0);
    uStack_35e = (undefined2)((uint)local_15c >> 0x10);
    uVar2 = FUN_0040234c(local_164);
    local_214 = local_214 + 1;
    FUN_00896b08(local_160,s_Balance__008e0924);
    local_214 = local_214 + 1;
    FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_160,uVar2);
    uVar17 = SUB42(local_164,0);
    uStack_35e = (undefined2)((uint)local_164 >> 0x10);
    lVar6 = (longdouble)*(double *)(local_234 + 0x3200) -
            (longdouble)*(double *)(local_234 + 0x3290);
    FUN_0040234c(local_168,local_164,local_234,SUB104(lVar6,0),(int)((unkuint10)lVar6 >> 0x20),
                 (short)((unkuint10)lVar6 >> 0x40));
    local_214 = local_214 + 1;
    FUN_0052839c();
    uVar2 = SUB42(local_168,0);
    uStack_362 = (undefined2)((uint)local_168 >> 0x10);
    uVar3 = FUN_0040234c(&local_16c);
    local_214 = local_214 + 1;
    FUN_00896d18(CONCAT22(uStack_35e,uVar17),CONCAT22(uStack_362,uVar2),uVar3);
    FUN_005e2c68(*(undefined4 *)(local_234 + 0x4b4),local_16c);
    local_214 = local_214 + -1;
    FUN_00896cc8(&local_16c,2);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_168,2);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_164,2);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_160,2);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_15c,2);
  }
  FUN_00896cf0(local_234 + 0x3cf8,&DAT_00936018);
  FUN_00896cf0(local_234 + 0x32a4,local_234 + 0x3cd4);
  cVar1 = FUN_004aeaf4(local_234,0);
  if (cVar1 != '\0') {
    local_220 = 0x120;
    uVar2 = FUN_0040234c(&local_174);
    local_214 = local_214 + 1;
    FUN_00896b08(local_170,s_Write_the_OutRecord_s_table_erro_008e092e);
    local_214 = local_214 + 1;
    FUN_00896d18(local_234 + 0x2de8,local_170,uVar2);
    FUN_004a45f0(local_234,local_174);
    local_214 = local_214 + -1;
    FUN_00896cc8(&local_174,2);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_170,2);
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_234 + 0x3a7c) = uVar3;
    while ((*(int *)(local_234 + 0x3a7c) != *(int *)(local_234 + 0x3a80) &&
           (cVar1 = FUN_00896d9c(local_234 + 0x3210,
                                 *(int *)(local_234 + 0x3a7c) * 4 + local_234 + 0x32a8),
           cVar1 != '\0'))) {
      uVar3 = FUN_0043ee68();
      *(undefined4 *)(local_234 + 0x3a7c) = uVar3;
    }
    *(undefined1 *)(local_234 + 0x3a84) = 0;
    *in_FS_OFFSET = local_230;
    return local_234;
  }
  local_220 = 0x138;
  uVar2 = FUN_0040234c(local_178);
  local_214 = local_214 + 1;
  FUN_00896f9c(local_234 + 0x3248,4,8,uVar2);
  uVar2 = SUB42(local_178,0);
  uStack_35e = (undefined2)((uint)local_178 >> 0x10);
  uVar3 = FUN_0040234c(local_17c);
  local_214 = local_214 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_35e,uVar2),uVar3);
  uVar17 = SUB42(local_17c,0);
  uStack_35e = (undefined2)((uint)local_17c >> 0x10);
  uVar2 = FUN_0040234c(local_184);
  local_214 = local_214 + 1;
  FUN_00896b08(local_180,&DAT_008e0952);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_180,uVar2);
  uVar2 = SUB42(local_184,0);
  uStack_35e = (undefined2)((uint)local_184 >> 0x10);
  uVar3 = FUN_0040234c(local_188);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar2),local_234 + 0x3248,uVar3);
  uVar17 = SUB42(local_188,0);
  uStack_35e = (undefined2)((uint)local_188 >> 0x10);
  uVar2 = FUN_0040234c(local_190);
  local_214 = local_214 + 1;
  FUN_00896b08(local_18c,&DAT_008e0954);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_18c,uVar2);
  uVar3 = FUN_0040234c(&local_194);
  local_214 = local_214 + 1;
  FUN_00525f2c(local_190[0],uVar3);
  FUN_005261f4(local_194);
  local_214 = local_214 + -1;
  FUN_00896cc8(&local_194,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_190,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_18c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_188,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_184,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_180,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_17c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_178,2);
  local_220 = 0x144;
  uVar2 = FUN_0040234c(local_198);
  local_214 = local_214 + 1;
  FUN_00896f9c(local_234 + 0x3248,4,8,uVar2);
  uVar2 = SUB42(local_198,0);
  uStack_35e = (undefined2)((uint)local_198 >> 0x10);
  uVar3 = FUN_0040234c(local_19c);
  local_214 = local_214 + 1;
  FUN_00896d18(&DAT_00935e24,CONCAT22(uStack_35e,uVar2),uVar3);
  uVar17 = SUB42(local_19c,0);
  uStack_35e = (undefined2)((uint)local_19c >> 0x10);
  uVar2 = FUN_0040234c(local_1a4);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1a0,&DAT_008e0960);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_1a0,uVar2);
  uVar2 = SUB42(local_1a4,0);
  uStack_35e = (undefined2)((uint)local_1a4 >> 0x10);
  uVar3 = FUN_0040234c(local_1a8);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar2),local_234 + 0x3248,uVar3);
  uVar17 = SUB42(local_1a8,0);
  uStack_35e = (undefined2)((uint)local_1a8 >> 0x10);
  uVar2 = FUN_0040234c(local_1b0);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1ac,&DAT_008e0962);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_1ac,uVar2);
  uVar2 = FUN_0040234c(local_1b4);
  local_214 = local_214 + 1;
  FUN_00896f9c(local_234 + 0x3248,4,8,uVar2);
  uVar2 = SUB42(local_1b4,0);
  uStack_362 = (undefined2)((uint)local_1b4 >> 0x10);
  uVar3 = FUN_0040234c(local_1b8);
  local_214 = local_214 + 1;
  FUN_00896d18(&DAT_00935e20,CONCAT22(uStack_362,uVar2),uVar3);
  uVar2 = SUB42(local_1b8,0);
  uStack_362 = (undefined2)((uint)local_1b8 >> 0x10);
  uVar3 = FUN_0040234c(local_1c0);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1bc,&DAT_008e0959);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),local_1bc,uVar3);
  uVar2 = SUB42(local_1c0,0);
  uStack_362 = (undefined2)((uint)local_1c0 >> 0x10);
  uVar3 = FUN_0040234c(local_1c4);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),local_234 + 0x3248,uVar3);
  uVar2 = SUB42(local_1c4,0);
  uStack_362 = (undefined2)((uint)local_1c4 >> 0x10);
  uVar3 = FUN_0040234c(local_1cc);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1c8,&DAT_008e095b);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_362,uVar2),local_1c8,uVar3);
  FUN_0043ede8();
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1cc,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1c8,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1c4,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1c0,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1bc,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1b8,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1b4,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1b0,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1ac,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1a8,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1a4,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1a0,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_19c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_198,2);
  local_220 = 0;
  cVar1 = FUN_0040f0d0(&DAT_00935fbc);
  if (cVar1 != '\0') goto LAB_004e1b66;
  local_220 = 0x15c;
  FUN_00896b08(local_1d0,&DAT_008e0967);
  local_214 = local_214 + 1;
  cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_1d0);
  if (cVar1 == '\0') {
    FUN_00896b08(local_1d4,s_Season_008e096b);
    local_214 = local_214 + 1;
    cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_1d4);
    uVar18 = (ushort)(cVar1 != '\0');
    local_214 = local_214 + -1;
    FUN_00896cc8(local_1d4,2);
    if (uVar18 != 0) goto LAB_004e178c;
    cVar1 = '\0';
  }
  else {
LAB_004e178c:
    cVar1 = '\x01';
  }
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1d0,2);
  if (cVar1 == '\0') {
    local_220 = 0x174;
    FUN_00896b08(local_1dc,&DAT_008e0972);
    local_214 = local_214 + 1;
    cVar1 = FUN_00896d9c(local_234 + 0x31f4,local_1dc);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_1dc,2);
    if (cVar1 == '\0') {
      local_220 = 0x18c;
      FUN_00896b08(local_1e4,s_Temporary_008e0977);
      local_214 = local_214 + 1;
      FUN_00896cf0(local_234 + 0x3d50,local_1e4);
      local_214 = local_214 + -1;
      FUN_00896cc8(local_1e4,2);
      FUN_00896cf0(local_234 + 0x3d58,&DAT_00935ff8);
    }
    else {
      FUN_00896cf0(local_234 + 0x3d50,&DAT_00936004);
      local_220 = 0x180;
      FUN_0040234c(local_1e0);
      local_214 = local_214 + 1;
      FUN_0052839c();
      FUN_00896cf0(local_234 + 0x3d58,local_1e0);
      local_214 = local_214 + -1;
      FUN_00896cc8(local_1e0,2);
    }
  }
  else {
    FUN_00896cf0(local_234 + 0x3d50,&DAT_00935fe0);
    local_220 = 0x168;
    uVar3 = FUN_0040234c(local_1d8);
    local_214 = local_214 + 1;
    FUN_008968ec(local_234 + 0x31f8,uVar3);
    FUN_00896cf0(local_234 + 0x3d58,local_1d8);
    local_214 = local_214 + -1;
    FUN_00896cc8(local_1d8,2);
  }
  FUN_00896cf0(local_234 + 0x3d54,local_234 + 0x31f4);
  local_220 = 0x198;
  FUN_00896b08(local_1e8,s_have_a_good_Journey_008e0981);
  local_214 = local_214 + 1;
  FUN_00896cf0(local_234 + 0x3d08,local_1e8);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1e8,2);
  uVar17 = 0;
  uVar2 = 1;
  uVar16 = 1;
  uVar3 = *(undefined4 *)(local_234 + 0x3bc8);
  uVar15 = 1;
  uVar14 = 0;
  uVar13 = 3;
  uVar12 = 1;
  uVar11 = *(undefined4 *)(local_234 + 0x3bc4);
  uVar10 = 1;
  uVar9 = 0x10;
  uVar8 = 0x40;
  uVar7 = 1;
  uVar4 = FUN_00897218(&DAT_00935fbc);
  local_220 = 0x1a4;
  uVar5 = FUN_0040234c(local_1f0);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1ec,&DAT_008e0995);
  local_214 = local_214 + 1;
  FUN_00896d18(local_234 + 0x3d50,local_1ec,uVar5,uVar4,uVar7,uVar8,uVar9,uVar10,uVar11,uVar12,
               uVar13,uVar14,uVar15,uVar3,uVar16,uVar2,uVar17);
  uVar3 = FUN_0040234c(local_1f4);
  local_214 = local_214 + 1;
  FUN_00896d18(local_1f0,local_234 + 0x3d54,uVar3);
  uVar3 = FUN_0040234c(local_1fc);
  local_214 = local_214 + 1;
  FUN_00896b08(local_1f8,&DAT_008e0997);
  local_214 = local_214 + 1;
  FUN_00896d18(local_1f4,local_1f8,uVar3);
  uVar3 = FUN_0040234c(local_200);
  local_214 = local_214 + 1;
  FUN_00896d18(local_1fc,local_234 + 0x3d58,uVar3);
  FUN_00897218(local_200);
  (*DAT_00935d4c)();
  local_214 = local_214 + -1;
  FUN_00896cc8(local_200,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1fc,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1f8,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1f4,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1f0,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_1ec,2);
LAB_004e1b66:
  local_220 = 0x1b0;
  uVar3 = FUN_0040234c(local_204);
  local_214 = local_214 + 1;
  FUN_008970d8(s_delete_from_CardIssue_where_Rema_008e0999,local_234 + 0x3210,uVar3);
  uVar17 = SUB42(local_204,0);
  uStack_35e = (undefined2)((uint)local_204 >> 0x10);
  uVar2 = FUN_0040234c(local_20c);
  local_214 = local_214 + 1;
  FUN_00896b08(local_208,&DAT_008e09da);
  local_214 = local_214 + 1;
  FUN_00896d18(CONCAT22(uStack_35e,uVar17),local_208,uVar2);
  FUN_004877f8();
  local_214 = local_214 + -1;
  FUN_00896cc8(local_20c,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_208,2);
  local_214 = local_214 + -1;
  FUN_00896cc8(local_204,2);
  FUN_004a4e48(local_234);
  uVar3 = FUN_0043ee68();
  *(undefined4 *)(local_234 + 0x3a7c) = uVar3;
  while ((*(int *)(local_234 + 0x3a7c) != *(int *)(local_234 + 0x3a80) &&
         (cVar1 = FUN_00896d9c(local_234 + 0x3210,
                               *(int *)(local_234 + 0x3a7c) * 4 + local_234 + 0x32a8), cVar1 != '\0'
         ))) {
    uVar3 = FUN_0043ee68();
    *(undefined4 *)(local_234 + 0x3a7c) = uVar3;
  }
  *(undefined1 *)(local_234 + 0x3a84) = 0;
  *in_FS_OFFSET = local_230;
  return local_234;
}



/* FUNCTION FUN_00497640 ENTRY 00497640 */

void FUN_00497640(int param_1,char param_2,undefined4 param_3)

{
  int *piVar1;
  int iVar2;
  undefined4 uVar3;
  undefined4 extraout_ECX;
  char extraout_DL;
  undefined4 *in_FS_OFFSET;
  undefined4 local_38;
  undefined4 local_14;
  undefined1 local_10 [4];
  undefined1 local_c [4];
  int local_8;
  
  if ('\0' < param_2) {
    param_1 = FUN_00897250();
    param_3 = extraout_ECX;
    param_2 = extraout_DL;
  }
  local_8 = param_1;
  FUN_0088747c(&DAT_008e1558);
  FUN_004022f4(local_8,0,param_3);
  FUN_0040234c(local_8 + 2000);
  FUN_0043e7d8(local_8 + 0x7e0);
  FUN_0043e7d8(local_8 + 0x7e8);
  iVar2 = local_8;
  FUN_0040234c(local_8 + 0x7f0);
  FUN_0040234c(iVar2 + 0xbf8);
  FUN_0040234c(iVar2 + 0xbfc);
  FUN_0043e7d8(iVar2 + 0xc00);
  FUN_0040234c(iVar2 + 0xc14);
  FUN_0040234c(iVar2 + 0xc18);
  FUN_0040234c(iVar2 + 0xc1c);
  FUN_0040234c(iVar2 + 0xc20);
  FUN_0040234c(iVar2 + 0xc24);
  FUN_0040234c(iVar2 + 0xc28);
  FUN_0040234c(iVar2 + 0xc2c);
  FUN_0040234c(iVar2 + 0xc30);
  FUN_0040234c(iVar2 + 0xc34);
  FUN_0040234c(iVar2 + 0xc38);
  FUN_0040234c(iVar2 + 0xc3c);
  FUN_0040234c(iVar2 + 0xc40);
  FUN_0043e7d8(iVar2 + 0xc48);
  FUN_0040234c(iVar2 + 0xc50);
  FUN_0040234c(iVar2 + 0xc54);
  FUN_0043e7d8(iVar2 + 0xc58);
  FUN_0043e7d8(iVar2 + 0xc70);
  FUN_0040234c(iVar2 + 0xc78);
  FUN_0043e7d8(iVar2 + 0xc80);
  FUN_0040234c(iVar2 + 0xca8);
  FUN_0040234c(iVar2 + 0xcac);
  FUN_00885e3c();
  FUN_0040234c(iVar2 + 0x1490);
  iVar2 = local_8;
  FUN_0040234c(local_8 + 0x1498);
  FUN_0040234c(iVar2 + 0x18a0);
  FUN_0040234c(iVar2 + 0x18a4);
  FUN_0043e7d8(iVar2 + 0x18a8);
  FUN_0040234c(iVar2 + 0x18bc);
  FUN_0040234c(iVar2 + 0x18c0);
  FUN_0040234c(iVar2 + 0x18c4);
  FUN_0040234c(iVar2 + 0x18c8);
  FUN_0040234c(iVar2 + 0x18cc);
  FUN_0040234c(iVar2 + 0x18d0);
  FUN_0040234c(iVar2 + 0x18d4);
  FUN_0040234c(iVar2 + 0x18d8);
  FUN_0040234c(iVar2 + 0x18dc);
  FUN_0040234c(iVar2 + 0x18e0);
  FUN_0040234c(iVar2 + 0x18e4);
  FUN_0040234c(iVar2 + 0x18e8);
  FUN_0043e7d8(iVar2 + 0x18f0);
  FUN_0040234c(iVar2 + 0x18f8);
  FUN_0040234c(iVar2 + 0x18fc);
  FUN_0043e7d8(iVar2 + 0x1900);
  FUN_0043e7d8(iVar2 + 0x1918);
  FUN_0040234c(iVar2 + 0x1920);
  FUN_0043e7d8(iVar2 + 0x1928);
  FUN_0040234c(iVar2 + 0x1950);
  FUN_0040234c(iVar2 + 0x1954);
  FUN_00885e3c();
  FUN_0040234c(iVar2 + 0x2138);
  iVar2 = local_8;
  FUN_0040234c(local_8 + 0x2140);
  FUN_0040234c(iVar2 + 0x2548);
  FUN_0040234c(iVar2 + 0x254c);
  FUN_0043e7d8(iVar2 + 0x2550);
  FUN_0040234c(iVar2 + 0x2564);
  FUN_0040234c(iVar2 + 0x2568);
  FUN_0040234c(iVar2 + 0x256c);
  FUN_0040234c(iVar2 + 0x2570);
  FUN_0040234c(iVar2 + 0x2574);
  FUN_0040234c(iVar2 + 0x2578);
  FUN_0040234c(iVar2 + 0x257c);
  FUN_0040234c(iVar2 + 0x2580);
  FUN_0040234c(iVar2 + 0x2584);
  FUN_0040234c(iVar2 + 0x2588);
  FUN_0040234c(iVar2 + 0x258c);
  FUN_0040234c(iVar2 + 0x2590);
  FUN_0043e7d8(iVar2 + 0x2598);
  FUN_0040234c(iVar2 + 0x25a0);
  FUN_0040234c(iVar2 + 0x25a4);
  FUN_0043e7d8(iVar2 + 0x25a8);
  FUN_0043e7d8(iVar2 + 0x25c0);
  FUN_0040234c(iVar2 + 0x25c8);
  FUN_0043e7d8(iVar2 + 0x25d0);
  FUN_0040234c(iVar2 + 0x25f8);
  FUN_0040234c(iVar2 + 0x25fc);
  FUN_00885e3c();
  FUN_0040234c(iVar2 + 0x2de0);
  iVar2 = local_8;
  FUN_0040234c(local_8 + 0x2de8);
  FUN_0040234c(iVar2 + 0x31f0);
  FUN_0040234c(iVar2 + 0x31f4);
  FUN_0043e7d8(iVar2 + 0x31f8);
  FUN_0040234c(iVar2 + 0x320c);
  FUN_0040234c(iVar2 + 0x3210);
  FUN_0040234c(iVar2 + 0x3214);
  FUN_0040234c(iVar2 + 0x3218);
  FUN_0040234c(iVar2 + 0x321c);
  FUN_0040234c(iVar2 + 0x3220);
  FUN_0040234c(iVar2 + 0x3224);
  FUN_0040234c(iVar2 + 0x3228);
  FUN_0040234c(iVar2 + 0x322c);
  FUN_0040234c(iVar2 + 0x3230);
  FUN_0040234c(iVar2 + 0x3234);
  FUN_0040234c(iVar2 + 0x3238);
  FUN_0043e7d8(iVar2 + 0x3240);
  FUN_0040234c(iVar2 + 0x3248);
  FUN_0040234c(iVar2 + 0x324c);
  FUN_0043e7d8(iVar2 + 0x3250);
  FUN_0043e7d8(iVar2 + 0x3268);
  FUN_0040234c(iVar2 + 0x3270);
  FUN_0043e7d8(iVar2 + 0x3278);
  FUN_0040234c(iVar2 + 0x32a0);
  FUN_0040234c(iVar2 + 0x32a4);
  FUN_00885e3c();
  FUN_0040234c(iVar2 + 0x3a88);
  FUN_00405f1c(local_8 + 0x3c04);
  FUN_00405f1c(local_8 + 0x3c08);
  FUN_00405f1c(local_8 + 0x3c0c);
  FUN_00405f1c(local_8 + 0x3c10);
  FUN_00405f1c(local_8 + 0x3c14);
  FUN_0040234c(local_8 + 0x3c18);
  FUN_0040234c(local_8 + 0x3c1c);
  FUN_0040234c(local_8 + 0x3c20);
  FUN_0040234c(local_8 + 0x3c24);
  FUN_0040234c(local_8 + 0x3c28);
  FUN_0040234c(local_8 + 0x3c2c);
  FUN_0040234c(local_8 + 0x3c30);
  FUN_00455e50(local_8 + 0x3c34);
  FUN_00455e50(local_8 + 0x3c38);
  FUN_00455e50(local_8 + 0x3c3c);
  FUN_00455e50(local_8 + 0x3c40);
  FUN_00455e50(local_8 + 0x3c44);
  FUN_00455e50(local_8 + 0x3c48);
  FUN_00455e50(local_8 + 0x3c4c);
  FUN_00455e50(local_8 + 0x3c50);
  FUN_00455e50(local_8 + 0x3c54);
  FUN_00455e50(local_8 + 0x3c58);
  FUN_00455e50(local_8 + 0x3c5c);
  FUN_00455e50(local_8 + 0x3c60);
  FUN_00455e50(local_8 + 0x3c64);
  FUN_00455e50(local_8 + 0x3c68);
  FUN_0043e7d8(local_8 + 0x3c80);
  FUN_0040234c(local_8 + 0x3c88);
  FUN_0040234c(local_8 + 0x3c8c);
  FUN_0040234c(local_8 + 0x3c90);
  FUN_0040234c(local_8 + 0x3c94);
  FUN_0040234c(local_8 + 0x3c98);
  FUN_0040234c(local_8 + 0x3c9c);
  FUN_0040234c(local_8 + 0x3ca0);
  FUN_0040234c(local_8 + 0x3ca4);
  FUN_0040234c(local_8 + 0x3ca8);
  FUN_0040234c(local_8 + 0x3cac);
  FUN_0040234c(local_8 + 0x3cb0);
  FUN_0040234c(local_8 + 0x3cb4);
  FUN_0040234c(local_8 + 0x3cb8);
  FUN_0040234c(local_8 + 0x3cbc);
  FUN_0040234c(local_8 + 0x3cc0);
  FUN_0040234c(local_8 + 0x3cc4);
  FUN_0040234c(local_8 + 0x3cc8);
  FUN_0040234c(local_8 + 0x3ccc);
  FUN_0040234c(local_8 + 0x3cd0);
  FUN_0040234c(local_8 + 0x3cd4);
  FUN_0040234c(local_8 + 0x3cd8);
  FUN_0040234c(local_8 + 0x3cdc);
  FUN_0040234c(local_8 + 0x3ce0);
  FUN_0040234c(local_8 + 0x3ce4);
  FUN_0040234c(local_8 + 0x3ce8);
  FUN_0040234c(local_8 + 0x3cec);
  FUN_0040234c(local_8 + 0x3cf0);
  FUN_0040234c(local_8 + 0x3cf4);
  FUN_0040234c(local_8 + 0x3cf8);
  FUN_0040234c(local_8 + 0x3cfc);
  FUN_0040234c(local_8 + 0x3d00);
  FUN_0040234c(local_8 + 0x3d04);
  FUN_0040234c(local_8 + 0x3d08);
  FUN_0040234c(local_8 + 0x3d44);
  FUN_0040234c(local_8 + 0x3d48);
  FUN_0040234c(local_8 + 0x3d4c);
  FUN_0040234c(local_8 + 0x3d50);
  FUN_0040234c(local_8 + 0x3d54);
  FUN_0040234c(local_8 + 0x3d58);
  FUN_0040234c(local_8 + 0x3d5c);
  FUN_0040234c(local_8 + 0x3d60);
  FUN_0040234c(local_8 + 0x3d64);
  FUN_0040234c(local_8 + 0x3d68);
  FUN_0040234c(local_8 + 0x3d6c);
  FUN_0040234c(local_8 + 0x3d70);
  FUN_0040234c(local_8 + 0x3d74);
  FUN_0040234c(local_8 + 0x3d78);
  FUN_0040234c(local_8 + 0x3d7c);
  FUN_0040234c(local_8 + 0x3d80);
  FUN_0040234c(local_8 + 0x3d84);
  FUN_0040234c(local_8 + 0x3d88);
  FUN_0040234c(local_8 + 0x3d8c);
  FUN_0040234c(local_8 + 0x3d90);
  FUN_0040234c(local_8 + 0x3d94);
  FUN_0040234c(local_8 + 0x3d98);
  FUN_0040234c(local_8 + 0x3d9c);
  FUN_0040234c(local_8 + 0x3da0);
  FUN_0040234c(local_8 + 0x3da4);
  FUN_0040234c(local_8 + 0x3da8);
  FUN_00455e50(local_8 + 0x3dac);
  FUN_00455e50(local_8 + 0x3db0);
  FUN_00455e50(local_8 + 0x3db4);
  FUN_00455e50(local_8 + 0x3db8);
  FUN_00455e50(local_8 + 0x3dbc);
  FUN_00455e50(local_8 + 0x3dc0);
  FUN_00455e50(local_8 + 0x3dc4);
  FUN_00455e50(local_8 + 0x3dc8);
  FUN_00455e50(local_8 + 0x3dcc);
  FUN_00455e50(local_8 + 0x3dd0);
  FUN_00455e50(local_8 + 0x3dd4);
  FUN_00455e50(local_8 + 0x3dd8);
  FUN_00455e50(local_8 + 0x3ddc);
  FUN_00455e50(local_8 + 0x3de0);
  FUN_00455e50(local_8 + 0x3de4);
  FUN_00455e50(local_8 + 0x3de8);
  FUN_00455e50(local_8 + 0x3dec);
  FUN_00455e50(local_8 + 0x3df0);
  FUN_00455e50(local_8 + 0x3df4);
  FUN_005e2de8(local_8,*(undefined4 *)(*(int *)PTR__FormMain_00934540 + 0x6c));
  piVar1 = *(int **)(local_8 + 0x2ac);
  uVar3 = FUN_0040234c(&local_14);
  FUN_00896b08(local_10,s__CARS_ICO_008dc928);
  FUN_0040234c(local_c);
  FUN_005261e8();
  FUN_00896d18(local_c,local_10,uVar3);
  (**(code **)(*piVar1 + 0x54))(piVar1,local_14);
  FUN_00896cc8(&local_14,2);
  FUN_00896cc8(local_10,2);
  FUN_00896cc8(local_c,2);
  FUN_00422c0b();
  FUN_00422c0b();
  FUN_00422c0b();
  FUN_00422c0b();
  _FormInOut = local_8;
  InitializeCriticalSection((LPCRITICAL_SECTION)(local_8 + 0x3d0c));
  *(undefined4 *)(local_8 + 0x3d24) = 0;
  *(undefined4 *)(local_8 + 0x3d28) = 0;
  *(undefined4 *)(local_8 + 0x3d2c) = 0;
  *(undefined4 *)(local_8 + 0x3d30) = 0;
  *(undefined4 *)(local_8 + 0x3d34) = 0;
  *(undefined4 *)(local_8 + 0x3d38) = 0;
  *(undefined4 *)(local_8 + 0x3d3c) = 0;
  *(undefined4 *)(local_8 + 0x3d40) = 0;
  DV_InitSDK();
  FUN_00422ee0();
  *in_FS_OFFSET = local_38;
  if (param_2 != '\0') {
    FUN_0089725d(local_8);
  }
  return;
}



/* FUNCTION FUN_004987c0 ENTRY 004987c0 */
/* SKIPPED: function body is too large for this pass */

/* FUNCTION FUN_004986e4 ENTRY 004986e4 */

void FUN_004986e4(int param_1)

{
  DV_ReleaseSDK();
  FUN_00422efc();
  *(undefined4 *)(*(int *)PTR__FormMain_00934540 + 0x448) = 0;
  DeleteCriticalSection((LPCRITICAL_SECTION)(param_1 + 0x3d0c));
  FUN_0043e630();
  FUN_0043e5d8();
  if (DAT_00935e87 != '\0') {
    ExitWindowsEx(1,0);
  }
  return;
}



/* FUNCTION FUN_004985f4 ENTRY 004985f4 */

undefined4 __stdcall FUN_004985f4(int param_1,int param_2)

{
  Sleep(0x46);
  if (param_1 == 0) {
    return 0xffffffff;
  }
  if (param_2 == 0) {
    return 0xffffffff;
  }
  DV_WriteRS485();
  Sleep(0x32);
  return 0;
}



/* FUNCTION FUN_004249f4 ENTRY 004249f4 */

int __stdcall FUN_004249f4(void)

{
  HMODULE hModule;
  int iVar1;
  FARPROC local_8;
  
  local_8 = (FARPROC)0x0;
  hModule = LoadLibraryA(s_SimpleLPRDevAgent_dll_008aac60);
  if (hModule == (HMODULE)0x0) {
    iVar1 = 0x1e;
  }
  else {
    if (hModule != (HMODULE)0x0) {
      local_8 = GetProcAddress(hModule,s_LPR_LoadApis_008aac76);
    }
    if (local_8 == (FARPROC)0x0) {
      iVar1 = 0x20;
    }
    else {
      iVar1 = (*local_8)();
    }
  }
  return iVar1;
}



/* FUNCTION FUN_0088747c ENTRY 0088747c */

void FUN_0088747c(int param_1)

{
  undefined4 *puVar1;
  undefined4 *puVar2;
  int unaff_EBP;
  undefined2 in_FS;
  
  puVar2 = (undefined4 *)(unaff_EBP + *(int *)(param_1 + 8));
  puVar2[2] = param_1;
  puVar2[3] = &stack0x00000004;
  puVar2[1] = &LAB_008874c3;
  *(undefined2 *)(puVar2 + 4) = 0;
  *(undefined2 *)((int)puVar2 + 0x12) = 0;
  puVar2[7] = 0;
  puVar1 = (undefined4 *)segment(in_FS,0);
  *puVar2 = *puVar1;
  puVar1 = (undefined4 *)segment(in_FS,0);
  *puVar1 = puVar2;
  return;
}



/* FUNCTION FUN_005c5a98 ENTRY 005c5a98 */

void FUN_005c5a98(int param_1,char param_2)

{
  if (param_2 != *(char *)(param_1 + 0x48)) {
    *(char *)(param_1 + 0x48) = param_2;
    FUN_005c59e0();
  }
  return;
}



/* FUNCTION FUN_007bf4e0 ENTRY 007bf4e0 */

void FUN_007bf4e0(int *param_1,char param_2)

{
  char cVar1;
  
  cVar1 = (**(code **)(*param_1 + 0x48))();
  if (param_2 != cVar1) {
    cVar1 = FUN_007ecc58(param_1);
    if ((cVar1 == '\0') && (cVar1 = FUN_007ecc50(param_1), cVar1 == '\0')) {
      if (param_2 != '\0') {
        (**(code **)(*param_1 + 0x4c))();
        return;
      }
      (**(code **)(*param_1 + 0x44))();
      return;
    }
    *(char *)(param_1 + 0x26) = param_2;
  }
  return;
}



/* FUNCTION FUN_0040f0d0 ENTRY 0040f0d0 */

bool FUN_0040f0d0(int *param_1)

{
  return *param_1 == 0;
}



/* FUNCTION FUN_00886f3f ENTRY 00886f3f */

undefined4 __stdcall FUN_00886f3f(undefined4 param_1,undefined1 param_2,undefined4 param_3)

{
  FUN_00886ea4(param_1,param_3,param_2);
  return param_1;
}



/* FUNCTION FUN_004060d8 ENTRY 004060d8 */

undefined4 FUN_004060d8(undefined4 param_1,undefined4 param_2)

{
  undefined4 *in_FS_OFFSET;
  undefined4 local_2c;
  
  FUN_0088747c(&DAT_0089a960);
  FUN_00894ab0(param_1,param_2,0);
  *in_FS_OFFSET = local_2c;
  return param_1;
}



/* FUNCTION FUN_00896b08 ENTRY 00896b08 */

undefined4 * FUN_00896b08(undefined4 *param_1,undefined4 param_2)

{
  undefined4 *in_FS_OFFSET;
  undefined4 local_2c;
  
  FUN_0088747c(&DAT_00934130);
  *param_1 = 0;
  FUN_004f1e80(param_1,param_2);
  *in_FS_OFFSET = local_2c;
  return param_1;
}



/* FUNCTION FUN_0040234c ENTRY 0040234c */

undefined4 * FUN_0040234c(undefined4 *param_1)

{
  undefined4 *in_FS_OFFSET;
  undefined4 local_2c;
  
  FUN_0088747c(&DAT_0089a910);
  *param_1 = 0;
  *in_FS_OFFSET = local_2c;
  return param_1;
}



/* FUNCTION FUN_005e2c30 ENTRY 005e2c30 */

void FUN_005e2c30(undefined4 param_1,undefined4 *param_2)

{
  int iVar1;
  undefined4 uVar2;
  
  iVar1 = FUN_005e2ba0(param_1);
  FUN_00545448(param_2,0,iVar1);
  if (iVar1 != 0) {
    uVar2 = FUN_00545398(*param_2);
    FUN_005e2bb0(param_1,uVar2,iVar1 + 1);
  }
  return;
}



/* FUNCTION FUN_00896f10 ENTRY 00896f10 */

undefined4 FUN_00896f10(undefined4 param_1,undefined4 param_2)

{
  undefined4 uVar1;
  undefined4 *puVar2;
  undefined4 *in_FS_OFFSET;
  undefined4 local_34;
  undefined1 local_c [4];
  undefined1 local_8 [4];
  
  FUN_0088747c(&DAT_009342f8);
  uVar1 = FUN_0040234c(local_c);
  puVar2 = (undefined4 *)FUN_00896b48(local_8,param_1);
  FUN_00524968(*puVar2,uVar1);
  FUN_00896cf0(param_2,local_c);
  FUN_00896cc8(local_c,2);
  FUN_00896cc8(local_8,2);
  *in_FS_OFFSET = local_34;
  return param_2;
}


