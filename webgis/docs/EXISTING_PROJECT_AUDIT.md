# 现有洪水 WebGIS 项目审计

审计日期：2026-11-23（北京时间）。审计方式：只读源码、目录与元数据检查、实际数据回读、校验和比对及本机 HTTP GET。本轮仅新增本文和 `INCREMENTAL_UPGRADE_PLAN.md`，不开展业务实现、依赖安装、数据下载、构建或 GIS 重处理。

## 1. 项目定位与检查范围

实际运行根目录：`C:\Users\ly5it\vibecoding\webgis`。当前聊天目录 `C:\Users\ly5it\Documents\ChatGPT\vibecoding 2` 为空，不能据此判断项目不存在。5173 端口所属 Vite 进程命令行指向实际项目的 `frontend/node_modules/vite/bin/vite.js`；现有后端进程也指向该项目的 `.venv`。

已阅读根 `AGENTS.md`、`PROJECT_SPEC.md`、`TASKS.md`、`README.md`，未发现子目录 AGENTS.md。当前规范写明“不开发完整水动力模型”，与本次新方向存在范围变化；本文记录评估，确认后再调整规范，不提前修改。TASKS.md 的阶段为 Phase 5 完成、Phase 6 等待确认。本轮用户只授权两份报告，故不改已有 TASKS.md。

检查前 Git 已有修改：`TASKS.md`、`frontend/src/components/MapViewer.vue`；已有未跟踪的 `data/processed/`、`docs/OPTIMIZATION_REVIEW.md`、`docs/chm_pre/`、IMERG/OSM/替代降雨记录和 `outputs/` 等。它们均为既存状态，不属于本轮新增或可清理文件。不提交、不推送、不还原。

```text
webgis/
  AGENTS.md / PROJECT_SPEC.md / TASKS.md / README.md
  frontend/
    package.json / package-lock.json / vite.config.js
    src/App.vue / components/{MapViewer,AnalysisCharts}.vue
    src/{analysisData,demTerrain,waterEffects,waterClock,riverFlowField}.js
    src/{style,analysis,waterEffects}.css
    public/analysis/       已导出的情景矢量与统计副本
    public/terrain/        FABDEM Float32网格、阴影图及来源
  backend/app/main.py      FastAPI基础元数据接口
  backend/app/gis/flood.py 静态连通淹没算法
  data/raw/               DEM、降雨原始字节段、OSM上下文
  data/processed/         CHM_PRE子集、当前河线、phase2/、phase3/
  data/study_area/         研究区边界
  data/scenarios/          四个假设水位配置
  data/.download_cache/    未完成传输/已有分段缓存
  scripts/                获取、GIS处理、导出与阶段验证
  docs/                   来源、阶段报告、验收JSON
  outputs/                已有截图、分析预览、源代码归档
  .venv/ / .tools/python/  基础API环境与独立h5py工具
```

## 2. 技术栈和现有功能

`frontend/package.json` 确认 Vue 3.5.46、Vite 8.3.8、Cesium 1.147.0、Three.js 0.187.0、ECharts 6.1.0；没有项目根 package.json，前端包位于 frontend。后端 requirements 为 FastAPI/Uvicorn，锁定文件已存在。不能因需求升级重建或换栈。

