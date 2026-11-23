# Phase 1 项目初始化验收

完成日期：2026 年 11 月 23 日。

## 已实现

1. Vue 3 + Vite 前端与独立 FastAPI 后端。
2. CesiumJS 本地静态资源配置、基础地球、南宁研究区定位框。
3. 二维/三维切换、返回研究区、在线街道与本地概览底图切换。
4. `/api/health` 健康检查和 `/api/project` 项目资料摘要。
5. 前端通过 Vite 的 `/api` 代理读取真实 Phase 0 元数据，显示 286.55 km² 研究区、DEM/降雨/河道资料状态。
6. 服务失败提示与重连按钮，桌面及窄屏布局，中文启动与复现说明。

## 实际验证

| 检查 | 结果与证据 |
|---|---|
| 前端生产构建 | `npm.cmd run build` 通过，Vue 与 Cesium 分块输出 |
| Python 依赖 | `pip check` 通过；完整版本保存在 requirements-lock.txt |
| 接口与代理 | 7 项检查通过，见 [phase1_api_checks.json](phase1_api_checks.json) |
| 开发启动命令 | `npm.cmd run dev` 实测启动，5173 页面和 `/api/project` 代理响应通过 |
| 浏览器交互 | 5 项检查通过，见 [phase1_browser_checks.json](phase1_browser_checks.json) |
| 在线底图 | 实测 OSM 瓦片请求 200，见 [独立底图检查记录](phase1_online_basemap_checks.json) |
| 页面异常 | 浏览器检查中没有脚本未捕获异常或 HTTP 错误响应 |
| 桌面截图 | [1440px 预览](../outputs/phase1_desktop.png)，实际地图瓦片加载完成后捕获 |
| 移动截图 | [390px 预览](../outputs/phase1_mobile.png)，没有横向溢出 |

7 项接口检查包含真实健康检查、项目资料与 Phase 0 报告一致、前端页面、代理通信、Cesium 本地资源，以及元数据缺失/损坏时返回 503。浏览器检查覆盖服务连接与真实面积、地图初始化、视角切换和定位、移动布局、断线恢复重试，以及底图切换。

构建初次发现 Vite 8 分块接口与旧写法不兼容，已改用该版本的 Rolldown 配置并复测通过。截图验证发现早期捕获发生在瓦片加载前，已增加瓦片完成状态检查并重新捕获真实地图。

## 当前边界

- 当前是基础椭球地形，没有加载真实 DEM 地形服务。
- 在线街道依赖网络；本地概览分辨率低，城区尺度可能接近单色，不代表地图初始化失败。
- “已验收数据”来自 Phase 0，当前没有降雨图层、河流分析图层、淹没计算、变化检测、统计图表或 Three.js 动画。
- 未使用数据库、未发布至云端、未提交或推送 Git。没有修改原始 GIS 数据。
- 首轮验收服务曾停止；用户反馈未看到地图后，已于 2026 年 11 月 23 日重新启动 5173 前端和 8000 后端，并在可见预览中实际确认地图。当前为用户查看保留运行，本机手动运行方式见 [README](../README.md)。

## 预览展示修正

默认三维研究区视角由俯视改为约 45° 倾斜，二维仍保持俯视。新增浏览器检查断言以读取实际场景模式与相机俯仰角；本次可见预览已确认倾斜街道地图，[实屏截图](../outputs/phase1_live_preview.png)已保存。真实 DEM 起伏仍未接入，没有将平面贴图描述为立体地形。

## 文件与环境

- 前端源码和依赖锁定：`frontend/`。
- 后端源码与依赖锁定：`backend/`，本机运行环境为根目录 `.venv/`。
- 检查脚本：`scripts/verify_phase1.py`、`scripts/verify_phase1_browser.mjs`。
- `.gitignore` 排除虚拟环境、node_modules、生成的 Cesium 资源、构建产物与缓存。
- 为避免旧数据报告覆盖阶段进度，Phase 0 报告生成器增加保护：后续阶段已开始时不回退 TASKS.md 的当前阶段。

## 下一步

Phase 1 五项任务完成。下一步建议 Phase 2：DEM 裁剪与地形处理、日降雨解析和区域统计、河流矢量处理与数据格式统一。本轮到此停止，等待用户确认。

## 参考图样式修正

2026 年 11 月 23 日，用户希望地图呈现卫星影像、真实地形起伏与蓝色水面叠加的效果。本轮在 Phase 1 中完成底图修正：新增并默认使用 Esri World Imagery，保留 OSM 街道与本地概览，继续采用约 45° 倾斜视角。卫星图像只作为参考底图，不声明是 2024 年灾时影像。

- 服务：[Esri World Imagery MapServer](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=pjson)。实际公开元数据读取成功，保留 Esri、Vantor、Earthstar Geographics 等版权来源标注。
- 实际验证：前端生产构建通过；可见浏览器中已确认南宁卫星影像和研究区框显示，[截图](../outputs/phase1_satellite_preview.png)已保存。
- 恢复处理：在线元数据失败时尝试本地概览，瓦片失败时提示切换；本轮没有专门模拟断网验证这条新回退分支。
- 尚未完成：真实 DEM 地形、蓝色淹没水面及水流动画。未生成装饰性淹没区，未将现状影像作为历史洪水实测依据。
