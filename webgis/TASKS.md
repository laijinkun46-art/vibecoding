# TASKS.md

## 当前阶段

Phase 5：Three.js 动画

状态：Phase 5 已完成；水面波纹、方向示意、启停与节能控制已验收。Phase 6 等待确认。

## Phase 0：数据准备

- [x] 确定南宁邕江研究区边界
- [x] 搜索并下载 DEM
- [x] 搜索并下载历史降雨
- [x] 下载邕江河流矢量
- [x] 验证数据空间覆盖
- [x] 验证数据时间范围
- [x] 检查数据格式和质量
- [x] 生成数据可用性报告

## Phase 1：项目初始化

- [x] 创建 Vue 3 项目
- [x] 创建 FastAPI 项目
- [x] 配置 CesiumJS
- [x] 加载三维地图
- [x] 实现前后端通信

## Phase 2：GIS 数据处理

- [x] DEM 裁剪与处理
- [x] 降雨数据解析
- [x] 河流矢量处理
- [x] 数据格式统一

## Phase 3：洪水分析

- [x] 实现简化淹没算法
- [x] 实现水深计算
- [x] 实现淹没面积统计
- [x] 实现两期变化检测

## Phase 4：WebGIS 可视化

- [x] 加载 DEM 地形
- [x] 加载河流图层
- [x] 显示洪水淹没范围
- [x] 实现时间轴
- [x] 实现统计图表

## Phase 5：Three.js 动画

- [x] 河流水面效果
- [x] 动态水流 Shader
- [x] 动画启停控制
- [x] 性能优化

## Phase 6：测试与交付

- [ ] 数据质量检查
- [ ] 算法结果检查
- [ ] 前后端联调
- [ ] 功能验收
- [ ] 编写 README
- [ ] 整理课程设计报告

## 开发记录

每完成一个阶段，记录：

- 完成日期
- 实际完成内容
- 修改文件
- 测试结果
- 遗留问题

未经用户确认，不自动进入下一阶段。
### 初始化检查（2026-11-23）

- 本轮范围：文档与需求检查、基础目录准备、Phase 0 执行方案；不开展数据下载和业务开发。
- 已确认：AGENTS.md、PROJECT_SPEC.md、TASKS.md 均存在并已阅读；当前阶段为 Phase 0，数据获取与验证保持未开始。
- 基础目录：data/raw/dem、data/raw/rainfall、data/raw/rivers、data/study_area、data/processed、outputs、docs、scripts。
- 目录用途：raw 保存原始数据，不修改原文件；study_area 保存研究区边界；processed 保存派生数据；outputs 保存分析成果；docs 保存来源记录和检查报告；scripts 保存后续数据检查与处理脚本。
- 待明确：国内数据源优先与指定首选数据源的执行顺序；Three.js 按需集成与动画验收项的关系；研究区范围；降雨时间区间的时区与端点；DEM 与水位垂直基准；情景时间轴与真实洪水观测的区别。
- 验证：三份文档可读；基础目录创建后检查；不勾选数据任务，不声明数据可用性已验证。
- 遗留事项：尚无数据、业务代码或可运行系统；数据源可访问性、许可和下载体积留待 Phase 0 检索核实。
- 下一步：等待用户确认 Phase 0 执行方案，不自动进入 Phase 1。

### Phase 0 数据获取与检查（2026-11-23）

