# 邕江全河段二维漫岸教学情景验收

日期 2026 年 11 月 24 日（北京时间）。上位执行文件为[全河段二维水动力陆地淹没增强执行文件](CONSTRAINT_FULL_REACH_OVERBANK_20261124.md)，总体范围采用[全河段水动力模拟总规范](YONGJIANG_HYDRODYNAMIC_SIMULATION_SPEC.md)。

## 一、运行与使用

打开[本机 WebGIS](http://127.0.0.1:5173/)，点「全河段模拟」。默认选中 `full_reach_v3`，点底部「播放」观看约 18 秒的完整过程。可暂停、拖到任意时刻、重播，或点「跳到漫岸洪峰」固定在 22.5 小时。在侧栏点「城区低地 A」或「城区低地 B」查看近景和点位过程。可改用 0.5×、1×、2×、4×、8×进行分段观察；1×的设计历时为 144 秒。「水动力情景」可以切回原方案 v2。[独立的「陆地淹没」连续演示](http://127.0.0.1:5173/?demo=land-flood)沿用原有 12 秒流程。

运行使用真实地表 DEM 和假设的河床、糙率、入流、尾水与边界条件。背景为 2024 年 9 月洪水，求解独立使用合成来水，CHM_PRE 降雨仅用于历史展示。该情景面向课程演示。静态 85 m 情景相对 75 m 的 109.13 km² 属于另一套等水位假设，二维试算及验收独立进行。

## 二、基线诊断与试算

v2 峰值新增陆地湿区约 2.13 km²。固定 v2 地形、网格、河槽过渡、侧界及湿深门槛，分别修改边界过程，以检查改善幅度。三组初始试算及一组补充试算从 v2 预热末状态启动，展示 42 h，W→E 是情景约定。下表东端逆向量按输出区间累积净通量的反向部分求和。

| 短试算 | 修改项 | 峰值时刻 | 峰值新增 ≥0.05 m | 峰值新增 ≥0.10 m | E 端累计区间净逆向量 |
| --- | --- | ---: | ---: | ---: | ---: |
| W 峰值增强 | W 端来流洪水增量 ×3 | 22.5 h | 21.70 km² | 20.68 km² | 0 m³ |
| 延长 W 来水 | W 端相对基流的过程时距 ×1.3 | 25.0 h | 2.25 km² | 2.23 km² | 2610 万 m³ |
| E 尾水增强 | E 端尾水涨幅 ×1.6 | 23.5 h | 5.90 km² | 5.68 km² | 6997 万 m³ |
| E 尾水延后 | E 端尾水过程平移 3 h，水位涨幅沿用 v2 | 26.0 h | 1.98 km² | 1.95 km² | 94 万 m³ |

全程版采用第一个方案。W 端基流为 409 m³/s，合成洪峰由 4000 改为 11,182 m³/s。E 侧尾水沿用 v2 过程，按 EGM2008 为 58.816～68.816 m。完整模拟含 36 h 预热及 60 h 展示，每 30 分钟输出。复用 33.682 km 主线、286.849 km² 计算域和 11,654 个模型单元。导出的网格与定位索引与 v2 逐字节一致。该敏感性结果说明，在现有网格和地形下，增强合成 W 来水足以形成明显漫岸；E 尾水单独增强会引入较大的端界反向量。源 DEM 和两岸床高均沿用 v2。[试算目录](../outputs/full_reach_overbank_v1/trials/)、[最终参数](../data/processed/hydrodynamics/runs/full_reach_v3/parameters.json)

## 三、陆地扩散、退水和连通证据

固定 v2 理想河槽及过渡带，统计其外部在展示 0 h 水深小于 0.05 m、且当前达到指定湿深门槛的单元面积。峰值时刻为两岸新增湿区面积最大的输出时刻。模型中仍有积水的单元在退水阶段保持显示。

| 同口径比较 | v2 | v3 |
| --- | ---: | ---: |
| 16 h 新增 ≥0.05 m | 0.86 km² | 2.42 km² |
| 峰值时刻 | 22.5 h | 22.5 h |
| 峰值新增 ≥0.05 m | 2.13 km² | **21.70 km²** |
| 同时刻新增 ≥0.10 m | 2.12 km² | **20.68 km²** |
| 60 h 新增 ≥0.05 m | 0.13 km² | 7.66 km² |
| 峰值至 60 h 回落 ≥0.05 m | 2.00 km² | **14.03 km²** |

19 h 首个达到湿深门槛的城区代表点分别位于主线两侧。以与求解器一致的通量公式重建该输出时刻模型相邻单元面通量，沿方向连续的湿格追踪至主河槽。两条证据路径的域内通量均由河槽流向陆地，路径长约 1.55、1.84 km。路径首次越过理想河槽及过渡带的网格面，重建净出流分别约 686 和 287 m³/s。通量为保存时刻的诊断结果，空间尺度受原网格约束。两点均至少连续两帧水深 ≥0.10 m，60 h 回落至湿深门槛以下。研究区其他位置仍有 7.66 km² 的新增湿区。

| 代表点 | 经度、纬度 | 0 h 水深 | 19 h 水深 | 22.5 h 水深／流速 | 60 h 水深 |
| --- | --- | ---: | ---: | ---: | ---: |
| 城区低地 A | 108.30935° E, 22.79696° N | 0 m | 0.43 m | 1.07 m／0.04 m/s | 0.0003 m |
| 城区低地 B | 108.29563° E, 22.82107° N | 0 m | 0.40 m | 1.37 m／0.12 m/s | 0.0087 m |

完整展示期 W 端入水、E 端净出水、侧界净流出约 6.794、5.062、1.571 亿 m³。E 端展示期各 30 分钟输出区间均未记录净反向通量。整体水量相对误差最大约 `3.01e-14`，最大流速 2.82 m/s，最小原始水深为 0 m，无体积修正；预热末段蓄量变化约 0.175%，通量不平衡约 1.54%。静水和溃坝干湿转换回归通过。121 帧网页 `h/stage/u/v` 与求解原始帧按 32 位导出规则逐值核对，并校验网页文件指纹。水位均沿用 EGM2008；模型为教学情景，网格无法解读单栋建筑或道路阻隔，也未经过实测洪水标定。[求解台账与检验](../data/processed/hydrodynamics/runs/full_reach_v3/validation.json)、[独立漫岸证据及完整路径](../data/processed/hydrodynamics/runs/full_reach_v3/independent_overbank_validation.json)

## 四、浏览器对照

- 固定卫星视角：[初始 0 h](../outputs/full_reach_overbank_v1/browser_acceptance_v1/base.png)、[涨水 16 h](../outputs/full_reach_overbank_v1/browser_acceptance_v1/rising.png)、[洪峰 22.5 h](../outputs/full_reach_overbank_v1/browser_acceptance_v1/peak.png)、[退水 60 h](../outputs/full_reach_overbank_v1/browser_acceptance_v1/recession.png)。
- 城区低地 A：[初始](../outputs/full_reach_overbank_v1/browser_acceptance_v1/land-6838-base.png)、[洪峰](../outputs/full_reach_overbank_v1/browser_acceptance_v1/land-6838-peak.png)。
- 城区低地 B：[初始](../outputs/full_reach_overbank_v1/browser_acceptance_v1/land-10193-base.png)、[洪峰](../outputs/full_reach_overbank_v1/browser_acceptance_v1/land-10193-peak.png)。
- [全河段快速播放录屏](../outputs/full_reach_overbank_v1/browser_acceptance_v1/overbank-replay.webm)。
- 城区 A、B 首次达到 0.05 m 的全景同镜头记录见[19 h 城区漫岸](../outputs/full_reach_overbank_v1/browser_acceptance_v1/first-city-overbank.png)。

Edge 浏览器实测快放 18.03 秒走完 60 h，符合 15–24 秒目标。桌面 1920×1080 在本地底图、标准画质、1×播放下连续测量 120 秒，Cesium 平均 131.79 fps。本次本机拖动的五次样本从提交到模型帧显示用时约 40–52 毫秒。测量环境为本机 Edge 自动化，设备、底图和缓存状态会影响表现。

前端 `npm.cmd run build` 通过。自然、水深、流速样式切换以及底图饱和度恢复通过，重播和切到后台自动暂停通过。暂停时画面保持静止，跨时刻跳转后保留各运行自身的初始湿区，跳转及快放会使首帧按正常缓存策略淘汰。主动阻断一帧后，时间保持在上一有效帧并可重试。记录中有一条刻意断帧造成的网络错误，未观察到 WebGL 错误。切换 v2/v3 均只有一套水面和跟踪点，退出时两项绘制资源释放。v2 配色和底图恢复回归通过；S01–S11、CHM_PRE 及「陆地淹没」独立模式回归通过，独立全程实测 12.03 秒，2× 6.03 秒。[主验收记录](../outputs/full_reach_overbank_v1/browser_acceptance_v1/checks.json)、[交互和底图](../outputs/full_reach_overbank_v1/browser_acceptance_v1/interaction.json)、[v2 回归](../outputs/full_reach_overbank_v1/v2_palette_regression/checks.json)、[静态连续演示回归](../outputs/full_reach_overbank_v1/static_replay_regression/checks.json)

## 五、数据完整性与项目变更

本次按已有清单复核 582 个不同文件的 SHA256，全部吻合，涵盖原始 DEM、Phase 2/3、C03、全河段准备成果、S01–S11 网页图层、独立连续演示及 v2、v3 帧。v2 和先前受保护的 329 个文件全部匹配。保留工作区既有修改。[核对记录](../outputs/full_reach_overbank_v1/data_protection.json)

- 新情景输入与离线工具见[试算设定](../data/scenarios/overbank_trials_v1.json)、[试算入口](../scripts/run_overbank_hydro.py)、[发布门槛校验](../scripts/verify_overbank_result.py)、[浏览器验收](../scripts/verify_overbank_browser.mjs)。尾水延后 3 小时为补充试算，单独保留参数与台账。
- 前端在现有地图模式增量接入运行选择、精确新增面积、重点低地查询和快放。模型帧、地形和缓存随版本隔离；快放跟踪点保持模型流向，给单次渲染推进设置上限，避免跳过干湿边界。
- 本阶段的模型峰值和面积基于合成来水；街区近景仍受现有网格颗粒度限制，建筑、局地道路和管网对洪水的影响未标定。60 h 仍有残余积水，可在退水截图核对。
