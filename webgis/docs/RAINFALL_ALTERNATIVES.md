# 南宁洪水课程设计替代降雨数据对比

采用结果（2026-11-23）：用户已接受日尺度并选择国内团队产品。正式降雨改为 CHM_PRE V2，目标研究区子集已获取并验收，详见 [当前数据报告](PHASE0_DATA_REPORT.md)和 [CHM_PRE 验证结果](chm_pre/validation.json)。以下内容保留为采用前的检索记录，不代表当前下载状态。

检查日期：2026 年 11 月 23 日。范围为 Phase 0 的来源检索与小样本可用性验证，不替换 PROJECT_SPEC.md 中的 IMERG 首选方案，不代表降雨数据整体验收完成。

## 结论

有其他真实来源可选。国内团队的 CHM_PRE V2 适合日尺度格点分析；Open-Meteo 提供的固定 ERA5 逐小时数据已通过小样本接口验证，获取最方便；CHIRPS v3 可作为卫星与站点融合的日尺度栅格备选。三者均不能直接精确决定邕江水位。

| 来源 | 数据性质 | 分辨率与时间 | 实际检查结果 | 适用与限制 |
|---|---|---|---|---|
| CHM_PRE V2，仓储版本 V2.1.1 | 北京师范大学团队制作的多站观测和协变量驱动的格点降水，属于估计产品，不是逐站原始实测 | 0.1°，逐日；2024 年文件已列出 | Zenodo 公开 API 返回版本、文件名、674,638,949 字节及 MD5；文件的 1 KB 范围探测遇到 TLS 错误，未取得完整文件 | 优先考虑的国内团队产品；全年约 674.6 MB，尚未下载或验证变量、缺失值及日界线；不能提供小时过程 |
| Open-Meteo ERA5 | ERA5 再分析，通过公开历史 API 分发 | 固定 ERA5 0.25°，逐小时 | 不带密钥取得约 5.5 KB 响应；八天对应 192 个完整小时段，时间、空值、非负检查通过 | 适合先验证历史降雨曲线；单个粗网格不是研究区面平均，也不是雨量站观测 |
| CHIRPS v3 Final sat | 卫星与站点融合格点产品；每日分配使用 IMERG Late V07 | 0.05°，逐日 | 官方目录实际列出 2024-09-06 至 2024-09-13 的 8 个 GeoTIFF；尚未下载栅格或核实下载总体积 | 可做日尺度空间展示和累计；不能重建半小时变化，日期标签不等同于统一的北京时间观测日 |
| GSMaP | JAXA 卫星降雨产品 | 可提供逐小时产品 | 官方下载说明要求注册；本轮未登录、未取数据 | 有小时尺度，但仍需账号，不能解决当前免注册需求 |
| NOAA GSOD | 站点日统计产品 | 逐日 | 本轮没有确认可用的南宁站点文件 | 不将未确认的站点当成已可用替代；即便取得也需核实位置、缺失值、统计时段及降雨单位 |

## 已验证的 ERA5 试样

- 请求位置：22.79°N、108.335°E；服务实际返回网格中心为 22.75°N、108.25°E。必须使用返回坐标记录来源，不能把请求位置写成实测站位置。
- 固定模型参数 `models=era5`，避免默认 Best Match 混合不同模型。
- 目标累计时段为北京时间 `[2024-09-06 00:00, 2024-09-14 00:00)`。
- 官方文档定义小时降水为此前一小时的累计量。因此读取结束标签从 9 月 6 日 01:00 至 9 月 14 日 00:00 的记录，共 192 个小时段，不能直接累计 9 月 6 日 00:00 至 9 月 13 日 23:00 的标签。
- 实际检查：192 个小时段连续，空值 0，负值 0，单位为 mm。上述结果只证明本次试样在这些基础检查中通过，没有验证其极端降雨精度。
- [原始扩展响应](rainfall_alternatives/open_meteo_era5_extended_response.json)、[对齐后小时段](rainfall_alternatives/open_meteo_era5_aligned_intervals.json)、[验证结果](rainfall_alternatives/detail_checks.json)。
- 原始扩展响应 SHA256：`8a3e9c666ba6367edc03502e748f4b9976e785caacb2ca0be185da96e65f0929`。