- 用户已确认启动 Phase 0，并明确当前没有 NASA Earthdata 账号，先完成其他检查。
- 已完成：定义 WGS84 矩形研究区（108.23–108.44°E、22.73–22.85°N）；获取 FABDEM v1.2 N22E108 原始分幅；获取并提取当前 OSM 邕江与朝阳溪中心线；建立 IMERG Final V07B 384 时次清单；生成数据可用性报告与覆盖检查图。
- 验证：DEM 最终 CRC32 和 SHA256 通过；研究区相交窗口 327781 像元全部有效；主河道在区内连续并穿过西东边界；两条河流几何有效，但原始节点未相连；降雨清单无重复、无缺失、时间区间检查通过。
- 未完成：降雨文件下载、实际像元空间与数值质量验收；水位垂直基准对齐；完整支流水系覆盖核验。时间清单验证不替代降雨文件验证，相关综合任务保持未勾选。
- 修改文件：data/study_area/nanning_yongjiang_aoi.geojson；data/raw/dem/ 原始分幅及说明；data/raw/rivers/ 原始响应；data/processed/rivers_osm_current.geojson；scripts/phase0_*.py 与 overpass_rivers.ql；docs/ 各来源、清单、检查记录和 PHASE0_DATA_REPORT.md；outputs/phase0_data_preview.png。
- 访问限制：Overpass 历史快照服务多次失败，改为 OSM 主站当前几何，明确不代表 2024 实测岸线；DEM 整段传输超时后通过 1 MiB 可续传分段成功。未绕过登录或禁用证书验证。
- 交付与复现：见 docs/PHASE0_DATA_REPORT.md、docs/phase0_validation.json、docs/raw_data_manifest.json。
- 阶段状态：Phase 0 进行中，未完成整阶段验收，未进入 Phase 1；没有前后端业务代码，没有安装依赖，没有提交或推送 Git。

### Phase 0 替代降雨来源检索（2026-11-23）

- 本轮范围：按用户要求检索其他真实降雨来源，并检查公开元数据和小型试样；不替换现有需求方案，不进入下一阶段。
- 已确认：CHM_PRE V2 仓储 V2.1.1 列出 2024 年逐日文件，约 674.6 MB；本轮只取元数据，文件范围探测遇到 TLS 错误，未下载年度数据。
- 已验证：Open-Meteo 固定 ERA5 试样约 5.5 KB，按此前一小时累计定义对齐北京时间八天，192 个小时段连续、无空值和负值；这是粗网格再分析，不是雨量站实测或研究区面平均。
- 已确认：CHIRPS v3 Final sat 公开目录包含目标八天的 8 个逐日 GeoTIFF；未下载和验收栅格，日界线不能直接等同于北京时间。GSMaP 仍要求注册，NOAA 南宁站点文件本轮未确认。
- 修改文件：docs/RAINFALL_ALTERNATIVES.md；docs/rainfall_alternatives/ 元数据、试样及检查记录；scripts/phase0_check_rainfall_alternatives.py、scripts/phase0_check_rainfall_details.py。
- 阶段状态：仍为 Phase 0；保留 IMERG 首选方案，相关下载与综合验收勾选不变。尚未下载大型替代文件、安装依赖、编写业务代码或执行 Git 提交。


### Phase 0 采用 CHM_PRE 日尺度并验收（2026-11-23）

- 用户已接受日尺度、选择国内团队 CHM_PRE，并明确授权安装 h5py 到项目隔离目录。
- 正式降雨改用 CHM_PRE V2，仓储 V2.1.1，需求中说明前一日北京时间 20:00 至当日 20:00 的气象日定义；产品日期 2024-09-06 至 2024-09-13 共八日。
- 成功获取：9 个原始 HTTP 字节段共 589824 字节，提取 8×2×3 个原始格点值并保存 HDF5 子集与 48 行 CSV。全年文件未完成下载，不宣称全年 MD5 通过；未完成缓存与正式数据分开。
- 验证通过：9 个原始分段 SHA256、48 个数值对原始文件字节逐值一致、CSV 回读一致、时间连续、原始单位 mm/day、6 个完整单元覆盖研究区、无缺失、无负值。没有重采样或生成虚构降雨。
- 总体验收：DEM 与邕江主线原有检查通过，CHM_PRE 离线验收通过；统一入口已处理 GDAL 与 h5py 的动态库冲突并复测。当前范围为研究区和主河道，不包含完整支流水系或站点独立精度验证。
- 修改文件：PROJECT_SPEC.md；TASKS.md；requirements-data.txt；.gitignore；scripts/phase0_chm_*.py；scripts/phase0_validate.py 与 phase0_write_report.py；data/raw/rainfall/chm_pre_v2_2024_byte_ranges/；data/processed/chm_pre_v2_nanning_20240906_13.h5 与对应 CSV；docs/chm_pre/、PHASE0_DATA_REPORT.md 和 raw_data_manifest.json；outputs/phase0_chm_precipitation_preview.png。
- 保留限制：源 NetCDF 无独立 EPSG，采用有记录的 WGS84 匹配假设；粗网格和气象日不支持街区级或小时实测结论；水位垂直基准、堤防与简化模型假设在分析阶段继续核实。
- 阶段结论：Phase 0 的八项基础任务完成；Phase 1 及后续任务全部保持未开始，不自动进入下一阶段。

