import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { WaterClock, shouldAnimate } from '../frontend/src/waterClock.js'

let checks = 0
function check(name, action) { action(); checks++; console.log('通过：' + name) }
const clock = new WaterClock()
check('默认时钟停止', () => { clock.advance(0); clock.advance(50); assert.equal(clock.seconds, 0) })
clock.configure({running:true,speed:1}, 50)
check('正常前进50毫秒', () => assert.equal(clock.advance(100), .05))
clock.configure({running:false,speed:1}, 150)
check('暂停精确冻结时间', () => assert.equal(clock.advance(2000), .1))
clock.configure({running:true,speed:2}, 2000)
check('双倍视觉速度', () => assert.equal(clock.advance(2050), .2))
clock.configure({running:true,speed:.5}, 2050)
check('半速不跳回起点', () => assert.ok(Math.abs(clock.advance(2100)-.225)<1e-12))
check('长任务之后限制单次时间步', () => assert.ok(Math.abs(clock.advance(10000)-.275)<1e-12))
check('时钟回退不倒流', () => assert.ok(Math.abs(clock.advance(9000)-.275)<1e-12))
check('拒绝无效时间', () => assert.throws(()=>clock.advance(NaN)))
check('拒绝未支持的速度', () => assert.throws(()=>clock.configure({running:true,speed:100}, 10000)))
const visibleScene = { enabled:true, paused:false, visible:true, mode3d:true, pageVisible:true }
for (const [name, changes, expected] of [
  ['可见三维水面允许刷新', {}, true],
  ['用户关闭特效后停止刷新', {enabled:false}, false],
  ['暂停后停止刷新', {paused:true}, false],
  ['隐藏水面后停止刷新', {visible:false}, false],
  ['二维视图停止刷新', {mode3d:false}, false],
  ['页面后台停止刷新', {pageVisible:false}, false],
  ['后台且隐藏时不被启用开关误恢复', {pageVisible:false,visible:false,paused:false}, false],
]) {
  check(name, () => assert.equal(shouldAnimate({...visibleScene,...changes}), expected))
}
const root = new URL('../', import.meta.url)
const record = JSON.parse(await fs.readFile(new URL('docs/phase3_processing.json',root),'utf8'))
const unchanged = []
for(const [path, expected] of Object.entries(record.outputs)) {
  const bytes = await fs.readFile(new URL(path.replaceAll('\\','/'),root))
  unchanged.push(createHash('sha256').update(bytes).digest('hex') === expected.sha256)
}
check('全部Phase3分析成果未被动画修改', () => assert.ok(unchanged.every(Boolean)))
await fs.writeFile(new URL('docs/phase5_logic_checks.json',root), JSON.stringify({passed:true,checks,analysis_files_unchanged:Object.keys(record.outputs).length},null,2))
console.log(`${checks} 项动画逻辑检查通过`)
