"""绘制假设淹没及变化，标题明确区分课程情景与实测洪水。"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import numpy as np
from osgeo import gdal
from phase3_analyze import ROOT, INPUT, OUT

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
summary = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
dem = gdal.Open(str(INPUT / 'dem_utm49n_30m.tif'))
gt = dem.GetGeoTransform()
extent = [gt[0], gt[0]+dem.RasterXSize*gt[1], gt[3]+dem.RasterYSize*gt[5], gt[3]]
shade = gdal.Open(str(INPUT / 'hillshade.tif')).ReadAsArray()
fig, axes = plt.subplots(2, 2, figsize=(13, 10))
titles = ['75 m 假设情景范围（含现有河道）', '85 m 假设情景水深', '75 → 80 m 假设水位上升', '85 → 78 m 假设水位回落']
for ax, title in zip(axes.flat, titles):
    ax.imshow(np.ma.masked_equal(shade, 0), extent=extent, cmap='gray', vmin=0, vmax=255, interpolation='nearest', alpha=.6)
    ax.set_title(title)
    ax.set_xlabel('东坐标 / m（UTM 49N）')
    ax.set_ylabel('北坐标 / m')
    ax.ticklabel_format(style='plain', useOffset=False)
wet = gdal.Open(str(OUT / 'S01_wet.tif')).ReadAsArray()
axes[0, 0].imshow(np.ma.masked_where(wet != 1, wet), extent=extent, cmap=ListedColormap(['#228bcc']), interpolation='nearest')
axes[0, 0].legend(handles=[Patch(color='#228bcc', label='连通湿区')], loc='upper right')
depth = gdal.Open(str(OUT / 'S03_depth.tif')).ReadAsArray()
im = axes[0, 1].imshow(np.ma.masked_where(depth <= 0, depth), extent=extent, cmap='Blues', interpolation='nearest', vmin=0)
fig.colorbar(im, ax=axes[0, 1], fraction=.046, pad=.04, label='假设水面减 DEM / m')
colors = ['#23bfd0', '#2670ba', '#df8b36']
for ax, name in zip(axes[1], ['S01_to_S02', 'S03_to_S04']):
    values = gdal.Open(str(OUT / f'{name}_change.tif')).ReadAsArray()
    ax.imshow(np.ma.masked_where((values == 0) | (values == 255), values), extent=extent,
              cmap=ListedColormap(colors), norm=BoundaryNorm([.5, 1.5, 2.5, 3.5], 3), interpolation='nearest')
    ax.legend(handles=[Patch(color=color, label=label) for color, label in zip(colors, ['新增湿区', '持续湿区', '退水区域'])], fontsize=9, loc='upper right')
fig.suptitle('Phase 3 简化连通淹没试验——全部水位为假设，非2024实测或预报', fontsize=16)
fig.text(.05, .025, 'FABDEM v1.2 / EGM2008；当前 OSM 邕江种子；四邻域连通；面积含现有河道。\n不含水动力、实测河床、精细堤防或滞水过程；历史降雨未换算为情景水位。', fontsize=10)
fig.tight_layout(rect=(0, .08, 1, .94), h_pad=3.5)
fig.savefig(ROOT / 'outputs/phase3_scenario_preview.png', dpi=150)
plt.close(fig)
print('outputs/phase3_scenario_preview.png')