| 已有功能 | 实际代码位置与入口 | 复用结论 / 边界 |
| --- | --- | --- |
| 唯一 Cesium 场景、二维/三维、底图切换与定位 | `frontend/src/components/MapViewer.vue:328` onMounted；330行 new Viewer；setMode、updateBasemap、resetView | 直接保留唯一 Viewer；Cesium原生timeline关闭，已有Vue情景滑杆 |
| 真实 DEM 与地形阴影、地形/水面同步拉伸 | `frontend/src/demTerrain.js:7,23`；MapViewer的syncRelief、updateTerrain；`scripts/export_dem_terrain.py`、`scripts/export_relief_shade.py` | 直接复用形态预览；EGM2008未转椭球高，不能用屏幕高度作精密水位读数 |
| 河流中心线、情景淹没面、变化分类与缓存 | MapViewer updateLayer（120行）、updateRivers（193行）、layerCache、scenarioSources | 保留旧图层；新增动态水深/流速图层接入同场景 |
| 情景滑杆、播放/暂停/重播 | `frontend/src/App.vue` scheduleNext、togglePlaying、scenario-timeline | 已有，不重做；每个情景加载完成后3500ms切下一帧，只有序号，无物理历时 |
| 面积、平均/最大水深及两期变化统计 | App.vue；`frontend/src/components/AnalysisCharts.vue:12` | 已有汇总数值；曲线为面积柱状图和历史降雨曲线，尚无点击位置水深/流速时序 |
| 资源完整性检查 | `frontend/src/analysisData.js` fetchCheckedJson/loadAnalysis；demTerrain.js | SHA256与格式错误明确报错，复用思想；loadAnalysis硬限制4情景/8降雨日，不能直接塞入动态帧 |
| 水面波纹、沿河方向示意、0.5/1/2倍播放、隐藏/后台节能 | `frontend/src/waterEffects.js:80` createWaterEffects；`waterClock.js`；`riverFlowField.js:12` | 控制、生命周期和局部坐标可复用；不是速度数据或水动力求解 |
| 静态连通淹没、水深、变化检测 | `backend/app/gis/flood.py:9,47,61` | 保留算法与既有结果作为静态模式和回归基线，不能从连通搜索队列推出到达时间 |
| 后端 API | `backend/app/main.py` GET /api/health、/api/project；`frontend/vite.config.js` 代理8000 | 只有健康和项目摘要；没有模拟任务、动态帧、地图取值或时序查询接口 |
| 预处理、统计与静态导出 | `scripts/gis_processing.py`；`phase2_process.py` process_dem/process_rivers/process_rainfall；`phase3_analyze.py`；`export_web_layers.py` | 坐标、网格、NoData、统计、来源和哈希流程可复用；不重跑产生覆盖 |

现行 Three.js 实际用途是 `riverFlowField.js` 中的 Vector2 向量运算，生成128×80的方向纹理。依据线段切向加权归一化，丢失物理速度幅值；方向沿OSM节点排列，并未验证为下游。当前水面使用 Cesium 自带 waterNormalsSmall.jpg，在水面 shader 中按固定相位平移，中心线 shader 也是固定相位。没有随时间变化的二维 u/v 场，也没有积分粒子轨迹。

早期 Phase 5 记录的“Three.js离屏16帧图集”描述与当前实现不同，应以现有源码为准；README已有“Three.js向量生成方向纹理”的更新。不得根据历史完成勾选判断存在真实流场。

## 3. 已有数据与可用性

CRS（坐标参考系）说明数据如何对应地球位置。经纬度表中范围单位为度，EPSG:32649 是 UTM 49N 米制坐标。空间分辨率只对栅格定义；矢量中心线没有“30m像元分辨率”。所有高程和静态水位解释遵循源 EGM2008，不能等同于未知站点水尺基准。

### 3.1 核心判断

