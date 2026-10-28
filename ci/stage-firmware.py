"""Stage lmipro from current Mu source and this device's stock XBL, without old ports."""
import argparse,contextlib,io,re,shutil,struct,uuid,json,hashlib
from pathlib import Path
from uefi_firmware.uefi import FirmwareVolume,FirmwareFile,FirmwareFileSystemSection
ap=argparse.ArgumentParser();ap.add_argument('--mu',type=Path,required=True);ap.add_argument('--xbl',type=Path,required=True)
a=ap.parse_args();mu=a.mu.resolve()
def walk(o):
    if o is not None:
        yield o
        for c in getattr(o,'objects',[]) or []:yield from walk(c)
d=a.xbl.read_bytes();v=FirmwareVolume(d[d.index(b'_FVH')-40:])
with contextlib.redirect_stdout(io.StringIO()):assert v.process()
catalog={}
for f in walk(v):
    if not isinstance(f,FirmwareFile):continue
    ss=[s for s in walk(f) if isinstance(s,FirmwareFileSystemSection)]
    names=[s.name for s in ss if s.type==0x15 and s.name]
    if names:catalog[names[0]]=(f,ss)
cfg=next(s.data for s in catalog['uefiplat.cfg'][1] if s.type==0x19).decode().rstrip('\0')
platform=mu/'Platforms/Xiaomi/lmiproPkg'
shutil.copytree(mu/'Platforms/Xiaomi/aliothPkg',platform,dirs_exist_ok=True)
for p in list(platform.rglob('*')):
    if p.is_file():
        try:p.write_text(p.read_text().replace('alioth','lmipro'))
        except UnicodeError:pass
for p in list(platform.glob('alioth.*')):p.replace(p.with_name(p.name.replace('alioth','lmipro')))
dsc=platform/'lmipro.dsc';s=dsc.read_text()
s=re.sub(r'SOC_TYPE\s*=\s*2','SOC_TYPE = 0',s)
s=re.sub(r'!if \$\(DEVICE_MODEL\) == 0.*?!endif','  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Redmi K30 Pro Zoom Edition"\n  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"lmipro"\n  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"lmipro"',s,flags=re.S)
s=re.sub(r'^\s*lmipro/AcpiTables.inf\s*$', '',s,flags=re.M)
libraries='''
[LibraryClasses]
  UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf

[Components]
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  DarwinBootPkg/Driver/DarwinBoot.inf
'''
s+=libraries
# Every vendor binary is extracted from the matching stock XBL, never alioth.
aliases={'ScmDxeLA':'ScmDxe','TzDxeLA':'TzDxe','ChipInfoDxe':'ChipInfo','DALSYSDxe':'DALSys','HALIOMMUDxe':'HALIOMMU','HWIODxe':'HWIODxeDriver','I2CDxe':'I2C','SPIDxe':'SPI','SPMIDxe':'SPMI','TLMMDxe':'DALTLMM','PlatformInfoDxe':'PlatformInfoDxeDriver','PmicDxeLa':'PmicDxe','ResetRuntimeDxe':'ResetRuntimeDxe','XhciPciEmulationDxe':'XhciPciEmulation','RngDxe':'RngDxe','ShmBridgeDxeLA':'ShmBridgeDxe'}
needed={}
for inc in (platform/'Include').glob('*.inc'):
    text=inc.read_text()
    for rel in re.findall(r'Binaries/lmipro/[^\s]+\.inf',text):needed[rel]=None
    if inc.name=='RAW.inc':continue
    # Use the source disk drivers, preserving the required FAT stack.
    text=text.replace('Binaries/lmipro/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf','MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf')
    text=text.replace('Binaries/lmipro/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf','MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf')
    inc.write_text(text)
manifest=[]
for rel in needed:
    if '/MdeModulePkg/' in rel:continue
    stem=Path(rel).stem;name=aliases.get(stem,stem)
    if name not in catalog:raise RuntimeError(f'Missing stock XBL module: {name}')
    f,ss=catalog[name];dest=mu/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    pe=next(x.data for x in ss if x.type in (0x10,0x12))
    (dest.parent/'module.efi').write_bytes(pe)
    depex=next((x.data for x in ss if x.type==0x13),None)
    module_type='DXE_RUNTIME_DRIVER' if f.type==9 else 'DXE_DRIVER'
    guid=str(uuid.UUID(bytes_le=f.guid))
    inf=f'[Defines]\n INF_VERSION = 0x00010017\n BASE_NAME = {stem}\n FILE_GUID = {guid}\n MODULE_TYPE = {module_type}\n VERSION_STRING = 1.0\n\n[Binaries.AARCH64]\n PE32|module.efi|*\n'
    if depex:
        (dest.parent/'module.depex').write_bytes(depex);inf+=' DXE_DEPEX|module.depex|*\n'
    dest.write_text(inf)
    s+='\n[Components]\n  '+rel+'\n'
    manifest.append(dict(name=name,guid=guid,sha256=hashlib.sha256(pe).hexdigest()))
