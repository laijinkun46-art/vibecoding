# 邕江全河段洪水配色方案一

版本 1.0，日期 2026 年 11 月 24 日（北京时间）。适用范围为全河段模拟的自然水面显示，既有 `full_reach_v2` 教学情景。

- 上位文档（被包含于）为[水面视觉优化项目执行规范](CONSTRAINT_WATER_SURFACE_EXECUTION_20261124.md)和[水面视觉优化方案](CONSTRAINT_WATER_SURFACE_VISUALS_20261124.md)。
- 总体范围见[全河段总规范](YONGJIANG_HYDRODYNAMIC_SIMULATION_SPEC.md)。下位文档暂无。
- 关联资料为[全河段建模交付报告](FULL_REACH_HYDRODYNAMIC_DELIVERY.md)和[既有水面优化验收](../outputs/hydro_water_visuals_v1/REVIEW.md)。本规范更新自然样式的分类、图例和底图色调，保留上位方案关于定量色标、地形遮挡和湿区限制的条款。

## 分类与参数

以预热结束后的首个展示时刻（0 小时）固定初始湿区。水深在相邻帧之间插值，湿深门槛读取清单，本情景为 0.05 m。当前仍湿的初始单元为暗绿，初始干燥而当前湿润的单元为青蓝，低于门槛、无效或域外时不绘水。初始标记独立于帧缓存，退出动态模式时销毁附属绘制缓冲。

| 显示项目 | 最终参数 |
| --- | --- |
| 初始湿区 | 暗绿 `#355C57` 至深绿 `#1F4540`，样式透明度系数 0.80–0.92 |
| 当前新增淹没 | 浅水 `#36B6DC` 至深水 `#165B98`，样式透明度系数 0.82–0.94 |
| 推进前缘 | `#B0E8F5`，岸内最宽 8 m，混色权重上限 0.32；仅用于相邻帧水深上升的新增湿单元 |
| 自然样式底图 | 卫星饱和度 0.60，亮度 1.00；本地和街道饱和度 0.72 |
| 定量与静态底图 | 卫星还原至饱和度 0.91、亮度 1.16、伽马 1.12、对比度 1.02；本地和街道还原为 1.00 |

光照、波纹和透明度会改变截图的实际像素颜色。暗绿代表模型初始湿区，现有卫星影像中可见的水面属于底图本身。洪峰时新淹色带的范围由模型决定；它与实际河岸的关系还受假设河床和现有模型网格限制。

## 部分补丁的处理

保留并核对了原有五处补丁。 `hydroData.js` 保留独立的首帧湿区标记并补充清单门槛核验。 `hydroRender.js` 保留固定单元属性，压缩为每顶点 1 字节，并接入原有销毁流程。 `hydroWaterShaders.js` 统一颜色参数，仅对正在涨水的新增湿区做岸内提亮。 `HydroControls.vue` 图例与着色共享颜色源，补充初始时刻说明。 `MapViewer.vue` 依据实际已挂载的底图恢复色调，保留原播放器、点位查询、波纹和水面几何。

## 验收结果

在 `frontend` 运行了 `npm.cmd run build`。使用本机 Edge 和相同的「漫岸近景」卫星镜头检查四个原输出时刻。面积由原模型单元面积统计，以下数值单位均为 km²。

| 时刻 | 初始湿区中当前仍湿 | 当前新增淹没 | 全域湿区 | 同视角截图 |
| --- | ---: | ---: | ---: | --- |
| 0 h 基流 | 7.494 | 0.000 | 7.494 | [基流](../outputs/hydro_flood_palette_v1/browser/base.png) |
| 16 h 涨水 | 7.494 | 4.002 | 11.496 | [涨水](../outputs/hydro_flood_palette_v1/browser/rise.png) |
| 22.5 h 洪峰 | 7.494 | 5.879 | 13.373 | [洪峰](../outputs/hydro_flood_palette_v1/browser/peak.png) |
| 60 h 退水末帧 | 7.494 | 0.855 | 8.349 | [退水](../outputs/hydro_flood_palette_v1/browser/recession.png) |

两个岸外抽查单元在洪峰显示青蓝，末帧均恢复到底图颜色；持续湿润的抽查单元在四个时刻均为暗绿。首帧退出缓存后，重播、暂停及再次拖回洪峰仍能复核同一分类。暂停期间同一相机的 Cesium 截图没有改变。检查了水深、流速、自定义图例、卫星与本地底图切换。退出动态后，原静态图层和 11 档水位可用，CHM_PRE 降雨正常，水面纹理及初始标记缓冲释放，场景绘制对象由 3 个恢复为 1 个。验收未观察到页面或 WebGL 错误。[浏览器记录](../outputs/hydro_flood_palette_v1/browser/checks.json)

在两帧之间抽查同一新增湿单元，插值水深从 0.04258 m 增至 0.06007 m，跨过同一 0.05 m 门槛。[帧间检查](../outputs/hydro_flood_palette_v1/interpolation.json)

核对了 329 个模型和来源文件的 SHA256，其中包含清单登记的 123 个网页资产；另比对了 4 个固定点位接口响应，包括域外查询。全部一致。洪峰和退水抽查读数及原时刻面积一致。[文件与查询指纹](../outputs/hydro_flood_palette_v1/protection-baseline.json)

受现有求解网格限制，贴近水面时仍可见初始与新增的个别单元折线。洪峰时，理想河槽及其过渡带之外的湿区较初态增加约 2.128 km²。退水末帧剩余 0.855 km² 的青蓝属于模型仍湿的单元。

## 动态录屏

[观看完整涨水、漫岸与退水录屏](../outputs/hydro_flood_palette_v1/recording/全河段涨水漫岸退水.webm)。在已有卫星底图上以 2× 播放完整 60 小时模型过程，实际录制约 74 秒，画幅 1580×960。第 2、24、45、61 秒均通过解码抽查。[录屏记录](../outputs/hydro_flood_palette_v1/recording/video.json) · [全河段洪峰视图](../outputs/hydro_flood_palette_v1/recording/satellite-full-peak.png)

可在项目根目录以现有 Playwright 环境运行 `node scripts/verify_hydro_palette.mjs`。先设置 `HYDRO_TEST_OUTPUT` 指向独立验收目录；重跑时可用 `HYDRO_PALETTE_CAPTURE` 指定新子目录。应用只在本机服务。[本机预览](http://127.0.0.1:5173/)
