"""绘制真实处理成果的静态检查图，不包含洪水模拟。"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from osgeo import gdal, ogr
from phase2_process import ROOT, OUT
from gis_processing import valid_pixels

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
for ax, filename, title, cmap, label in zip(axes.flat[:3],
        ['dem_utm49n_30m.tif', 'slope.tif', 'hillshade.tif'],
        ['真实 DEM 与当前河流中心线', 'Horn 坡度', '地形阴影（非卫星影像）'],
        ['terrain', 'YlOrRd', 'gray'], ['高程 / m（EGM2008）', '坡度 / °', '阴影强度']):
    raster = gdal.Open(str(OUT / filename))
    values, valid = valid_pixels(raster)
    gt = raster.GetGeoTransform()
    extent = [gt[0], gt[0]+gt[1]*raster.RasterXSize, gt[3]+gt[5]*raster.RasterYSize, gt[3]]
    image = ax.imshow(np.ma.masked_where(~valid, values), extent=extent, cmap=cmap, interpolation='nearest')
    ax.set_title(title)
    ax.set_xlabel('东坐标 / m（UTM 49N）')
    ax.set_ylabel('北坐标 / m')
    ax.ticklabel_format(style='plain', useOffset=False)
    fig.colorbar(image, ax=ax, fraction=.046, pad=.04, label=label)
    if filename.startswith('dem_'):
        source = ogr.Open(str(OUT / 'rivers_utm49n.gpkg'))
        for feature in source.GetLayer(0):
            geometry = feature.GetGeometryRef()
            lines = [geometry] if geometry.GetGeometryName() == 'LINESTRING' else list(geometry)
            for line in lines:
                points = np.array(line.GetPoints())
                ax.plot(points[:, 0], points[:, 1], color='#007bcc', linewidth=1.1)
rain = json.loads((OUT / 'rainfall_timeseries.json').read_text(encoding='utf-8'))
days = rain['daily']
ax = axes[1, 1]
x = np.arange(len(days))
ax.bar(x, [row['mean_precip_mm'] for row in days], color='#298aab', label='逐日面平均')
ax.set_xticks(x, [row['date_label'][5:] for row in days])
ax.set_ylabel('单日降雨量 / mm')
ax.set_xlabel('2024 年产品日期（前一日20时至当日20时）')
second = ax.twinx()
second.plot(x, [row['cumulative_precip_mm'] for row in days], color='#c97820', marker='o', label='累计面平均')
second.set_ylabel('累计降雨量 / mm')
ax.set_title(f'CHM_PRE 原生格点面积加权（累计 {rain["total_precip_mm"]:.2f} mm）')
fig.suptitle('Phase 2 南宁邕江 GIS 数据处理检查', fontsize=17)
fig.text(.05, .025, 'FABDEM v1.2；CHM_PRE V2.1.1；© OpenStreetMap contributors（当前中心线）\n30 m 为分析网格，不提高源数据精度；降雨未细化；图中没有洪水淹没或真实灾时水面。', fontsize=10)
fig.tight_layout(rect=(0, .08, 1, .95))
fig.savefig(ROOT / 'outputs/phase2_processing_preview.png', dpi=150)
plt.close(fig)
print('outputs/phase2_processing_preview.png')