### Phase 1 初始化与验收（2026-11-23）

- 用户已确认继续 Phase 1。本轮范围为前后端骨架、Cesium 基础地图与通信，不进入 GIS 处理或洪水分析。
- 已完成：Vue 3/Vite/Cesium 前端、FastAPI/Uvicorn 后端；健康与项目元数据 API；真实研究区定位、二维/三维、在线 OSM 与本地概览底图、断线提示和恢复重连、窄屏布局。
- 依赖与环境：使用本机现有 Node.js，后端新建项目 .venv；安装本阶段既定技术栈的必需依赖并记录锁定版本，未安装数据库或新增框架。浏览器检查复用现有 Playwright 与 Edge。
- 测试：生产构建、pip check、7 项接口/代理/异常输入检查、5 项浏览器交互检查通过；真实 OSM 瓦片返回 200，桌面与移动截图已检查，无页面脚本异常。
- 修改文件：frontend/；backend/；README.md；.gitignore；scripts/verify_phase1.py 与 verify_phase1_browser.mjs；docs/PHASE1_REPORT.md 和检查 JSON；outputs/phase1_*.png。Phase 0 报告生成脚本增加保护，防止重建旧报告回退当前阶段。
- 限制：地图为基础椭球，真实 DEM 地形与业务图层尚未接入；本地概览分辨率低，在线街道需网络；没有新增洪水算法或 Three.js 动画。
- 交付：详见 README.md 与 docs/PHASE1_REPORT.md。验收用本地服务完成后停止；未发布、未进行 Git 提交或推送。
- 阶段结论：Phase 1 五项任务完成；Phase 2 及后续保持未开始，等待用户确认。

### Phase 1 预览展示修正（2026-11-23）

- 用户反馈未看到三维地图，重新启动本机 5173 前端与 8000 后端，打开并保留可见地图预览。
- 修改 MapViewer.vue：三维研究区定位改为约 45° 倾斜视角，二维保持俯视；更新相机视角检查脚本及启动说明。
- 已实际观察到预览中的南宁街道、研究区框和倾斜视角，截图为 outputs/phase1_live_preview.png；服务为用户查看暂时保留运行。
- 仍属 Phase 1 展示修正，未加载真实 DEM 起伏，未进入 Phase 2。

### Phase 1 参考图底图修正（2026-11-23）

- 用户给出的目标效果包含卫星影像、真实地形和蓝色水面。本轮先完成当前阶段的底图展示修正。
- 修改 frontend/src/App.vue 与 components/MapViewer.vue：默认 Esri World Imagery 影像，保留 OSM 街道及本地概览；保留倾斜视角和底图来源标注，增加在线底图初始化失败的本地回退。
- 测试：公开服务元数据读取成功、前端生产构建通过、可见预览实际显示卫星影像。截图为 outputs/phase1_satellite_preview.png；新的初始化回退分支尚未专门模拟断网测试。
- README.md 和 docs/PHASE1_REPORT.md 已更新。影像未认定为 2024 年灾时拍摄，真实 DEM 和淹没水面仍未实现。
- 完整参考效果作为后续目标：Phase 2 准备真实 DEM 等数据处理结果，Phase 3 计算水位情景与淹没结果，Phase 4 接入地形和淹没图层，Phase 5 添加水流视觉效果。本轮不自动推进下一阶段。

### Phase 1 隐藏地图研究区框（2026-11-23）

- 按用户要求移除地图上的青绿色研究区矩形和“课程研究区”图例。
- 保留研究区边界数据、面积资料和定位功能，供后续分析使用；影像日期说明移至侧栏。
- 修改文件：frontend/src/components/MapViewer.vue、frontend/src/App.vue、README.md、TASKS.md。
- 验证：npm.cmd run build --prefix frontend 构建通过；浏览器刷新后图例已移除。
- 当前仍为 Phase 1 界面调整，不进入 Phase 2。

