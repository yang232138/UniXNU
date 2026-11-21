"""Keep compiled images encrypted while publishing exact build hashes."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


base = Path(os.environ["RUNNER_TEMP"]) / "houji-public-ram"
paths = [base / "xnu/BUILD/obj/mach.development.houji", base / "hello.macho"]
hashes = {}
archive = io.BytesIO()
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
    for path in paths:
        data = path.read_bytes()
        hashes[path.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        zipped.writestr(path.name, data)

nonce = secrets.token_bytes(12)
key = bytes.fromhex(os.environ["HOUJI_ARTIFACT_SECRET"])
sealed = nonce + AESGCM(key).encrypt(nonce, archive.getvalue(), b"houji-public-23g90-ram-v1")
Path("evidence/compiled.zip.aesgcm").write_bytes(sealed)
report = {
    "workflow_commit": os.environ["GITHUB_SHA"],
    "public_commit": os.environ["HOUJI_PUBLIC_REVISION"],
    "scope": "linked RAM-only XNU and static PID1",
    "firmware_image_built": False,
    "physical_device_accessed": False,
    "files": hashes,
    "archive_sha256": hashlib.sha256(sealed).hexdigest(),
}
Path("evidence/build.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
# Symbolset fix rebuild.