试样仅保存在 docs/rainfall_alternatives，供比较复核；尚未作为正式原始降雨数据纳入 data/raw/rainfall。研究区跨越的相关网格、面积权重与完整质量检查留待确定替代方案后处理。不把一个格点直接当成区域平均，更不重采样虚构 30 m 降雨精度。

## CHM_PRE 文件及版本

- 数据记录：[Zenodo 20378336](https://zenodo.org/records/20378336)，版本 V2.1.1，许可证由 API 返回为 CC BY 4.0。
- 文件：`CHM_PRE_V2_daily_2024.nc`，674,638,949 字节（约 674.6 MB）。
- 仓储提供的 MD5：`3360750e943c9372761b8cf0bc6f2fa2`。这是待下载时比对的参考值，本轮没有宣称完成文件哈希校验。
- [保存的官方元数据](rainfall_alternatives/chm_pre_2024_metadata.json)及[文件范围探测结果](rainfall_alternatives/chm_pre_file_probe.json)。
- [国内数据中心发布说明](https://cms.casdc.cn/article/912)确认了国内团队和覆盖 2024 年的产品；[原论文](https://essd.copernicus.org/articles/17/3987/2025/index.html)描述的初始年份范围与持续更新仓储不同，应以选定仓储版本和文件为准。

本轮只下载元数据，没有下载约 674.6 MB 的年度文件。若采用此方案，须先核实日累计定义、坐标、变量单位、缺失值和研究区覆盖；逐日数据的时间轴只能诚实表达日尺度变化。

## CHIRPS 版本与日期限制

旧版 CHIRPS-2.0 目录本次返回 404，另一次根目录请求返回 429，故改查官方当前 v3 路径，没有反复请求旧路径。

- [CHIRPS v3 官方说明](https://www.chc.ucsb.edu/data/chirps3)。
- [2024 年 Final sat 目录](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/2024/)及[保存的目录响应](rainfall_alternatives/chirps3_2024_index.html)。
- `chirps-v3.0.sat.2024.09.06.tif` 至 `chirps-v3.0.sat.2024.09.13.tif` 均已在目录找到，未把目录存在当成栅格已下载或验收。

CHIRPS v3 官方说明指出：日尺度来自对五日累计量的分配，sat 使用 IMERG Late V07，rnl 使用 ERA5；其日期是统一处理中的标签，不能假定所有站点共享一致的观测日窗口。因此无法直接用八个日文件精确替代当前定义的北京时间八天小时累计。

## 建议

如果课程允许逐日降雨过程并优先国内研究成果，先进一步验证 CHM_PRE。若希望免账号快速验证小时降雨曲线，可选择已验证试样的 ERA5，并明确标注再分析来源和较粗空间网格。若保留半小时卫星降雨要求，继续取得 IMERG Final 仍最符合原需求，不能把日数据插值成半小时实测。

目前不修改 PROJECT_SPEC.md，不勾选“搜索并下载历史降雨”或综合质量验收任务。确认具体替代方案后，再记录替换原因、获取正式文件并更新报告。

## 官方参考与复现

- [Open-Meteo 历史 API](https://open-meteo.com/en/docs/historical-weather-api)：ERA5 网格、模型选择及此前一小时累计定义。
- [GSMaP 用户指南](https://sharaku.eorc.jaxa.jp/GSMaP/guide.html)及[注册说明](https://sharaku.eorc.jaxa.jp/GSMaP/registration.html)。
- 检索脚本：`scripts/phase0_check_rainfall_alternatives.py`、`scripts/phase0_check_rainfall_details.py`。只使用本机已有 Python 标准库和 curl，没有安装新依赖。
- 本次各请求和错误记录位于 docs/rainfall_alternatives。在线服务可发生目录调整、限流或临时网络错误，重新运行可能得到不同可访问性结果。
