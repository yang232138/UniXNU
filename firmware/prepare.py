"""Assemble a documented lmi board from public source and a verified target XBL.

No vendor PE/depex edits. No implicit substitute module or memory-range fallback.
"""
from pathlib import Path
import argparse
import contextlib
import csv
import hashlib
import io
import json
import re
import shutil
import struct
import uuid
from uefi_firmware.uefi import FirmwareVolume, FirmwareFile, FirmwareFileSystemSection

XBL_SHA = '25821d1f882fef9ec6a4db75f8d0a6ed9d173919e68dda9ed4dc39cf5e1519fc'
ALIASES = {
    'ScmDxeLA': 'ScmDxe', 'TzDxeLA': 'TzDxe', 'ChipInfoDxe': 'ChipInfo',
    'DALSYSDxe': 'DALSys', 'HALIOMMUDxe': 'HALIOMMU', 'HWIODxe': 'HWIODxeDriver',
    'I2CDxe': 'I2C', 'SPIDxe': 'SPI', 'SPMIDxe': 'SPMI', 'TLMMDxe': 'DALTLMM',
    'PlatformInfoDxe': 'PlatformInfoDxeDriver', 'PmicDxeLa': 'PmicDxe',
    'QcomChargerDxeLA': 'QcomChargerDxeLA', 'XhciPciEmulationDxe': 'XhciPciEmulation',
    'ShmBridgeDxeLA': 'ShmBridgeDxe',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def walk(obj):
    yield obj
    for child in getattr(obj, 'objects', []) or []:
        yield from walk(child)

def parse_firmware(data):
    fv = FirmwareVolume(data[data.index(b'_FVH') - 40:])
    with contextlib.redirect_stdout(io.StringIO()):
        assert fv.process(), 'firmware parser rejected input'
    return list(walk(fv))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mu', type=Path, required=True)
    parser.add_argument('--xbl', type=Path, required=True)
    args = parser.parse_args()
    data = args.xbl.read_bytes()
    assert sha(data) == XBL_SHA, 'target stock XBL hash mismatch'
    mu = args.mu.resolve()
    overlay = Path(__file__).parent / 'overlay'
    for folder in ('Platforms', 'Resources'):
        shutil.copytree(overlay / folder, mu / folder, dirs_exist_ok=True)
    pkg = mu / 'Platforms/Xiaomi/lmiPkg'
    assert re.search(r'USE_CUSTOM_DISPLAY_DRIVER\s*=\s*0\b', (pkg / 'lmi.dsc').read_text()), 'review the display selection before changing the FV inventory'
    objects = parse_firmware(data)
    modules = {}
    config = None
    for obj in objects:
        if not isinstance(obj, FirmwareFile):
            continue
        sections = [s for s in walk(obj) if isinstance(s, FirmwareFileSystemSection)]
        names = [s.name for s in sections if s.type == 0x15 and s.name]
        if not names:
            continue
        name = names[0]
        if name == 'uefiplat.cfg':
            raw = [s.data for s in sections if s.type == 0x19]
            assert len(raw) == 1
            config = raw[0]
        pe = [s.data for s in sections if s.type == 0x10]
        if pe:
            dep = [s.data for s in sections if s.type == 0x13]
            modules.setdefault(name, []).append((obj, pe, dep))
    assert config is not None, 'missing target uefiplat.cfg'

    # Resolve every vendor INF reference, including APRIORI-only modules.
    paths = sorted(set(re.findall(r'INF\s+(Binaries/lmi/[^\s{}]+\.inf)',
        '\n'.join(p.read_text() for p in (pkg / 'Include').glob('*.inc')))))
    assert len(paths) >= 45, f'unexpected vendor module count {len(paths)}'
    manifest = {'xbl_sha256': XBL_SHA, 'uefiplat_cfg_sha256': sha(config),
                'vendor_code_modified': False, 'display_mode': 'inherited-framebuffer', 'modules': []}
    for rel in paths:
        inf = mu / rel
        stem = inf.stem
        name = ALIASES.get(stem, stem)
        candidates = modules.get(name, [])
        assert len(candidates) == 1, f'{rel}: expected one target module {name}, found {len(candidates)}'
        obj, pe, deps = candidates[0]
        assert len(pe) == 1 and len(deps) <= 1, f'ambiguous sections in {name}'
        image = pe[0]
        peoff = struct.unpack_from('<I', image, 0x3c)[0]
        assert image[peoff:peoff+4] == b'PE\0\0'
        assert struct.unpack_from('<H', image, peoff+4)[0] == 0xaa64
        subsystem = struct.unpack_from('<H', image, peoff+24+68)[0]
        module_type = 'DXE_RUNTIME_DRIVER' if subsystem == 12 else 'DXE_DRIVER'
        guid = str(uuid.UUID(bytes_le=bytes(obj.guid)))
        inf.parent.mkdir(parents=True, exist_ok=True)
        # Scm and Tz share a directory: each gets its own PE and depex filename.
        pefile = stem + '.efi'
        (inf.parent / pefile).write_bytes(image)
        binaries = f'  PE32|{pefile}|*\n'
        if deps:
            depfile = stem + '.depex'
            (inf.parent / depfile).write_bytes(deps[0])
            binaries += f'  DXE_DEPEX|{depfile}|*\n'
        inf.write_text(f'''# Generated from the hash-checked target XBL; vendor bytes unmodified.
[Defines]
  INF_VERSION = 0x00010005
  BASE_NAME = {stem}
  FILE_GUID = {guid}
  MODULE_TYPE = {module_type}
  VERSION_STRING = 1.0
[Binaries.AARCH64]
{binaries}''', newline='\n')
        manifest['modules'].append({'inf': rel, 'name': name, 'guid': guid,
            'included_in_fv': name not in ('CPRDxe', 'DisplayDxe'),
            'pe32_bytes': len(image), 'pe32_sha256': sha(image),
            'depex_sha256': sha(deps[0]) if deps else None})
    (pkg / 'Include/VendorComponents.inc').write_text(
        '\n'.join('  ' + p for p in paths) + '\n', newline='\n')

    # Read the handset firmware's own memory/register/configuration tables.
    text = config.decode('ascii').strip('\0')
    section = ''
    regions, parameters = [], []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section in ('[MemoryMap]', '[RegisterMap]') and line.startswith('0x'):
            row = next(csv.reader([line], skipinitialspace=True))
            assert len(row) == 8
            base, size = (int(x, 0) for x in row[:2])
            regions.append([row[2], base, size, *[x.strip() for x in row[3:]]])
        elif section == '[ConfigParameters]':
            m = re.fullmatch(r'(\w+)\s*=\s*(0x[\da-fA-F]+|\d+)\s*(?:#.*)?', line)
            if m and m[1] != 'ConfigParameterCount':
                value = int(m[2], 0)
                # No stock persistent LogFS writes in this temporary bring-up.
                if m[1] == 'EnableLogFsSyncInRetail':
                    value = 0
                parameters.append((m[1], value))
    # Config explicitly marks the first 6 MiB unusable, with IPC SHM inside it.
    # Preserve IPC SHM exactly, reserving the two remaining ranges.
    ipc = next(r for r in regions if r[0] == 'IPC SHM')
    assert ipc[1:3] == [0x805d0000, 0x20000]
    regions += [
        ['Unusable DDR prefix', 0x80000000, 0x5d0000, 'AddMem', 'SYS_MEM', 'SYS_MEM_CAP', 'Reserv', 'NS_DEVICE'],
        ['Unusable DDR tail', 0x805f0000, 0x10000, 'AddMem', 'SYS_MEM', 'SYS_MEM_CAP', 'Reserv', 'NS_DEVICE'],
    ]
    ram = sorted((r for r in regions if r[1] >= 0x80000000), key=lambda r: r[1])
    for a, b in zip(ram, ram[1:]):
        assert a[1] + a[2] <= b[1], f'memory overlap {a[0]} / {b[0]}'
    fd = next(r for r in regions if r[0] == 'UEFI FD')
    assert fd[1:3] == [0x9fc00000, 0x300000]
    assert len(regions) < 100 and len(parameters) > 20
    memrows = '\n'.join('  {"%s", 0x%X, 0x%X, %s},' %
        (r[0], r[1], r[2], ', '.join(r[3:])) for r in regions)
    (pkg / 'Library/MemoryMapLib/MemoryMapLib.c').write_text('''/* SPDX-License-Identifier: BSD-2-Clause */
/* Generated from target XBL uefiplat.cfg; see firmware-inputs.json. */
#include <Library/MemoryMapLib.h>
STATIC EFI_MEMORY_REGION_DESCRIPTOR gMemoryDescriptor[] = {
''' + memrows + '''
};
VOID GetMemoryMap (OUT EFI_MEMORY_REGION_DESCRIPTOR **Map, OUT UINT8 *Count) {
  *Map = gMemoryDescriptor;
  *Count = ARRAY_SIZE (gMemoryDescriptor);
}
''', newline='\n')
    cfgrows = '\n'.join('  {"%s", 0x%X},' % pair for pair in parameters)
    (pkg / 'Library/ConfigurationMapLib/ConfigurationMapLib.c').write_text('''/* SPDX-License-Identifier: BSD-2-Clause */
/* Target XBL numeric configuration, except persistent LogFS sync disabled. */
#include <Library/ConfigurationMapLib.h>
STATIC EFI_CONFIGURATION_ENTRY_DESCRIPTOR gConfigurationDescriptor[] = {
''' + cfgrows + '''
};
VOID GetConfigurationMap (OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **Map, OUT UINT8 *Count) {
  *Map = gConfigurationDescriptor;
  *Count = ARRAY_SIZE (gConfigurationDescriptor);
}
''', newline='\n')
    manifest['memory_regions'] = regions
    manifest['config_parameters'] = dict(parameters)
    (mu / 'firmware-inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Validated {len(paths)} unchanged vendor modules; {len(regions)} memory regions; {len(parameters)} numeric parameters')

if __name__ == '__main__':
    main()
