#!/usr/bin/env python3
"""Configure or build the iPhone iOS 26 native kernel on pinned UniXNU."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "targets/ios-26.6.2-23G90"


def command(*args, cwd=None, capture=False):
    return subprocess.run(
        [str(arg) for arg in args], cwd=cwd, check=True,
        text=True, stdout=subprocess.PIPE if capture else None,
    ).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu", type=Path, required=True, help="Separate UniXNU checkout at the locked commit")
    parser.add_argument("--output", type=Path, required=True, help="Separate build output directory")
    parser.add_argument("--check", action="store_true", help="Resolve the profile and defconfig offline")
    args = parser.parse_args()

    pin = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))["iphone_ios26"]
    unixnu = args.unixnu.resolve()
    if command("git", "rev-parse", "HEAD", cwd=unixnu, capture=True).strip() != pin["unixnu_revision"]:
        parser.error("UniXNU checkout differs from sources.lock.json")
    if command("git", "diff", "HEAD", "--name-only", cwd=unixnu, capture=True).strip():
        parser.error("Use a separate UniXNU checkout with the pinned sources")
    staged = unixnu / "profiles" / "os" / TARGET.name / "profile.toml"
    profile = (TARGET / "profile.toml").read_bytes()
    staged.parent.mkdir(exist_ok=True)
    if staged.exists() and staged.read_bytes() != profile:
        parser.error(f"Conflicting profile at {staged}")
    staged.write_bytes(profile)

    output = args.output.resolve()
    base = [sys.executable, unixnu / "unixnu"]
    options = ["--device", TARGET, "--out", output, "--os", TARGET.name]
    config = tomllib.loads((TARGET / "board.toml").read_text(encoding="utf-8"))["kernel"]["defconfig"]
    # Keep CLI commands in the UniXNU checkout so its existing local options work as designed.
    command(*base, "defconfig", config, *options, cwd=unixnu)
    status = command(*base, "status", "--json", *options, cwd=unixnu, capture=True)
    resolved = json.loads(status)
    board = resolved["board"]
    ipsw = board["ipsw"]
    if (ipsw["product"], ipsw["build"], board["os"]["arch"], board["arch"]["page_size"]) != (
        "iPhone18,1", "23G90", "arm64e", 4096,
    ):
        parser.error("Unexpected OS, donor or kernel architecture")
    work = Path(resolved["output"])
    (output / "resolved-profile.json").write_text(status, encoding="utf-8")
    print(f"Resolved {ipsw['product']} iOS {ipsw['version']} ({ipsw['build']}), arm64e / 4 KiB", flush=True)
    if args.check:
        return
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        parser.error("This build needs an Apple Silicon macOS host with Xcode and the iPhoneOS SDK")

    command("git", "submodule", "update", "--init", "drivers/ArmCpu", cwd=unixnu)
    with tempfile.TemporaryDirectory(prefix="iphone26-armcpu-") as temporary:
        armcpu = Path(temporary) / "ArmCpu"
        shutil.copytree(unixnu / "drivers" / "ArmCpu", armcpu, ignore=shutil.ignore_patterns(".git"))
        command("git", "apply", "--no-index", TARGET / "armcpu-no-suspend.patch", cwd=armcpu)
        command(
            *base, "build", "kernel", "--skip-prelink", *options,
            "--local-module", f"driver:ArmCpu={armcpu}", cwd=unixnu,
        )
    kernel = work / "kernel" / "kernel.macho"
    data = kernel.read_bytes()
    magic, cpu, subtype, filetype = struct.unpack_from("<IIII", data)
    if (magic, cpu, subtype & 0xffffff, filetype) != (0xfeedfacf, 0x0100000c, 2, 2):
        parser.error("Kernel output must be an arm64e MH_EXECUTE")
    receipt = json.loads(kernel.with_suffix(".json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(data).hexdigest()
    if receipt["mode"] != "native-only" or receipt["candidate_sha256"] != digest:
        parser.error("UniXNU native kernel receipt does not match the output")
    command("file", kernel)
    print(f"arm64e MH_EXECUTE sha256 {digest}", flush=True)


if __name__ == "__main__":
    main()
