# 真实 DEM 三维预览

日期：2026-11-23。用户要求查看导入DEM之后的三维影像，本轮只提前实现Phase 4中的DEM地形展示。Phase 3洪水分析未开展，Phase 4其余项也未勾选。

## 展示方式

Cesium使用本机已有的CustomHeightmapTerrainProvider和HeightmapTerrainData，读取真实FABDEM v1.2原生高程。卫星影像仍为Esri World Imagery，贴在由高程构造的网格上；不使用Three.js进行地形计算，不新增依赖、不下载新数据、不需要Cesium ion密钥。

导出的原生网格为1189列×793行，包含研究区及外围浏览缓冲，约108.17–108.50°E、22.68–22.90°N。Float32高程文件为3,771,508字节。导出不重采样，每个像元与原始GeoTIFF逐值相同；浏览器以双线性方式为Cesium采样65×65节点瓦片，最高真实瓦片层级13。显示插值不提高约30m源数据精度。

默认相机观察青秀山附近，起伏比例1×，没有夸大高程。侧栏“查看地形近景”可返回该位置；“定位研究区”返回全区，二维/三维及底图切换保留。没有恢复用户已要求移除的研究区边框。

页面保留Cesium、在线影像、FABDEM作者与许可标注。导出的NOTICE.txt和LICENSE.txt直接复制原始数据附带说明，保留Copernicus来源声明及CC BY-NC-SA 4.0许可。该数据仍按课程非商业用途使用。

## 高程与范围限制

FABDEM源高程为EGM2008，Cesium网格通常使用椭球高。本轮没有取得可靠的大地水准面转换格网，未编造固定偏移量，直接将源值用于地形形态预览并在页面明确注明。该预览存在绝对高程基准偏差，不能用于精密三维叠合、准确椭球高读取或水位判断。计算用GeoTIFF不受此次展示修改影响。

导出范围以外返回零高程，不代表范围外真实地形；边缘可能出现接缝。默认近景和计算研究区均在真实覆盖范围内部。卫星影像没有认定为2024年洪水期间拍摄；FABDEM移除了大部分建筑和林冠影响，不会生成城市三维建筑，也不是水下河床数据。

## 复现与检查

项目根目录PowerShell：

```powershell
$env:PATH = 'D:\Arcgis10.8.2\bin;' + $env:PATH
$env:GDAL_DATA = 'D:\Arcgis10.8.2\apps\gdal\share\gdal'
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\Arcgis10.8.2\apps\Python312\python.exe' '.\scripts\export_dem_terrain.py'
node '.\scripts\verify_dem_terrain.mjs'
npm.cmd run build --prefix frontend
```

运行JavaScript检查前保持5173前端启动，检查脚本通过本机HTTP读取同一份地形文件。生成文件位于frontend/public/terrain，构建时Vite会复制到dist/terrain，无需后端加载GDAL。

实际结果：

- 导出后原始DEM的SHA256未变；高程二进制回读与原始像元逐值一致，见[导出检查](terrain_export_checks.json)。
- 14项运行检查通过：源节点位置、四点插值、范围外值、Cesium瓦片高程、末级子瓦片、相邻边界连续、真实HTTP加载、404、长度错误、哈希错误，见[运行检查](terrain_runtime_checks.json)。
- 前端生产构建通过。
- 实际浏览器中显示“FABDEM 已加载 · 起伏比例 1×”，卫星影像与山体起伏可见。地图瓦片待加载数为0，实际渲染网格在108.3939°E、22.7908°N的查询高程约288.22m；源网格双线性采样约288.90m，差异来自显示瓦片采样和三角网插值。这是预览源高程数值，不是已转换的真实椭球高。页面没有可见错误提示。
- 二维/三维切换未在本轮重新操作验收；本轮重点检查真实地形加载和当前三维近景。

![实际三维地图截图](../outputs/dem_3d_preview.png)

预览保留在本机[地图页面](http://127.0.0.1:5173/)，没有发布到公网或提交Git。后续洪水计算仍须单独确认，不将本次显示结果称为洪水模拟成果。
