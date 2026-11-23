"""使用本机已有 netCDF-C 的官方只读字节范围模式探测元数据。"""
import ctypes as c,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
lib=c.CDLL('D:/Arcgis10.8.2/bin/netcdf.dll')
lib.nc_strerror.restype=c.c_char_p
import requests
lib.nc_rc_set.argtypes=[c.c_char_p,c.c_char_p]
lib.nc_rc_set(b'HTTP.SSL.CAINFO',requests.certs.where().replace('\\','/').encode())
lib.nc_rc_set(b'HTTP.TIMEOUT',b'45')
url='https://zenodo.org/records/20378336/files/CHM_PRE_V2_daily_2024.nc?download=1#mode=bytes'
ident=c.c_int(); code=lib.nc_open(url.encode(),0,c.byref(ident))
out={'url':url,'nc_open_code':code,'message':lib.nc_strerror(code).decode()}
if code==0:
    nd,nv,na,unlim=c.c_int(),c.c_int(),c.c_int(),c.c_int()
    lib.nc_inq(ident,c.byref(nd),c.byref(nv),c.byref(na),c.byref(unlim))
    out.update(dimensions=nd.value,variables=nv.value,global_attributes=na.value)
    out['dims']=[]
    for i in range(nd.value):
        name=c.create_string_buffer(257); size=c.c_size_t()
        lib.nc_inq_dim(ident,i,name,c.byref(size)); out['dims'].append({'name':name.value.decode(),'size':size.value})
    lib.nc_close(ident)
(ROOT/'docs/chm_pre/netcdf_range_probe.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2),flush=True)