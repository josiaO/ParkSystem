
/* FUNCTION Play_Init ENTRY 10001fe0 */

undefined4 Play_Init(void)

{
  rsize_t _DstSize;
  void *_Src;
  void *_Dst;
  int iVar1;
  uint *puVar2;
  
                    /* 0x1fe0  10  Play_Init */
  iVar1 = Rtsp_Init();
  if (iVar1 != 0) {
    Log("%s Fail\n","Play_Init");
    return 0xffffffff;
  }
  Decode_Init();
  puVar2 = &DAT_1000754c;
  do {
    *(undefined1 *)(puVar2 + -0x55) = 0;
    puVar2[-0x54] = 0xffffffff;
    puVar2[-0x53] = 0xffffffff;
    puVar2[-0x52] = 0;
    puVar2[-0x51] = 0;
    puVar2[-0x4d] = 0xffffffff;
    puVar2[-0x4b] = 0;
    puVar2[-0x4c] = 0;
    puVar2[-0x4a] = 0;
    puVar2[-0x49] = 0;
    *(undefined1 *)(puVar2 + -0x48) = 0;
    puVar2[-7] = 0;
    puVar2[-6] = 0;
    puVar2[-5] = 0;
    puVar2[-0x50] = 0;
    puVar2[-0x4f] = 0;
    puVar2[-0x4e] = 0;
    _Src = (void *)*puVar2;
    if (_Src < (void *)puVar2[-1]) {
      _invalid_parameter_noinfo();
    }
    _Dst = (void *)puVar2[-1];
    if ((void *)*puVar2 < _Dst) {
      _invalid_parameter_noinfo();
    }
    if (puVar2 == (uint *)0x8) {
      _invalid_parameter_noinfo();
    }
    if (_Dst != _Src) {
      iVar1 = (int)(*puVar2 - (int)_Src) >> 2;
      _DstSize = iVar1 * 4;
      if (0 < iVar1) {
        memmove_s(_Dst,_DstSize,_Src,_DstSize);
      }
      *puVar2 = (uint)(_DstSize + (int)_Dst);
    }
    puVar2[0x12] = 0;
    memset(puVar2 + 2,0,0x40);
    puVar2 = puVar2 + 0x68;
  } while ((int)puVar2 < 0x1000a94c);
  return 0;
}



/* FUNCTION Play_OpenCamera ENTRY 10002240 */

undefined4 Play_OpenCamera(int param_1,undefined4 param_2,undefined4 param_3)

{
  undefined1 *_ArgList;
  HANDLE hHandle;
  int iVar1;
  uintptr_t uVar2;
  int iVar3;
  undefined4 local_4;
  
                    /* 0x2240  11  Play_OpenCamera */
  local_4 = 0xffffffff;
  if (param_1 == -1) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_OpenCamera",0xffffffff);
    return 0xffffffff;
  }
  iVar3 = param_1 * 0x1a0;
  *(undefined4 *)(&DAT_1000753c + iVar3) = param_2;
  *(undefined4 *)(&DAT_10007540 + iVar3) = param_3;
  iVar1 = Decode_GetPort(&local_4);
  if (iVar1 == 0) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_OpenCamera",param_1);
    return 0xffffffff;
  }
  (&DAT_10007400)[param_1 * 0x68] = local_4;
  iVar1 = Decode_StreamOpenEx(local_4,param_3,1,0xf,0xfa000);
  if (iVar1 == 0) {
    Log("%s Decode_StreamOpenEx Fail, nCamId = %d\n","Play_OpenCamera",param_1);
    return 0xffffffff;
  }
  iVar1 = Decode_StreamPlayEx(local_4);
  if (iVar1 == 0) {
    Log("%s Decode_StreamPlayEx Fail, nCamId = %d\n","Play_OpenCamera",param_1);
    return 0xffffffff;
  }
  iVar1 = Rtsp_StartVideo(param_1,param_2,1);
  if (iVar1 != 0) {
    Log("%s Rtsp_StartVideo Fail, nCamId = %d,eCode = %d\n","Play_OpenCamera",param_1,iVar1);
    return 0xffffffff;
  }
  _ArgList = &DAT_100073f8 + iVar3;
  *_ArgList = 1;
  uVar2 = _beginthreadex((void *)0x0,0,FUN_10003240,_ArgList,0,(uint *)0x0);
  if (uVar2 == 0) {
    Log("%s _beginthreadex -> ThreadRtspRecv Fail, nCamId = %d\n","Play_OpenCamera",param_1);
    *_ArgList = 0;
    return 0xffffffff;
  }
  (&DAT_1000740c)[param_1 * 0x68] = uVar2;
  uVar2 = _beginthreadex((void *)0x0,0,(_StartAddress *)&LAB_10003490,_ArgList,0,(uint *)0x0);
  if (uVar2 == 0) {
    Log("%s _beginthreadex -> ThreadNetSig Fail, nCamId = %d\n","Play_OpenCamera",param_1);
    hHandle = (HANDLE)(&DAT_1000740c)[param_1 * 0x68];
    *_ArgList = 0;
    WaitForSingleObject(hHandle,0xffffffff);
    Sleep(100);
    return 0xffffffff;
  }
  (&DAT_10007410)[param_1 * 0x68] = uVar2;
  return 0;
}



