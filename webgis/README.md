# 南宁邕江洪水动态变化检测 WebGIS

本科 GIS 课程设计，基于 DEM、CHM_PRE 逐日降雨和 OSM 河流参考数据，研究 2024 年 9 月南宁洪水背景下的简化淹没情景。

当前已完成 Phase 0 至 Phase 5。页面显示真实 FABDEM 地形、卫星影像、当前河流、假设水位淹没、两期变化、情景播放、统计和 ECharts 图表。已加入Cesium 法线波纹材质及沿河弯的方向示意，Three.js 向量仅用于生成方向纹理，支持关闭、暂停和速度控制。历史逐日降雨独立展示，不直接推算水位。默认打开 S01（75 m）假设情景，动画不改变分析成果。

## 本机启动

请在 VS Code 中打开 `C:\Users\ly5it\vibecoding\webgis`，准备两个 **PowerShell 终端**。以下是终端命令，不是聊天输入。

第一个终端启动后端：

```powershell
Set-Location 'C:\Users\ly5it\vibecoding\webgis'
& '.\.venv\Scripts\python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

第二个终端启动前端：

```powershell
Set-Location 'C:\Users\ly5it\vibecoding\webgis\frontend'
npm.cmd run dev
```

浏览器访问 [http://127.0.0.1:5173](http://127.0.0.1:5173)。API 文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。关闭时在各终端按 Ctrl+C。

无需激活虚拟环境或修改 PowerShell 执行策略，直接调用虚拟环境中的 python.exe 和 npm.cmd 即可。本机依赖已经安装，正常启动不必重新安装。

## 依赖与重新安装

- 本轮实际使用 Node.js 24.16.0、Python 3.12。
- 前端：Vue 3.5.46、Vite 8.3.8、CesiumJS 1.147.0、ECharts 6.1.0、Three.js 0.187.0；版本由 `frontend/package-lock.json` 固定。
- 后端：FastAPI 0.165.0、Uvicorn 0.54.0；完整依赖固定于 `backend/requirements-lock.txt`。
- 数据工具 h5py 单独保存在 `.tools/python`，用于 Phase 0 离线验收，不混入基础 API 环境。

新环境需先准备相应 Node.js 和 Python 3.12，使用自己的 Python 解释器创建 `.venv`。本机重装依赖时：

```powershell
Set-Location 'C:\Users\ly5it\vibecoding\webgis'
& '.\.venv\Scripts\python.exe' -m pip install -r '.\backend\requirements-lock.txt'
Set-Location '.\frontend'
npm.cmd ci
```

## 地图与数据说明

- 默认底图为 Esri World Imagery 在线影像，可在“底图”中切换 OpenStreetMap 在线街道或本地概览。页面保留相应影像与 Cesium 的来源标注，在线底图需联网。
- 在线影像用于空间参考，没有认定其拍摄时间为 2024 年洪水期间，不能当作灾时观测影像。影像本身不会生成真实山体起伏。
- 在线服务元数据加载失败时会尝试切换本地概览；部分瓦片加载失败时会提示切换底图。
- 本地概览使用 Cesium 自带的低分辨率 Natural Earth 数据，城区放大后细节很少，不能当成街道或高精度影像。
- 真实 FABDEM 地形已加载，展示范围约108.17–108.50°E、22.68–22.90°N；范围外不提供DEM，仍为零高程基础椭球，边缘可能存在接缝。研究区边框保持隐藏。
- 三维默认以 1.2× 同步显示地形与水面，斜看邕江及青秀山。左侧“三维地形拉伸”可选 1× 原比例、1.1×、1.2×、1.3×、3×，二维使用原比例。S01 默认水位为 75 m，面积和水深始终读取原始分析结果；“查看地形近景”返回青秀山，“定位全研究区”恢复全区视角，二维保持俯视。
- FABDEM源高程为EGM2008，当前未转换到Cesium使用的椭球高，直接用于形态预览，不能据此读取准确椭球高、进行精密三维叠合或判断洪水水位。分析文件中的高程未修改。
- 左侧情景统计直接读取Phase 3已验收成果；面积包含现有河道，不是受灾陆地面积。两期变化用青色表示新增、蓝色表示持续、橙色表示退水。
- CHM_PRE 日期表示前一天北京时间 20:00 至当天 20:00 的气象日，不能解释为零点到零点。
- 基础 API 只读 `docs/phase0_validation.json` 的白名单摘要。该报告缺失或格式错误时返回 503，不编造默认数据。
- “水流与波纹”控制只改变材质和播放倍率，不表示实测流速、真实下游方向或物理波高。点击“查看水流近景”可沿真实邕江中心线定位；变化检测、二维、隐藏水面或页面进入后台时停止动画刷新。系统偏好减少动态效果时默认关闭特效。

## 项目结构

```text
frontend/              Vue 与 Cesium 页面
backend/app/           FastAPI 基础服务
data/raw/              原始数据与官方字节段，禁止修改
data/study_area/       研究区边界
data/processed/        已提取的数据子集
scripts/               数据获取、验收及 Phase 1 检查脚本
docs/                  数据来源、验收报告和检查结果
outputs/               数据检查图与页面截图
```

前端请求相对地址 `/api`，由 Vite 代理到 `127.0.0.1:8000`。开发服务使用 5173，构建预览使用 4173；基础服务均只监听本机。

## 构建与检查

在前端目录构建：

```powershell
npm.cmd run build
```

`predev` 和 `prebuild` 会从已安装的 Cesium 包复制 Workers、Assets、ThirdParty 和 Widgets 静态资源，无需额外密钥。

运行接口检查前，保持后端运行；另在前端终端执行 `npm.cmd run preview`，确认 4173 服务启动后，在第三个 PowerShell 终端运行：

```powershell
Set-Location 'C:\Users\ly5it\vibecoding\webgis'
& '.\.venv\Scripts\python.exe' '.\scripts\verify_phase1.py'
```

如果前端使用开发端口 5173，可在检查终端设置 `$env:WEBGIS_FRONTEND_URL='http://127.0.0.1:5173'`。这些变量只影响当前终端。

浏览器自动化检查脚本为 `scripts/verify_phase1_browser.mjs`，本轮复用机器现有的 Playwright 与 Edge，不是应用运行依赖。本机复现：

```powershell
$env:PLAYWRIGHT_MODULE_PATH='C:\Users\ly5it\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
node '.\scripts\verify_phase1_browser.mjs'
```

此检查默认访问 4173，需要后端和前端预览同时运行；截图输出至 `outputs/phase1_desktop.png` 和 `outputs/phase1_mobile.png`。

## 阶段资料

- [项目规范](AGENTS.md)
- [项目需求](PROJECT_SPEC.md)
- [阶段任务](TASKS.md)
- [Phase 0 数据可用性报告](docs/PHASE0_DATA_REPORT.md)
- [Phase 1 初始化验收](docs/PHASE1_REPORT.md)
- [Phase 2 GIS 数据处理与复现](docs/PHASE2_REPORT.md)
- [真实 DEM 三维预览及验证](docs/DEM_3D_PREVIEW.md)
- [Phase 3 洪水情景分析与验证](docs/PHASE3_REPORT.md)
- [Phase 4 可视化操作与验收](docs/PHASE4_REPORT.md)
- [Phase 5 水流效果与验收](docs/PHASE5_REPORT.md)

下一阶段是Phase 6综合测试与课程设计交付，须经用户确认后启动。简化洪水情景不能描述为真实洪水预报。
