#!/usr/bin/env bash
set -euo pipefail
ROOT=$(pwd)
mkdir -p results
git init upstream
git -C upstream remote add origin https://github.com/UniXNU/UniXNU.git
git -C upstream fetch --depth 1 origin 120067ccc43ebb5e76ec62c9219a48c897052838
git -C upstream checkout --detach FETCH_HEAD
git init mu
git -C mu remote add origin https://github.com/Project-Silicium/Mu-Silicium.git
git -C mu fetch --depth 1 origin 4cba43c90e02cdbefbcd9fcdbda33d2328deaec0
git -C mu checkout --detach FETCH_HEAD
git -C mu submodule update --init --depth 1 Common/Mu Common/Mu_OEM_Sample
UNIXNU_SOURCE="$ROOT/upstream" STOCK_OUTPUT="$ROOT/stock-inputs" XBL_ONLY=1 python3 ci/extract-stock.py
python3 ci/stage-firmware.py --mu mu --xbl stock-inputs/xbl_4.elf
cd upstream
./unixnu defconfig lmipro_uefi_defconfig -D "$ROOT/device"
./unixnu build firmware -D "$ROOT/device" --uefi "$ROOT/mu" 2>&1 | tee "$ROOT/results/firmware.log"
cp "$ROOT/mu/Build/lmiproPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" "$ROOT/results/"
cp "$ROOT/mu/lmipro-input-manifest.json" "$ROOT/results/"
find out -name unixnu.lock -exec cp {} "$ROOT/results/" \;
sha256sum "$ROOT/results/SILICIUM_UEFI.fd" > "$ROOT/results/SHA256SUMS"