/* FUNCTION FUN_10003510 ENTRY 10003510 */

undefined4 FUN_10003510(int param_1)

{
  undefined4 *puVar1;
  rsize_t _DstSize;
  int iVar2;
  undefined4 uVar3;
  undefined4 uVar4;
  void *_Src;
  void *_Dst;
  uint uVar5;
  uint uVar6;
  undefined4 *puVar7;
  int iVar8;
  int iVar9;
  char *pcVar10;
  uint local_48;
  undefined4 local_34;
  undefined1 local_30 [8];
  undefined1 local_28 [4];
  undefined4 *local_24;
  undefined4 *local_20;
  int local_1c;
  void *local_14;
  undefined1 *puStack_10;
  undefined4 local_c;
  
  puStack_10 = &LAB_10004928;
  local_14 = ExceptionList;
  ExceptionList = &local_14;
  iVar2 = *(int *)(param_1 + 4);
  iVar9 = iVar2 * 0x1a0;
  uVar3 = *(undefined4 *)(&DAT_1000753c + iVar9);
  uVar4 = *(undefined4 *)(&DAT_10007540 + iVar9);
  local_34 = (&DAT_10007428)[iVar2 * 0x68];
  local_24 = (undefined4 *)0x0;
  local_20 = (undefined4 *)0x0;
  local_1c = 0;
  local_c = 0;
  Log("%s, nCamId = %d\n","ThreadReOpenCamera",iVar2,DAT_10007018 ^ (uint)&stack0xffffffa8);
  local_48 = 0;
  while ((iVar8 = (&DAT_10007548)[iVar2 * 0x68], iVar8 != 0 &&
         (local_48 < (uint)((&DAT_1000754c)[iVar2 * 0x68] - iVar8 >> 2)))) {
    if ((iVar8 == 0) || ((uint)((&DAT_1000754c)[iVar2 * 0x68] - iVar8 >> 2) <= local_48)) {
      _invalid_parameter_noinfo();
    }
    puVar7 = local_20;
    puVar1 = (undefined4 *)((&DAT_10007548)[iVar2 * 0x68] + local_48 * 4);
    if ((local_24 == (undefined4 *)0x0) ||
       ((uint)(local_1c - (int)local_24 >> 2) <= (uint)((int)local_20 - (int)local_24 >> 2))) {
      if (local_20 < local_24) {
        _invalid_parameter_noinfo();
      }
      FUN_10003ae0(local_30,puVar1,local_28,puVar7);
      local_48 = local_48 + 1;
    }
    else {
      local_48 = local_48 + 1;
      *local_20 = *puVar1;
      local_20 = local_20 + 1;
    }
  }
  Sleep(500);
  iVar8 = Play_CloseCamera(iVar2);
  if (iVar8 == -1) {
    pcVar10 = "%s Play_CloseCameraEx Fail, nCamId = %d\n";
  }
  else {
    Sleep(500);
    iVar8 = Play_OpenCamera(iVar2,uVar3,uVar4);
    if (iVar8 != -1) {
      _Src = (void *)(&DAT_1000754c)[iVar2 * 0x68];
      if (_Src < (void *)(&DAT_10007548)[iVar2 * 0x68]) {
        _invalid_parameter_noinfo();
      }
      _Dst = (void *)(&DAT_10007548)[iVar2 * 0x68];
      if ((void *)(&DAT_1000754c)[iVar2 * 0x68] < _Dst) {
        _invalid_parameter_noinfo();
      }
      if (_Dst != _Src) {
        iVar8 = (&DAT_1000754c)[iVar2 * 0x68] - (int)_Src >> 2;
        _DstSize = iVar8 * 4;
        if (0 < iVar8) {
          memmove_s(_Dst,_DstSize,_Src,_DstSize);
        }
        (&DAT_1000754c)[iVar2 * 0x68] = (void *)(_DstSize + (int)_Dst);
      }
      (&DAT_10007428)[iVar2 * 0x68] = local_34;
      local_48 = 0;
      while ((local_24 != (undefined4 *)0x0 &&
             (local_48 < (uint)((int)local_20 - (int)local_24 >> 2)))) {
        uVar3 = local_24[local_48];
        local_34 = uVar3;
        if (iVar2 == -1) {
          Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_AddPlayWindow",0xffffffff);
          local_48 = local_48 + 1;
        }
        else {
          iVar8 = Decode_StreamAddPlayWindow((&DAT_10007400)[iVar2 * 0x68],uVar3);
          if (iVar8 == 0) {
            Log("%s Decode_StreamAddPlayWindow Fail, nCamId = %d\n","Play_AddPlayWindow",iVar2);
            local_48 = local_48 + 1;
          }
          else {
            uVar5 = (&DAT_10007548)[iVar2 * 0x68];
            if ((uVar5 == 0) ||
               ((uint)((int)(*(int *)(&DAT_10007550 + iVar9) - uVar5) >> 2) <=
                (uint)((int)((&DAT_1000754c)[iVar2 * 0x68] - uVar5) >> 2))) {
              uVar6 = (&DAT_1000754c)[iVar2 * 0x68];
              if (uVar6 < uVar5) {
                _invalid_parameter_noinfo();
              }
              FUN_10003ae0(local_30,&local_34,&DAT_10007544 + iVar9,uVar6);
              local_48 = local_48 + 1;
            }
            else {
              puVar1 = (undefined4 *)(&DAT_1000754c)[iVar2 * 0x68];
              *puVar1 = uVar3;
              local_48 = local_48 + 1;
              (&DAT_1000754c)[iVar2 * 0x68] = puVar1 + 1;
            }
          }
        }
      }
      iVar9 = Decode_ShowPlateRegion
                        ((&DAT_10007400)[iVar2 * 0x68],*(undefined4 *)(&DAT_10007554 + iVar9),
                         (&DAT_10007594)[iVar2 * 0x68],*(undefined4 *)(&DAT_10007558 + iVar9),
                         *(undefined4 *)(&DAT_1000755c + iVar9),&DAT_10007564 + iVar9,
                         *(undefined4 *)(&DAT_10007560 + iVar9));
      if (iVar9 == 0) {
        Log("%s Decode_ShowPlateRegion Fail, nCamId = %d\n","ThreadReOpenCamera",iVar2);
        if (local_24 != (undefined4 *)0x0) {
          operator_delete(local_24);
        }
        ExceptionList = local_14;
        return 0xffffffff;
      }
      goto LAB_10003673;
    }
    pcVar10 = "%s Play_OpenCamera Fail, nCamId = %d\n";
  }
  Log(pcVar10,"ThreadReOpenCamera",iVar2);
LAB_10003673:
  if (local_24 != (undefined4 *)0x0) {
    operator_delete(local_24);
  }
  ExceptionList = local_14;
  return 0;
}



