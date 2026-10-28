"""Stage lmipro from current Mu source and this device's stock XBL, without old ports."""
import argparse,contextlib,io,re,shutil,struct,uuid,json,hashlib
from pathlib import Path
from uefi_firmware.uefi import FirmwareVolume,FirmwareFile,FirmwareFileSystemSection

def adapt_vendor_binary(name,data):
    if name!='TzDxe':return data,[]
    # Fastboot-only bring-up reuses the QSEE environment established by stock
    # XBL/ABL. Checked independently against both init call paths in this PE.
    # Reference: https://github.com/Fsasdddd/lmi-uefi-touch-gpu/blob/main/tools/patch-lmi-firmware.py
    expected='24dc99af29ad12fae95fc215840af1044178ab67b0b801621ef4cd112385ef74'
    assert hashlib.sha256(data).hexdigest()==expected, 'Unsupported TZ firmware'
    assert data[0x2e28:0x2e2c]==bytes.fromhex('e9a65139')
    branch=struct.unpack_from('<I',data,0x2e30)[0]
    assert branch & 0xff00001f==0x34000009
    assert 0x2e30+((branch>>5)&0x7ffff)*4==0x2e80
    assert data[0x32d8:0x32dc]==bytes.fromhex('c9a65139')
    assert data[0xd469]==0
    result=bytearray(data);result[0xd469]=1
    assert [i for i,(a,b) in enumerate(zip(data,result)) if a!=b]==[0xd469]
    return bytes(result),[dict(offset='0xd469',before='00',after='01',purpose='Reuse stock QSEE initialized state for temporary fastboot boot',source_sha256=expected)]

ap=argparse.ArgumentParser();ap.add_argument('--mu',type=Path,required=True);ap.add_argument('--xbl',type=Path,required=True)
a=ap.parse_args();mu=a.mu.resolve()
# Diagnostic-only screen hold: retain the complete assertion line before the
# original DebugAssert handling proceeds. Do not change error checks or status.
fb_source=mu/'Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib/FrameBufferSerialPortLib.c'
fb=fb_source.read_text()
write_anchor='  // Get Frame Buffer Memory\n  Status = GetFrameBufferMemory (&FbBase, &FbLength);'
hold_code='''  BOOLEAN HoldAssertion = FALSE;
  for (UINTN Index = 0; Index + 7 <= NumberOfBytes; Index++) {
    if (CompareMem (Buffer + Index, "ASSERT ", 7) == 0) {
      HoldAssertion = TRUE;
      break;
    }
  }

'''
assert fb.count(write_anchor)==1, 'Unexpected framebuffer writer source'
fb=fb.replace(write_anchor,hold_code+write_anchor)
flush_anchor='  WriteBackInvalidateDataCacheRange ((VOID *)FbBase, FbLength);\n\n  return NumberOfBytes;'
assert fb.count(flush_anchor)==1, 'Unexpected framebuffer flush source'
fb=fb.replace(flush_anchor,'  WriteBackInvalidateDataCacheRange ((VOID *)FbBase, FbLength);\n\n  if (HoldAssertion) {\n    MicroSecondDelay (20000000);\n  }\n\n  return NumberOfBytes;')
fb_source.write_text(fb)
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
  lmiproPkg/MemoryDiagDxe/MemoryDiagDxe.inf
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
    if inc.name=='APRIORI.inc':
        anchor='  INF Binaries/lmipro/QcomPkg/Drivers/TzDxe/TzDxeLA.inf'
        assert text.count(anchor)==1
        text=text.replace(anchor,'  INF lmiproPkg/MemoryDiagDxe/MemoryDiagDxe.inf\n'+anchor)
    inc.write_text(text)
manifest=[]
for rel in needed:
    if '/MdeModulePkg/' in rel:continue
    stem=Path(rel).stem;name=aliases.get(stem,stem)
    if name not in catalog:raise RuntimeError(f'Missing stock XBL module: {name}')
    f,ss=catalog[name];dest=mu/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    pe=next(x.data for x in ss if x.type in (0x10,0x12))
    pe,adaptations=adapt_vendor_binary(name,pe)
    binary=dest.parent/(stem+'.efi')
    binary.write_bytes(pe)
    depex=next((x.data for x in ss if x.type==0x13),None)
    module_type='DXE_RUNTIME_DRIVER' if f.type==9 else 'DXE_DRIVER'
    guid=str(uuid.UUID(bytes_le=f.guid))
    inf=f'[Defines]\n INF_VERSION = 0x00010017\n BASE_NAME = {stem}\n FILE_GUID = {guid}\n MODULE_TYPE = {module_type}\n VERSION_STRING = 1.0\n\n[Binaries.AARCH64]\n PE32|{binary.name}|*\n'
    if depex:
        dependency=dest.parent/(stem+'.depex')
        dependency.write_bytes(depex);inf+=f' DXE_DEPEX|{dependency.name}|*\n'
    dest.write_text(inf)
    s+='\n[Components]\n  '+rel+'\n'
    manifest.append(dict(name=name,guid=guid,binary=str(binary.relative_to(mu)),sha256=hashlib.sha256(pe).hexdigest(),adaptations=adaptations))
