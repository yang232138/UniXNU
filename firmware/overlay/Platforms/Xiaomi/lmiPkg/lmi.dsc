##
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = lmi
  PLATFORM_GUID                  = 28F1A3BF-193A-47E3-A7B9-5A435EAAB2EE
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/lmiPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = lmiPkg/lmi.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

  #
  # 0 = SM8250
  # 1 = SM8250-AB
  # 2 = SM8250-AC
  #
  SOC_TYPE                       = 0

!include KonaPkg/KonaPkg.dsc.inc

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0x9FF90000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Xiaomi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"lmi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Redmi K30 Pro Zoom Edition"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"lmi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"lmi"

  #
  # Simple Frame Buffer
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1080
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2400
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|lmiPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|lmiPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

  #
  # UniXNU: libraries the shared drivers need. UniXNURamDiskDxe reads the Mu-Silicium
  # FDT handoff through FdtLib and publishes a block device through HobLib.
  #
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
  UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf

#
# UniXNU modules. The paths resolve through the firmware PACKAGES_PATH entries:
# UniXNUPkg comes from the UniXNU build tree's package/, DarwinBootPkg from its
# drivers/DarwinBoot. They are added on top of the KonaPkg/QcomPkg component list.
#
[Components]
  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  DarwinBootPkg/Driver/DarwinBoot.inf

# DXE-only Advanced Logger: allocation and protocol publication happen in DXE
# Core. SEC keeps the upstream framebuffer serial implementation. No file logger.
[LibraryClasses.common.DXE_CORE,LibraryClasses.common.DXE_DRIVER,LibraryClasses.common.UEFI_DRIVER,LibraryClasses.common.UEFI_APPLICATION,LibraryClasses.common.DXE_RUNTIME_DRIVER]
  DebugLib|AdvLoggerPkg/Library/BaseDebugLibAdvancedLogger/BaseDebugLibAdvancedLogger.inf
  AssertLib|AdvLoggerPkg/Library/AssertLib/AssertLib.inf
  AdvancedLoggerHdwPortLib|AdvLoggerPkg/Library/AdvancedLoggerHdwPortLib/AdvancedLoggerHdwPortLib.inf
  AdvancedLoggerAccessLib|AdvLoggerPkg/Library/AdvancedLoggerAccessLib/AdvancedLoggerAccessLib.inf
  QrEncoderLib|MsGraphicsPkg/Library/QrEncoderLib/QrEncoderLib.inf

[LibraryClasses.common.DXE_CORE]
  AdvancedLoggerLib|AdvLoggerPkg/Library/AdvancedLoggerLib/DxeCore/AdvancedLoggerLib.inf

[LibraryClasses.common.DXE_DRIVER,LibraryClasses.common.UEFI_DRIVER,LibraryClasses.common.UEFI_APPLICATION]
  AdvancedLoggerLib|AdvLoggerPkg/Library/AdvancedLoggerLib/Dxe/AdvancedLoggerLib.inf

[LibraryClasses.common.DXE_RUNTIME_DRIVER]
  AdvancedLoggerLib|AdvLoggerPkg/Library/AdvancedLoggerLib/Runtime/AdvancedLoggerLib.inf

[PcdsFixedAtBuild]
  gUniXNUPkgTokenSpaceGuid.PcdUniXNUDeviceModel|"lmipro"
  gAdvLoggerPkgTokenSpaceGuid.PcdAdvancedLoggerPages|256

[PcdsFeatureFlag]
  gAdvLoggerPkgTokenSpaceGuid.PcdAdvancedLoggerFixedInRAM|FALSE
  gAdvLoggerPkgTokenSpaceGuid.PcdAdvancedLoggerLocator|FALSE

[Components]
  UniXNUPkg/Driver/AdvancedLogDxe/AdvancedLogDxe.inf
  !include Include/VendorComponents.inc
