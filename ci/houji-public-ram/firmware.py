"""Stage only the exact firmware bytes pinned by the houji source profile."""
import base64
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zlib


base = Path(os.environ["RUNNER_TEMP"]) / "houji-public-ram"
firmware = base / "firmware"
firmware.mkdir()
revision = "07b822cc556d2053838a0687b62d1dca15cad9b6"
upstream = f"https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/{revision}/qcom"
for name in ("gmu_gen70900.bin", "gen70900_aqe.fw"):
    with urllib.request.urlopen(f"{upstream}/{name}?format=TEXT", timeout=30) as response:
        (firmware / name).write_bytes(base64.b64decode(response.read(200_000), validate=True))

sqe = os.environ["HOUJI_SQE_A"] + os.environ["HOUJI_SQE_B"]
if not os.environ["HOUJI_SQE_A"] or not os.environ["HOUJI_SQE_B"]:
    raise SystemExit("Missing pinned host-only SQE input")
(firmware / "gen70900_sqe.fw").write_bytes(zlib.decompress(base64.b64decode(sqe, validate=True)))
subprocess.run([
    sys.executable, str(base / "houji/tools/make-firmware-headers.py"),
    "--gmu", str(firmware / "gmu_gen70900.bin"), "--sqe", str(firmware / "gen70900_sqe.fw"),
    "--aqe", str(firmware / "gen70900_aqe.fw"),
    "--output", str(base / "xnu/iokit/Kernel/houji-ufs-root"),
], check=True)
print("PASS: generated kernel firmware headers from all three pinned SHA-256 inputs")
