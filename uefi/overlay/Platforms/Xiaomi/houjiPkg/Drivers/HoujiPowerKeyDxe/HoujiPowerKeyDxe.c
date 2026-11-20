// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>

#include <Library/DebugLib.h>
#include <Library/IoLib.h>
#include <Library/TimerLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/EfiKeypadDevice.h>

#include <Configuration/BootDevices.h>

#ifndef SCAN_SUSPEND
#define SCAN_SUSPEND  0x0102
#endif

//
// houji stock vendor DT describes SPMI bus 0, EE 0. These windows
// are already mapped as Device memory by the platform AOSS descriptor.
// The stock overlay places the PMK8550 PON HLOS block at SID 0, 0x1300.
//
#define SPMI_CORE_BASE         0x0C400000U
#define SPMI_CNFG_BASE         0x0C42D000U
#define SPMI_OBSERVER_BASE     0x0C440000U
#define SPMI_V7_MIN            0x70000000U
#define SPMI_V8_MIN            0x80000000U
#define SPMI_FEATURES_OFFSET   0x04U
#define SPMI_APID_MAP_OFFSET   0x2000U
#define SPMI_V7_APID_LIMIT     1024U
#define SPMI_APID_COUNT_MASK   0x7FFU
#define SPMI_PPID_MASK         0xFFFU
#define SPMI_OWNER_MASK        0x07U
#define SPMI_APPS_EE           0U
#define SPMI_OBSERVER_STRIDE   0x20U
#define SPMI_READ_BYTE         (1U << 27)
#define SPMI_STATUS_OFFSET     0x08U
#define SPMI_RDATA_OFFSET      0x18U
#define SPMI_STATUS_ERRORS     (BIT1 | BIT2 | BIT3)
#define SPMI_TIMEOUT_US        1000U

#define PON_PPID               0x013U
#define PON_SUBTYPE_OFFSET     0x05U
#define PON_HLOS_SUBTYPE       0x09U
#define PON_RT_STS_OFFSET      0x10U
#define PON_POWER_PRESSED      BIT7
#define POWER_KEY_DEBOUNCE_NS  15000000ULL

STATIC UINTN    mObserver;
STATIC BOOLEAN  mArmed;
STATIC BOOLEAN  mLastSamplePressed;
STATIC UINT64   mStableNanoseconds;

