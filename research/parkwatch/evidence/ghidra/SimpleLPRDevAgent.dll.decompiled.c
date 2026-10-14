
/* FUNCTION LPR_Create ENTRY 10006660 */

void LPR_Create(undefined4 *param_1)

{
  int *piVar1;
  char cVar2;
  char *pcVar3;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
                    /* 0x6660  1  LPR_Create */
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009f74;
  local_10 = ExceptionList;
  ExceptionList = &local_10;
  if ((*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa44) &&
     (FUN_10008bc3(&DAT_1000fa44), DAT_1000fa44 == -1)) {
    local_8 = 0;
    DAT_1000fa48 = (int *)cx::GetLogger("LPR_Create");
    local_8 = 0xffffffff;
    FUN_10008b84(&DAT_1000fa44);
  }
  DAT_1000f860 = DAT_1000f860 + 1;
  cVar2 = (**(code **)(*DAT_1000fa48 + 0x40))();
  if (cVar2 != '\0') {
    (**(code **)(*DAT_1000fa48 + 0x20))(DAT_1000fa48,"ENTER: COUNT(%d)",DAT_1000f860);
  }
  if (param_1 == (undefined4 *)0x0) {
    cVar2 = (**(code **)(*DAT_1000fa48 + 0x40))();
    if (cVar2 != '\0') {
      (**(code **)(*DAT_1000fa48 + 0x10))(DAT_1000fa48," -> ERROR: %d, %s",4,"Null argument.");
    }
  }
  else {
    cVar2 = FUN_10005b00();
    if (cVar2 == '\0') {
      cVar2 = (**(code **)(*DAT_1000fa48 + 0x40))();
      if (cVar2 != '\0') {
        (**(code **)(*DAT_1000fa48 + 0x10))(DAT_1000fa48," -> ERROR: %d, %s",6,"Not ready.");
      }
    }
    else {
      local_8 = 1;
      pcVar3 = (char *)FUN_100086de(1);
      *pcVar3 = '\0';
      local_8 = CONCAT31(local_8._1_3_,2);
      if (*pcVar3 == '\0') {
        *pcVar3 = '\x01';
      }
      piVar1 = DAT_1000fa48;
      *param_1 = pcVar3;
      cVar2 = (**(code **)(*piVar1 + 0x40))();
      if (cVar2 != '\0') {
        (**(code **)(*DAT_1000fa48 + 0x20))(DAT_1000fa48," -> EXIT");
      }
    }
  }
  ExceptionList = local_10;
  FUN_100086c8();
  return;
}



/* FUNCTION LPR_Release ENTRY 10006840 */

undefined4 LPR_Release(char *param_1)

{
  char cVar1;
  
                    /* 0x6840  11  LPR_Release */
  if (*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa4c) {
    FUN_10008bc3(&DAT_1000fa4c);
    if (DAT_1000fa4c == -1) {
      DAT_1000fa50 = (int *)cx::GetLogger("LPR_Release");
      FUN_10008b84(&DAT_1000fa4c);
    }
  }
  DAT_1000f85c = DAT_1000f85c + 1;
  cVar1 = (**(code **)(*DAT_1000fa50 + 0x40))();
  if (cVar1 != '\0') {
    (**(code **)(*DAT_1000fa50 + 0x20))(DAT_1000fa50,"ENTER: COUNT(%d)",DAT_1000f85c);
  }
  if (param_1 != (char *)0x0) {
    if (*param_1 != '\0') {
      *param_1 = '\0';
    }
    FUN_10008734(param_1,1);
  }
  cVar1 = (**(code **)(*DAT_1000fa50 + 0x40))();
  if (cVar1 != '\0') {
    (**(code **)(*DAT_1000fa50 + 0x20))(DAT_1000fa50," -> EXIT");
  }
  return 0;
}



/* FUNCTION LPR_Recognize ENTRY 10006910 */

int LPR_Recognize(int param_1,int param_2,int param_3)