assert len({record['binary'] for record in manifest})==len(manifest), 'Vendor output path collision'
for record in manifest:
    assert hashlib.sha256((mu/record['binary']).read_bytes()).hexdigest()==record['sha256'], f"Vendor binary overwritten: {record['name']}"
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
# The measured bootloader FDT describes DRAM at 0xc0000000..0x180000000.
# Its reserved-memory nodes do not intersect this 64 MiB early UEFI arena.
# SCM's uncached allocator first requests pages below 0xffffffff; RamManagerDxe
# has not exposed the remaining DDR at this point in the APRIORI sequence.
entries.append('  {"Early low32 RAM", 0xC0000000, 0x04000000, AddMem, SYS_MEM, SYS_MEM_CAP, Conv, WRITE_BACK_XN},')
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
probe=platform/'MemoryDiagDxe'
probe.mkdir(exist_ok=True)
(probe/'MemoryDiagDxe.inf').write_text('''[Defines]
 INF_VERSION = 0x00010017
 BASE_NAME = LmiproMemoryDiagDxe
 FILE_GUID = C6F53B23-FBA2-4F32-98A5-0ED5B379B257
 MODULE_TYPE = DXE_DRIVER
 VERSION_STRING = 1.0
 ENTRY_POINT = MemoryDiagEntry
[Sources]
 MemoryDiagDxe.c
[Packages]
 MdePkg/MdePkg.dec
[LibraryClasses]
 UefiDriverEntryPoint
 UefiBootServicesTableLib
 DebugLib
[Depex]
 TRUE
''')
(probe/'MemoryDiagDxe.c').write_text(r'''#include <Uefi.h>
#include <Library/DebugLib.h>
#include <Library/UefiBootServicesTableLib.h>

EFI_STATUS EFIAPI MemoryDiagEntry (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable) {
  EFI_STATUS Status;
  EFI_MEMORY_DESCRIPTOR *Map = NULL;
  UINTN MapSize = 0, Key = 0, EntrySize = 0;
  UINT32 Version = 0;
  UINT64 FreePages = 0, Largest = 0;
  EFI_PHYSICAL_ADDRESS Address = 0xffffffff;
  Status = gBS->GetMemoryMap (&MapSize, Map, &Key, &EntrySize, &Version);
  if (Status == EFI_BUFFER_TOO_SMALL) {
    MapSize += 2 * EntrySize;
    Status = gBS->AllocatePool (EfiBootServicesData, MapSize, (VOID **)&Map);
    if (!EFI_ERROR (Status)) {
      Status = gBS->GetMemoryMap (&MapSize, Map, &Key, &EntrySize, &Version);
      if (!EFI_ERROR (Status)) {
        for (UINTN Offset = 0; Offset < MapSize; Offset += EntrySize) {
          EFI_MEMORY_DESCRIPTOR *D = (VOID *)((UINT8 *)Map + Offset);
          if (D->Type == EfiConventionalMemory && D->PhysicalStart < 0x100000000ULL) {
            UINT64 Pages = D->NumberOfPages;
            UINT64 Limit = (0x100000000ULL - D->PhysicalStart) >> 12;
            if (Pages > Limit) { Pages = Limit; }
            FreePages += Pages;
            if (Pages > Largest) { Largest = Pages; }
          }
        }
      }
      gBS->FreePool (Map);
    }
  }
  DEBUG ((DEBUG_WARN, "LMIPRO MEM: low32 free=%Lu KiB largest=%Lu KiB map=%r\n", FreePages * 4, Largest * 4, Status));
  Status = gBS->AllocatePages (AllocateMaxAddress, EfiReservedMemoryType, 0x82, &Address);
  DEBUG ((DEBUG_WARN, "LMIPRO MEM: 520KiB low32 probe=%r address=0x%Lx\n", Status, Address));
  if (!EFI_ERROR (Status)) { gBS->FreePages (Address, 0x82); }
  return EFI_SUCCESS;
}
''')
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
