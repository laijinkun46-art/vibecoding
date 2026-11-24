# 2024 年洪水背景下的陆地淹没连续演示

在[本机演示](http://127.0.0.1:5173/?demo=land-flood)选择「陆地淹没」。该演示由已有静态情景的教学假设水位构成，以 2024 年 9 月南宁洪水为背景。时间轴单位是演示秒。洪水位置和水位情景沿用已有分析，[全河段水动力情景](FULL_REACH_HYDRODYNAMIC_DELIVERY.md)在原入口独立运行。

## 静态结果如何连续显示

根据既有 30 m FABDEM、主河道种子和四邻域连通规则，从河道向可达像元计算通路上的最低阻挡高程。任意展示水位高于该高程时，才显示该像元为湿区。现有 S01–S11 的湿区栅格逐像元对照一致。以原 S01、S02、S03、S04 水位为四个锚点，水位在 75→80→85→78 m 之间连续变化。85 m 洪峰短暂停留约 0.72 秒，方便观察。时间和水位用于教学情景，历史水文过程需要独立的观测资料。

渲染继续使用唯一 Cesium 场景和现有地形。地形上的蓝色图层读取同一份连通阈值，按当前水位增减覆盖。暗绿表示 75 m 初始湿区，蓝色表示该范围以外当前的湿区。蓝色采用地形叠色，保留影像中的道路和街区纹理。图层只展示现有研究区；洪峰局部直边对应分析范围边缘。面积由原投影栅格统计。陆地近景受 30 m 源数据限制，实际渲染会在边缘做窄范围渐隐。

## 浏览器验收

同一卫星镜头、1920×1080、Edge 实测。水位基准为 EGM2008，面积单位为 km²。

| 演示时刻 | 水位 | 全域湿区 | 相对 75 m 新增湿区 | 画面 |
| --- | ---: | ---: | ---: | --- |
| 0 s 基流 | 75 m | 23.7168 | 0.0000 | [基流](../outputs/stage_replay_v1/browser/base.png) |
| 3.84 s 涨水 | 80 m | 101.2095 | 77.4927 | [涨水](../outputs/stage_replay_v1/browser/rising.png) |
| 7.2 s 洪峰 | 85 m | 132.8472 | 109.1304 | [洪峰](../outputs/stage_replay_v1/browser/peak.png) |
| 12 s 退水末帧 | 78 m | 80.4600 | 56.7432 | [退水](../outputs/stage_replay_v1/browser/recession.png) |

生产构建通过。浏览器验证了连续水位、拖动、暂停冻结、重播、静态与水动力模式切换以及旧水动力新增的 4×、8× 倍率选项。1× 完整播放 12.03 秒，2× 为 6.03 秒。截图对照的蓝色判定像素从基流 433 增至洪峰 235,604，退水减少至 116,322，仅作画面变化验证。未见页面或 WebGL 错误。[实测记录](../outputs/stage_replay_v1/browser/checks.json) · [12 秒动态录屏](../outputs/stage_replay_v1/browser/stage-replay.webm)

## 复现与来源

[资产准备脚本](../scripts/prepare_stage_replay.py)复用已验收地形和静态结果，生成独立的[阈值纹理、面积和来源清单](../frontend/public/analysis/stage_replay_v1/manifest.json)。[Cesium 地形材质](../frontend/src/stageReplay.js)与[时间控制](../frontend/src/components/StageReplayControls.vue)处理连续展示。[浏览器验收脚本](../scripts/verify_stage_replay.mjs)保留同视角截图、播放时长和录屏，可在现有 Playwright 环境设置新 `STAGE_REPLAY_OUTPUT` 目录后复验。