/* FUNCTION Play_GetJpgBuffer ENTRY 10002660 */

undefined4 Play_GetJpgBuffer(int param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  
                    /* 0x2660  8  Play_GetJpgBuffer */
  if (param_1 == -1) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_GetJpgBuffer",0xffffffff);
    return 0xffffffff;
  }
  iVar1 = Decode_GetJpgBuffer((&DAT_10007400)[param_1 * 0x68],param_2,param_3);
  if (iVar1 == 0) {
    Log("%s Decode_GetJpgBuffer Fail, nCamId = %d\n","Play_GetJpgBuffer",param_1);
    return 0xffffffff;
  }
  return 0;
}



/* FUNCTION Play_GetFrameData ENTRY 100026d0 */

undefined4 Play_GetFrameData(int param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4)

{
  int iVar1;
  
                    /* 0x26d0  7  Play_GetFrameData */
  if (param_1 == -1) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_GetFrameData",0xffffffff);
    return 0xffffffff;
  }
  iVar1 = Decode_GetFrameData((&DAT_10007400)[param_1 * 0x68],param_2,param_3,param_4);
  if (iVar1 == 0) {
    Log("%s Decode_GetJpgBuffer Fail, nCamId = %d\n","Play_GetFrameData",param_1);
    return 0xffffffff;
  }
  return 0;
}