dsc.write_text(s)
raw=[]
for name,(f,ss) in catalog.items():
    if f.type!=2 or name=='uefiplat.cfg':continue
    section=next((x for x in ss if x.type==0x19),None)
    if section is None:continue
    dest=mu/'Binaries/lmipro/RawFiles'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(section.data)
    raw.append(f'FILE FREEFORM = {uuid.UUID(bytes_le=f.guid)} {{\n SECTION UI = "{name}"\n SECTION RAW = Binaries/lmipro/RawFiles/{name}\n}}')
(platform/'Include/RAW.inc').write_text('\n'.join(raw))
# Recreate board-specific memory and configuration from stock uefiplat.cfg.
entries=[];section=''
for line in cfg.splitlines():
    if line.startswith('['):section=line.strip()
    if section not in ('[MemoryMap]','[RegisterMap]') or not line.startswith('0x'):continue
    values=[v.strip() for v in line.split(',')]
    assert len(values)==8
    base,size,label,*attrs=values
    entries.append('  {'+', '.join([label,base,size,*attrs])+'},')
# Bootloader RAM starts at 0x80000000; never expose its secure prefix as free.
entries.insert(0,'  {"HYP", 0x80000000, 0x005D0000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, NS_DEVICE},')
entries.insert(1,'  {"HYP tail", 0x805F0000, 0x00010000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, NS_DEVICE},')
# Match Mu's SEC validation before spending a cloud build or boot attempt.
# IPC SHM occupies 0x805d0000..0x805f0000 inside the Linux HYP reservation;
# retain its stock descriptor and reserve the surrounding HYP pieces.
ranges=[]
for entry in entries:
    match=re.search(r'\{"([^"]+)",\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)',entry)
    assert match,entry
    name,base,size=match.groups();ranges.append((int(base,16),int(size,16),name))
ranges.sort()
for current,following in zip(ranges,ranges[1:]):
    if current[0]>=0x80000000 and current[0]+current[1]>following[0]:
        raise RuntimeError(f'Memory map overlap: {current[2]} and {following[2]}')
memory='#include <Library/MemoryMapLib.h>\nSTATIC EFI_MEMORY_REGION_DESCRIPTOR gMemoryDescriptor[] = {\n'+'\n'.join(entries)+'\n};\nVOID GetMemoryMap(OUT EFI_MEMORY_REGION_DESCRIPTOR **Map, OUT UINT8 *Count) { *Map=gMemoryDescriptor; *Count=ARRAY_SIZE(gMemoryDescriptor); }\n'
(platform/'Library/MemoryMapLib/MemoryMapLib.c').write_text(memory)
params=cfg.split('[ConfigParameters]',1)[1];values=[]
for line in params.splitlines():
    m=re.fullmatch(r'\s*(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*',line)
    if m and m[1]!='ConfigParameterCount':values.append(f'  {{"{m[1]}", {m[2]}}},')
# No persistent firmware logs during the initial temporary boot.
values=[x.replace('{"EnableLogFsSyncInRetail", 0x1}','{"EnableLogFsSyncInRetail", 0x0}') for x in values]
configuration='#include <Library/ConfigurationMapLib.h>\nSTATIC EFI_CONFIGURATION_ENTRY_DESCRIPTOR gConfigurationDescriptor[] = {\n'+'\n'.join(values)+'\n};\nVOID GetConfigurationMap(OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **Map, OUT UINT8 *Count) { *Map=gConfigurationDescriptor; *Count=ARRAY_SIZE(gConfigurationDescriptor); }\n'
(platform/'Library/ConfigurationMapLib/ConfigurationMapLib.c').write_text(configuration)
fdf=platform/'lmipro.fdf';s=fdf.read_text();s=re.sub(r'^\s*INF RuleOverride = ACPITABLE lmipro/AcpiTables.inf\s*$','',s,flags=re.M)
s=s.replace('  !include Include/RAW.inc','  !include Include/RAW.inc\n'+''.join('  INF '+line.strip()+'\n' for line in libraries.split('[Components]')[1].splitlines() if line.strip()))
fdf.write_text(s)
config=mu/'Resources/Configs/lmipro.toml';config.write_text('''[boot_shim]
requires_kernel_header = true
[uefi_fd]
base = 0x9fc00000
size = 0x300000
[boot_image_kernel]
kernel_compression = "gzip"
append_dtb = true
[boot_image]
header_version = 2
base = 0
kernel_offset = 0x8000
tags_offset = 0x1e00000
pagesize = 4096
''')
(mu/'lmipro-input-manifest.json').write_text(json.dumps(manifest,indent=2))
print(f'Staged lmipro: {len(manifest)} target vendor modules; {len(entries)} memory descriptors; {len(values)} configuration entries.')