- FABDEM v1.2 原始分幅存在且全部像元可读：3600×3600，1角秒（约30m），原始文件28,214,328字节。原文件波段单位字段为空，m及EGM2008来自已有来源说明；不是2024洪水期间实测河床。无需重新获取。
- 正式降雨为 CHM_PRE V2 / V2.1.1，不是GPM：HDF5子集8×2×3和48行CSV可用。经度中心108.25/108.35/108.45，纬度中心22.75/22.85，单元边缘范围108.2～108.5、22.7～22.9，0.1°，prec单位mm/day。源无独立EPSG/椭球字段，WGS84是既有显式匹配假设。
- 标签2024-09-06～13，共八个气象日；整体为北京时间2024-09-05 20:00～09-13 20:00。逐日GeoTIFF单位mm是该完整气象日累计量，与源mm/day的逐日产品语义对应，不是小时雨强。面平均八日累计约137.42584mm。
- 9个原始64KiB字节段合计589,824字节。它们不是9幅独立雨量栅格；本轮构造只读本地稀疏字节读取器，以h5py读取源元数据并逐值核对48值，没有网络请求。
- `docs/imerg_download_manifest.json` 有384项GPM IMERG半小时文件清单；扫描data、docs、frontend/public未发现实际GPM HDF5或SWW。不能用已有CHM_PRE的.h5后缀声称已取得GPM。
- `data/.download_cache/chm_pre_2024.nc.part` 长46,137,344字节，年度源应为674,638,949字节，当前仅是未完成缓存；没有完整可用的年度.nc文件，不按完整NetCDF验收，不续传、不补下载。
- OSM有当前邕江与朝阳溪两条线及裁剪/投影副本；不是2024年河岸或水下地形，不能直接给出实际流向、流速。raw中OSM XML bounds只有一个小窗口；完整线提取依据还有 `docs/osm_main_api_river_ways.json`，不要把上下文XML等同完整全区河网。
- S01～S04是75、80、85、78m独立静态水位，均没有物理时间；已有depth.tif是真实运行静态算法得到的假设差值水深，不是实测水深或动态水动力输出。没有真实流速数据、传播到达时间或经率定动态结果。

### 3.2 逐文件数据清单

下表由本轮实际只读回读结果整理。所有GeoTIFF都读取了波段数组，GeoJSON/GPKG逐几何检查，CSV/JSON解析；HDF5另进程验证。非降雨栅格没有事件时间维，静态情景没有日期。极值为排除NoData后的全有效区值，不表示精度验收。

