"""依据 CHM_PRE 实际验收结果更新 Phase 0 报告和任务，不进入下一阶段。"""
import datetime as dt,hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]; DOC=ROOT/'docs'
qa=json.loads((DOC/'phase0_validation.json').read_text(encoding='utf-8'))
r=json.loads((DOC/'chm_pre/validation.json').read_text(encoding='utf-8')); d=qa['dem']
assert qa['aoi']['geometry_valid'] and d['aoi_fully_covered'] and d['download_hash_matches']
assert r['source_values_replayed_exactly'] and r['csv_values_roundtrip_equal'] and r['time_sequence_passed'] and r['aoi_cell_coverage_passed']
assert r['missing_count']==r['negative_count']==0 and qa['rivers']['main_channel_check']['main_channel_coverage_passed']
assert qa['rainfall']['dataset']=='CHM_PRE V2'
rows='\n'.join(f"| {x['date_label']} | {x['min_mm_per_day']:.2f} | {x['max_mm_per_day']:.2f} |" for x in r['daily_statistics'])
body=f'''# Phase 0 数据可用性报告

更新日期：2026 年 11 月 23 日。

## 验收结论

已完成本课程研究区所需 DEM、逐日降雨子集和主河道参考的获取与基础验证，Phase 0 完成。仍停在 Phase 0，等待用户确认后才可进入 Phase 1。此结论只代表输入数据可用于后续课程开发，不代表洪水算法、历史淹没重建或系统功能已经验收。

用户已接受日尺度并选择国内团队产品，正式降雨由 GPM IMERG Final V07 改为北京师范大学团队制作的 CHM_PRE V2，仓储版本固定 V2.1.1。替换原因是当前无 Earthdata 账号且用户优先国内团队数据，允许以逐日过程代替半小时过程。需求已同步至 [PROJECT_SPEC.md](../PROJECT_SPEC.md)。国内制作不等于文件托管在国内，正式来源为官方公开 Zenodo 记录。

## 研究范围与时间

- [研究区边界](../data/study_area/nanning_yongjiang_aoi.geojson)：WGS84，经度 108.23°–108.44°，纬度 22.73°–22.85°，面积约 {qa['aoi']['area_km2']:.2f} km²。
- 边界为人工定义的课程计算范围，不是行政边界、流域边界或实际洪水边界。邕江主线在矩形中连续，并通过西、东边界。
- 降雨日期标签为 2024-09-06 至 2024-09-13，共 8 天。
- [官方仓储说明](https://zenodo.org/records/20378336)定义：每日数值是前一日北京时间 20:00 至标签日 20:00 的累计。八日合计对应 2024-09-05 20:00 至 2024-09-13 20:00，不能标成 9 月 6 日零时至 9 月 14 日零时。
- 日期标签与结束时刻一并保存于 CSV；未对逐日数据作小时插值。

## 已取得的数据

| 数据 | 保存内容 | 实际检查 | 结论 |
|---|---|---|---|
| FABDEM v1.2 | N22E108 原始 GeoTIFF，28,214,328 字节，及官方说明、许可 | 原始 ZIP CRC32、SHA256、格式、坐标与研究区像元 | 本研究区地形输入可用 |
| CHM_PRE V2 V2.1.1 | 9 个原始 HTTP 字节段，共 {r['raw_byte_count']:,} 字节；独立 HDF5 子集和格点 CSV | 原始分段 SHA256、48 个源字节数值独立比对、时段、单位、覆盖、空值、非负与回读 | 8 日×2 纬度×3 经度子集可用 |
| 当前 OSM 河流 | 原始地图 XML及提取的邕江、朝阳溪两条中心线 | 几何有效性、相交和主河道连续性 | 主河道参考可用，非 2024 年实测岸线 |

### DEM

原始分幅水平 EPSG:4326，3600×3600、Float32、1 角秒间距，NoData=-9999。官方 [README](../data/raw/dem/readme.txt)标注垂直基准 EGM2008 EPSG:3855。研究区相交窗口 757×433，共 327,781 个像元，全部有效。高程约 {d['elevation_m']['min']:.2f}–{d['elevation_m']['max']:.2f} m；这是格网高程统计，不是实测河床或水深。

约 2.86 GB 的完整分区 ZIP 没有下载，只提取了其中的原始单幅。分幅 SHA256：`{d['sha256']}`。没有重采样虚构分辨率；高程绝对精度没有地面测量验证。

### CHM_PRE 日降雨

官方年文件 `CHM_PRE_V2_daily_2024.nc` 为 674,638,949 字节；其仓储 MD5 是 `3360750e943c9372761b8cf0bc6f2fa2`。本项目未取得完整年文件，因此不宣称全年文件 MD5 校验通过。先前约 46 MB 的未完成传输保留为 `data/.download_cache/chm_pre_2024.nc.part`，与正式原始数据分开，不能当作完整 NetCDF 使用。

实际按需获取 [原始字节段清单](../data/raw/rainfall/chm_pre_v2_2024_byte_ranges/manifest.json)及所列 9 个分段。每段保存原样字节、偏移、长度、HTTP 来源和 SHA256。然后用原文件 HDF5 元数据读取研究区相交的 6 个完整格点，未修改原始响应、未重采样：

- 纬度中心：22.75°、22.85°；经度中心：108.25°、108.35°、108.45°。
- 虽然 108.45° 中心在矩形外，其 0.1° 单元仍覆盖研究区东部边缘；按单元相交保留，不能仅按中心落入筛选。
- 变量 prec，原始 Float64，单位 mm/day；时间为 `days since 1960-01-01`，公历日序列。
- 目标形状 8×2×3，共 48 个值；缺失 0、负值 0；数值范围 {r['min']:.2f}–{r['max']:.2f} mm/day。
- 原始 `_FillValue` 为 NaN；JSON 元数据用 null 表示该缺失值标识，不代表子集存在空值。
- 源 NetCDF 只声明经纬度及角度单位，没有独立 EPSG 或椭球字段。依据官方对产品 GeoTIFF 的 WGS84 说明，本项目作 WGS84 匹配假设并显式记录；没有伪称文件内存在 EPSG 标签，也没有进行坐标转换。

[HDF5 子集](../data/processed/chm_pre_v2_nanning_20240906_13.h5)是本项目提取文件，不是完整官方年度文件；其 SHA256：`{r['subset_sha256']}`。[格点 CSV](../data/processed/chm_pre_v2_nanning_daily_cells.csv)保留每个气象日、起止时间、格点位置与原始降雨值，尚未计算研究区面积加权平均。

以下为六个相交格点的日最小、最大值，只用于质量检查，不是区域平均：

| 产品日期标签 | 格点最小值 mm/day | 格点最大值 mm/day |
|---|---:|---:|
{rows}

![CHM_PRE 八日降水格点检查](../outputs/phase0_chm_precipitation_preview.png)

子集在离线环境中重新打开原始分段，直接根据连续存储的 Float64 源字节偏移逐值比对，48 个值全部相等；CSV 也逐值回读一致。本轮验收不访问网络，不依赖未完成年度缓存。

### 河流

历史 Overpass 服务多次失败，保留查询与失败记录，转用 OSM 主站当前地图响应。原始 XML为 `data/raw/rivers/osm_map_context_current.osm`，[提取的 GeoJSON](../data/processed/rivers_osm_current.geojson)只包含 river 中心线。

邕江 way 42366144 有 195 个节点，最后修改时间 2026-07-28，研究区内裁切为有效单条线，穿过西、东边界。朝阳溪另有 46 个节点；两条线原始节点不相连，未擅自吸附或接线。本阶段按研究区主河道满足最低数据需求，不宣称完整支流水系已覆盖。后续连通性约束优先使用已确认的邕江主线，不能直接假设朝阳溪已经接通。

![DEM 与河流覆盖检查](../outputs/phase0_data_preview.png)

## 数据来源与使用说明

- [CHM_PRE V2 官方记录](https://doi.org/10.5281/zenodo.20378336)：V2.1.1、CC BY 4.0；[国内数据中心发布说明](https://cms.casdc.cn/article/912)；[数据论文](https://doi.org/10.5194/essd-17-3987-2025)。按记录引用作者与版本。格点数据由观测与协变量方法生成，不等于研究区逐点实测。
- [FABDEM 官方目录](https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/)和保存的 README、license：说明要求 CC BY-NC-SA 4.0，须保留原始 Copernicus 来源声明。
- [OSM 主站原始请求](https://www.openstreetmap.org/api/0.6/map?bbox=108.30,22.79,108.33,22.82)：标注 © OpenStreetMap contributors、ODbL；数据版本是当前河道，不是历史岸线。
- IMERG、ERA5 和 CHIRPS 检索记录保留于 [替代来源对比](RAINFALL_ALTERNATIVES.md)，不会混入正式 CHM_PRE 序列。

## 限制与后续处理边界

1. 0.1° 降雨格点仅覆盖少量单元，无法提供街区或 30 m 级降雨差异。6 个格点的直接平均不等同于研究区面平均；面积权重和累计统计留到 Phase 2。
2. 每日气象日必须保持 20:00—20:00 的定义。时间轴可展示日尺度情景节点，但平滑播放不能称为连续实测洪水演变。
3. 本地降雨不代表上游完整流域输入，不能直接精确确定水位。公开洪峰报道没有为本项目提供可直接使用的垂直基准转换；后续必须说明水位情景和 DEM 的高程关系。
4. DEM 缺少实测水下地形与精细堤防信息，OSM 中心线也不提供河宽、河床和闸门。简化连通淹没结果必须标为情景模拟。
5. 基础质量验收不等于站点独立精度验证或工程级洪水预报验收；上述限制不通过虚构高精度数据补足。

## 环境与复现

用户已授权将 h5py 3.16.0 安装至项目 `.tools/python`，复用本机已有 NumPy 2.4.4。未改系统 Python。依赖版本记录于 [requirements-data.txt](../requirements-data.txt)。首次统一验收遇到 GDAL 与 h5py 的 HDF5 DLL 冲突，已将二者分到独立进程，统一入口复测通过。

在 PowerShell、项目根目录执行：

```powershell
Set-Location 'C:\\Users\\ly5it\\vibecoding\\webgis'
$env:PATH = 'D:\\Arcgis10.8.2\\bin;' + $env:PATH
& 'D:\\Arcgis10.8.2\\apps\\Python312\\python.exe' '.\\scripts\\phase0_chm_validate.py'
& 'D:\\Arcgis10.8.2\\apps\\Python312\\python.exe' '.\\scripts\\phase0_validate.py'
& 'D:\\Arcgis10.8.2\\apps\\Python312\\python.exe' '.\\scripts\\phase0_write_report.py'
```

前两条为离线验证，最后一条生成当前报告并刷新任务记录。项目目录已忽略本地工具、传输缓存和原始二进制数据，未初始化 Git 仓库、未提交或推送。

主要证据：[CHM_PRE 验收](chm_pre/validation.json)、[源文件实际元数据](chm_pre/file_metadata.json)、[总体检查](phase0_validation.json)、[原始数据哈希清单](raw_data_manifest.json)。

## 下一步

Phase 0 基础数据准备结束。建议下一阶段为 Phase 1 项目初始化：创建前后端骨架、配置 Cesium、加载基础三维地图并验证通信。本轮不自动进入下一阶段，等待用户确认。水位基准核实和简化模型假设在对应分析阶段继续处理。
'''
report=DOC/'PHASE0_DATA_REPORT.md'
if report.exists() and report.read_text(encoding='utf-8')!=body:
    backup=report.with_name(report.name+'.backup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')); backup.write_bytes(report.read_bytes())