STATIC
EFI_STATUS
FindPonObserver (
  OUT UINTN  *Observer
  )
{
  UINT32  Version;
  UINT32  Count;
  UINTN   Apid;
  UINTN   Match;
  UINTN   AppsMatch;
  UINTN   Matches;
  UINTN   AppsMatches;

  Version = MmioRead32 (SPMI_CORE_BASE);
  if ((Version < SPMI_V7_MIN) || (Version >= SPMI_V8_MIN)) {
    return EFI_UNSUPPORTED;
  }

  Count = MmioRead32 (SPMI_CORE_BASE + SPMI_FEATURES_OFFSET) & SPMI_APID_COUNT_MASK;
  if ((Count == 0) || (Count > SPMI_V7_APID_LIMIT)) {
    return EFI_UNSUPPORTED;
  }

  Match       = 0;
  AppsMatch   = 0;
  Matches     = 0;
  AppsMatches = 0;
  for (Apid = 0; Apid < Count; Apid++) {
    if (((MmioRead32 (SPMI_CORE_BASE + SPMI_APID_MAP_OFFSET + sizeof (UINT32) * Apid) >> 8) &
         SPMI_PPID_MASK) != PON_PPID) {
      continue;
    }

    Match = Apid;
    Matches++;
    if ((MmioRead32 (SPMI_CNFG_BASE + sizeof (UINT32) * Apid) & SPMI_OWNER_MASK) == SPMI_APPS_EE) {
      AppsMatch = Apid;
      AppsMatches++;
    }
  }

  if (AppsMatches == 1) {
    Match = AppsMatch;
  } else if (Matches != 1) {
    return EFI_NOT_FOUND;
  }

  *Observer = SPMI_OBSERVER_BASE + SPMI_OBSERVER_STRIDE * Match;
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
ReadPonByte (
  IN  UINTN  Observer,
  IN  UINT8  Register,
  OUT UINT8  *Value
  )
{
  UINT32  Status;
  UINTN   Wait;

  // The command register starts a one-byte read. No PMIC writes are issued.
  MmioWrite32 (Observer, SPMI_READ_BYTE | ((UINT32)Register << 4));
  for (Wait = 0; Wait < SPMI_TIMEOUT_US; Wait++) {
    Status = MmioRead32 (Observer + SPMI_STATUS_OFFSET);
    if ((Status & BIT0) != 0) {
      if ((Status & SPMI_STATUS_ERRORS) != 0) {
        return EFI_DEVICE_ERROR;
      }

      *Value = (UINT8)MmioRead32 (Observer + SPMI_RDATA_OFFSET);
      return EFI_SUCCESS;
    }

    MicroSecondDelay (1);
  }

  return EFI_TIMEOUT;
}

STATIC
EFI_STATUS
EFIAPI
ResetPowerKey (
  IN KEYPAD_DEVICE_PROTOCOL  *This
  )
{
  // Require a stable release after reset, even when Power is already held.
  mArmed             = FALSE;
  mLastSamplePressed = TRUE;
  mStableNanoseconds = 0;
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
GetPowerKey (
  IN KEYPAD_DEVICE_PROTOCOL  *This,
  IN KEYPAD_RETURN_API       *ReturnApi,
  IN UINT64                  Delta
  )
{
  EFI_STATUS    Status;
  UINT8         Value;
  BOOLEAN       Pressed;
  EFI_KEY_DATA  Key = { { SCAN_SUSPEND, 0 }, { 0, 0 } };

  if (mObserver == 0) {
    return EFI_NOT_READY;
  }

  Status = ReadPonByte (mObserver, PON_RT_STS_OFFSET, &Value);
  if (EFI_ERROR (Status)) {
    // A timed-out command might still be pending in the observer channel.
    mObserver = 0;
    DEBUG ((DEBUG_WARN, "houji power key: observer read stopped (%r)\n", Status));
    return Status;
  }

  Pressed = (Value & PON_POWER_PRESSED) != 0;
  if (Pressed != mLastSamplePressed) {
    mLastSamplePressed = Pressed;
    mStableNanoseconds = 0;
    return EFI_SUCCESS;
  }

  if (mStableNanoseconds < POWER_KEY_DEBOUNCE_NS) {
    if (Delta < POWER_KEY_DEBOUNCE_NS - mStableNanoseconds) {
      mStableNanoseconds += Delta;
      return EFI_SUCCESS;
    }

    mStableNanoseconds = POWER_KEY_DEBOUNCE_NS;
    if (Pressed && mArmed) {
      ReturnApi->PushEfikeyBufTail (ReturnApi, &Key);
    }

    mArmed = !Pressed;
  }

  return EFI_SUCCESS;
}

STATIC KEYPAD_DEVICE_PROTOCOL mPowerKey = {
  ResetPowerKey,
  GetPowerKey
};

EFI_STATUS
EFIAPI
InitializeHoujiPowerKey (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  UINTN       Observer;
  UINT8       Value;

  Status = FindPonObserver (&Observer);
  if (!EFI_ERROR (Status)) {
    Status = ReadPonByte (Observer, PON_SUBTYPE_OFFSET, &Value);
    if (!EFI_ERROR (Status) && (Value != PON_HLOS_SUBTYPE)) {
      Status = EFI_UNSUPPORTED;
    }
  }

  if (!EFI_ERROR (Status)) {
    Status = ReadPonByte (Observer, PON_RT_STS_OFFSET, &Value);
  }

  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "houji power key: observer unavailable (%r)\n", Status));
    return Status;
  }

  mObserver = Observer;
  ResetPowerKey (&mPowerKey);
  return gBS->InstallMultipleProtocolInterfaces (
                &ImageHandle,
                &gKeypadDeviceProtocolGuid,
                &mPowerKey,
                &gEfiDevicePathProtocolGuid,
                &KeypadDevicePath,
                NULL
                );
}