### Phase 2 GIS 数据处理（2026-11-23）

- 用户已确认继续。本轮仅进行 Phase 2，使用已有数据与本机 GIS 依赖，不下载数据、不安装新依赖。
- 已完成：原生 DEM 无重采样裁剪、UTM 49N 30 m 分析网格、Horn 坡度、地形阴影、研究区掩膜；河流裁剪与投影、所有河流及邕江主线种子网格；0.1° 降雨原值栅格、等积面积加权逐日与累计量；统一数据清单。
- 实际结果：21 个成果文件共3,185,542字节；有效DEM像元318,721个；八日格点估计面平均累计137.42584381580474 mm；保留两条河流的不连通事实，邕江主线种子为单个八邻域连通分量。
- 修改文件：scripts/gis_processing.py、phase2_process.py、verify_phase2.py、phase2_preview.py；data/processed/phase2/；docs/phase2_processing.json、phase2_checks.json、PHASE2_REPORT.md；outputs/phase2_processing_preview.png；README.md；TASKS.md。
- 测试：43项检查通过，包含输入哈希不变、原始像元逐值一致、空间对齐、解析坡度、独立面积权重、降雨逐值与累计核对、河流网格连通与文件回读；已目视检查四联图。前后端未改，本轮未运行其构建或浏览器测试。
- 遗留：水位垂直基准尚未对齐；粗格点雨量与当前河流不代表2024年逐点实测；真实地形与降雨尚未接入地图。下一阶段 Phase 3 待确认，不自动进入。

### Phase 4 按用户要求提前展示真实 DEM（2026-11-23）

- 授权范围：用户要求查看导入 DEM 后的三维影像，本轮只做 Phase 4 的 DEM 展示项，不开展 Phase 3 洪水分析或 Phase 4 其余功能。
- 已完成：真实 FABDEM 原生像元导出到 frontend/public/terrain；Cesium 高程瓦片接入及 SHA256 完整性检查；默认青秀山近景、1×起伏比例、返回近景按钮、垂直基准和覆盖范围说明，保留数据许可与Copernicus来源说明。
- 修改文件：scripts/export_dem_terrain.py、verify_dem_terrain.mjs；frontend/src/demTerrain.js、components/MapViewer.vue、App.vue；frontend/public/terrain/；docs/terrain_export_checks.json、terrain_runtime_checks.json、DEM_3D_PREVIEW.md；outputs/dem_3d_preview.png；README.md；TASKS.md。
- 验证：源文件哈希未变、导出像元回读一致、14项地形运行检查通过、前端构建通过；实际浏览器山体与卫星影像显示正常，瓦片待加载为0，渲染高程探针约288.22m，页面无可见错误。截图已保存，预览服务继续供用户查看。
- 限制：EGM2008源高程未转换为椭球高，仅作地形形态展示；覆盖区外为零高程基础椭球；未生成洪水、水深、变化检测或城市三维建筑。等待用户下一步指示。

### Phase 3 简化洪水情景分析（2026-11-23）

- 用户确认继续，按阶段开展洪水分析；本轮未修改地图页面，不自动完成 Phase 4 其余功能。
- 已完成：独立封装 DEM+邕江主线种子四邻域连通淹没、水深、面积及静态水柱统计；新增/持续/退水两期变化；生成21个GeoTIFF/GeoJSON/CSV/JSON成果。
- 配置为75、80、85、78m的EGM2008假设水面高程，不绑定历史日期，不把降雨换算为水位。对应连通湿区面积23.7168、101.2095、132.8472、80.4600km²，均含现有河道，不是实测受灾陆地面积。
- 修改文件：backend/app/gis/；data/scenarios/flood_scenarios.json；scripts/phase3_analyze.py、verify_phase3.py、phase3_preview.py；data/processed/phase3/；docs/phase3_processing.json、phase3_checks.json、PHASE3_REPORT.md；outputs/phase3_scenario_preview.png；README.md；TASKS.md。
- 测试：12个可手算算法测试及55项真实数据检查全部通过；原输入哈希不变；湿区GeoJSON回栅格逐像元一致，变化面积守恒；静态检查图已生成。前后端未变，本轮不重复构建或浏览器检查。
- 限制：全部情景为静态等水位敏感性试验，缺少实测水位率定、可靠水下河床和精细堤防，结果触及计算区边界；不模拟滞水、流速或到达时间。待用户确认后才接入地图与情景播放。

