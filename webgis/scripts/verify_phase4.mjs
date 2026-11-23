// 验证网页成果与分析源文件一致，并实际请求本机静态服务；不控制浏览器。
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { loadAnalysis, fetchCheckedJson } from '../frontend/src/analysisData.js'

const root = new URL('../', import.meta.url)
const nativeFetch = globalThis.fetch
globalThis.fetch = (path, options) => nativeFetch(new URL(path, 'http://127.0.0.1:5173'), options)
let checks = 0
const data = await loadAnalysis()
assert.equal(data.summary.kind, 'hypothetical_scenario_not_observation'); checks++
assert.equal(Object.keys(data.catalog.assets).length, 10); checks++
for (const [name, asset] of Object.entries(data.catalog.assets)) {
  const value = await fetchCheckedJson(asset)
  const sourcePath = new URL(asset.source.replaceAll('\\', '/'), root)
  const sourceBytes = await fs.readFile(sourcePath)
  assert.equal(createHash('sha256').update(sourceBytes).digest('hex'), asset.source_sha256)
  assert.deepEqual(value, JSON.parse(sourceBytes.toString('utf8')))
  checks += 2
  console.log('通过：'+name+' 哈希与源数据一致')
}
assert.deepEqual(data.summary.scenarios.map(row => row.area_km2), [23.7168, 101.2095, 132.8472, 80.46]); checks++
assert.ok(Math.abs(data.rainfall.total_precip_mm-137.42584381580474)<1e-10); checks++
assert.equal(data.rainfall.daily[0].interval_start_bjt, '2024-09-05T20:00:00+08:00'); checks++
assert.equal(data.rainfall.daily.at(-1).interval_end_bjt, '2024-09-13T20:00:00+08:00'); checks++
await assert.rejects(fetchCheckedJson({url:'/analysis/nonexistent.json',sha256:''}), /成果不可用/); checks++
await assert.rejects(fetchCheckedJson({...data.catalog.assets.summary,sha256:'wrong'}), /完整性校验失败/); checks++
globalThis.fetch = nativeFetch
await fs.writeFile(new URL('docs/phase4_asset_checks.json', root), JSON.stringify({passed:true,checks,assets:10},null,2))
console.log(`${checks} 项网页资源检查通过`)