{
  int *piVar1;
  char cVar2;
  bool bVar3;
  int iVar4;
  undefined4 uVar5;
  int iVar6;
  code *pcVar7;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_28 [24];
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
                    /* 0x6910  9  LPR_Recognize */
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009fa7;
  local_10 = ExceptionList;
  ExceptionList = &local_10;
  if (*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa54) {
    FUN_10008bc3(&DAT_1000fa54,DAT_1000f00c ^ (uint)&stack0xfffffffc);
    if (DAT_1000fa54 == -1) {
      DAT_1000fa58 = (int *)cx::GetLogger("LPR_Recognize");
      FUN_10008b84(&DAT_1000fa54);
    }
  }
  DAT_1000f858 = DAT_1000f858 + 1;
  cVar2 = (**(code **)(*DAT_1000fa58 + 0x40))();
  if (cVar2 != '\0') {
    (**(code **)(*DAT_1000fa58 + 0x20))(DAT_1000fa58,"ENTER: COUNT(%d)",DAT_1000f858);
  }
  if (((param_1 != 0) && (param_2 != 0)) && (param_3 != 0)) {
    FUN_100018e0(param_2);
    bVar3 = cx::File::Exists(local_28);
    FUN_10001940();
    if (!bVar3) {
      cVar2 = (**(code **)(*DAT_1000fa58 + 0x40))();
      if (cVar2 != '\0') {
        (**(code **)(*DAT_1000fa58 + 0x10))(DAT_1000fa58," -> ERROR: %d, %s",0xc,"File not exist.");
      }
      ExceptionList = local_10;
      return 0xc;
    }
    iVar4 = _Mtx_lock(&DAT_1000f8b8);
    pcVar7 = _Throw_C_error_exref;
    if (iVar4 != 0) {
      std::_Throw_C_error(iVar4);
    }
    iVar4 = FUN_100035b0(param_2,param_3);
    cVar2 = (**(code **)(*DAT_1000fa58 + 0x40))();
    piVar1 = DAT_1000fa58;
    if (cVar2 != '\0') {
      if (iVar4 == 0) {
        (**(code **)(*DAT_1000fa58 + 0x20))(DAT_1000fa58," -> EXIT");
      }
      else {
        iVar6 = *DAT_1000fa58;
        uVar5 = LPR_GetErrorMessage(iVar4);
        (**(code **)(iVar6 + 0x10))(piVar1," -> ERROR: %d, %s",iVar4,uVar5);
        pcVar7 = _Throw_C_error_exref;
      }
    }
    local_8 = 0;
    iVar6 = _Mtx_unlock(&DAT_1000f8b8);
    if (iVar6 != 0) {
      (*pcVar7)(iVar6);
    }
    ExceptionList = local_10;
    return iVar4;
  }
  cVar2 = (**(code **)(*DAT_1000fa58 + 0x40))();
  if (cVar2 != '\0') {
    (**(code **)(*DAT_1000fa58 + 0x10))(DAT_1000fa58," -> ERROR: %d, %s",4,"Null argument.");
  }
  ExceptionList = local_10;
  return 4;
}



/* FUNCTION LPR_RecognizeAll ENTRY 10006b30 */

int LPR_RecognizeAll(int param_1,int param_2,int param_3,int param_4,undefined4 param_5,
                    undefined4 param_6)