report.write_text(body,encoding='utf-8')
manifest=[]
for p in sorted((ROOT/'data/raw').rglob('*')):
    if p.is_file(): manifest.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(DOC/'raw_data_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
tasks=ROOT/'TASKS.md'; before=tasks.read_text(encoding='utf-8'); after=before
status='状态：已完成 Phase 0 基础数据准备与验证（CHM_PRE 日尺度；等待确认进入 Phase 1）'
# 后续阶段已经启动时，重建 Phase 0 报告不能回退当前阶段状态。
current_stage=after.split('## 当前阶段',1)[1].split('## Phase 0：数据准备',1)[0]
if 'Phase 0：数据获取与验证' in current_stage:
    after=re.sub(r'^状态：.*$',lambda _:status,after,count=1,flags=re.M)
start=after.index('## Phase 0：数据准备'); end=after.index('## Phase 1：项目初始化')
after=after[:start]+after[start:end].replace('- [ ] ','- [x] ')+after[end:]
heading='### Phase 0 采用 CHM_PRE 日尺度并验收（2026-11-23）'
if heading not in after:
    after+='''\n\n'''+heading+'''

- 用户已接受日尺度、选择国内团队 CHM_PRE，并明确授权安装 h5py 到项目隔离目录。
- 正式降雨改用 CHM_PRE V2，仓储 V2.1.1，需求中说明前一日北京时间 20:00 至当日 20:00 的气象日定义；产品日期 2024-09-06 至 2024-09-13 共八日。
- 成功获取：9 个原始 HTTP 字节段共 589824 字节，提取 8×2×3 个原始格点值并保存 HDF5 子集与 48 行 CSV。全年文件未完成下载，不宣称全年 MD5 通过；未完成缓存与正式数据分开。
- 验证通过：9 个原始分段 SHA256、48 个数值对原始文件字节逐值一致、CSV 回读一致、时间连续、原始单位 mm/day、6 个完整单元覆盖研究区、无缺失、无负值。没有重采样或生成虚构降雨。
- 总体验收：DEM 与邕江主线原有检查通过，CHM_PRE 离线验收通过；统一入口已处理 GDAL 与 h5py 的动态库冲突并复测。当前范围为研究区和主河道，不包含完整支流水系或站点独立精度验证。
- 修改文件：PROJECT_SPEC.md；TASKS.md；requirements-data.txt；.gitignore；scripts/phase0_chm_*.py；scripts/phase0_validate.py 与 phase0_write_report.py；data/raw/rainfall/chm_pre_v2_2024_byte_ranges/；data/processed/chm_pre_v2_nanning_20240906_13.h5 与对应 CSV；docs/chm_pre/、PHASE0_DATA_REPORT.md 和 raw_data_manifest.json；outputs/phase0_chm_precipitation_preview.png。
- 保留限制：源 NetCDF 无独立 EPSG，采用有记录的 WGS84 匹配假设；粗网格和气象日不支持街区级或小时实测结论；水位垂直基准、堤防与简化模型假设在分析阶段继续核实。
- 阶段结论：Phase 0 的八项基础任务完成；Phase 1 及后续任务全部保持未开始，不自动进入下一阶段。
'''
if after!=before:
    tasks.with_name('TASKS.md.backup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')).write_bytes(tasks.read_bytes())
    tasks.write_text(after,encoding='utf-8')
print(json.dumps({'phase':'Phase 0','basic_data_checks_complete':True,'raw_files':len(manifest),'phase0_checked_tasks':after[start:after.index('## Phase 1：项目初始化')].count('- [x] '),'report':'docs/PHASE0_DATA_REPORT.md'},ensure_ascii=True))