### Phase 4 情景地图、播放与统计图表（2026-11-23）

- 用户确认继续，并明确授权在本项目前端安装ECharts；固定版本6.1.0，未修改系统环境或新增后端依赖。
- 已完成：当前河流中心线、四个假设水位的蓝色淹没面、三组两期变化、图层开关、情景顺序滑杆与播放/暂停/重播、面积水深面板、ECharts面积与真实降雨双图、可读数值表和宽窄屏布局。真实日期与假设情景顺序分开显示。
- 修改文件：scripts/export_web_layers.py、verify_phase4.mjs；frontend/src/App.vue、components/MapViewer.vue、components/AnalysisCharts.vue、analysisData.js、analysis.css、main.js；frontend/package.json及锁文件；frontend/public/analysis/；docs/phase4_*、PHASE4_REPORT.md；outputs/phase4_*.png；README.md；TASKS.md。
- 测试：10个资源导出对象回读一致；28项资源检查通过；9项实际浏览器检查通过；前端构建通过。修复缺失JSON的HTML回退识别，以及304px预览下图表固有宽度导致的横向溢出。未修改分析源文件或算法，不重复GIS算法测试。
- 最终状态：S01/75m、23.7168km²、河流可见、真实DEM加载、瓦片待加载0、两个图表、无可见错误和浏览器错误日志；已保存桌面、变化、图表、窄屏截图并保留用户预览。
- 限制：水位为假设情景，不绑定历史时刻；面积含现有河道；高程仍为EGM2008源数值近似展示，未作椭球高转换；未模拟整页断网恢复全过程。Three.js水流与波纹保持未开始，等待Phase 5确认。

### Phase 5 Three.js水流与波纹（2026-11-23）

- 用户确认继续，明确授权新增Three.js；固定0.187.0版本，只修改本项目前端依赖与锁文件。
- 已完成：Three.js离屏Shader生成16帧512×512波纹图集；Cesium在既有淹没几何内播放纹理，中心线Shader显示方向示意；启停、暂停恢复、0.5/1/2倍视觉速度、真实河道节点近景定位。
- 性能：波纹图集一次生成及编码上传，释放Three渲染上下文；共享动画时间，不重建网格或重算GIS；刷新请求上限24次/秒，本机实际采样约21.91次/秒；隐藏/变化/二维/后台停止连续刷新，减少动态效果偏好时默认关闭。
- 修改文件：frontend/src/waterEffects.js、waterClock.js、waterEffects.css、components/MapViewer.vue、App.vue、main.js；前端依赖与锁文件；scripts/verify_phase5.mjs；docs/phase5_logic_checks.json、phase5_browser_checks.json、PHASE5_REPORT.md；outputs/phase5_*.png；README.md；TASKS.md。
- 测试：17项逻辑检查、28项资源检查、11项实际浏览器检查及生产构建通过。21个Phase 3成果哈希不变；暂停时钟及帧计数冻结，关闭后停止更新；S03面积仍132.8472km²，恢复S01为23.7168km²，304px窗口无横向溢出。修复Canvas材质模板克隆问题，最终重新加载后无新增渲染错误。
- 限制：波纹不改变真实几何、水深或面积，方向只沿源坐标顺序示意，倍率不是实测流速；不代表水动力计算。未做长时GPU压力、多设备或实际后台耗电测试。Phase 6仍未开始，等待用户确认。

### Phase 5 地形拉伸与水陆对比（2026-11-23）

- 三维地图默认使用 5× 垂直拉伸，可以选择 1×、3×、5×、8×。水面显示高度与地形使用相同倍率，二维使用原比例。面积与水深仍取自原始分析成果。
- 卫星底图略降低亮度及饱和度，水面改用亮青色，默认视角斜看邕江与青秀山。
- 修改了 App.vue、MapViewer.vue、waterEffects.js、analysis.css 及 README.md。浏览器实景示例见 [S02 水陆对比](outputs/terrain_water_relief_5x.jpg)。
- 生产构建、14 项 DEM 检查、28 项资源检查、17 项动画检查通过。浏览器核对了 S01 在 1× 和 8× 时面积均为 23.7168 km²、二维禁用倍率、返回三维后 S02 在 5× 时面积为 101.2095 km²，检查时无页面错误提示。
- 地形斜率的视觉观感随倍率改变。请切换到 1× 查看原始比例。Phase 6 等待确认。

