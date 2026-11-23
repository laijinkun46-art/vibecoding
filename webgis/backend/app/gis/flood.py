"""DEM与主河道连通约束的静态等水位情景；不是水动力模型或洪水预报。"""
from collections import deque

import numpy as np

DEPTH_NODATA = -9999.0


def connected_inundation(dem, valid, river_seeds, water_level_m, connectivity=4):
    """输入同网格DEM(m)、有效掩膜、河流种子及同基准水面高程(m)。

    输出(wet, depth)：布尔淹没掩膜及水深(m)，干地0、无效区-9999。
    仅从低于水面的有效主河道种子扩展，排除不连通低洼地。
    默认四邻域，避免从两个高地像元的对角缝隙穿过；可显式选择八邻域。
    """
    dem = np.asarray(dem, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    river_seeds = np.asarray(river_seeds, dtype=bool)
    if dem.ndim != 2 or dem.shape != valid.shape or dem.shape != river_seeds.shape:
        raise ValueError('DEM、有效区和河流种子必须为同尺寸二维数组')
    if not np.isfinite(water_level_m) or not np.isfinite(dem[valid]).all():
        raise ValueError('水位与有效 DEM 高程必须为有限数')
    if connectivity not in (4, 8):
        raise ValueError('连通邻域仅支持4或8')
    if not (river_seeds & valid).any():
        raise ValueError('有效区内没有河流种子')
    candidate = valid & (dem < water_level_m)
    wet = river_seeds & candidate
    queue = deque(map(tuple, np.argwhere(wet)))
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    height, width = dem.shape
    while queue:
        row, col = queue.popleft()
        for dr, dc in offsets:
            nr, nc = row + dr, col + dc
            if 0 <= nr < height and 0 <= nc < width and candidate[nr, nc] and not wet[nr, nc]:
                wet[nr, nc] = True
                queue.append((nr, nc))
    depth = np.full(dem.shape, DEPTH_NODATA, dtype=np.float64)
    depth[valid] = 0
    depth[wet] = water_level_m - dem[wet]
    return wet, depth


def inundation_statistics(wet, depth, cell_area_m2):
    """输入淹没掩膜、水深与平面像元面积，返回面积、水深、静态水柱体积统计。"""
    wet, depth = np.asarray(wet, dtype=bool), np.asarray(depth)
    if wet.shape != depth.shape or not np.isfinite(cell_area_m2) or cell_area_m2 <= 0:
        raise ValueError('统计输入尺寸或像元面积不正确')
    values = depth[wet]
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('淹没像元水深必须为有限正数')
    return {'wet_pixels': int(wet.sum()), 'area_km2': float(wet.sum() * cell_area_m2 / 1e6),
            'mean_depth_m': float(values.mean()) if values.size else 0.,
            'max_depth_m': float(values.max()) if values.size else 0.,
            'water_column_volume_m3': float(values.sum() * cell_area_m2)}


def detect_change(before, after, valid):
    """输入同网格两期布尔淹没范围，输出分类：0均干、1新增、2持续、3退水、255无效。"""
    before, after, valid = [np.asarray(value, dtype=bool) for value in (before, after, valid)]
    if before.ndim != 2 or before.shape != after.shape or before.shape != valid.shape:
        raise ValueError('两期范围与有效掩膜必须同网格')
    if ((before | after) & ~valid).any():
        raise ValueError('两期淹没范围不得超出有效区')
    result = np.full(before.shape, 255, dtype=np.uint8)
    result[valid] = 0
    result[valid & ~before & after] = 1
    result[before & after] = 2
    result[before & ~after] = 3
    return result
