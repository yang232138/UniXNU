# K30 Pro fresh port — 2026-10-28

Fresh start from https://unixnu.com/zh/porting/steps. No previous local port was inspected or reused.

Measured today through the connected phone: Android product lmipro, Redmi K30 Pro Zoom Edition; fastboot product lmi; unlocked yes; kona; Android 12 / V14.0.4.0.SJKCNXM; MemTotal 7795796 kB. No root and stock recovery: full live DT and raw partition reads are denied.

This branch deliberately starts with a standalone AArch64 UniXNU package build from pinned current upstream. Its EFI outputs are components, not an Android boot image. Device firmware, memory reservations, firmware DTB, and XNU drivers still need measured inputs and integration. No boot, recovery, dtbo, userdata or partition-table writes have been performed.

Next: obtain boot/DTBO/XBL from matching official Xiaomi ROM, verify board-specific hardware descriptions, adapt Mu-Silicium firmware and integrate UniXNU/DarwinBoot/RAM-disk/FAT/logging. Validate a temporary fastboot boot before any installation.
