
/* FUNCTION FUN_00407e50 ENTRY 00407e50 */

void __thiscall FUN_00407e50(int param_1,int param_2)

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
  
  local_4 = DAT_0046b5c0 ^ (uint)auStack_138;
  local_130 = (LPCRITICAL_SECTION)(param_1 + 0x348);
  EnterCriticalSection(local_130);
  local_134 = 1;
  if (*(ushort *)(param_1 + 0x13c) == 0xffffffff) {
    local_134 = 0;
    goto LAB_00407f7c;
  }
  iVar1 = Net_AddCamera(param_2);
  if (iVar1 == -1) {
LAB_00407f61:
    local_134 = 0;
  }
  else {
    iVar2 = Net_ConnCamera(iVar1,30000,5);
    if (iVar2 != 0) goto LAB_00407f61;
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
    if (iVar2 != 0) goto LAB_00407f61;
  }
  if (iVar1 != -1) {
    Net_DisConnCamera(iVar1);
    Net_DelCamera(iVar1);
  }
LAB_00407f7c:
  LeaveCriticalSection(local_130);
  FUN_00436a45();
  return;
}



/* FUNCTION FUN_00407fb0 ENTRY 00407fb0 */

undefined4 FUN_00407fb0(undefined4 param_1)

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
      if (iVar2 == 0) goto LAB_0040801a;
    }
  }
  uVar3 = 0;
LAB_0040801a:
  if (iVar1 != -1) {
    Net_DisConnCamera(iVar1);
    Net_DelCamera(iVar1);
  }
  LeaveCriticalSection(lpCriticalSection);
  return uVar3;
}



/* FUNCTION FUN_00436a45 ENTRY 00436a45 */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void __fastcall FUN_00436a45(int param_1,undefined4 param_2)

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
  
  if (param_1 == DAT_0046b5c0) {
    return;
  }
  _DAT_0046f4f0 =
       (uint)(in_NT & 1) * 0x4000 | (uint)SBORROW4((int)&stack0xfffffffc,0x328) * 0x800 |
       (uint)(in_IF & 1) * 0x200 | (uint)(in_TF & 1) * 0x100 | (uint)((int)&local_32c < 0) * 0x80 |
       (uint)(&stack0x00000000 == (undefined1 *)0x32c) * 0x40 | (uint)(in_AF & 1) * 0x10 |
       (uint)((POPCOUNT((uint)&local_32c & 0xff) & 1U) == 0) * 4 |
       (uint)(&stack0xfffffffc < (undefined1 *)0x328) | (uint)(in_ID & 1) * 0x200000 |
       (uint)(in_VIP & 1) * 0x100000 | (uint)(in_VIF & 1) * 0x80000 | (uint)(in_AC & 1) * 0x40000;
  _DAT_0046f4f4 = &stack0x00000004;
  _DAT_0046f430 = 0x10001;
  _DAT_0046f3d8 = 0xc0000409;
  _DAT_0046f3dc = 1;
  local_32c = DAT_0046b5c0;
  local_328 = DAT_0046b5c4;
  _DAT_0046f3e4 = unaff_retaddr;
  _DAT_0046f4bc = in_GS;
  _DAT_0046f4c0 = in_FS;
  _DAT_0046f4c4 = in_ES;
  _DAT_0046f4c8 = in_DS;
  _DAT_0046f4cc = unaff_EDI;
  _DAT_0046f4d0 = unaff_ESI;
  _DAT_0046f4d4 = unaff_EBX;
  _DAT_0046f4d8 = param_2;
  _DAT_0046f4dc = param_1;
  _DAT_0046f4e0 = in_EAX;
  _DAT_0046f4e4 = unaff_EBP;
  DAT_0046f4e8 = unaff_retaddr;
  _DAT_0046f4ec = in_CS;
  _DAT_0046f4f8 = in_SS;
  DAT_0046f428 = IsDebuggerPresent();
  FUN_0044258b(1);
  SetUnhandledExceptionFilter((LPTOP_LEVEL_EXCEPTION_FILTER)0x0);
  UnhandledExceptionFilter((_EXCEPTION_POINTERS *)&PTR_DAT_00459e30);
  if (DAT_0046f428 == 0) {
    FUN_0044258b(1);
  }
  uExitCode = 0xc0000409;
  hProcess = GetCurrentProcess();
  TerminateProcess(hProcess,uExitCode);
  return;
}


