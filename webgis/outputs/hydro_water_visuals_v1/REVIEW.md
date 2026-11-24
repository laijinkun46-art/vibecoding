# 邕江全河段水面视觉优化验收

日期 2026 年 11 月 24 日（北京时间）。应用使用既有 `full_reach_v2`，覆盖研究区内 33.68 km 邕江及两岸。演示统一标识为“基于真实地形和假设参数的洪水动态情景模拟”。

执行依据：[水面视觉优化项目执行规范](../../docs/CONSTRAINT_WATER_SURFACE_EXECUTION_20261124.md)、[上位视觉优化方案](../../docs/CONSTRAINT_WATER_SURFACE_VISUALS_20261124.md)、[全河段总规范](../../docs/YONGJIANG_HYDRODYNAMIC_SIMULATION_SPEC.md)。

## 使用入口

在 [本机 WebGIS](http://127.0.0.1:5173/) 点击「全河段模拟」。默认使用「自然水面」，可切换「水深」和「流速」查看固定色标，点击水面或两岸可读取模型单元数值。用「全河段」「河弯斜视」「漫岸近景」切换镜头，打开「原单元边界」查看原网格。「节能」保留岸线、模型和时间逻辑，降低波纹和跟踪点开销。

## 实现与展示核对

- 保留唯一 Cesium Viewer 以及现有两张模型帧纹理。显示网格从原地理格索引构建，细格与粗格共用边界节点。真实相邻的湿单元才参与显示插值，需双方的水面均高于公共侧较高床面及湿深门槛。单元中心维持原值，边缘在邻域模型水面范围内插值。原帧依据按单元打包的序号读取，保持最近邻。
- 每片水面先检查所属原单元的 0.05 m 湿深门槛，再检查显示水面与该单元床高，同时继续由 Cesium 地形深度遮挡。岸内约 17–28 m 做有限渐隐，原湿区范围、统计和点位查询从原数据得到。显示地形保持旧版取样，沿用 EGM2008 与现有拉伸约定及 0.24 m 防深度冲突偏移。细堤和窄支沟的可见精度仍受源网格与地形瓦片限制。
- 自然样式采用灰蓝绿色、弱掠射反光及 26 m、88 m 双尺度纹理。外观参数集中在 `hydroWaterShaders.js`。地理定位的法线纹理只改变外观，由模型速度分量按投影方向驱动。相位按模拟时间计算，使用交错的两个周期避免循环跳变，低流速逐渐趋于静止。标准配置 320 个跟踪点，节能配置最多 112 个并省去细尺度纹理。
- 自然、水深、流速及网格对照共用水面对象。分析色标分别为 0–10 m 及 0–2.5 m/s，超过范围饱和；分析颜色可在显示顶点间连续过渡，点击得到原模型单元值。
- 数据未返回时保留上一完整画面，显示加载状态。失败时可重试，旧响应不能覆盖更晚的拖动结果。通常只更新插值、样式和时间，切换模型帧对时才传输帧数据。帧缓存保留目标帧附近最多 7 帧。

### 全景、斜视与漫岸对照

同一 Edge、同一 1920×1080、本地底图、1.2× 拉伸，记录了镜头的地球固定坐标、观察方向与上方向。对原版基准构建仅在自动化浏览器中注入镜头定位探针。18 张对照图在三个镜头及三个原输出时刻成对拍摄。

| 场景 | 旧版 | 优化后 |
| --- | --- | --- |
| 全河段基流 | [对照图](comparison_final/before-full-base.png) | [新图](comparison_final/after-full-base.png) |
| 全河段洪峰 | [对照图](comparison_final/before-full-peak.png) | [新图](comparison_final/after-full-peak.png) |
| 全河段退水末帧 | [对照图](comparison_final/before-full-recession.png) | [新图](comparison_final/after-full-recession.png) |
| 河弯洪峰 | [对照图](comparison_final/before-bend-peak.png) | [新图](comparison_final/after-bend-peak.png) |
| 漫岸近景洪峰 | [对照图](comparison_final/before-bank-peak.png) | [新图](comparison_final/after-bank-peak.png) |

河弯和岸边近景的整块平涂、边缘硬折和亮点明显减弱，深水能看见流动纹理。陡岸与粗格过渡处仍保留模型边缘的形态。可直接切换[原单元边界](comparison_final/after-bank-grid.png)、[水深](comparison_final/after-bank-depth.png)或[流速](comparison_final/after-bank-speed.png)核对。所有镜头下，基流、洪峰、退水末帧的面积分别为 7.49、13.37、8.35 km²。[镜头与对照记录](comparison_final/comparison.json)

## 实际验证

- 生产构建通过。已有浏览器回归核对了只读 API、域内外查询、播放暂停、拖动、倍速、重播、后台暂停、静态 S01–S04 和 CHM_PRE 历史降雨。
- 网格逐三角形核验覆盖 11,654 个原计算单元，重建得到 59,434 个显示顶点、47,780 个显示三角形。71,572 条内部边各匹配两次，196 条周界边各出现一次。每个单元仍由其自身三角形覆盖，顶点位置与真实地理邻接模板一致。
- 对比脚本在指定水面裁剪区域连续截图，暂停时像素一致，播放时像素变化。测试中主动中断一帧请求，地图保留上一个完整时刻，重试后到达目标。交错的两次请求保持最新时刻，缓存上限保持在 7 帧内。三种水面样式、画质和原网格开关均实测。
- 核对模型、源数据、Phase 2/3、研究区、C03 准备成果及旧网页静态资源共 409 项 SHA256，保护文件内容一致。[指纹快照](protected-fingerprints.json)

## 性能与稳定性

桌面 1920×1080、Edge 156.0.4314.58、i7-14700HX 和 RTX 4070 Laptop GPU（ANGLE D3D11）。标准画质，额定 320 个点。计数取自 Cesium 场景实际完成的绘制事件，在同一机器分开运行基准和新版。

| 底图 | 旧版平均 fps | 新版平均 fps | 旧版 / 新版 95% 帧间隔（ms） | 旧版 / 新版最长帧间隔（ms） |
| --- | ---: | ---: | ---: | ---: |
| 本地概览 | 129.92 | 130.09 | 8.40 / 8.40 | 30.50 / 11.80 |
| 卫星影像 | 129.92 | 129.99 | 8.40 / 8.40 | 9.30 / 9.40 |

四组均在预热后连续测量约 120 s。新版的两组均超过 30 fps 验收门槛，各组均无超过 500 ms 的帧间隔。这里的 fps 是本机自动化测试的 Cesium 绘制频率，显示器实际刷新率和其他设备表现可不同。[本地旧版](baseline/browser.json) · [本地新版](optimized_final/browser.json) · [卫星旧版](baseline-satellite/browser.json) · [卫星新版](optimized-satellite/browser.json)

新版 600.02 s 长测包含 24 次拖动及自然、水深、流速轮换。拖动到可操作的中位数 48.48 ms、最大 58.09 ms。绘制对象前后 3 个，水面纹理 4 张，缓存末尾 6 帧；切回旧静态情景后绘制对象回到 1 个。固定显示几何 4.09 MB，双帧纹理 0.38 MB，邻接索引纹理 0.32 MB。主动回收前后测得 JS 堆端点约 23.96→29.19 MB，页面节点 542→558。试验中未出现 WebGL 上下文丢失。额外四次切入动态再切回静态，资源计数均恢复到相同值。[重复切换记录](mode-cycles.json)GPU 显存占用及更长时间内存趋势未单独测量。

## 录屏

[涨水、漫岸与退水录屏](全河段涨水漫岸退水.webm)来自卫星底图实况，历时约 73 秒，画幅 1580×960，以 2× 播放覆盖完整的 60 h 模拟，依次检查全景、河弯和岸边。抽取第 2、24、45、61 秒均解码成功。[录屏校验](video.json) · [卫星全景](satellite-full-peak.png) · [卫星河弯](satellite-bend-peak.png) · [卫星漫岸近景](satellite-bank-peak.png)

## 复现与停止

原版用保存的改动前生产构建在单独本机端口预览，新版按 [README](../../README.md#全河段动态水动力演示) 启动。PowerShell 从项目根目录设置已有 Playwright 的 `PLAYWRIGHT_MODULE_PATH`、独立的 `HYDRO_TEST_OUTPUT` 以及原版 `HYDRO_VISUAL_BASELINE`（默认本机 5174）。

```powershell
node scripts/verify_hydro_surface.mjs
node scripts/verify_hydro_visuals.mjs
node scripts/verify_hydrodynamics.mjs --long --visuals
node scripts/verify_hydro_visuals.mjs --record
```

`verify_hydrodynamics.mjs --performance` 仅执行 120 s 采样，可用 `HYDRO_BENCH_BASEMAP=satellite` 单独记录卫星底图。每次捕获使用新的输出路径。前端 `127.0.0.1:5173`，API `127.0.0.1:8000`。手动启动的终端按 Ctrl+C 停止，后台预览的停止方法和本机进程核对命令见 [端到端交付报告](../../docs/FULL_REACH_HYDRODYNAMIC_DELIVERY.md#复现与停止服务)。

## 文件

- [显示网格](../../frontend/src/hydroSurfaceGeometry.js)及[水面着色](../../frontend/src/hydroWaterShaders.js)负责显示拓扑、岸线限制、流动纹理和视觉参数。
- [水面渲染](../../frontend/src/hydroRender.js)、[结果帧缓存](../../frontend/src/hydroData.js)、[控制面板](../../frontend/src/components/HydroControls.vue)及[地图](../../frontend/src/components/MapViewer.vue)负责图形资源、固定镜头与一个共享时间。
- [拓扑检查](../../scripts/verify_hydro_surface.mjs)、[对照和录屏](../../scripts/verify_hydro_visuals.mjs)及[浏览器回归](../../scripts/verify_hydrodynamics.mjs)用于实际验收。