| 文件（相对项目根） | 字节 | CRS / 尺寸 / 分辨率 | 范围（西、南、东、北） | 变量、单位、时间与复用判断 |
| --- | ---: | --- | --- | --- |
| `data/processed/chm_pre_v2_nanning_20240906_13.h5` | 10768 | 经纬度，无显式EPSG；WGS84匹配假设；8×2×3；0.1° | 108.2, 22.7, 108.5, 22.9 | prec (mm/day)、time、lat、lon；2024-09-06～13气象日。独立h5py进程回读和48值比对通过，可直接复用。 |
| `data/processed/chm_pre_v2_nanning_daily_cells.csv` | 4561 | 不适用 | 不适用 | 48 行；字段：date_label, interval_start_bjt, interval_end_bjt, lat, lon, prec_mm_per_day。可复用；降雨为八日气象日，情景统计无真实历时。 |
| `data/processed/phase2/aoi_mask.tif` | 2183 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 1=计算区；0=计算区外；单位 1；有效范围 0～1。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/dem_native_clip.tif` | 677398 | EPSG:4326；433×757 行×列；0.00027778×0.00027778° | 108.22986111, 22.72986111, 108.44013889, 22.85013889 | 高程；单位 m；有效范围 63～289.27999878。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/dem_utm49n_30m.tif` | 1069376 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 高程；单位 m；有效范围 63～288.0690918。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/hillshade.tif` | 180762 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | hillshade.tif；单位 1；有效范围 41～252。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/main_river_mask.tif` | 2666 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 1=中心线触及像元；不是河宽或淹没范围；单位 1；有效范围 0～1。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/rainfall_2024-09-06.tif` | 1151 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 0～0。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-07.tif` | 1230 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 24.6970042～34.69646935。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-08.tif` | 1228 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 16.55472551～45.6085768。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-09.tif` | 1231 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 40.92824491～66.30371536。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-10.tif` | 1228 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 4.00532582～15.00157634。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-11.tif` | 1227 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 3.48573818～7.5174954。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-12.tif` | 1228 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 2.48448847～6.39118648。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_2024-09-13.tif` | 1229 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 原生格点单个24小时累计降雨量；单位 mm；有效范围 2.96884434～9.59886935。日期为文件名气象日；可直接复用。 |
| `data/processed/phase2/rainfall_accumulated.tif` | 1214 | EPSG:4326；2×3 行×列；0.1×0.1° | 108.2, 22.7, 108.5, 22.9 | 8个气象日累计降雨量；单位 mm；有效范围 116.65406604～159.28925312。八日累计；可复用。 |
| `data/processed/phase2/rainfall_cells_wgs84.geojson` | 4234 | EPSG:4326；6 要素；无栅格分辨率 | 108.2, 22.7, 108.5, 22.9 | 几何有效，0 个无效。0.1°降雨格点面；八日覆盖参考，可复用。 |
| `data/processed/phase2/rainfall_daily_aoi.csv` | 1152 | 不适用 | 不适用 | 8 行；字段：date_label, interval_start_bjt, interval_end_bjt, mean_precip_mm, cumulative_precip_mm, min_cell_mm, max_cell_mm。可复用；降雨为八日气象日，情景统计无真实历时。 |
| `data/processed/phase2/rainfall_timeseries.json` | 3176 | 不适用 | 不适用 | 八日面平均与累计降雨 mm，20:00—20:00；JSON可读，可直接复用。 |
| `data/processed/phase2/river_mask.tif` | 2799 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 1=中心线触及像元；不是河宽或淹没范围；单位 1；有效范围 0～1。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase2/rivers_utm49n.gpkg` | 98304 | EPSG:32649；2 要素；无栅格分辨率 | 215691.61762371, 2519200.07856926, 237175.86243519, 2527388.61451328 | 几何有效，0 个无效。当前河流参考，无测量分辨率或2024历史保证；可复用定位。 |
| `data/processed/phase2/rivers_wgs84.geojson` | 12881 | EPSG:4326；2 要素；无栅格分辨率 | 108.23, 22.7593442, 108.44, 22.8303415 | 几何有效，0 个无效。当前河流参考，无测量分辨率或2024历史保证；可复用定位。 |
| `data/processed/phase2/slope.tif` | 1119645 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | slope.tif；单位 degree；有效范围 0～40.35219955。非事件时序；可复用，保留原精度与基准限制。 |
| `data/processed/phase3/change_statistics.csv` | 351 | 不适用 | 不适用 | 无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S01_depth.tif` | 72101 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 假设水位减DEM；干地0，无效-9999；单位 m；有效范围 0～12。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S01_to_S02_change.geojson` | 1505773 | EPSG:4326；212 要素；无栅格分辨率 | 108.22985222, 22.73009482, 108.44014113, 22.85013741 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S01_to_S02_change.tif` | 11071 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0均干、1新增、2持续、3退水、255无效；单位 1；有效范围 0～2。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S01_wet.geojson` | 392733 | EPSG:4326；1 要素；无栅格分辨率 | 108.23002912, 22.73613631, 108.44007542, 22.843491 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S01_wet.tif` | 6184 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0干地、1情景淹没、255无效；单位 1；有效范围 0～1。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S02_depth.tif` | 366813 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 假设水位减DEM；干地0，无效-9999；单位 m；有效范围 0～17。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S02_to_S03_change.geojson` | 2154684 | EPSG:4326；528 要素；无栅格分辨率 | 108.22985222, 22.72986724, 108.44014619, 22.85013741 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S02_to_S03_change.tif` | 13238 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0均干、1新增、2持续、3退水、255无效；单位 1；有效范围 0～2。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S02_wet.geojson` | 637412 | EPSG:4326；1 要素；无栅格分辨率 | 108.22985222, 22.73009482, 108.44014113, 22.85013741 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S02_wet.tif` | 8411 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0干地、1情景淹没、255无效；单位 1；有效范围 0～1。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S03_depth.tif` | 491293 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 假设水位减DEM；干地0，无效-9999；单位 m；有效范围 0～22。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S03_to_S04_change.geojson` | 2552077 | EPSG:4326；336 要素；无栅格分辨率 | 108.22985222, 22.72986724, 108.44014619, 22.85013741 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S03_to_S04_change.tif` | 14826 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0均干、1新增、2持续、3退水、255无效；单位 1；有效范围 0～3。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S03_wet.geojson` | 668862 | EPSG:4326；1 要素；无栅格分辨率 | 108.22985222, 22.72986724, 108.44014619, 22.85013741 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S03_wet.tif` | 8794 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0干地、1情景淹没、255无效；单位 1；有效范围 0～1。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S04_depth.tif` | 289986 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 假设水位减DEM；干地0，无效-9999；单位 m；有效范围 0～15。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S04_wet.geojson` | 879359 | EPSG:4326；1 要素；无栅格分辨率 | 108.22985222, 22.73119674, 108.44013102, 22.85013679 | 几何有效，0 个无效。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/S04_wet.tif` | 9839 | EPSG:32649；457×728 行×列；30×30 m | 215460, 2515890, 237300, 2529600 | 0干地、1情景淹没、255无效；单位 1；有效范围 0～1。无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/scenario_statistics.csv` | 593 | 不适用 | 不适用 | 无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/phase3/summary.json` | 3742 | 不适用 | 不适用 | 无真实时间轴；静态假设情景，可作旧功能及回归基线。 |
| `data/processed/rivers_osm_current.geojson` | 19406 | EPSG:4326；2 要素；无栅格分辨率 | 108.1059146, 22.7593442, 108.4884871, 22.8303415 | 几何有效，0 个无效。当前河流参考，无测量分辨率或2024历史保证；可复用定位。 |
| `data/raw/dem/license.txt` | 21286 | 不适用 | 不适用 | 来源/许可文本；文件可读，保留。空间时间元数据见同目录DEM说明。 |
| `data/raw/dem/N22E108_FABDEM_V1-2.tif` | 28214328 | EPSG:4326；3600×3600 行×列；0.00027778×0.00027778° | 107.99986111, 22.00013889, 108.99986111, 23.00013889 | 高程；单位 文件未标注（DEM说明为 m）；有效范围 1～980.7800293。非事件时序；可复用，保留原精度与基准限制。 |
| `data/raw/dem/readme.txt` | 18866 | 不适用 | 不适用 | 来源/许可文本；文件可读，保留。空间时间元数据见同目录DEM说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0000000000-0000065535.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0459210752-0459276287.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0461045760-0461111295.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0462880768-0462946303.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0464715776-0464781311.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0466550784-0466616319.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0468385792-0468451327.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0470286336-0470351871.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/0472121344-0472186879.bin` | 65536 | 不适用 | 不适用 | 原年度NetCDF/HDF5的64 KiB字节段；每段SHA256通过；合用可离线读取所需元数据及48值，不能各自当完整栅格。CRS/时间/单位继承CHM_PRE说明。 |
| `data/raw/rainfall/chm_pre_v2_2024_byte_ranges/manifest.json` | 4330 | 不适用 | 不适用 | 字节偏移、长度、来源和SHA256清单；JSON可读；可复用追溯。 |
| `data/raw/rivers/osm_map_context_current.osm` | 3399855 | OSM经纬度；无栅格分辨率 | 108.30, 22.79, 108.33, 22.82（XML bounds） | XML解析通过；当前小窗口上下文，不是全研究区河网。复用追溯；全区线源另见docs/osm_main_api_river_ways.json。 |
| `data/scenarios/flood_scenarios.json` | 571 | 不适用 | 不适用 | S01～S04：75/80/85/78 m EGM2008；无真实时刻，可保留。 |
| `data/study_area/nanning_yongjiang_aoi.geojson` | 976 | EPSG:4326；1 要素；无栅格分辨率 | 108.23, 22.73, 108.44, 22.85 | 几何有效，0 个无效。人工选定计算边界，可复用。 |

