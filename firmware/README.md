# Documented UEFI build

Reference: https://unixnu.com/zh/porting/uefi-firmware

The public board overlay is pinned at yang232138/uefi-lmipro
20e41895a8b24c9b2a32aa3b81947f45280d49f7. Only Platforms and Resources/Configs
source files are imported; the legacy workflow, binaries, XBL, DTB and BootShim
are not used. Upstream Mu-Silicium e51cd877e31c8fbb322032dc4cb6715e83d25ad3
provides the shared source and BootShim. Mu_Basecore is fixed by unixnu.lock.
Original file license headers remain in place.

The target XBL hash is checked before extraction. All referenced vendor PE and
DEPEX sections remain byte-identical, with a distinct path for every module.
Memory and numeric configuration come from that XBL uefiplat.cfg, replacing the
historical board map. No guessed free RAM, borrowed panel configuration, fixed
logger address or vendor binary patch is added. The DXE logger allocates a 1 MiB
reserved buffer through UEFI services; SEC logs still use the stock framebuffer.
LogFS syncing is disabled. QR export is provided by AdvancedLogDxe.

From the pinned UniXNU checkout, after assembling the Mu tree and running the
extract/prepare steps shown in .github/workflows/uefi.yml:

```sh
./unixnu defconfig lmipro_defconfig -D ../device
./unixnu build package firmware --uefi ../mu
```

This independent firmware job does not require a successful XNU compilation.
It publishes the FD, module hashes and text logs. A valid FD is not proof that
SCM/TZ, the menu or XNU works on this handset. Review runtime memory/TZ handoff
before packaging a fresh temporary-boot image; never send a raw FD to fastboot.

## Deliverable

The artifact now includes boot.img, boot.json and SHA256SUMS. It is an Android-v2 UEFI menu smoke-test image with an empty ramdisk, as allowed by the boot guide; it contains no XNU kernel or operating system. The firmware DTB is reconstructed from matching stock boot/DTBO input and its digest must match the independently extracted handset tree. The board adapter retains strict shim/FD and v2 DTB-section round-trip checks. No automatic flashing or device boot is performed by CI.

The boot/DTBO inputs in run 40671017967 match the handset backup hashes. Its Ubuntu libfdt 1.7.0 result differs only in six existing audio-node phandles, overwriting base references. Pin dtc/libfdt v1.8.1 at 8f48565e5cfedc74d3f7512f1e0188e9d85dc1de, matching the local tool and preserving base phandles via overlay_prevent_phandle_overwrite. Retain the original exact resulting-DTB hash guard. The two original tree inputs are reused from the hash-checked artifact of that run to avoid redownloading the whole boot/DTBO members.

Run 40677138940 built the FD. The reviewed inventory requires the 52 enabled vendor modules; CPRDxe and DisplayDxe must be absent under USE_CUSTOM_DISPLAY_DRIVER=0, with SimpleFbDxe present. ResetRuntimeDxe is now emitted in the FV as well as being listed in APRIORI. Vendor PE and DEPEX digests are checked in the final FV.
