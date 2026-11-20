#!/usr/bin/env python3
"""Reuse the verified first-entry FAT volume with UniXNU's entry probes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import tomllib
import zlib


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def add_arm_init_marker(kernel, scripts, stage):
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("entry_probe", scripts / "patch-xnu-entry-probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    image = bytearray(kernel.read_bytes())
    probe.load_segments(image)
    entry = probe.unixthread_pc(image)
    arm_init, = (address for address, symbol in probe.kernel_symbols(kernel).items() if symbol == "_arm_init")
    if (entry, arm_init) != (0xfffffff007521488, 0xfffffff007be25a4):
        raise SystemExit("The arm_init marker is pinned to the verified houji kernel layout")
    site = probe.file_offset(arm_init)
    if struct.unpack_from("<I", image, site)[0] != 0xd503237f:
        raise SystemExit("The arm_init prologue no longer begins with the expected PACIBSP")
    source = Path(__file__).resolve().parents[1] / "targets/ios-26.6.2-23G90/arm-init-marker.S"
    cave = entry + 0x138
    data = probe.assemble(source.read_text(), cave, {"resume": arm_init + 4}, stage)
    start = probe.file_offset(cave)
    if not 0 < len(data) <= 0xc0 or any(image[start:start + 0xc0]):
        raise SystemExit("The arm_init marker does not fit unused kernel entry padding")
    image[start:start + len(data)] = data
    struct.pack_into("<I", image, site, probe.branch(arm_init, cave))
    kernel.write_bytes(image)
    print("Added a non-restarting framebuffer marker at arm_init")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True, help="Disposable copy of the verified FAT volume")
    parser.add_argument("--post-mmu-reset", action="store_true", help="Reset six seconds after MMU enable")
    parser.add_argument("--arm-init-marker", action="store_true", help="Draw one screen marker at arm_init")
    args = parser.parse_args()
    if args.post_mmu_reset and args.arm_init_marker:
        parser.error("The arm_init marker requires no post-MMU reset")
    payload_record = args.payload.with_suffix(".json")
    record = json.loads(payload_record.read_text())
    original = args.payload.read_bytes()
    if (sha256(original) != record["sha256"] or not record["contains_xnu"]
            or len(original) != 0x4000000 or original[71:90] != b"HOUJIESP   FAT32   "):
        parser.error("Input differs from the verified houji first-entry FAT volume")
    env = dict(os.environ, UNIXNU_XNU_ARCH="arm64e", UNIXNU_IOS_VERSION="26.0")

    with tempfile.TemporaryDirectory(dir=args.payload.parent) as directory:
        stage = Path(directory)
        kernel = stage / "kernel.macho"
        adt = stage / "kernel.macho.adt"
        config = stage / "unixnu.toml"
        candidate = stage / args.payload.name
        candidate.write_bytes(original)
        volume = "::/EFI/UniXNU/"
        for path, name in ((kernel, "Payloads/kernel.macho"), (adt, "Payloads/kernel.macho.adt"),
                           (config, "unixnu.toml")):
            subprocess.run(["mcopy", "-i", str(candidate), volume + name, str(path)], check=True)
        kernel_digest = sha256(kernel.read_bytes())
        if kernel_digest != record["kernel_sha256"] or sha256(adt.read_bytes()) != record["adt_sha256"]:
            parser.error("The FAT volume does not contain the recorded kernel and ADT")
        config_text = config.read_text()
        boot = tomllib.loads(config_text)
        if boot["boot"] != {"default": "xnu", "timeout": 5} or boot["entry"][0]["id"] != "xnu":
            parser.error("The FAT volume does not have the qualified automatic menu")
        # On a console with no input, UniXNU uses its fallback rotation even
        # when rotate=0. A one-entry menu keeps the countdown without rotation.
        prefix, xnu_entry, _ = config_text.split("\n[[entry]]", 2)
        single_entry = prefix + "\n[[entry]]" + xnu_entry.rstrip() + "\n"
        if tomllib.loads(single_entry) != {**boot, "entry": boot["entry"][:1]}:
            parser.error("Could not preserve the original XNU boot entry")
        config.write_text(single_entry)
        scripts = args.unixnu / "scripts"
        reset_options = ["--reset-delay", "6"] if args.post_mmu_reset else ["--no-reset"]
        subprocess.run([sys.executable, str(scripts / "patch-xnu-entry-probe.py"), str(kernel), *reset_options],
                       env=env, check=True)
        if args.arm_init_marker:
            add_arm_init_marker(kernel, scripts, stage)
        subprocess.run([sys.executable, str(scripts / "seal-source-crypto-kernel.py"), str(kernel),
                        "--kernel-args", boot["entry"][0]["args"]], env=env, check=True)
        patched = kernel.read_bytes()
        patched_digest = sha256(patched)
        if patched_digest == kernel_digest:
            parser.error("The entry probe did not change the kernel")
        kernel_path = volume + "Payloads/kernel.macho"
        subprocess.run(["mcopy", "-o", "-i", str(candidate), str(kernel), kernel_path], check=True)
        subprocess.run(["mcopy", "-o", "-i", str(candidate), str(config), volume + "unixnu.toml"], check=True)
        readback = stage / "readback.macho"
        subprocess.run(["mcopy", "-i", str(candidate), kernel_path, str(readback)], check=True)
        if readback.read_bytes() != patched:
            parser.error("The probed kernel did not round-trip through FAT")
        menu_readback = stage / "readback.toml"
        subprocess.run(["mcopy", "-i", str(candidate), volume + "unixnu.toml", str(menu_readback)], check=True)
        if menu_readback.read_bytes() != config.read_bytes():
            parser.error("The one-entry menu did not round-trip through FAT")

        data = candidate.read_bytes()
        record.update(sha256=sha256(data), crc32=f"{zlib.crc32(data):08x}", kernel_sha256=patched_digest,
                      original_kernel_sha256=kernel_digest, entry_probe="entry and pre-MMU",
                      post_mmu_reset_seconds=6 if args.post_mmu_reset else None, menu_entries=["xnu"],
                      arm_init_marker=args.arm_init_marker)
        candidate.replace(args.payload)
        payload_record.write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
