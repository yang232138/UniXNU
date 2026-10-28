import sys, io, zipfile, pathlib, json, hashlib, urllib.request, os
sys.path.insert(0, str(pathlib.Path(os.environ.get('UNIXNU_SOURCE', str(pathlib.Path(__file__).parent/'UniXNU-fresh'))) / 'scripts'))
from unixnu.ipsw import RangeFile
url='https://hugeota.d.miui.com/V14.0.4.0.SJKCNXM/miui_LMI_V14.0.4.0.SJKCNXM_7af1b0266e_12.0.zip'
out=pathlib.Path(os.environ.get('STOCK_OUTPUT',str(pathlib.Path(__file__).parent/'stock-inputs')))
out.mkdir(exist_ok=True)
class CachedRange(RangeFile):
    def _block(self,index):
        cache=out/f'block-{index}.cache'
        start=index*self.block
        end=min(start+self.block,self.size)-1
        if cache.exists() and cache.stat().st_size==end-start+1: return cache.read_bytes()
        for attempt in range(8):
            try:
                request=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{end}'})
                with urllib.request.urlopen(request,timeout=25) as response:
                    if response.status!=206: raise RuntimeError('Range request refused')
                    data=response.read()
                if len(data)!=end-start+1: raise RuntimeError('Short range')
                cache.write_bytes(data)
                return data
            except Exception as e: print('Retry block',index,attempt,type(e).__name__,flush=True)
        raise RuntimeError('Download failed')
with zipfile.ZipFile(io.BufferedReader(CachedRange(url,block=1024*1024))) as archive:
    names=archive.namelist()
    (out/'members.json').write_text(json.dumps(names,indent=2))
    wanted=('xbl_4.elf',) if os.environ.get('XBL_ONLY')=='1' else ('boot.img','dtbo.img','xbl.elf','xbl_config.elf','xbl_4.elf','xbl_5.elf')
    selected=[n for n in names if pathlib.PurePosixPath(n).name in wanted]
    print('SELECTED',selected,flush=True)
    manifest=[]
    for name in sorted(selected, key=lambda n: ('xbl' not in n,'dtbo' not in n,n)):
        data=archive.read(name)
        dest=out/pathlib.PurePosixPath(name).name
        dest.write_bytes(data)
        manifest.append(dict(member=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        print(manifest[-1],flush=True)
    (out/'manifest.json').write_text(json.dumps(dict(url=url,files=manifest),indent=2))
