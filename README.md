# Redmi K30 Pro Zoom Edition (lmipro)

Configuration baseline following [the UniXNU porting procedure](https://unixnu.com/zh/porting/steps).
This branch does not carry the previous experimental firmware patch script. `board.example = true` is retained because firmware integration, peripheral services and OS inputs remain incomplete.

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

Review the resolved components, source pins and patch order; commit the generated `unixnu.lock`. Complete the firmware DSC/FDF and logging review, the hardware descriptions and required external OS inputs before removing the example guard. Subsequent stages follow `build kernel`, `build package`, `build firmware`, `build payload`, `bootimg`, with separate device evidence for every checkpoint.