/* FUNCTION Play_CloseCamera ENTRY 10002f90 */

undefined4 Play_CloseCamera(int param_1)

{
  undefined4 uVar1;
  int iVar2;
  
                    /* 0x2f90  4  Play_CloseCamera */
  if (param_1 == -1) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_CloseCamera",0xffffffff);
    return 0xffffffff;
  }
  uVar1 = (&DAT_10007400)[param_1 * 0x68];
  (&DAT_100073f8)[param_1 * 0x1a0] = 0;
  (&DAT_10007408)[param_1 * 0x68] = 0;
  (&DAT_10007418)[param_1 * 0x68] = 0xffffffff;
  FUN_10003a80();
  if ((&DAT_10007428)[param_1 * 0x68] == 1) {
    Play_StopRecord(param_1);
  }
  if ((HANDLE)(&DAT_1000740c)[param_1 * 0x68] != (HANDLE)0x0) {
    WaitForSingleObject((HANDLE)(&DAT_1000740c)[param_1 * 0x68],0xffffffff);
    Sleep(100);
    CloseHandle((HANDLE)(&DAT_1000740c)[param_1 * 0x68]);
    (&DAT_1000740c)[param_1 * 0x68] = 0;
  }
  if ((HANDLE)(&DAT_10007410)[param_1 * 0x68] != (HANDLE)0x0) {
    WaitForSingleObject((HANDLE)(&DAT_10007410)[param_1 * 0x68],0xffffffff);
    Sleep(100);
    CloseHandle((HANDLE)(&DAT_10007410)[param_1 * 0x68]);
    (&DAT_10007410)[param_1 * 0x68] = 0;
  }
  iVar2 = Rtsp_StopVideo(param_1);
  if (iVar2 != 0) {
    Log("%s Rtsp_StopVideo Fail, nCamId = %d\n","Play_CloseCamera",param_1);
    return 0xffffffff;
  }
  iVar2 = Decode_StreamStopEx(uVar1);
  if (iVar2 == 0) {
    Log("%s Decode_StreamStopEx Fail, nCamId = %d\n","Play_CloseCamera",param_1);
    return 0xffffffff;
  }
  Sleep(100);
  iVar2 = Decode_StreamCloseEx(uVar1);
  if (iVar2 == 0) {
    Log("%s Decode_StreamCloseEx Fail, nCamId = %d\n","Play_CloseCamera",param_1);
    return 0xffffffff;
  }
  (&DAT_10007400)[param_1 * 0x68] = 0xffffffff;
  iVar2 = Decode_FreePort(uVar1);
  if (iVar2 == 0) {
    Log("%s Decode_FreePort Fail, nCamId = %d\n","Play_CloseCamera",param_1);
    return 0xffffffff;
  }
  return 0;
}