### 3.3 网页副本、备选样本及缓存

| 位置 | 格式 / 内容 / 时空属性 | 读取与复用结论 |
| --- | --- | --- |
| `frontend/public/analysis/catalog.json` 及所列10个资源 | summary.json、rainfall_timeseries.json、rivers_wgs84.geojson、4个wet.geojson、3个change.geojson；元数据继承源文件 | 10个资源逐项SHA256与源JSON对象相等；可直接保留；未导出空间水深纹理 |
| `frontend/public/terrain/fabdem.f32` 与 metadata.json | 793×1189，小端Float32；EPSG:4326、1角秒；范围108.16986111,22.67986111,108.50013889,22.90013889；高程m，EGM2008，58.79～354m；无事件时间 | 3,771,508字节、SHA256通过；网页形态网格，分析使用phase2 DEM |
| `frontend/public/terrain/relief_shade.png`、NOTICE.txt、LICENSE.txt | 与上述地形相配的视觉阴影及来源；PNG不是DEM，也没有独立物理变量 | 保留，未新增影像下载；本轮未重新渲染截图 |
| `docs/rainfall_alternatives/open_meteo_era5_sample.json`、`open_meteo_era5_extended_response.json`、`open_meteo_era5_aligned_intervals.json` | 既有ERA5备选点样本与192个对齐小时区间；样本点22.75N/108.25E；降水mm；对齐范围2024-09-06 00:00～09-14 00:00 BJT | 本轮解析样本及对齐JSON；不是正式面雨量，不擅自替换CHM_PRE或拼接雨量 |
| `docs/rainfall_alternatives/` 其余JSON/HTML | CHIRPS、NOAA、CHM_PRE等既有来源探测与目录元数据，无已验收CHIRPS栅格或站点实测序列 | 追溯参考；部分记录存在编码替换字符，不据此补造数值 |
| `docs/imerg_granule_sample.json`、`imerg_download_manifest.json` | 产品元数据及文件清单；清单北京时间09-06 00:00～09-14 00:00，与CHM_PRE气象日不同 | 已读取清单；降雨变量、单位、CRS及质量尚无实文件验证 |
| `docs/chm_pre/header_64k.bin` 与来源元数据JSON | 既有源头部探测副本，非完整年度降雨 | 追溯用，不能当全年产品 |
| `data/.download_cache/fabdem_n22e108/000.part`～`026.part` | 27个已有分段，000～025各1MiB，026为951,352字节；DEM传输缓存 | 正式原始DEM已存在，无需拼接、下载或清理；缓存非独立GIS数据 |
| `outputs/` 的PNG/JPG与 `webgis-source-b11ad4f.zip` | 既有截图、分析预览、源代码归档，无独立流速变量 | 不当观测或模拟输入；未解压旧归档建立第二套项目 |