{
  int iVar1;
  int *piVar2;
  char cVar3;
  bool bVar4;
  int iVar5;
  undefined4 uVar6;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> abStack_20 [28];
  
                    /* 0x6b30  10  LPR_RecognizeAll */
  if (*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa5c) {
    FUN_10008bc3(&DAT_1000fa5c);
    if (DAT_1000fa5c == -1) {
      DAT_1000fa60 = (int *)cx::GetLogger("LPR_RecognizeAll");
      FUN_10008b84(&DAT_1000fa5c);
    }
  }
  DAT_1000f854 = DAT_1000f854 + 1;
  cVar3 = (**(code **)(*DAT_1000fa60 + 0x40))();
  if (cVar3 != '\0') {
    (**(code **)(*DAT_1000fa60 + 0x20))(DAT_1000fa60,"ENTER: COUNT(%d)",DAT_1000f854);
  }
  if (((param_1 == 0) || (param_2 == 0)) || (param_3 == 0)) {
    cVar3 = (**(code **)(*DAT_1000fa60 + 0x40))();
    if (cVar3 != '\0') {
      (**(code **)(*DAT_1000fa60 + 0x10))(DAT_1000fa60," -> ERROR: %d, %s",4,"Null argument.");
    }
    return 4;
  }
  if (param_4 == 0) {
    cVar3 = (**(code **)(*DAT_1000fa60 + 0x40))();
    if (cVar3 != '\0') {
      (**(code **)(*DAT_1000fa60 + 0x10))(DAT_1000fa60," -> ERROR: %d, %s",3,"Invalid argument.");
    }
    return 3;
  }
  FUN_100018e0(param_2);
  bVar4 = cx::File::Exists(abStack_20);
  FUN_10001940();
  if (!bVar4) {
    cVar3 = (**(code **)(*DAT_1000fa60 + 0x40))();
    if (cVar3 != '\0') {
      (**(code **)(*DAT_1000fa60 + 0x10))(DAT_1000fa60," -> ERROR: %d, %s",0xc,"File not exist.");
    }
    return 0xc;
  }
  FUN_10007730(&DAT_1000f8b8);
  iVar5 = FUN_10003740(param_2,param_3,param_4,param_5,param_6);
  cVar3 = (**(code **)(*DAT_1000fa60 + 0x40))();
  piVar2 = DAT_1000fa60;
  if (cVar3 != '\0') {
    if (iVar5 == 0) {
      (**(code **)(*DAT_1000fa60 + 0x20))(DAT_1000fa60," -> EXIT");
      FUN_100076e0();
      return 0;
    }
    iVar1 = *DAT_1000fa60;
    uVar6 = LPR_GetErrorMessage(iVar5);
    (**(code **)(iVar1 + 0x10))(piVar2," -> ERROR: %d, %s",iVar5,uVar6);
  }
  FUN_100076e0();
  return iVar5;
}



/* FUNCTION LPR_LoadApis ENTRY 10007760 */

void LPR_LoadApis(undefined4 *param_1)