/* FUNCTION Play_UnInit ENTRY 10003170 */

void Play_UnInit(void)

{
  rsize_t _DstSize;
  void *_Src;
  void *_Dst;
  int iVar1;
  uint *puVar2;
  
                    /* 0x3170  24  Play_UnInit */
  Rtsp_UNinit();
  puVar2 = &DAT_1000754c;
  do {
    if ((void *)puVar2[-0x52] != (void *)0x0) {
      free((void *)puVar2[-0x52]);
      puVar2[-0x52] = 0;
    }
    puVar2[-0x4b] = 0;
    puVar2[-0x51] = 0;
    puVar2[-0x4c] = 0;
    puVar2[-0x4a] = 0;
    puVar2[-0x49] = 0;
    *(undefined1 *)(puVar2 + -0x48) = 0;
    puVar2[-7] = 0;
    puVar2[-6] = 0;
    puVar2[-5] = 0;
    _Src = (void *)*puVar2;
    if (_Src < (void *)puVar2[-1]) {
      _invalid_parameter_noinfo();
    }
    _Dst = (void *)puVar2[-1];
    if ((void *)*puVar2 < _Dst) {
      _invalid_parameter_noinfo();
    }
    if (puVar2 == (uint *)0x8) {
      _invalid_parameter_noinfo();
    }
    if (_Dst != _Src) {
      iVar1 = (int)(*puVar2 - (int)_Src) >> 2;
      _DstSize = iVar1 * 4;
      if (0 < iVar1) {
        memmove_s(_Dst,_DstSize,_Src,_DstSize);
      }
      *puVar2 = (uint)(_DstSize + (int)_Dst);
    }
    puVar2 = puVar2 + 0x68;
  } while ((int)puVar2 < 0x1000a94c);
  return;
}



/* FUNCTION Play_SetRealDataCallBack ENTRY 100038d0 */

undefined4 Play_SetRealDataCallBack(int param_1,undefined4 param_2,int param_3)

{
                    /* 0x38d0  17  Play_SetRealDataCallBack */
  if (param_3 == 0) {
    return 0xffffffff;
  }
  (&DAT_10007408)[param_1 * 0x68] = param_3;
  (&DAT_10007418)[param_1 * 0x68] = param_2;
  return 0;
}



/* FUNCTION Play_SetRealDataCallBackEx ENTRY 10003900 */

undefined4 Play_SetRealDataCallBackEx(int param_1,undefined4 param_2,int param_3,undefined4 param_4)

{
                    /* 0x3900  18  Play_SetRealDataCallBackEx */
  if (param_3 == 0) {
    return 0xffffffff;
  }
  (&DAT_1000741c)[param_1 * 0x68] = param_3;
  (&DAT_10007418)[param_1 * 0x68] = param_2;
  (&DAT_10007420)[param_1 * 0x68] = param_4;
  return 0;
}



/* FUNCTION FUN_10003ae0 ENTRY 10003ae0 */

void FUN_10003ae0(int *param_1,undefined4 param_2,int param_3,int param_4)

