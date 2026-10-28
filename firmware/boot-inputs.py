"""Prepare this handset's firmware DTB and strict v2 boot-image adapter.

The source boot/DTBO must be the selected MIUI build. The final DTB digest is
cross-checked against the independently extracted handset backup from this run.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import os
from pathlib import Path
import struct
import sys

EXPECTED_DTB_SHA = '405241b9ed29193145ec36e0c183aa6bc6ced547144e294519a1ffcfacd9d2d3'

def replace_once(text, old, new):
    assert text.count(old) == 1, f'pinned source changed: {old[:60]}'
    return text.replace(old, new, 1)

parser = argparse.ArgumentParser()
parser.add_argument('--boot', type=Path, required=True)
parser.add_argument('--dtbo', type=Path, required=True)
parser.add_argument('--unixnu', type=Path, required=True)
parser.add_argument('--mu', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.unixnu.resolve() / 'scripts'))
from unixnu.devicetree import read_fdt

out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
boot = args.boot.read_bytes()
assert boot[:8] == b'ANDROID!'
k, ka, r, ra, second, _, tags, page, version, _ = struct.unpack_from('<10I', boot, 8)
assert (ka, ra, tags, page, version) == (0x8000, 0x1000000, 0x100, 4096, 2)
dtb_size, dtb_addr = struct.unpack_from('<IQ', boot, 1648)
assert dtb_addr == 0x1f00000
recovery_dtbo_size = struct.unpack_from('<I', boot, 1632)[0]
align = lambda n: (n + page - 1) // page * page
start = page + align(k) + align(r) + align(second) + align(recovery_dtbo_size)
region = boot[start:start+dtb_size]
assert len(region) == dtb_size
bases = []
pos = 0
while pos < len(region):
    if region[pos:pos+4] != b'\xd0\x0d\xfe\xed':
        assert not region[pos:].strip(b'\0'), 'unexpected bytes between stock DTBs'
        break
    size = struct.unpack_from('>I', region, pos+4)[0]
    data = region[pos:pos+size]
    node = read_fdt(data)
    cells = node.cells('qcom,msm-id')
    if any(cells[i:i+2] == [0x164, 0x20001] for i in range(0, len(cells), 2)):
        bases.append(data)
    pos += size
assert len(bases) == 1, f'expected one matching stock base DTB, found {len(bases)}'
(out / 'stock-base.dtb').write_bytes(bases[0])

dtbo = args.dtbo.read_bytes()
magic, total, header_size, entry_size, count, entries_offset, _, table_version = struct.unpack_from('>8I', dtbo)
assert magic == 0xd7b7ab1e and entry_size >= 32 and count > 8 and total <= len(dtbo)
size, offset = struct.unpack_from('>2I', dtbo, entries_offset + 8 * entry_size)
overlay = dtbo[offset:offset+size]
ov = read_fdt(overlay)
assert ov.cells('qcom,board-id') == [0x25, 0]
(out / 'selected-overlay.dtbo').write_bytes(overlay)
dest = out / 'firmware.dtb'
library = ctypes.util.find_library('fdt')
if os.name == 'nt' and not library:
    os.add_dll_directory('C:/msys64/ucrt64/bin')
    library = 'C:/msys64/ucrt64/bin/libfdt-1.dll'
assert library, 'libfdt shared library is required'
fdt = ctypes.CDLL(library)
fdt.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
fdt.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
fdt.fdt_setprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int]
fdt.fdt_pack.argtypes = [ctypes.c_void_p]
buffer = ctypes.create_string_buffer(len(bases[0]) + len(overlay) + 65536)
overlay_buffer = ctypes.create_string_buffer(overlay)
assert fdt.fdt_open_into(bases[0], buffer, len(buffer)) == 0
assert fdt.fdt_overlay_apply(buffer, overlay_buffer) == 0
# libfdt applies overlay fragments, while Qualcomm's root selection metadata
# belongs to the overlay root and must be copied separately.
for prop in ('model', 'compatible', 'qcom,board-id'):
    value = ov.properties[prop]
    assert fdt.fdt_setprop(buffer, 0, prop.encode(), value, len(value)) == 0
assert fdt.fdt_pack(buffer) == 0
size = struct.unpack_from('>I', buffer.raw, 4)[0]
dest.write_bytes(buffer.raw[:size])
assert hashlib.sha256(dest.read_bytes()).hexdigest() == EXPECTED_DTB_SHA, 'firmware DTB differs from this handset backup'

# ARM64 image_size covers the complete shim+FD, as required by the documented
# Unixnu verifier. Flush assembler literals before the appended payload label.
shim = args.mu / 'BootShim/BootShim.S'
s = shim.read_text()
s = replace_once(s, '.quad FD_SIZE         /* Image Size */', '.quad FD_SIZE + (_Payload - _Head) /* Complete uncompressed image size */')
s = replace_once(s, '.text\n.align 4\n\n_Payload:', '.ltorg\n.text\n.align 4\n\n_Payload:')
shim.write_text(s, newline='\n')

# The handset uses the Android-v2 DTB section. Upstream currently always appends
# the tree to the compressed kernel. Add only the configured non-append path;
# keep default behavior and all round-trip checks, and validate the v2 section.
config = args.mu / 'Resources/Configs/lmi.toml'
s = replace_once(config.read_text(), 'append_dtb = true', 'append_dtb = false')
s += '\ndtb_offset = 0x01f00000\n'
config.write_text(s, newline='\n')
driver = args.unixnu / 'scripts/unixnu/bootimg.py'
s = driver.read_text()
s = replace_once(s, "'second_offset', 'cmdline')", "'second_offset', 'cmdline', 'dtb_offset')")
s = replace_once(s, 'kernel = gzip.compress(combined, mtime=0) + tree', "append_dtb = config.get('boot_image_kernel', {}).get('append_dtb', True)\n        kernel = gzip.compress(combined, mtime=0) + (tree if append_dtb else b'')")
s = replace_once(s, "command = ['python3', mkbootimg, '--kernel', kernel_path, '--ramdisk', ramdisk_path, '-o', out]", "command = ['python3', mkbootimg, '--kernel', kernel_path, '--ramdisk', ramdisk_path, '-o', out]\n        if not append_dtb:\n            if image['header_version'] != 2:\n                raise Error('the configured separate DTB requires Android header v2')\n            dtb_path = scratch / 'firmware.dtb'\n            dtb_path.write_bytes(tree)\n            command += ['--dtb', dtb_path]")
s = replace_once(s, 'report = verify(out, combined, tree, ramdisk_path, image)', 'report = verify(out, combined, tree, ramdisk_path, image, append_dtb=append_dtb)')
s = replace_once(s, 'def verify(path, combined, tree, ramdisk_path, image):', 'def verify(path, combined, tree, ramdisk_path, image, append_dtb=True):')
s = replace_once(s, 'unpacker.unused_data != tree:', "unpacker.unused_data != (tree if append_dtb else b''):")
s = replace_once(s, "return {'kernel_sha256':", "if not append_dtb:\n        dtb_size, dtb_address = struct.unpack_from('<IQ', data, 1648)\n        dtb_start = start + page * (-(-ramdisk_size // page))\n        if dtb_size != len(tree) or dtb_address != image['base'] + image['dtb_offset'] or data[dtb_start:dtb_start+dtb_size] != tree:\n            raise Error('Android-v2 DTB section does not round-trip')\n    return {'dtb_placement': 'appended' if append_dtb else 'header-v2', 'kernel_sha256':")
driver.write_text(s, newline='\n')
print('Validated target DTBO index 8, firmware DTB hash and original Android-v2 load parameters')
print('Prepared strict shim header and Android-v2 DTB-section support for unixnu bootimg')