{
  uint *puVar1;
  char cVar2;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> *pbVar3;
  void *pvVar4;
  uint uStack_21c;
  basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_> local_20c [24];
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_1f4 [16];
  undefined4 local_1e4;
  undefined4 local_1e0;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_1dc [16];
  undefined4 local_1cc;
  undefined4 local_1c8;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_1c4 [16];
  undefined4 local_1b4;
  undefined4 local_1b0;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_1ac [16];
  undefined4 local_19c;
  undefined4 local_198;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_194 [16];
  undefined4 local_184;
  undefined4 local_180;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_17c [16];
  undefined4 local_16c;
  undefined4 local_168;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_164 [16];
  undefined4 local_154;
  undefined4 local_150;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_14c [16];
  undefined4 local_13c;
  undefined4 local_138;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_134 [16];
  undefined4 local_124;
  undefined4 local_120;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_11c [16];
  undefined4 local_10c;
  undefined4 local_108;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_104 [16];
  undefined4 local_f4;
  undefined4 local_f0;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_ec [16];
  undefined4 local_dc;
  undefined4 local_d8;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_d4 [16];
  undefined4 local_c4;
  undefined4 local_c0;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_bc [16];
  undefined4 local_ac;
  undefined4 local_a8;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_a4 [16];
  undefined4 local_94;
  undefined4 local_90;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_8c [16];
  undefined4 local_7c;
  undefined4 local_78;
  undefined1 local_74;
  undefined4 local_64;
  undefined4 local_60;
  SharedLibrary local_38 [32];
  uint local_18;
  undefined1 *local_14;
  void *local_10;
  undefined1 *puStack_c;
  undefined4 local_8;
  
                    /* 0x7760  8  LPR_LoadApis */
  local_8 = 0xffffffff;
  puStack_c = &LAB_1000a146;
  local_10 = ExceptionList;
  uStack_21c = DAT_1000f00c ^ (uint)&stack0xfffffffc;
  local_14 = (undefined1 *)&uStack_21c;
  ExceptionList = &local_10;
  local_18 = uStack_21c;
  puVar1 = &uStack_21c;
  if ((*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa7c) &&
     (FUN_10008bc3(&DAT_1000fa7c), puVar1 = (uint *)local_14, DAT_1000fa7c == -1)) {
    local_8 = 0;
    DAT_1000fa80 = (int *)cx::GetLogger("LPR_LoadApis");
    local_8 = 0xffffffff;
    FUN_10008b84(&DAT_1000fa7c);
    puVar1 = (uint *)local_14;
  }
  local_14 = (undefined1 *)puVar1;
  DAT_1000fa00 = DAT_1000fa00 + 1;
  cVar2 = (**(code **)(*DAT_1000fa80 + 0x40))();
  if (cVar2 != '\0') {
    (**(code **)(*DAT_1000fa80 + 0x20))(DAT_1000fa80,"ENTER: COUNT(%d)",DAT_1000fa00);
  }
  if (param_1 != (undefined4 *)0x0) {
    local_8 = 1;
    Poco::SharedLibrary::SharedLibrary(local_38);
    local_8._0_1_ = 2;
    local_60 = 0xf;
    local_64 = 0;
    local_74 = 0;
    FUN_100017e0("SimpleLPRDevAgent",0x11);
    local_8._0_1_ = 3;
    FUN_100010d0();
    local_8._0_1_ = 4;
    pbVar3 = (basic_string<char,std::char_traits<char>,std::allocator<char>_> *)
             cx::Convert::ANSIToUTF8(local_20c);
    local_8._0_1_ = 5;
    Poco::SharedLibrary::load(local_38,pbVar3);
    FUN_10001940();
    FUN_10001940();
    local_8._0_1_ = 2;
    FUN_10001940();
    local_78 = 0xf;
    local_7c = 0;
    local_8c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_SetCountry",0xe);
    local_8._0_1_ = 6;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_8c);
    *param_1 = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_90 = 0xf;
    local_94 = 0;
    local_a4[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_SetAllCountriesWeight",0x19);
    local_8._0_1_ = 7;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_a4);
    param_1[1] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_a8 = 0xf;
    local_ac = 0;
    local_bc[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_SetCountryWeight",0x14);
    local_8._0_1_ = 8;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_bc);
    param_1[2] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_c0 = 0xf;
    local_c4 = 0;
    local_d4[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_GetCountryWeight",0x14);
    local_8._0_1_ = 9;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_d4);
    param_1[3] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_d8 = 0xf;
    local_dc = 0;
    local_ec[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("[redacted]",0x11);
    local_8._0_1_ = 10;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_ec);
    param_1[4] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_f0 = 0xf;
    local_f4 = 0;
    local_104[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_Create",10);
    local_8._0_1_ = 0xb;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_104);
    param_1[5] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_108 = 0xf;
    local_10c = 0;
    local_11c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_Release",0xb);
    local_8._0_1_ = 0xc;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_11c);
    param_1[6] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_120 = 0xf;
    local_124 = 0;
    local_134[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_Recognize",0xd);
    local_8._0_1_ = 0xd;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_134);
    param_1[7] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_138 = 0xf;
    local_13c = 0;
    local_14c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_RecognizeAll",0x10);
    local_8._0_1_ = 0xe;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_14c);
    param_1[8] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_150 = 0xf;
    local_154 = 0;
    local_164[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_GetErrorMessage",0x13);
    local_8._0_1_ = 0xf;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_164);
    param_1[9] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_168 = 0xf;
    local_16c = 0;
    local_17c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_GetCountryCount",0x13);
    local_8._0_1_ = 0x10;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_17c);
    param_1[10] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_180 = 0xf;
    local_184 = 0;
    local_194[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_GetCountryName",0x12);
    local_8._0_1_ = 0x11;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_194);
    param_1[0xb] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_198 = 0xf;
    local_19c = 0;
    local_1ac[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_SaveSubImage",0x10);
    local_8._0_1_ = 0x12;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_1ac);
    param_1[0xc] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_1b0 = 0xf;
    local_1b4 = 0;
    local_1c4[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_SearchFiles",0xf);
    local_8._0_1_ = 0x13;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_1c4);
    param_1[0xd] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_1c8 = 0xf;
    local_1cc = 0;
    local_1dc[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_GetFileListItem",0x13);
    local_8._0_1_ = 0x14;
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_1dc);
    param_1[0xe] = pvVar4;
    local_8._0_1_ = 2;
    FUN_10001940();
    local_1e0 = 0xf;
    local_1e4 = 0;
    local_1f4[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("LPR_DeleteFileList",0x12);
    local_8 = CONCAT31(local_8._1_3_,0x15);
    pvVar4 = Poco::SharedLibrary::getSymbol(local_38,local_1f4);
    param_1[0xf] = pvVar4;
    FUN_10001940();
    Poco::SharedLibrary::~SharedLibrary(local_38);
  }
  ExceptionList = local_10;
  FUN_100086c8();
  return;
}



