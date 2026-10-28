"""Check FD size, FV contents, required modules and unchanged vendor PE bytes."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import uuid
from uefi_firmware.uefi import FirmwareVolume, FirmwareFile, FirmwareFileSystemSection

def walk(obj):
    yield obj
    for child in getattr(obj, 'objects', []) or []:
        yield from walk(child)

parser = argparse.ArgumentParser()
parser.add_argument('--fd', type=Path, required=True)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
data = args.fd.read_bytes()
assert len(data) == 0x300000, 'FD must be exactly 3 MiB'
fv = FirmwareVolume(data[data.index(b'_FVH')-40:])
with contextlib.redirect_stdout(io.StringIO()):
    assert fv.process(), 'invalid FD/FV'
modules = {}
for obj in walk(fv):
    if not isinstance(obj, FirmwareFile):
        continue
    sections = [s for s in walk(obj) if isinstance(s, FirmwareFileSystemSection)]
    pe = [s.data for s in sections if s.type == 0x10]
    if not pe:
        continue
    guid = str(uuid.UUID(bytes_le=bytes(obj.guid)))
    modules[guid] = {'names': [s.name for s in sections if s.type == 0x15 and s.name],
                     'depex_sha256': [hashlib.sha256(s.data).hexdigest() for s in sections if s.type == 0x13],
                     'pe32_sha256': [hashlib.sha256(p).hexdigest() for p in pe]}
manifest = json.loads(args.manifest.read_text())
for entry in manifest['modules']:
    if not entry.get('included_in_fv', True):
        assert manifest.get('display_mode') == 'inherited-framebuffer'
        assert entry['name'] in ('CPRDxe', 'DisplayDxe'), 'unexpected excluded vendor driver'
        assert entry['guid'] not in modules, f"disabled driver unexpectedly included: {entry['name']}"
        continue
    assert entry['guid'] in modules, f"missing vendor {entry['name']}"
    assert entry['pe32_sha256'] in modules[entry['guid']]['pe32_sha256'], f"vendor PE changed: {entry['name']}"
    if entry.get('depex_sha256'):
        assert entry['depex_sha256'] in modules[entry['guid']]['depex_sha256'], f"vendor depex changed: {entry['name']}"
names = {n for entry in modules.values() for n in entry['names']}
required = {'UniXNU', 'UniXNUDxe', 'UniXNURamDiskDxe', 'DarwinBoot', 'AdvancedLogDxe', 'Fat', 'EnglishDxe', 'DxeCore', 'SimpleFbDxe', 'ResetRuntimeDxe'}
assert required <= names, f'missing required modules: {required - names}'
report = {'fd_bytes': len(data), 'fd_sha256': hashlib.sha256(data).hexdigest(),
          'required_modules': sorted(required), 'unchanged_vendor_modules': sum(e.get('included_in_fv', True) for e in manifest['modules']),
          'module_names': sorted(names), 'runtime_verified': False}
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
