// 验证真实源节点、双线性插值、瓦片边界与错误分支；不模拟浏览器界面。
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { Cartographic } from '../frontend/node_modules/cesium/Source/Cesium.js'
import { loadDemTerrain, sampleHeight } from '../frontend/src/demTerrain.js'

const root = new URL('../', import.meta.url)
const metadata = JSON.parse(await fs.readFile(new URL('frontend/public/terrain/metadata.json', root), 'utf8'))
const bytes = await fs.readFile(new URL('frontend/public/terrain/fabdem.f32', root))
const grid = new Float32Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength))
let checks = 0
function check(name, action) { action(); checks++; console.log('通过：' + name) }
const gt = metadata.geotransform
for (const [x, y] of [[0, 0], [metadata.width - 1, metadata.height - 1], [380, 250]]) {
  check(`源像元中心 ${x},${y}`, () => assert.ok(Math.abs(sampleHeight(metadata, grid, gt[0]+(x+.5)*gt[1], gt[3]+(y+.5)*gt[5])-grid[y*metadata.width+x]) < 1e-7))
}
check('经纬度正反轴方向与四点插值', () => assert.equal(sampleHeight({ width: 2, height: 2, geotransform: [0, 1, 0, 2, 0, -1] }, new Float32Array([0, 20, 40, 60]), 1, 1), 30))
check('覆盖区外不产生伪造地形', () => assert.equal(sampleHeight(metadata, grid, 0, 0), 0))
const nativeFetch = globalThis.fetch
globalThis.fetch = (path, options) => nativeFetch(new URL(path, 'http://127.0.0.1:5173'), options)
const { provider } = await loadDemTerrain()
checks++
const location = Cartographic.fromDegrees(108.3939, 22.7908)
const tile = provider.tilingScheme.positionToTileXY(location, 13)
const terrain = await provider.requestTileGeometry(tile.x, tile.y, 13)
const rectangle = provider.tilingScheme.tileXYToRectangle(tile.x, tile.y, 13)
check('Cesium 瓦片山顶高程与原始采样差小于3m', () => assert.ok(Math.abs(terrain.interpolateHeight(rectangle, location.longitude, location.latitude)-sampleHeight(metadata, grid, 108.3939, 22.7908)) < 3))
check('末级没有子瓦片', () => assert.equal(terrain.childTileMask, 0))
check('超过末级不请求真实数据', () => assert.equal(provider.getTileDataAvailable(0, 0, 14), false))
const parent = await provider.requestTileGeometry(tile.x >> 1, tile.y >> 1, 12)
check('中间层允许细分', () => assert.equal(parent.childTileMask, 15))
// 相邻瓦片共享边界必须得到同一个值，否则会出现裂缝。
const neighbor = await provider.requestTileGeometry(tile.x + 1, tile.y, 13)
const neighborRect = provider.tilingScheme.tileXYToRectangle(tile.x + 1, tile.y, 13)
const latitude = (rectangle.north + rectangle.south)/2
check('相邻瓦片公共边界连续', () => assert.ok(Math.abs(terrain.interpolateHeight(rectangle, rectangle.east, latitude)-neighbor.interpolateHeight(neighborRect, neighborRect.west, latitude)) < 1e-7))
globalThis.fetch = async () => new Response('', { status: 404 })
await assert.rejects(loadDemTerrain(), /元数据不可用/); checks++
globalThis.fetch = async (url) => url.endsWith('metadata.json') ? new Response(JSON.stringify(metadata)) : new Response(new ArrayBuffer(4))
await assert.rejects(loadDemTerrain(), /长度不正确/); checks++
const corrupted = bytes.slice(); corrupted[0] ^= 1
globalThis.fetch = async (url) => url.endsWith('metadata.json') ? new Response(JSON.stringify(metadata)) : new Response(corrupted)
await assert.rejects(loadDemTerrain(), /完整性校验失败/); checks++
globalThis.fetch = nativeFetch
await fs.writeFile(new URL('docs/terrain_runtime_checks.json', root), JSON.stringify({ passed: true, checks,
  source_node_samples: 3, tile_level: 13, probe_height_m: sampleHeight(metadata, grid, 108.3939, 22.7908) }, null, 2))
console.log(`${checks} 项地形检查通过`)
