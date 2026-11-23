"""从已校验的 FABDEM 网页网格生成透明坡面明暗图，仅用于三维卫星底图。"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    directory = Path(__file__).resolve().parents[1] / 'frontend/public/terrain'
    meta = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    raw = (directory / 'fabdem.f32').read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['sha256']:
        raise ValueError('高程网格校验失败')
    dem = np.frombuffer(raw, dtype='<f4').reshape(meta['height'], meta['width'])
    _, dx, _, north, _, dy = meta['geotransform']
    metres_x = dx * 111320 * np.cos(np.deg2rad(north + dem.shape[0] * dy / 2))
    south_grad, east_grad = np.gradient(dem, -dy * 111132, metres_x)
    # 西北侧光。平地透明，坡度越大明暗越明显；轻微平滑避免单像元噪声。
    strength = (east_grad + south_grad) / np.sqrt(2 * (1 + east_grad**2 + south_grad**2))
    padded = np.pad(strength, 1, mode='edge')
    h, w = dem.shape
    strength = sum(padded[y:y+h, x:x+w] for y in range(3) for x in range(3)) / 9
    gray = np.where(strength > 0, 239, 26).astype('uint8')
    opacity = np.where(strength > 0, .16, .30)
    alpha = (opacity * np.clip(abs(strength) / .44, 0, 1) * 255).astype('uint8')
    Image.fromarray(np.stack([gray, alpha], axis=-1)).save(directory / 'relief_shade.png')


if __name__ == '__main__':
    main()