/* FUNCTION FUN_10008bc3 ENTRY 10008bc3 */

void FUN_10008bc3(int *param_1)

{
  FUN_10008c09();
  do {
    if (*param_1 == 0) {
      *param_1 = -1;
LAB_10008c02:
      LeaveCriticalSection((LPCRITICAL_SECTION)&DAT_1000f4d4);
      return;
    }
    if (*param_1 != -1) {
      *(undefined4 *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) = DAT_1000f004;
      goto LAB_10008c02;
    }
    FUN_10008c62(100);
  } while( true );
}



/* FUNCTION FUN_10008b84 ENTRY 10008b84 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_10008b84(int *param_1)

{
  byte bVar1;
  uint uVar2;
  
  FUN_10008c09();
  DAT_1000f004 = DAT_1000f004 + 1;
  *param_1 = DAT_1000f004;
  *(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) = DAT_1000f004;
  FUN_10008c56();
  if (DAT_1000f4f0 == (HANDLE)0x0) {
    uVar2 = DAT_1000f00c ^ _DAT_1000f4f8;
    bVar1 = (byte)DAT_1000f00c & 0x1f;
    guard_check_icall(&DAT_1000f4ec);
    (*(code *)(uVar2 >> bVar1 | uVar2 << 0x20 - bVar1))();
    return;
  }
  SetEvent(DAT_1000f4f0);
  ResetEvent(DAT_1000f4f0);
  return;
}



/* FUNCTION FUN_10005b00 ENTRY 10005b00 */

undefined1 FUN_10005b00(void)

{
  char cVar1;
  int iVar2;
  uint uVar3;
  undefined1 uVar4;
  int iVar5;
  code *pcVar6;
  undefined1 local_30 [24];
  undefined *local_18;
  int local_14;
  void *local_10;
  undefined1 *puStack_c;
  uint local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009ee3;
  local_10 = ExceptionList;
  if (DAT_1000f880 != '\0') {
    return DAT_1000f8f8;
  }
  local_18 = &DAT_1000f888;
  ExceptionList = &local_10;
  iVar2 = _Mtx_lock(&DAT_1000f888,DAT_1000f00c ^ (uint)&stack0xfffffffc);
  pcVar6 = _Throw_C_error_exref;
  if (iVar2 != 0) {
    std::_Throw_C_error(iVar2);
  }
  local_8 = 0;
  uVar4 = DAT_1000f8f8;
  if (DAT_1000f880 == '\0') {
    if ((*(int *)(*(int *)((int)ThreadLocalStoragePointer + _tls_index * 4) + 4) < DAT_1000fa14) &&
       (FUN_10008bc3(&DAT_1000fa14), DAT_1000fa14 == -1)) {
      local_8._0_1_ = 1;
      DAT_1000fa18 = (int *)cx::GetLogger("Initialize");
      local_8 = (uint)local_8._1_3_ << 8;
      FUN_10008b84(&DAT_1000fa14);
    }
    DAT_1000f878 = DAT_1000f878 + 1;
    cVar1 = (**(code **)(*DAT_1000fa18 + 0x40))();
    if (cVar1 != '\0') {
      (**(code **)(*DAT_1000fa18 + 0x20))(DAT_1000fa18,"ENTER: COUNT(%d)",DAT_1000f878);
    }
    DAT_1000f880 = '\x01';
    cVar1 = FUN_10001f80();
    if (cVar1 == '\0') {
      uVar4 = 0;
    }
    else {
      local_14 = FUN_10003360();
      iVar2 = 0;
      if (0 < local_14) {
        do {
          uVar3 = FUN_10003490(local_30,iVar2);
          local_8 = CONCAT31(local_8._1_3_,2);
          if ((uVar3 < DAT_1000f8ec) && (DAT_1000f8e8 <= uVar3)) {
            iVar5 = uVar3 - DAT_1000f8e8;
            if (DAT_1000f8ec == DAT_1000f8f0) {
              FUN_100040b0(DAT_1000f8ec);
            }
            uVar3 = DAT_1000f8e8 + (iVar5 / 0x18) * 0x18;
          }
          else if (DAT_1000f8ec == DAT_1000f8f0) {
            FUN_100040b0(DAT_1000f8ec);
          }
          if (DAT_1000f8ec != 0) {
            FUN_10001630(uVar3);
          }
          DAT_1000f8ec = DAT_1000f8ec + 0x18;
          local_8 = local_8 & 0xffffff00;
          FUN_10001940();
          iVar2 = iVar2 + 1;
          pcVar6 = _Throw_C_error_exref;
        } while (iVar2 < local_14);
      }
      uVar4 = 1;
    }
  }
  local_8 = 3;
  iVar2 = _Mtx_unlock(&DAT_1000f888);
  if (iVar2 != 0) {
    (*pcVar6)(iVar2);
  }
  ExceptionList = local_10;
  return uVar4;
}