### 3.4 当前模拟和演示数据的真实性边界

现有静态情景面积依次23.7168、101.2095、132.8472、80.4600km²，最大差值水深12、17、22、15m。面积含现有河道，四情景均触及分析边界；不能称完整受灾面积。退水情景重新计算连通性，不模拟滞水和退水时间。

真实来源输入（DEM、格点估计降雨、当前OSM）、假设静态模型结果、纯视觉水面、在线卫星背景必须分别标识。卫星底图没有已核实2024灾时拍摄日期。场景播放3500ms是界面等待时间，不是洪水传播历时。

## 4. 可直接复用与待改位置

可直接保留：唯一Cesium Viewer、底图和相机、DEM加载和来源声明、当前河流定位、既有静态成果、图层加载状态和缓存、ECharts初始化/销毁、FastAPI实例和Vite代理、GIS坐标/掩膜/统计工具、原始数据及哈希清单。

待扩展：App.vue的统一物理时间、MapViewer的动态图层和点击拾取、AnalysisCharts的点位水深/流速曲线、waterEffects的模型模式材质更新、waterClock的物理播放时钟接口、analysisData的独立动态清单入口。riverFlowField只保留示意用途，不能归一化模型u/v后冒充速度。

`backend/app/gis/flood.py` 保持静态基线；ANUGA若确认引入，另设很小的水动力适配模块，而不是重写静态算法。修改与最少新增文件清单详见升级方案。

