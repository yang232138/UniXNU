// Stage-1 firmware modules. Variables use the emulated RAM store.
  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf
  INF HoujiVendorPkg/EnvDxeEnhanced/EnvDxeEnhanced.inf
  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
!if $(WITH_HOUJI_ROOT_RAM) == TRUE
  INF houjiPkg/Drivers/HoujiRootRAMDxe/HoujiRootRAMDxe.inf
!endif
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf
  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf
  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
  INF houjiPkg/Drivers/NoCapsuleRuntimeDxe/NoCapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
!if $(WITH_HOUJI_POWER_KEY) == TRUE
  INF houjiPkg/Drivers/HoujiPowerKeyDxe/HoujiPowerKeyDxe.inf
  INF SiliciumPkg/Drivers/KeypadDxe/KeypadDxe.inf
!endif
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf
  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf
  INF UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
!if $(WITH_HOUJI_IPHONE26_AUTO_BOOT) == TRUE
  INF DarwinBootPkg/Driver/DarwinBoot.inf
!endif
  INF UniXNUPkg/Application/UniXNU/UniXNU.inf