### 高分辨率 DEM 来源核查（2026-11-23）

- 已核对当前 FABDEM v1.2 的原生网格为 1 角秒（约 30 m）。读取研究区 30 m 分析栅格并排除 NoData 后，318721 个有效像元的第 10、50、90 百分位分别为 74.44、86.37、122.19 m。
- [星图云 5 m DEM](https://open.geovisearth.com/service/resource/128)按指定区域定制，可提供 TIF。未取得邕江研究区文件及课程使用许可。[广西基础测绘规划](https://dnr.gxzf.gov.cn/zfxxgk/fdzdgknr/zcfg/btzdgkwj/W020230427775197740512.pdf)列出全区 2 m 格网 DEM 目标，所查页面未提供对应的公开分幅下载。
- 下一步优先核实学校能否提供本区可用于课程展示的裸地高程文件，核对覆盖、年代与垂直基准后再接入。本次仅核查数据，没有更换 DEM 或重新计算情景。

### Phase 5 水陆材质与三维地形显示复验（2026-11-23）

- 已核查真实 FABDEM 高程瓦片、定高 GeoJSON 淹没面、地形深度检测、预计算的四档水位边界，以及旧版 Three.js 离屏波纹图集。原图集重复平铺、青色自发光和 5× 默认拉伸是此次调整的重点。
- 水面基础色采用 `#526C61`。Cesium Shader 以本地米制坐标采样两组错开的自带法线纹理，沿邕江 OSM 中心线的切向移动。弱高光、轻微透明度变化只作用于已经计算出的水面。Three.js 仅用于一次性方向纹理的向量运算，省去第二个 WebGL 上下文。
- 默认拉伸 1.2×，可调 1.0–1.3×。默认镜头从西南斜看青秀山与邕江弯道。透明明暗图由现有 FABDEM 网格导出，平地透明，卫星影像和淹没面仍由 Cesium 进行遮挡。重新生成明暗图可在项目根目录用现有含 NumPy、Pillow 的 GIS Python 运行 `scripts/export_relief_shade.py`。
- 交互核验：实际操作滑块依次得到 S01、S02、S03、S04，面积为 23.7168、101.2095、132.8472、80.4600 km²。已验证时间轴自动从 S01 播至 S02 再暂停、水纹独立暂停恢复、变化模式与二维挂起。运行时固定 150×95 像素水面区域两帧不同，暂停后同区域截图完全相同。
- 本机对照使用同一内置浏览器、1440×900、S02、1×、卫星底图、水流近景、默认速度。待瓦片就绪后，用相同的临时 Cesium postRender 计数，旧版 39.738 秒绘制 868 帧（21.84 帧/秒），新版 28.793 秒绘制 626 帧（21.74 帧/秒）。均使用项目的动画请求上限 24 次/秒。单次采样未见明显变化，测试计数已移除。特效 JS 构建分块从 529.98 kB 降至 89.62 kB，另加 551370 字节静态地形明暗图及按需读取的既有 34121 字节法线纹理。
- 验证：生产构建通过，14 项地形、28 项资源及 17 项动画逻辑检查通过。原始 FABDEM 与 21 份 Phase 3 成果 SHA256 通过核对。三维近景和全景查看中未观察到明显闪烁或大面积穿模。岸线局部仍受 30 m 分析网格与三维瓦片插值差异影响。最后一次完整页面加载后未见渲染错误。
- 主要修改：`frontend/src/App.vue`、`frontend/src/components/MapViewer.vue`、`frontend/src/waterEffects.js`、`frontend/src/riverFlowField.js`、`frontend/src/analysis.css`、`scripts/export_relief_shade.py`、`frontend/public/terrain/relief_shade.png`、`README.md`、`TASKS.md`。
- 截图：[75 m 全景](outputs/water_natural_s01.jpg)、[80 m 全景](outputs/water_natural_s02.jpg)、[新版近景](outputs/water_natural_close.jpg)、[旧版同视角](outputs/water_before_close.jpg)。本轮停留在 Phase 5。


### 3× 地形效果预览

在 App.vue 的三维地形拉伸选项中加入 3×，首次打开默认 1.2×。S02（80 m）固定地图视角与卫星底图后，分别截取 [1.2×](outputs/relief_comparison_1_2x.jpg) 与 [3×](outputs/relief_comparison_3x.jpg)。两档均显示面积 101.2095 km²，真实地形已加载，前端生产构建通过。预览停在 3×，该倍率仅供比较地形起伏。

### Phase 5 沿江低视角近景

GitHub 已保存调整前版本。本机“查看水流近景”改为沿邕江向青秀山看，使用实际中心线节点、约 11.5° 俯角与 1850 m 观察距离。卫星影像提高亮度和暗部显示。修改文件为 frontend/src/components/MapViewer.vue 和本记录。生产构建和 28 项网页资源检查通过；实际浏览器查看了 S02 水面与 S03/S04 退水分类，截图保存在 outputs/river_low_angle_bright.jpg 和 outputs/river_low_angle_change.jpg。Phase 6 仍待确认。


### 扩展 4.1.2 全河段计算域与地形输入准备（2026-11-24）

- 采用既有 AOI 覆盖研究区内 33.682 km 邕江主线及两岸地形，直接引用 Phase 2 DEM。
- 新增全河段计算域、84 段周界及 2 个主线端界候选、周界采样和来源清单。边界水力类型和参数暂未指定。
- 已复核 CRS、掩膜、全线连续性、周界拓扑、纵剖面及 2,327 个周界样点，Phase 2、Phase 3 和 C03 指纹核对通过。
- 详见 [全河段地形准备报告](docs/PHASE_4_1_2_FULL_REACH_TERRAIN_REVIEW.md)。边界条件、河床参数、网格和求解留待后续阶段。


### 扩展 4.1.4 全河段教学情景参数准备（2026-11-24）

- 首轮采用独立来水与零域内降雨，CHM_PRE 留作背景，4.1.3 降雨强迫待独立验收。
- 新增河床、糙率、初态、预热、来流、尾水和逐段边界参数。已回读核对时间、单位、84 段边界和理想断面基流相容性。
- 详见 [假设参数约束与评审](docs/CONSTRAINT_FULL_REACH_SCENARIO_20261124.md)。派生地形、网格、求解及地图接入待另行开展。


### 全河段动态水动力端到端交付（2026-11-24）

- 已完成 `full_reach_v2` 教学情景，覆盖研究区内 33.682 km 邕江主线及两岸。采用真实地形与假设河床、边界及糙率，独立来流情景不叠加降雨。
- 以二维浅水方程离线求解，36 h 预热及 60 h 展示，最大相对水量残差 3.30×10⁻¹⁴。湿面积由 7.494 km² 增至 13.373 km²，退至 8.349 km²。
- 新增只读模型 API，复用原 Cesium 场景实现动态水面、流速跟踪点、播放与拖动、面积及点位时序查询。保留 S01–S04 和已有历史降雨。
- 通过独立模型帧、旧成果指纹和生产构建核验。本机 Edge 1920×1080 的 120 s 测试平均 130.02 fps，10 min 含 24 次拖动的稳定性测试通过。启动命令、参数、性能记录和限制见 [交付与验收报告](docs/FULL_REACH_HYDRODYNAMIC_DELIVERY.md)。


### 全河段水面视觉优化（2026-11-24）

- 复用已验收的 `full_reach_v2`、FastAPI 只读接口和唯一 Cesium 场景。
- 重建共享的显示边界，按模型湿区约束做岸内渐隐。自然水面由模型流速驱动双尺度纹理，保留水深、流速、原网格和节能模式。
- 新增全河段、河弯斜视和漫岸近景，播放、缺帧重试、点位查询及静态情景回归通过。
- 验收含 18 张同镜头前后对照、73 秒录屏、拓扑核对和 10 分钟长测。本地与卫星底图各 120 s 平均约 130 fps，详见[视觉优化验收](outputs/hydro_water_visuals_v1/REVIEW.md)。
