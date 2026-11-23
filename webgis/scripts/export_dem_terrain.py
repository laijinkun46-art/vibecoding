"""将真实 FABDEM 的研究区及外围原生像元导出为浏览器可读高程网格。

只读原始文件；不重采样，不转换垂直基准，不生成洪水数据。
"""
import json
import shutil
from pathlib import Path

import numpy as np
from osgeo import gdal
from gis_processing import digest, save_json, valid_pixels

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/raw/dem/N22E108_FABDEM_V1-2.tif'
DEST = ROOT / 'frontend/public/terrain'


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE.parent / 'readme.txt', DEST / 'NOTICE.txt')
    shutil.copyfile(SOURCE.parent / 'license.txt', DEST / 'LICENSE.txt')
    before = digest(SOURCE)
    # 外围缓冲用于浏览地形；计算研究区和分析网格保持不变。
    crop = gdal.Translate('', str(SOURCE), format='MEM', projWin=[108.17, 22.90, 108.50, 22.68])
    values, valid = valid_pixels(crop)
    if not valid.all():
        raise ValueError('展示范围内 DEM 存在缺失，不以虚构高程填充')
    values = values.astype('<f4')
    grid = DEST / 'fabdem.f32'
    grid.write_bytes(values.tobytes(order='C'))
    gt = crop.GetGeoTransform()
    source = gdal.Open(str(SOURCE))
    sgt = source.GetGeoTransform()
    xoff = round((gt[0]-sgt[0])/sgt[1])
    yoff = round((gt[3]-sgt[3])/sgt[5])
    reread = np.fromfile(grid, dtype='<f4').reshape(values.shape)
    if not np.array_equal(reread, source.ReadAsArray(xoff, yoff, crop.RasterXSize, crop.RasterYSize)):
        raise ValueError('高程二进制回读与原始像元不一致')
    meta = {'source': 'FABDEM v1.2', 'horizontal_epsg': 4326,
            'vertical_datum': 'EGM2008 / EPSG:3855，未转换为椭球高，仅作地形形态展示',
            'width': crop.RasterXSize, 'height': crop.RasterYSize,
            'geotransform': list(gt), 'encoding': 'little-endian Float32, north to south row-major',
            'url': '/terrain/fabdem.f32', 'bytes': grid.stat().st_size,
            'sha256': digest(grid), 'source_sha256': before,
            'elevation_m': {'min': float(values.min()), 'max': float(values.max())},
            'credit': '<a href="/terrain/NOTICE.txt" target="_blank">FABDEM v1.2 · Hawker et al. · CC BY-NC-SA 4.0 · Copernicus</a>',
            'resampling': 'none on export; bilinear for Cesium display tiles',
            'outside_coverage': 'no DEM; globe height is zero outside the exported grid',
            'bounds_wsen': [gt[0], gt[3]+gt[5]*crop.RasterYSize, gt[0]+gt[1]*crop.RasterXSize, gt[3]]}
    save_json(DEST / 'metadata.json', meta)
    if before != digest(SOURCE):
        raise ValueError('源文件发生变化')
    save_json(ROOT / 'docs/terrain_export_checks.json', {'passed': True, 'native_values_exact': True,
              'raw_unchanged': True, 'metadata': meta})
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()