/* FUNCTION FUN_100086de ENTRY 100086de */

void FUN_100086de(size_t param_1)

{
  int iVar1;
  void *pvVar2;
  
  while( true ) {
    pvVar2 = malloc(param_1);
    if (pvVar2 != (void *)0x0) break;
    iVar1 = _callnewh(param_1);
    if (iVar1 == 0) {
      if (param_1 == 0xffffffff) {
        FUN_100091d6();
      }
      else {
        FUN_100091b9();
      }
    }
  }
  return;
}



/* FUNCTION FUN_10008734 ENTRY 10008734 */

void FUN_10008734(void *param_1)

{
  free(param_1);
  return;
}



/* FUNCTION FUN_100018e0 ENTRY 100018e0 */

undefined1 * __thiscall FUN_100018e0(undefined1 *param_1,char *param_2)

{
  char cVar1;
  char *pcVar2;
  
  *(undefined4 *)(param_1 + 0x14) = 0xf;
  *(undefined4 *)(param_1 + 0x10) = 0;
  *param_1 = 0;
  if (*param_2 == '\0') {
    FUN_100017e0(param_2,0);
    return param_1;
  }
  pcVar2 = param_2;
  do {
    cVar1 = *pcVar2;
    pcVar2 = pcVar2 + 1;
  } while (cVar1 != '\0');
  FUN_100017e0(param_2,(int)pcVar2 - (int)(param_2 + 1));
  return param_1;
}



/* FUNCTION FUN_10001940 ENTRY 10001940 */

void __fastcall FUN_10001940(uint *param_1)

{
  void *pvVar1;
  void *_Memory;
  
  if (0xf < param_1[5]) {
    pvVar1 = (void *)*param_1;
    _Memory = pvVar1;
    if (0xfff < param_1[5] + 1) {
      if (((uint)pvVar1 & 0x1f) != 0) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      _Memory = *(void **)((int)pvVar1 - 4);
      if (pvVar1 <= _Memory) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      if ((uint)((int)pvVar1 - (int)_Memory) < 4) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
      if (0x23 < (uint)((int)pvVar1 - (int)_Memory)) {
                    /* WARNING: Subroutine does not return */
        _invalid_parameter_noinfo_noreturn();
      }
    }
    free(_Memory);
  }
  param_1[5] = 0xf;
  param_1[4] = 0;
  if (0xf < param_1[5]) {
    param_1 = (uint *)*param_1;
  }
  *(undefined1 *)param_1 = 0;
  return;
}



/* FUNCTION FUN_100017e0 ENTRY 100017e0 */

int * __thiscall FUN_100017e0(int *param_1,int *param_2,uint param_3)

