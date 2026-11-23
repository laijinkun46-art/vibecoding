"""Phase 2 GIS 公用函数；坐标顺序统一为经度、纬度或东、北。"""
import hashlib
import json
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
NODATA = -9999.0


def spatial_ref(epsg):
    """输入 EPSG 编号，返回采用传统 GIS 轴顺序的坐标参考系。"""
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(epsg)
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


def transform_geometry(geometry, source_epsg, target_epsg):
    """输入 OGR 几何及源/目标 EPSG，返回转换后的副本，不修改输入。"""
    result = geometry.Clone()
    result.Transform(osr.CoordinateTransformation(spatial_ref(source_epsg), spatial_ref(target_epsg)))
    return result


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def valid_pixels(dataset):
    """输入单波段 GDAL 数据集，返回数组及排除 NoData/非有限数的掩膜。"""
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray()
    valid = np.isfinite(values)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        valid &= values != nodata
    return values, valid


def write_grid(path, values, reference, nodata, unit, description):
    """按参考栅格的网格写出单波段 GeoTIFF；不改变数值或坐标。"""
    kind = gdal.GDT_Byte if values.dtype == np.uint8 else gdal.GDT_Float64
    output = gdal.GetDriverByName('GTiff').Create(str(path), reference.RasterXSize, reference.RasterYSize,
                                               1, kind, options=['COMPRESS=DEFLATE', 'TILED=YES'])
    output.SetGeoTransform(reference.GetGeoTransform())
    output.SetProjection(reference.GetProjection())
    band = output.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.SetUnitType(unit)
    band.SetDescription(description)
    band.WriteArray(values)
    output.FlushCache()
    return output


def geometry_mask(geometries, reference, all_touched=False):
    """将同一坐标系几何烧入参考网格，返回 0/1；河流可选择所有触及像元。"""
    vector = ogr.GetDriverByName('MEM').CreateDataSource('')
    layer = vector.CreateLayer('geometry', srs=reference.GetSpatialRef(), geom_type=ogr.wkbUnknown)
    for geometry in geometries:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)
    raster = gdal.GetDriverByName('MEM').Create('', reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Byte)
    raster.SetGeoTransform(reference.GetGeoTransform())
    raster.SetProjection(reference.GetProjection())
    raster.GetRasterBand(1).Fill(0)
    gdal.RasterizeLayer(raster, [1], layer, burn_values=[1], options=['ALL_TOUCHED=TRUE'] if all_touched else [])
    return raster.ReadAsArray()