## 5. 缺失数据与风险

| 缺口 | 对动态传播研究的影响 |
| --- | --- |
| 上游流量/水位过程、下游水位过程及站点基准 | 不能建立可追溯的2024事件边界条件；本地降雨不能替代上游流域来水 |
| 可靠水下河床、河道断面、精细堤防/闸坝及结构物 | FABDEM不能可靠代表水下地形和防洪通道；直接模型化会系统性偏差 |
| 糙率分区、初始水面和速度场 | 动量耗散、传播时间和初始过渡均未确定 |
| 实测流速、水位时序、到达时间、灾时淹没范围 | 不能校准或独立验证动态结果，无法声称历史复现精度 |
| 更高时间分辨率及上游流域降雨（若开展降雨径流模型） | 现有城区0.1°逐日格点只能作为事件背景或明确的低频强迫，不能造出半小时观测 |
| 可用二维水动力时间帧与物理时间 | 目前不存在h/u/v输出，动态粒子和点位流速曲线无数据来源 |

本轮只登记缺口，没有搜寻或下载这些数据。

主要工程风险：已有未提交改动需保留；旧加载器写死4情景；旧视觉时钟截断长间隔，不宜直接当模拟时钟；UTM向量到地图局部东/北需正确旋转；浅水除法可能放大速度；大时序一次加载会占用显存/内存；地形垂直拉伸不能改变m/s或查询数值；现有EGM2008/椭球高差异仍需显式说明。

## 6. 本轮验证与限制

- 本机HTTP：首页5173、代理/api/health、代理/api/project、8000/openapi.json、/analysis/catalog.json、/terrain/metadata.json 均200。OpenAPI只列两条既有业务路由。API的phase/stage仍是Phase 1元数据，不能据此否定前端已完成Phase 5。
- GDAL 3.12.4只读回读全部数据GeoTIFF，OGR回读全部GeoJSON/GPKG且无无效几何；OSM XML、CSV、JSON可解析。第一次直接启动GIS Python遇DLL定位错误，后在当前检查进程使用os.add_dll_directory指向既有 `D:\Arcgis10.8.2\bin` 后通过；未修改系统PATH或安装工具。
- 独立h5py进程验证9段SHA256、48个HDF5值、48个源字节值及48行CSV精确相等；降雨值全部有限、非负，0～66.30371536mm/day。避免与GDAL的HDF5 DLL混用。
- Phase 2全部21个、Phase 3全部21个成果与既有清单SHA256一致；10个网页JSON与源对象一致；网页DEM Float32哈希一致。
- 基础API的.venv缺NumPy/GDAL/h5py/ANUGA；既有GIS Python有GDAL/NumPy，检测未安装ANUGA；h5py在.tools/python。不能直接把求解器导入API主进程。
- 为遵守只读范围，未运行会改写验收JSON的verify_phase2.py/verify_phase3.py、数据生成脚本和会复制Cesium静态资源的npm构建，也未开展浏览器交互回归或长时性能测试。本轮通过HTTP不等于已完成新功能验收。
- 对现有代码、数据、配置和文档建立260个文件的SHA256基线，交付前比对；只允许新增指定两份报告。详细升级方式、阶段门槛与后续验证见[增量升级方案](INCREMENTAL_UPGRADE_PLAN.md)。

本轮结论：现有工程可复用程度高，但现有结果不足以支撑真实动态流速与洪水前锋传播研究。应在已有架构中补充可信模型数据链，不应以重命名现有效果来宣称完成水动力升级。