{
  uint uVar1;
  int *piVar2;
  
  if (param_2 != (int *)0x0) {
    uVar1 = param_1[5];
    piVar2 = param_1;
    if (0xf < uVar1) {
      piVar2 = (int *)*param_1;
    }
    if (piVar2 <= param_2) {
      piVar2 = param_1;
      if (0xf < uVar1) {
        piVar2 = (int *)*param_1;
      }
      if (param_2 < (int *)(param_1[4] + (int)piVar2)) {
        if (0xf < uVar1) {
          piVar2 = (int *)FUN_10001d30(param_1,(int)param_2 - *param_1,param_3);
          return piVar2;
        }
        piVar2 = (int *)FUN_10001d30(param_1,(int)param_2 - (int)param_1,param_3);
        return piVar2;
      }
    }
  }
  if (param_3 == 0xffffffff) {
                    /* WARNING: Subroutine does not return */
    std::_Xlength_error("string too long");
  }
  if ((uint)param_1[5] < param_3) {
    FUN_10001aa0(param_3,param_1[4]);
    if (param_3 == 0) {
      return param_1;
    }
  }
  else if (param_3 == 0) {
    param_1[4] = 0;
    if (0xf < (uint)param_1[5]) {
      *(undefined1 *)*param_1 = 0;
      return param_1;
    }
    *(undefined1 *)param_1 = 0;
    return param_1;
  }
  piVar2 = param_1;
  if (0xf < (uint)param_1[5]) {
    piVar2 = (int *)*param_1;
  }
  if (param_3 != 0) {
    memcpy(piVar2,param_2,param_3);
  }
  param_1[4] = param_3;
  if ((uint)param_1[5] < 0x10) {
    *(undefined1 *)((int)param_1 + param_3) = 0;
    return param_1;
  }
  *(undefined1 *)(*param_1 + param_3) = 0;
  return param_1;
}



/* FUNCTION FUN_100010d0 ENTRY 100010d0 */

void __fastcall FUN_100010d0(undefined4 param_1,undefined4 param_2)

{
  bool bVar1;
  uint uVar2;
  undefined4 uVar3;
  undefined4 extraout_ECX;
  basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_> local_ac [24];
  undefined4 local_94;
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_8c [16];
  undefined4 local_7c;
  undefined4 local_78;
  basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_> local_74 [24];
  basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_> local_5c [24];
  basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_> local_44 [24];
  basic_string<char,std::char_traits<char>,std::allocator<char>_> local_2c [16];
  undefined4 local_1c;
  undefined4 local_18;
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  int local_8;
  
  local_8 = 0xffffffff;
  puStack_c = &LAB_10009831;
  local_10 = ExceptionList;
  uVar2 = DAT_1000f00c ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_94 = 0;
  local_18 = 0xf;
  local_1c = 0;
  local_2c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
  local_14 = uVar2;
  FUN_10001d30(param_2,0,0xffffffff);
  local_8 = 0;
  local_78 = 0xf;
  local_7c = 0;
  local_8c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
  FUN_100017e0(&DAT_1000b350,4);
  local_8._0_1_ = 1;
  bVar1 = cx::StringUtils::EndsWith(local_2c,local_8c,true);
  local_8 = (uint)local_8._1_3_ << 8;
  FUN_10001940(uVar2);
  if (!bVar1) {
    uVar3 = FUN_10001300(extraout_ECX);
    FUN_10001720(uVar3);
    FUN_10001940();
  }
  bVar1 = cx::Path::IsPathRooted(local_2c);
  if (bVar1) {
    FUN_10001630(local_2c);
  }
  else {
    cx::Module::GetExeDirectory();
    local_8._0_1_ = 2;
    local_78 = 0xf;
    local_7c = 0;
    local_8c[0] = (basic_string<char,std::char_traits<char>,std::allocator<char>_>)0x0;
    FUN_100017e0("plugins",7);
    local_8._0_1_ = 3;
    cx::Path::GetFileNameWithoutExtension(local_ac);
    local_8._0_1_ = 4;
    cx::Path::Combine(local_74,local_5c,
                      (basic_string<char,struct_std::char_traits<char>,class_std::allocator<char>_>
                       *)local_8c);
    FUN_10001940();
    local_8._0_1_ = 7;
    FUN_10001940();
    cx::Path::Combine(local_44,local_74);
    local_8 = CONCAT31(local_8._1_3_,8);
    bVar1 = cx::File::Exists((basic_string<char,std::char_traits<char>,std::allocator<char>_> *)
                             local_44);
    if (!bVar1) {
      uVar3 = cx::Path::Combine(local_ac,local_5c);
      FUN_10001720(uVar3);
      FUN_10001940();
      cx::File::Exists((basic_string<char,std::char_traits<char>,std::allocator<char>_> *)local_44);
    }
    FUN_10001630(local_44);
    FUN_10001940();
    FUN_10001940();
    FUN_10001940();
  }
  FUN_10001940();
  ExceptionList = local_10;
  FUN_100086c8();
  return;
}


