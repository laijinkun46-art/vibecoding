"""根据实际检查结果生成中文报告，并仅勾选已有证据的 Phase 0 任务。"""
import datetime as dt, hashlib, json, pathlib, re
ROOT=pathlib.Path(__file__).resolve().parents[1]
DOC=ROOT/'docs'
# 保留旧 IMERG 报告逻辑用于历史方案；当前采用 CHM_PRE 时路由至对应报告。
if (DOC/'chm_pre/validation.json').exists():
    import subprocess,sys
    subprocess.run([sys.executable,str(ROOT/'scripts/phase0_chm_report.py')],check=True)
    raise SystemExit(0)
qa=json.loads((DOC/'phase0_validation.json').read_text(encoding='utf-8'))
acq=json.loads((DOC/'phase0_acquisition.json').read_text(encoding='utf-8'))
osm=json.loads((DOC/'osm_main_api_result.json').read_text(encoding='utf-8'))
dem,rain,rivers=qa['dem'],qa['rainfall'],qa['rivers']
assert dem['download_hash_matches'] and dem['archive_crc32_verified'] and dem['aoi_fully_covered']
assert rain['time_inventory_passed'] and rain['data_files_downloaded']==0
assert rivers['main_channel_check']['main_channel_coverage_passed']
report=f'''# Phase 0 数据可用性报告

检查日期：2026 年 11 月 23 日。

## 当前结论

Phase 0 进行中，尚未验收完成。真实 FABDEM 分幅和当前 OSM 河流参考已获取，本地格式与覆盖检查通过；IMERG Final V07B 已建立完整时间清单，但未取得降雨文件。用户确认目前没有 Earthdata 账号，本轮不进行登录或降雨下载。未进入 Phase 1，未安装依赖、未编写前后端业务或洪水计算代码。

## 研究区与时间定义

- [研究区 GeoJSON](../data/study_area/nanning_yongjiang_aoi.geojson)：WGS84，经度 108.23°–108.44°、纬度 22.73°–22.85°，椭球面积约 {qa['aoi']['area_km2']:.2f} km²。
- 这是课程设计人工选定的矩形计算范围，包含邕江城区连续主河道；不是行政边界、流域边界或实测洪水边界。范围可按后续教学要求调整。
- 降雨区间按北京时间完整八天定义为 `[2024-09-06 00:00, 2024-09-14 00:00)`。
- 对应 UTC 区间为 `[2024-09-05 16:00, 2024-09-13 16:00)`，应有 384 个半小时时次。右端点不包含在内。

## 数据获取与验证

| 数据 | 实际取得内容 | 本轮验证 | 结论 |
|---|---|---|---|
| FABDEM v1.2 | N22E108 原始 GeoTIFF，{dem['bytes']:,} 字节 | ZIP CRC32、SHA256、栅格读取、覆盖、有效值 | 可用于后续地形处理；精度未做实测验证 |
| GPM IMERG Final V07B | 384 项文件元数据和下载链接，0 个 HDF5 文件 | 清单起止时间、重复、缺失、半小时区间 | 仅元数据通过；降雨值尚不可用 |
| OSM 河流 | 当前主站原始 XML，{osm['bytes']:,} 字节；提取邕江、朝阳溪两条中心线 | 几何有效性、研究区相交、主河道连续覆盖、节点连通性 | 主河道参考可用；不能作为 2024 年岸线观测 |

### DEM

[官方 README](../data/raw/dem/readme.txt) 标注水平 WGS84 EPSG:4326，高程基准 EGM2008 EPSG:3855。实际读取到水平 EPSG:{dem['horizontal_epsg']}、3600×3600 像元、Float32、间距 1 角秒、NoData={dem['nodata']}。约 30 m 是网格间距量级，不代表高程精度；本轮未重采样。

研究区相交窗口为 {dem['aoi_window_size'][0]}×{dem['aoi_window_size'][1]}，共 {dem['aoi_pixels']:,} 个像元；有效 {dem['valid_pixels']:,} 个，无效 {dem['invalid_pixels']} 个。这里统计的是包围研究区的原始像元窗口，包括边缘相交像元。高程约 {dem['elevation_m']['min']:.2f}–{dem['elevation_m']['max']:.2f} m，中位数约 {dem['elevation_m']['median']:.2f} m。

完整分区 ZIP 为 2,859,088,810 字节；服务器返回 206 字节范围响应。本轮仅提取其中的 28,214,328 字节分幅，没有下载整个约 2.86 GB 压缩包。整幅范围传输先后超时，改为 1 MiB 分段后成功，最终长度和 ZIP CRC32 校验通过。可续传缓存保留在 `data/.download_cache/fabdem_n22e108/`，与原始数据分开。

原始文件 SHA256：`{dem['sha256']}`。

### 降雨

CMR 清单为 {rain['file_count']} 项、{rain['unique_start_count']} 个唯一开始时间，缺失 {rain['missing_count']}、意外时次 {rain['unexpected_count']}、异常结束时间 {rain['bad_interval_end_count']}。原始全球文件合计 {rain['total_mib']:.2f} MiB，约 {rain['total_mib']/1024:.2f} GiB。

清单位于 [imerg_download_manifest.json](imerg_download_manifest.json)。CMR 的 bounding_box 只筛选覆盖研究区的文件，不会把全球文件裁成研究区。后续优先核实官方区域子集服务，先下载小样本；子集实际体积需登录后确认。未下载文件，因此单位、填充值、质量标识、实际空间像元和降雨值尚未验收。

IMERG 是卫星降雨估计，不是本地雨量站逐点实测。官方产品网格为 0.1°，不能通过插值到 DEM 网格声称拥有 30 m 降雨信息。后续需依据实际文件单位，将半小时降雨率正确换算为雨量，再累计；本轮没有生成降雨时序或模拟数字。

### 河流

历史快照的 Overpass 查询遇到 502、504、TLS 和超时问题，查询语句保留在 [overpass_rivers.ql](../scripts/overpass_rivers.ql)。本轮保留 OSM 数据源，替换访问方式为主站小范围地图 API，并明确采用当前几何。没有伪造历史快照。

原始响应保存在 `data/raw/rivers/osm_map_context_current.osm`。该地图响应还包含节点及上下文要素，保持原样；仅提取其中 `waterway=river` 的两条线用于检查，保存为 [rivers_osm_current.geojson](../data/processed/rivers_osm_current.geojson)。没有做节点吸附、简化、河网修复或水面推断。

邕江 way 42366144 包含 195 个节点，OSM 最后修改时间为 2026-07-28T02:43:29Z。它在矩形内裁切为有效的单一 LineString，穿过西、东边界，满足本计算区主河道参考需求。朝阳溪 way 136060113 含 46 个节点。两条线均有效且与研究区相交，但按原始 OSM 节点有 2 个连通分量，不能直接当成已经连接的河网。完整支流水系覆盖未验收。

OSM 数据须保留 `© OpenStreetMap contributors` 与 ODbL 来源标注。当前中心线不能提供河宽、实测河床、堤防高度或 2024 年实测岸线。

## 可视化检查

![研究区与 DEM 河流覆盖检查](../outputs/phase0_data_preview.png)

底图颜色表示 DEM 高程，不是水深或淹没区域。研究区和主河道覆盖已做数值检查，预览图用于复核空间位置。

## 数据来源与选择理由

1. [FABDEM 官方分区目录](https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/)与[官方说明](https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/readme.txt)：版本 v1.2，说明中列出 CC BY-NC-SA 4.0；原始许可文本与说明均已保留，引用和衍生数据发布应同时遵循其要求。
2. [NASA IMERG 产品说明](https://gpm.nasa.gov/data/imerg)、[GES DISC 数据集](https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary)及 [Earthdata 检索入口](https://search.earthdata.nasa.gov/search/granules?p=C2723754847-GES_DISC)：指定 Final V07，清单实际文件为 V07B，未替换为 Early 或 Late。
3. [OSM 主站查询](https://www.openstreetmap.org/api/0.6/map?bbox=108.30,22.79,108.33,22.82)与[Overpass 官方 Wiki](https://wiki.openstreetmap.org/wiki/Overpass_API)：历史服务不可用后取得当前基础河道，访问失败和时间差异已记录。
4. [地理空间数据云 DEM 说明](https://www.gscloud.cn/sources/details/302)：国内镜像的 DEM 下载需要注册；本轮未登录或下载该替代数据，继续使用需求指定的公开 FABDEM。
5. [国家气象科学数据中心资源目录](https://k.data.cma.cn/mekb/?r=site%2FthemeData)及[气象数据实名获取说明](https://data.nsmc.org.cn/DataPortal/cn/support/faq.html)：已检索国内获取渠道，但尚未取得 2024 年南宁站点降雨文件，不能认定该替代数据已可用。
6. [应急管理部转载的广西应急管理厅事件记录](https://www.mem.gov.cn/xw/gdyj/202409/t20240914_501320.shtml)：确认 2024 年 9 月洪水事件背景。其 9 月 12 日洪峰报道不是连续水位数据，也没有提供本项目可直接采用的垂直基准转换。

## 分析边界与待解决问题

- 公开洪峰水位不能直接与 EGM2008 DEM 相减。需核实站点位置、水位零点、垂直基准和沿程差异；没有可靠转换时只做明确标注的假设情景。
- 降雨与洪水水位之间受上游来水、工程调度等因素影响。本地研究区降雨不是上游完整流域输入，不能据此精确反演水位。
- DEM 不是实测河床或精细堤防模型；缺少水下地形和堤防资料，连通性约束也不能保证重现城市防洪闸、暗管和排涝过程。
- Phase 0 尚未完成全部数据空间覆盖、时间范围与质量验收；尤其不能把元数据清单通过写成降雨数据通过。

## 本地复现

在 PowerShell 中执行，路径指向本机已经存在的 GIS Python 环境；只修改当前进程 PATH，不持久修改系统设置：

```powershell
Set-Location 'C:\\Users\\ly5it\\vibecoding\\webgis'
$env:PATH = 'D:\\Arcgis10.8.2\\bin;' + $env:PATH
& 'D:\\Arcgis10.8.2\\apps\\Python312\\python.exe' '.\\scripts\\phase0_validate.py'
```

本轮实际环境：GDAL 3.12.4、NumPy {qa['runtime']['numpy']}，并复用已有 pyproj 与 Matplotlib。文件夹名称不代表这里使用 ArcGIS 的旧版 Python。没有安装新依赖。检查结果位于 [phase0_validation.json](phase0_validation.json)，下载记录位于 [phase0_acquisition.json](phase0_acquisition.json)，当前河流的来源记录位于 [osm_main_api_result.json](osm_main_api_result.json)。

## 下一步

继续停留 Phase 0。用户自行注册并登录 Earthdata 后，先通过官方入口获取一个研究区子集样本；检查实际单位、变量、坐标、NoData 和质量字段，再制定完整子集下载清单。完成八天降雨下载与数值验证后更新报告和任务清单。未经确认不进入 Phase 1。
'''
(DOC/'PHASE0_DATA_REPORT.md').write_text(report,encoding='utf-8')
# 确认原始数据未被验证过程修改，生成统一哈希清单。
manifest=[]
for path in sorted((ROOT/'data/raw').rglob('*')):
    if path.is_file(): manifest.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(DOC/'raw_data_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
assert next(x for x in manifest if x['path']==dem['file'].replace('\\','/'))['sha256']==dem['sha256']
assert next(x for x in manifest if x['path']==osm['raw_file'].replace('\\','/'))['sha256']==osm['sha256']
tasks=ROOT/'TASKS.md'; before=tasks.read_text(encoding='utf-8')
if '### Phase 0 数据获取与检查（2026-11-23）' not in before:
    backup=tasks.with_name('TASKS.md.backup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.write_bytes(tasks.read_bytes())
    after=before.replace('状态：未开始','状态：进行中（DEM 与当前河流参考已获取；降雨待 Earthdata 账号和文件验证）',1)
    for text in ['确定南宁邕江研究区边界','搜索并下载 DEM','下载邕江河流矢量','生成数据可用性报告']:
        after=after.replace('- [ ] '+text,'- [x] '+text,1)
    after+='''\n\n### Phase 0 数据获取与检查（2026-11-23）

- 用户已确认启动 Phase 0，并明确当前没有 NASA Earthdata 账号，先完成其他检查。
- 已完成：定义 WGS84 矩形研究区（108.23–108.44°E、22.73–22.85°N）；获取 FABDEM v1.2 N22E108 原始分幅；获取并提取当前 OSM 邕江与朝阳溪中心线；建立 IMERG Final V07B 384 时次清单；生成数据可用性报告与覆盖检查图。
- 验证：DEM 最终 CRC32 和 SHA256 通过；研究区相交窗口 327781 像元全部有效；主河道在区内连续并穿过西东边界；两条河流几何有效，但原始节点未相连；降雨清单无重复、无缺失、时间区间检查通过。
- 未完成：降雨文件下载、实际像元空间与数值质量验收；水位垂直基准对齐；完整支流水系覆盖核验。时间清单验证不替代降雨文件验证，相关综合任务保持未勾选。
- 修改文件：data/study_area/nanning_yongjiang_aoi.geojson；data/raw/dem/ 原始分幅及说明；data/raw/rivers/ 原始响应；data/processed/rivers_osm_current.geojson；scripts/phase0_*.py 与 overpass_rivers.ql；docs/ 各来源、清单、检查记录和 PHASE0_DATA_REPORT.md；outputs/phase0_data_preview.png。
- 访问限制：Overpass 历史快照服务多次失败，改为 OSM 主站当前几何，明确不代表 2024 实测岸线；DEM 整段传输超时后通过 1 MiB 可续传分段成功。未绕过登录或禁用证书验证。
- 交付与复现：见 docs/PHASE0_DATA_REPORT.md、docs/phase0_validation.json、docs/raw_data_manifest.json。
- 阶段状态：Phase 0 进行中，未完成整阶段验收，未进入 Phase 1；没有前后端业务代码，没有安装依赖，没有提交或推送 Git。
'''
    tasks.write_text(after,encoding='utf-8')
# 获取脚本元数据入口避免意外重跑覆盖已有取得状态。
p=ROOT/'scripts/phase0_acquire.py'; code=p.read_text(encoding='utf-8')
needle='def metadata():\n'
guard="def metadata():\n    if STATE.exists():\n        raise RuntimeError('已有获取记录，拒绝覆盖；续传请运行 phase0_dem_chunks.py，清单更新请运行 phase0_inventory.py')\n"
if '已有获取记录，拒绝覆盖' not in code:
    assert needle in code
    p.write_text(code.replace(needle,guard,1),encoding='utf-8')
print(json.dumps({'report':'docs/PHASE0_DATA_REPORT.md','raw_files':len(manifest),'checked_tasks':len(re.findall(r'^- \[x\] ',tasks.read_text(encoding='utf-8'),re.M)),'phase':'Phase 0','complete':False},ensure_ascii=True))