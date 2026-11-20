#!/usr/bin/env python3
"""Create owner-encrypted Android boot v4 image using pinned encrypted evidence. No flashing."""
import argparse, base64, gzip, hashlib, io, json, os, struct, zipfile, zlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

FD_HASH = "422afec91c1c8c8aeb0d3df386ae21ab225855137fce9e7e43b7ddc76ebe2a3f"
FAT_HASH = "b72d0d0aeca573bd6708bd9bc40bde9dd06c12a1b76a3c3f5b460c2f26e128e9"
AAD = b"houji-xnu-entry-probe/bootimg-v4"
def sha(b): return hashlib.sha256(b).hexdigest()
def decrypt(path, key, associated):
    b=path.read_bytes()
    if len(b)<29: raise ValueError("Truncated encrypted artifact")
    return AESGCM(key).decrypt(b[:12], b[12:], associated)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact-dir",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--recipient-public-key",required=True)
    a=p.parse_args()
    if len(a.recipient_public_key)!=64: raise ValueError("Invalid recipient public key")
    vendor=os.environ.get("HOUJI_VENDOR_BUNDLE")
    payload_key=os.environ.get("HOUJI_ARTIFACT_KEY")
    if not vendor or not payload_key: raise ValueError("Missing Actions Secrets, no output")
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(vendor,validate=True))) as v:
        fw_key=v.read("artifact.key")
    pl_key=base64.b64decode(payload_key,validate=True)
    if len(fw_key)!=32 or len(pl_key)!=32: raise ValueError("Unexpected AES key size")
    folder=a.artifact_dir
    firmware=json.loads((folder/"firmware.json").read_text())
    receipt=json.loads((folder/"probe-payload.json").read_text())
    if firmware["SILICIUM_UEFI.fd"]["sha256"]!=FD_HASH or receipt["sha256"]!=FAT_HASH or receipt["crc32"]!="d9b41eb8":
        raise ValueError("This is not the pinned run 44673296323")
    if receipt["entry_probe"]!="entry and pre-MMU, no reset":
        raise ValueError("Unexpected kernel probe")
    fd=decrypt(folder/"SILICIUM_UEFI.fd.aesgcm",fw_key,b"SILICIUM_UEFI.fd")
    fat=decrypt(folder/"probe-payload.img.aesgcm",pl_key,b"payload.img")
    if len(fd)!=0x300000 or sha(fd)!=FD_HASH: raise ValueError("UEFI verification failed")
    if len(fat)!=0x4000000 or sha(fat)!=FAT_HASH or fat[71:90]!=b"HOUJIESP   FAT32   ":
        raise ValueError("RAM payload verification failed")
    if zlib.crc32(fat)&0xffffffff != int(receipt["crc32"],16):
        raise ValueError("Payload CRC mismatch")
    # Preserve the successful first-entry image's 112 bytes of 0xff and zero padding.
    raw=fd+b"\xff"*112+b"\x00"*(4096-112)+fat
    gz=gzip.compress(raw,compresslevel=9,mtime=0)
    h=bytearray(4096);h[:8]=b"ANDROID!"
    struct.pack_into("<I",h,8,len(gz))
    struct.pack_into("<I",h,20,1584)
    struct.pack_into("<I",h,40,4)
    boot=bytes(h)+gz+b"\x00"*((-len(gz))%4096)
    if gzip.decompress(boot[4096:4096+len(gz)])!=raw: raise ValueError("Boot roundtrip failed")
    pub=X25519PublicKey.from_public_bytes(bytes.fromhex(a.recipient_public_key))
    ephemeral=X25519PrivateKey.generate()
    ephemeral_bytes=ephemeral.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=AAD).derive(ephemeral.exchange(pub))
    nonce=os.urandom(12)
    encrypted=b"HJBENCR1"+ephemeral_bytes+nonce+AESGCM(key).encrypt(nonce,boot,AAD)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/"houji-xnu-entry-probe.img.enc").write_bytes(encrypted)
    result={"boot_sha256":sha(boot),"boot_size":len(boot),"cipher_sha256":sha(encrypted),
            "uefi_sha256":sha(fd),"fat_sha256":sha(fat),"fat_crc32":receipt["crc32"],
            "source_run":44673296323,"device":"houji","header_version":4,
            "warning":"Hardware boot not tested. No device operations performed."}
    (a.outdir/"receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS encrypted delivery, no plaintext boot written",result["boot_sha256"])
if __name__=="__main__": main()