{
  uint uVar1;
  int in_EAX;
  int iVar2;
  
  uVar1 = *(uint *)(in_EAX + 4);
  if ((uVar1 == 0) || ((int)(*(uint *)(in_EAX + 8) - uVar1) >> 2 == 0)) {
    iVar2 = 0;
  }
  else {
    if (*(uint *)(in_EAX + 8) < uVar1) {
      _invalid_parameter_noinfo();
    }
    if ((param_3 == 0) || (param_3 != in_EAX)) {
      _invalid_parameter_noinfo();
    }
    iVar2 = (int)(param_4 - uVar1) >> 2;
  }
  FUN_10003ba0(param_3,param_4);
  uVar1 = *(uint *)(in_EAX + 4);
  if (*(uint *)(in_EAX + 8) < uVar1) {
    _invalid_parameter_noinfo();
  }
  uVar1 = uVar1 + iVar2 * 4;
  if ((*(uint *)(in_EAX + 8) < uVar1) || (uVar1 < *(uint *)(in_EAX + 4))) {
    _invalid_parameter_noinfo();
  }
  param_1[1] = uVar1;
  *param_1 = in_EAX;
  return;
}



/* FUNCTION FUN_10003a80 ENTRY 10003a80 */

void FUN_10003a80(void)

{
  rsize_t _DstSize;
  void *_Src;
  void *_Dst;
  int iVar1;
  int unaff_EBX;
  
  _Src = *(void **)(unaff_EBX + 8);
  if (_Src < *(void **)(unaff_EBX + 4)) {
    _invalid_parameter_noinfo();
  }
  _Dst = *(void **)(unaff_EBX + 4);
  if (*(void **)(unaff_EBX + 8) < _Dst) {
    _invalid_parameter_noinfo();
  }
  if (_Dst != _Src) {
    iVar1 = *(int *)(unaff_EBX + 8) - (int)_Src >> 2;
    _DstSize = iVar1 * 4;
    if (0 < iVar1) {
      memmove_s(_Dst,_DstSize,_Src,_DstSize);
    }
    *(void **)(unaff_EBX + 8) = (void *)(_DstSize + (int)_Dst);
  }
  return;
}



/* FUNCTION Play_StopRecord ENTRY 10002e70 */

undefined4 Play_StopRecord(int param_1)

{
  int iVar1;
  BOOL BVar2;
  
                    /* 0x2e70  23  Play_StopRecord */
  if (param_1 == -1) {
    Log("%s Fail, nCamId = %d, Invalid Handle\n","Play_StopRecord",0xffffffff);
    return 0xffffffff;
  }
  if (((&DAT_10007428)[param_1 * 0x68] == 0) || ((&DAT_10007424)[param_1 * 0x68] == 0)) {
    Log("%s bRecordState = FALSE OR pRecordHandle = NULL  Fail, nCamId = %d\n","Play_StopRecord",
        param_1);
    return 0;
  }
  (&DAT_10007428)[param_1 * 0x68] = 0;
  Sleep(100);
  iVar1 = FUN_10001a00();
  if (iVar1 != 0) {
    Log("%s AVIRecordStop Fail, nCamId = %d\n","Play_StopRecord",param_1);
    return 0xffffffff;
  }
  iVar1 = FUN_10001820();
  if (iVar1 != 0) {
    Log("%s DeleteAVIRecordHandle Fail, nCamId = %d\n","Play_StopRecord",param_1);
    return 0xffffffff;
  }
  if (0 < (int)(&DAT_10007530)[param_1 * 0x68]) {
    BVar2 = PathIsDirectoryA(&DAT_1000742c + param_1 * 0x1a0);
    if (BVar2 == 0) {
      FUN_10001e10();
    }
  }
  (&DAT_10007424)[param_1 * 0x68] = 0;
  (&DAT_10007530)[param_1 * 0x68] = 0;
  (&DAT_10007534)[param_1 * 0x68] = 0;
  (&DAT_10007538)[param_1 * 0x68] = 0;
  (&DAT_1000742c)[param_1 * 0x1a0] = 0;
  return 0;
}


