# Confirmed links and unresolved selection

```mermaid
flowchart TD
  Park[Park.exe x86] -->|ordinary import| DV[DVNETSDK.DLL]
  Park -->|LoadLibraryA and LPR_LoadApis| Agent[SimpleLPRDevAgent.dll]
  QY[IPC_QY.dll adapter] -->|ordinary import and traced calls| Net[NetSDK.dll]
  QY -->|ordinary import| Base[AppBase.dll]
  App[Active camera adapter selection: unresolved] -.-> QY
  Net -->|documented callback contract| Event[Plate metadata and image pointers]
  Net -->|StartVideo HWND interface| Video[SDK playback]
```

Solid links represent static code/import evidence or the labeled vendor contract, not observed runtime traffic. Park.exe to the active QY adapter has not been established. Inventory JSON contains ordinary dependency names for all parsed binaries; Windows loader resolution and delay/dynamic dependencies are outside that graph.
