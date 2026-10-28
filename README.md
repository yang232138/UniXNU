# Redmi K30 Pro Zoom Edition (lmipro)

Configuration baseline following [the UniXNU porting procedure](https://unixnu.com/zh/porting/steps).
This branch does not carry the previous experimental firmware patch script. Concrete kernel inputs have been reviewed and `board.example = false` permits the documented kernel/package host checks. Firmware integration, peripheral services and payload inputs remain incomplete; this does not authorize a phone image to be called validated.

## Current evidence

The connected device reports lmipro, kona, Android 12 / MIUI V14.0.4.0.SJKCNXM, 8 GiB class RAM, and fastboot product lmi. Sanitized measured hardware and original partition backup hashes are in `evidence/`. Full backups stay local. Native CPU boot, storage, display, input, GPU and system userspace are not device-verified.

The draft XNU DTS selects one boot CPU and a conservative measured contiguous 3 GiB RAM window. It is not the Android firmware DTB. The iPadOS 17.7.11 profile is a build target and does not certify iPadOS works on this phone.

## Documented configuration checks

Run inside the pinned UniXNU source checkout:

```sh
./unixnu defconfig lmipro_defconfig -D ../device
./unixnu fetch -D ../device
./unixnu status --json -D ../device
./unixnu tree -D ../device
python3 scripts/porting-record.py check --device ../device
```

Review the resolved components, source pins and patch order; commit the generated `unixnu.lock`. Complete the firmware DSC/FDF and logging review, hardware handoff and required external payload inputs before building or testing a phone image. Subsequent stages follow `build kernel`, `build package`, `build firmware`, `build payload`, `bootimg`, with separate device evidence for every checkpoint.

## Kernel and package CI

The macOS job follows the pinned upstream build commands and selected profile. It checks Xcode and the iPhoneOS SDK, resolves sources, fetches the profile IPSW members, builds the prelinked kernel, then builds the EFI package. It publishes text logs only, following the upstream macOS workflow. No firmware, payload or device boot is attempted by this job.

## Independent UEFI build

The firmware job follows the [UEFI guide](https://unixnu.com/zh/porting/uefi-firmware) using the pinned public lmi board overlay, target stock XBL, and DXE Advanced Logger/QR export. See firmware/README.md. It runs build package followed by build firmware; XNU compilation is a separate checkpoint. The current kernel run 40665400238 failed before compilation because the upstream zzz-boot-progress.patch does not apply to bsd_init.c. No kernel or phone boot success is claimed.
