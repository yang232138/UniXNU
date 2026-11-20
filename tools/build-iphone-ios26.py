#!/usr/bin/env python3
"""Configure or build the iPhone iOS 26 native kernel on pinned UniXNU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "targets/ios-26.6.2-23G90"


def command(*args, cwd=None, capture=False, env=None):
    return subprocess.run(
        [str(arg) for arg in args], cwd=cwd, check=True, env=env,
        text=True, stdout=subprocess.PIPE if capture else None,
    ).stdout


def build_release_reference(unixnu, work, output, board, build_env):
    tree = work / "tree"
    records = tree / "build/xnu/fileset-reference"
    reference = records / "mach.release.bcm2837.unstripped.noctf"
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    os_profile = board["os"]
    versions = {
        "UNIXNU_IOS_VERSION": os_profile["ios_version"],
        "UNIXNU_XNU_DARWIN": os_profile["darwin"],
        "UNIXNU_XNU_VERSION": os_profile["xnu_version"],
    }
    env = dict(build_env, UNIXNU_XNU_TARGET=os_profile["target"], **versions)
    try:
        command(sys.executable, unixnu / "scripts/build-fileset-release-reference.py",
                "--tree", tree, "--lto", cwd=tree, env=env)
    finally:
        for directory in sorted(records.glob("lto-*")):
            for name in ("inputs.json", "lto-command.json", "lto-build.log"):
                record = directory / name
                if record.is_file():
                    shutil.copy2(record, evidence / f"reference-{directory.name}-{name}")

    receipt_path = reference.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    if (receipt["sha256"] != digest or receipt["inputs"]["mode"] != "lto"
            or receipt["inputs"]["target"] != os_profile["target"] or receipt["inputs"]["versions"] != versions):
        raise SystemExit("The RELEASE reference output differs from its build receipt")
    shutil.copy2(receipt_path, evidence / "apfs-release-reference.json")
    return reference


def audit_apfs(unixnu, output, board, kernel, reference=None):
    sys.path.insert(0, str(unixnu / "scripts"))
    prelink_source = unixnu / "kits/XnuPrelink"
    sys.path.insert(0, str(prelink_source))
    from unixnu.ipsw import Ipsw, im4p_payload
    from fileset_emit import dependency_closure
    from fileset_layout import split_references
    from kc_image import Image

    native_bytes = kernel.read_bytes()
    native = Image(native_bytes)
    if native.command(0x80000034) is None:
        raise SystemExit("The APFS audit input lacks LC_DYLD_CHAINED_FIXUPS")
    split_count = sum(1 for _ in split_references(native))
    if not split_count:
        raise SystemExit("The APFS audit input has an empty split-segment relocation table")

    source = Ipsw(SimpleNamespace(board=board, out_root=output), board["ipsw"]["url"])
    donor_member = source.extract("KernelCache")
    root = "com.apple.filesystems.apfs"
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="iphone26-apfs-", dir=output) as stage:
        stage = Path(stage)
        prelink = stage / "XnuPrelink"
        shutil.copytree(prelink_source, prelink, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        reviewed_path = TARGET / "fileset-23G90-symbols.json"
        reviewed_bytes = reviewed_path.read_bytes()
        (prelink / "fixtures" / reviewed_path.name).write_bytes(reviewed_bytes)
        reviewed = json.loads(reviewed_bytes)
        packed, donor = stage / "kernelcache.lzfse", stage / "kernelcache.macho"
        packed.write_bytes(im4p_payload(donor_member.read_bytes()))
        command("/usr/bin/compression_tool", "-decode", "-a", "lzfse", "-i", packed, "-o", donor)
        donor_bytes = donor.read_bytes()
        donor_digest = hashlib.sha256(donor_bytes).hexdigest()
        magic, cpu, subtype, kind = struct.unpack_from("<IIII", donor_bytes)
        if (donor_digest != "a17cd978b8c20c5a1099d2bbd5a142e5cbc80f36fc85a6676d4b7fa9ea7d6165"
                or (magic, cpu, subtype & 0xff, kind) != (0xfeedfacf, 0x0100000c, 2, 12)):
            raise SystemExit("The decompressed donor differs from the pinned iPhone arm64e fileset")
        if reviewed["inputs"]["kernelcache_sha256"] != donor_digest:
            raise SystemExit("Reviewed APFS symbols belong to another kernelcache")
        closure = sorted(dependency_closure(Image(donor_bytes), [root]))
        receipt = {
            "iphone": board["ipsw"]["product"],
            "build": board["ipsw"]["build"],
            "donor_sha256": donor_digest,
            "native_sha256": hashlib.sha256(native_bytes).hexdigest(),
            "split_segment_records": split_count,
            "root": root,
            "closure": closure,
            "reviewed_symbols_sha256": hashlib.sha256(reviewed_bytes).hexdigest(),
            "reviewed_symbol_count": len(reviewed["functions"]),
            "runtime_verified": False,
        }
        print(f"Fileset input: {split_count} split-segment records. APFS closure: {len(closure)} entries.", flush=True)
        candidate = stage / "candidate.macho"
        reference_args = []
        if reference is not None:
            receipt["reference_sha256"] = hashlib.sha256(reference.read_bytes()).hexdigest()
            reference_args = ["--fileset-reference", reference]
        try:
            command(sys.executable, prelink / "emit_prelink.py", "--kernel", kernel,
                    "--prelinked", donor, "--root", root, "--slide", "0", "--output", candidate,
                    *reference_args)
        finally:
            for suffix, filename in ((".json", "apfs-prelink.json"), (".map.json", "apfs-pairing.json")):
                report = candidate.with_suffix(suffix)
                if report.is_file():
                    shutil.copy2(report, evidence / filename)
            pairing_report = candidate.with_suffix(".map.json")
            if pairing_report.is_file():
                functions = json.loads(pairing_report.read_text(encoding="utf-8"))["functions"]
                receipt["reviewed_symbols_unbound"] = [
                    entry["native_symbol"] for entry in reviewed["functions"]
                    if functions.get(entry["original"], {}).get("how") != "reviewed"
                ]
            if candidate.is_file():
                receipt["candidate_sha256"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
            (evidence / "apfs-inputs.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu", type=Path, required=True, help="Separate UniXNU checkout at the locked commit")
    parser.add_argument("--output", type=Path, required=True, help="Separate build output directory")
    parser.add_argument("--check", action="store_true", help="Resolve the profile and defconfig offline")
    parser.add_argument("--apfs-audit", action="store_true",
                        help="Build chained-fixup XNU and run strict APFS prelink without packaging a boot image")
    parser.add_argument("--apfs-reference", action="store_true",
                        help="Build and use an isolated same-profile RELEASE LTO reference for the APFS audit")
    args = parser.parse_args()
    if args.apfs_reference and not args.apfs_audit:
        parser.error("--apfs-reference requires --apfs-audit")

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

    build_env = dict(os.environ, XNU_KERNEL_CHAINED_FIXUPS="1") if args.apfs_audit else None
    command("git", "submodule", "update", "--init", "drivers/ArmCpu", cwd=unixnu)
    with tempfile.TemporaryDirectory(prefix="iphone26-armcpu-") as temporary:
        armcpu = Path(temporary) / "ArmCpu"
        shutil.copytree(unixnu / "drivers" / "ArmCpu", armcpu, ignore=shutil.ignore_patterns(".git"))
        command("git", "apply", "--no-index", TARGET / "armcpu-no-suspend.patch", cwd=armcpu)
        command(
            *base, "build", "kernel", "--skip-prelink", *options,
            "--local-module", f"driver:ArmCpu={armcpu}", cwd=unixnu, env=build_env,
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
    if args.apfs_audit:
        reference = build_release_reference(unixnu, work, output, board, build_env) if args.apfs_reference else None
        audit_apfs(unixnu, output, board, kernel, reference=reference)


if __name__ == "__main__":
    main()
