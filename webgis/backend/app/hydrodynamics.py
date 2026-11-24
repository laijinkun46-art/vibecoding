"""Read-only distribution of validated offline result frames."""
import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

RUNS = Path(__file__).resolve().parents[2] / 'data/processed/hydrodynamics/runs'
router = APIRouter(prefix='/api/hydrodynamics', tags=['Hydrodynamics'])
RUN_ID = re.compile(r'full_reach_v[1-9][0-9]*')
ASSET = re.compile(r'(?:cells|index|[0-9]{4})\.bin')
CELL = struct.Struct('<ffff')
INDEX = struct.Struct('<I')


@lru_cache(maxsize=4)
def _read_manifest(path, modified_ns):
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data['status'] != 'ready' or data['schema'] != 1 or not data['frames']
            or data['observed'] is not False or data['validation']['pilot']):
        raise ValueError('results are not validated')
    return data


def _run(run_id):
    if not RUN_ID.fullmatch(run_id):
        raise HTTPException(404, '未知情景')
    folder = RUNS / run_id
    path = folder / 'manifest.json'
    try:
        if folder.resolve().parent != RUNS.resolve() or path.resolve().parent != folder.resolve():
            raise ValueError('invalid result path')
        return folder, _read_manifest(path, path.stat().st_mtime_ns)
    except FileNotFoundError as error:
        raise HTTPException(404, '情景尚未验收') from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(503, '情景成果清单不可用') from error


def _asset(folder, info, filename):
    if not ASSET.fullmatch(filename) or filename not in info['assets']:
        raise HTTPException(404, '未知资源')
    path = folder / 'web' / filename
    try:
        if path.resolve().parent != (folder / 'web').resolve() or path.stat().st_size != info['assets'][filename]['bytes']:
            raise ValueError('invalid asset')
    except (OSError, ValueError) as error:
        raise HTTPException(503, '情景资源缺失或损坏') from error
    return path


@router.get('/runs')
def runs():
    results = []
    for folder in sorted(RUNS.glob('full_reach_v*'), key=lambda p: p.name):
        try:
            _, data = _run(folder.name)
        except HTTPException:
            continue
        results.append({'id': folder.name, 'label': data['label'], 'observed': False})
    return results


@router.get('/runs/{run_id}/manifest')
def manifest(run_id: str):
    return _run(run_id)[1]


@router.get('/runs/{run_id}/assets/{filename}')
def asset(run_id: str, filename: str):
    folder, info = _run(run_id)
    return FileResponse(_asset(folder, info, filename), media_type='application/octet-stream',
                        headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/runs/{run_id}/series')
def series(run_id: str, lon: float, lat: float):
    folder, info = _run(run_id)
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(422, '坐标必须为有效经纬度')
    w, s, e, n = info['bounds']
    if not (w <= lon <= e and s <= lat <= n):
        return {'state': 'outside', 'series': []}
    width, height = info['cols'], info['rows']
    col = min(width - 1, int((lon-w)/(e-w)*width))
    row = min(height - 1, int((lat-s)/(n-s)*height))
    try:
        with _asset(folder, info, 'index.bin').open('rb') as f:
            f.seek(INDEX.size * (row*width+col))
            cell = INDEX.unpack(f.read(INDEX.size))[0]
        if cell >= info['cell_count']:
            raise ValueError('invalid cell lookup')
        values = []
        for frame in info['frames']:
            with _asset(folder, info, frame['file']).open('rb') as f:
                f.seek(cell * CELL.size)
                h, stage, u, v = CELL.unpack(f.read(CELL.size))
            if not all(map(math.isfinite, (h, stage, u, v))) or h < 0:
                raise ValueError('invalid model result')
            values.append({'t_seconds': frame['t_seconds'], 'depth_m': h, 'stage_m': stage,
                           'speed_mps': math.hypot(u,v), 'wet': h >= info['wet_threshold_m']})
        return {'state': 'ok', 'cell': cell, 'lon': lon, 'lat': lat, 'series': values}
    except (OSError, ValueError, struct.error) as error:
        raise HTTPException(503, '情景查询数据不可用') from error
