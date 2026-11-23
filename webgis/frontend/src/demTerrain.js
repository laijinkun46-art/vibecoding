import { CustomHeightmapTerrainProvider, GeographicTilingScheme, HeightmapTerrainData } from 'cesium'

const TILE_SIZE = 65
const MAX_LEVEL = 13 // 约 35 m 瓦片节点间距；不把显示插值称为提高数据精度。

/** 输入原生网格与经纬度，返回双线性高程。覆盖区外返回0，不冒充全球DEM。 */
export function sampleHeight(metadata, grid, lon, lat) {
  const [west, dx, , north, , dy] = metadata.geotransform
  let x = (lon - west) / dx - 0.5
  let y = (lat - north) / dy - 0.5
  if (x < -0.5 || y < -0.5 || x > metadata.width - 0.5 || y > metadata.height - 0.5) return 0
  x = Math.min(metadata.width - 1, Math.max(0, x))
  y = Math.min(metadata.height - 1, Math.max(0, y))
  const x0 = Math.floor(x), y0 = Math.floor(y)
  const x1 = Math.min(x0 + 1, metadata.width - 1), y1 = Math.min(y0 + 1, metadata.height - 1)
  const fx = x - x0, fy = y - y0
  const top = grid[y0 * metadata.width + x0] * (1 - fx) + grid[y0 * metadata.width + x1] * fx
  const bottom = grid[y1 * metadata.width + x0] * (1 - fx) + grid[y1 * metadata.width + x1] * fx
  return top * (1 - fy) + bottom * fy
}

/** 读取本地真实DEM并构造Cesium地形；文件不完整或非有限数时明确失败。 */
export async function loadDemTerrain() {
  const response = await fetch('/terrain/metadata.json', { signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error('DEM 元数据不可用')
  const metadata = await response.json()
  const raster = await fetch(metadata.url, { signal: AbortSignal.timeout(30000) })
  if (!raster.ok) throw new Error('DEM 高程文件不可用')
  const bytes = await raster.arrayBuffer()
  if (bytes.byteLength !== metadata.width * metadata.height * 4 || bytes.byteLength !== metadata.bytes) throw new Error('DEM 高程文件长度不正确')
  const grid = new Float32Array(bytes)
  if (!grid.every(Number.isFinite)) throw new Error('DEM 高程包含无效值')
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('')
  if (hash !== metadata.sha256) throw new Error('DEM 文件完整性校验失败')
  const tilingScheme = new GeographicTilingScheme()
  const sampleTile = (x, y, level) => {
    const rectangle = tilingScheme.tileXYToRectangle(x, y, level)
    const result = new Float32Array(TILE_SIZE * TILE_SIZE)
    const degrees = 180 / Math.PI
    for (let row = 0; row < TILE_SIZE; row++) {
      const latitude = (rectangle.north - (rectangle.north - rectangle.south) * row / (TILE_SIZE - 1)) * degrees
      for (let col = 0; col < TILE_SIZE; col++) {
        const longitude = (rectangle.west + (rectangle.east - rectangle.west) * col / (TILE_SIZE - 1)) * degrees
        result[row * TILE_SIZE + col] = sampleHeight(metadata, grid, longitude, latitude)
      }
    }
    return result
  }
  const provider = new CustomHeightmapTerrainProvider({ width: TILE_SIZE, height: TILE_SIZE,
    tilingScheme, callback: sampleTile, credit: metadata.credit })
  // 使用公开接口指定末级子瓦片不可用，避免无限细分同一30m源网格。
  provider.requestTileGeometry = (x, y, level) => Promise.resolve(new HeightmapTerrainData({
    buffer: sampleTile(x, y, level), width: TILE_SIZE, height: TILE_SIZE, childTileMask: level < MAX_LEVEL ? 15 : 0,
  }))
  provider.getTileDataAvailable = (x, y, level) => level <= MAX_LEVEL
  return { provider, metadata }
}
