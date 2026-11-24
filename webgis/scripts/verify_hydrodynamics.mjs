import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
import { performance } from 'node:perf_hooks'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base = process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:5173'
const long = process.argv.includes('--long')
const performanceRun = long || process.argv.includes('--performance')
const basemap = process.env.HYDRO_BENCH_BASEMAP || 'local'
const visuals = process.argv.includes('--visuals')
const output = process.env.HYDRO_TEST_OUTPUT
const errors = [], evidence = {}
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms))
let browser
async function checkJson(path) {
  const result = await fetch(base + path)
  assert.equal(result.status,200,path)
  return result.json()
}
const checks = []
async function check(name,run) { await run(); checks.push(name); console.log('通过：' + name) }
try {
  const runs = await checkJson('/api/hydrodynamics/runs')
  assert.ok(runs.length)
  const run = '/api/hydrodynamics/runs/' + runs.at(-1).id
  const info = await checkJson(run + '/manifest')
  const peak = info.frames.reduce((a,b) => a.overbank_km2 > b.overbank_km2 ? a : b)
  await check('只读 API 与域内外查询',async () => {
    const center = await checkJson(run + '/series?lon=108.32565&lat=22.77507')
    assert.equal(center.state,'ok')
    assert.equal(center.series.length,info.frames.length)
    assert.ok(center.series.some(row=>row.wet && row.depth_m>1 && row.speed_mps>0))
    assert.equal((await checkJson(run+'/series?lon=0&lat=0')).state,'outside')
    assert.equal((await fetch(base+run+'/assets/nonexistent.bin')).status,404)
    assert.equal((await checkJson('/api/health')).status,'ok')
    const bytes=await (await fetch(base+run+'/assets/'+info.frames[0].file)).arrayBuffer()
    assert.equal(bytes.byteLength,16*info.cell_count)
  })
  browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-webgl','--ignore-gpu-blocklist']})
  const page=await browser.newPage({viewport:{width:1920,height:1080}})
  page.on('pageerror',error=>errors.push(String(error)))
  page.on('console',msg=>{ if (msg.type()==='error') errors.push(msg.text().slice(0,800)) })
  if(basemap==='local') await page.route(/https:\/\/(services\.arcgisonline\.com|tile\.openstreetmap\.org)\//,route=>route.abort())
  await page.goto(base+'/?measureHydro=1',{waitUntil:'domcontentloaded'})
  await page.locator('.basemap-label select').selectOption(basemap,{timeout:30000})
  await page.locator('[data-testid=area-stat]').waitFor({timeout:30000})
  const staticArea=await page.locator('[data-testid=area-stat]').textContent()
  assert.match(staticArea,/23\.7168/)
  await page.locator('[data-testid=hydro-mode]').click({timeout:30000})
  const play=page.locator('[data-testid=hydro-play]')
  const slider=page.getByRole('slider',{name:'模拟时刻'})
  await play.waitFor({timeout:30000})
  assert.match(await page.locator('.app-header').innerText(),/基于真实地形和假设参数的洪水动态情景模拟/)
  await page.waitForFunction(()=>document.querySelector('.cesium-map')?.dataset.pendingTiles==='0')
  const map = page.locator('.cesium-map')
  const inspect=()=>map.evaluate(e=>{e.dispatchEvent(new Event('hydro-inspect'));return JSON.parse(e.dataset.hydroStats || '{}')})
  if(visuals) await page.waitForFunction(()=>{
    const e=document.querySelector('.cesium-map')
    e.dispatchEvent(new Event('hydro-inspect'))
    return JSON.parse(e.dataset.hydroStats || '{}').normal_ready
  })
  if(output) await page.screenshot({path:output+'/base.png'})
  const time=()=>slider.evaluate(e=>Number(e.value))
  const seek=async sec=>{
    await slider.evaluate((e,n)=>{e.value=n;e.dispatchEvent(new Event('input',{bubbles:true}))},sec)
    await page.waitForFunction(()=>!document.querySelector('[data-testid=hydro-play]')?.disabled)
  }
  await check('基流、播放与暂停',async()=>{
    const t=await time()
    await play.click()
    await page.waitForFunction(()=>Number(document.querySelector('[aria-label="模拟时刻"]').value)>200)
    await play.click()
    const stopped=await time()
    await sleep(550)
    assert.ok(stopped>t)
    assert.equal(await time(),stopped)
  })
  await check('峰值拖动、流速图层和地图点位过程',async()=>{
    await seek(peak.t_seconds)
    assert.equal(await time(),peak.t_seconds)
    assert.ok(Math.abs(parseFloat(await page.locator('[data-testid=hydro-area]').textContent())-peak.wet_km2)<.015)
    await page.getByLabel('水面着色').selectOption('speed')
    await page.getByLabel('模拟播放倍率').selectOption('0.5')
    await page.getByLabel('模拟播放倍率').selectOption('2')
    const canvas=page.locator('.cesium-widget canvas')
    const box=await canvas.boundingBox()
    await canvas.click({position:{x:Math.floor(box.width*.54),y:Math.floor(box.height*.46)}})
    await page.locator('[data-testid=hydro-point]').waitFor({timeout:10000})
    evidence.point=(await page.locator('[data-testid=hydro-point]').innerText()).trim()
    await page.getByLabel('水面着色').selectOption('depth')
    if(output) await page.screenshot({path:output+'/peak.png'})
    await seek(info.duration_seconds)
    assert.match(await play.textContent(),/重播/)
    assert.ok(parseFloat(await page.locator('[data-testid=hydro-area]').textContent())<peak.wet_km2)
    if(output) await page.screenshot({path:output+'/recession.png'})
  })
  await check('重播与后台暂停逻辑',async()=>{
    await play.click()
    await page.waitForFunction(()=>document.querySelector('[data-testid=hydro-play]')?.textContent==='暂停')
    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'))})
    const stopped=await time()
    await sleep(400)
    assert.equal(await time(),stopped)
    assert.match(await play.textContent(),/播放/)
    await page.evaluate(()=>{delete document.hidden})
  })
  evidence.renderer=await page.evaluate(()=>{
    const gl=document.querySelector('.cesium-widget canvas').getContext('webgl2')
    const ext=gl.getExtension('WEBGL_debug_renderer_info')
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
  })
  evidence.browser=browser.version()
  if(performanceRun) {
    await seek(0)
    if(visuals) await page.getByLabel('水面着色').selectOption('natural')
    await page.getByLabel('模拟播放倍率').selectOption('1')
    const devtools=await page.context().newCDPSession(page)
    const snapshot=async()=>{
      await devtools.send('HeapProfiler.collectGarbage')
      return { heap:(await devtools.send('Runtime.getHeapUsage')).usedSize,
        nodes:(await devtools.send('Memory.getDOMCounters')).nodes }
    }
    await page.evaluate(()=>{window.hydroFrameTimes=[]; document.querySelector('.cesium-map').addEventListener('hydro-render',
      ()=>window.hydroFrameTimes.push(performance.now()))})
    const memoryBefore=await snapshot()
    if(visuals) evidence.visualResourcesBefore=await inspect()
    await play.click()
    await sleep(5000)
    const start=performance.now()
    await page.evaluate(()=>{window.hydroFrameTimes.length=0})
    await sleep(120000)
    const frames=await page.evaluate(()=>window.hydroFrameTimes.slice())
    const duration=(frames.at(-1)-frames[0])/1000
    const gaps=frames.slice(1).map((value,i)=>value-frames[i])
    const p95=[...gaps].sort((a,b)=>a-b)[Math.floor(gaps.length*.95)]
    evidence.performance={window_s:duration,rendered_frames:frames.length,average_fps:(frames.length-1)/duration,
      p95_gap_ms:p95,max_gap_ms:Math.max(...gaps),gaps_over_500_ms:gaps.filter(v=>v>500).length,
      viewport:[1920,1080],basemap:await page.locator('.basemap-label select').inputValue(),particles:320,memoryBefore}
    console.log('120 秒呈现性能',JSON.stringify(evidence.performance))
    assert.ok(evidence.performance.average_fps>=30,'桌面平均帧率低于 30 fps')
    assert.equal(evidence.performance.gaps_over_500_ms,0,'出现超过 500 ms 的渲染间隔')
    assert.equal(evidence.performance.basemap,basemap)
    const actions=[]
    while(long && performance.now()-start<600000) {
      const target=(actions.length*7920+450)%(info.duration_seconds-1800)
      const before=performance.now()
      await seek(target)
      actions.push(performance.now()-before)
      if(visuals) await page.getByLabel('水面着色').selectOption(['natural','depth','speed'][actions.length%3])
      await page.getByLabel('模拟播放倍率').selectOption(actions.length%2?'2':'0.5')
      await play.click()
      await sleep(Math.max(1,Math.min(20000,600000-(performance.now()-start))))
      const area=parseFloat(await page.locator('[data-testid=hydro-area]').textContent())
      assert.ok(area>0 && Number.isFinite(area))
      if(actions.length%4===0) console.log('长测进度',Math.round((performance.now()-start)/1000),'秒')
    }
    if((await play.textContent()).trim()==='暂停') await play.click()
    if(long) {
      evidence.performance.stability_s=(performance.now()-start)/1000
      evidence.performance.seeks=actions.length
      evidence.performance.seek_max_ms=Math.max(...actions)
      evidence.performance.seek_median_ms=[...actions].sort((a,b)=>a-b)[Math.floor(actions.length/2)]
    }
    evidence.performance.memoryAfter=await snapshot()
    if(visuals) {
      evidence.visualResourcesAfter=await inspect()
      for (const field of ['primitives','textures','vertices','geometry_bytes'])
        assert.equal(evidence.visualResourcesAfter[field],evidence.visualResourcesBefore[field],field)
      assert.equal(evidence.visualResourcesAfter.context_lost,false)
      assert.ok(evidence.visualResourcesAfter.cache_count<=7)
    }
    if(long) console.log('600 秒稳定性',JSON.stringify(evidence.performance))
    assert.equal(await map.getAttribute('data-hydro'),'ready')
  }
  await check('回到旧静态模式与历史降雨',async()=>{
    await page.getByRole('button',{name:'静态情景',exact:true}).click()
    assert.match(await page.locator('[data-testid=area-stat]').textContent(),/23\.7168/)
    if(visuals && performanceRun) {
      evidence.staticResources=await inspect()
      assert.equal(evidence.staticResources.textures,undefined)
      assert.equal(evidence.staticResources.primitives,evidence.visualResourcesBefore.primitives-2)
    }
    await page.getByText('真实历史降雨 · CHM_PRE',{exact:true}).waitFor()
    const scenarios=page.getByRole('combobox',{name:/假设水位/})
    for (const [option, area] of [['1','101.2095'],['2','132.8472'],['3','80.4600']]) {
      await scenarios.selectOption(option)
      assert.ok((await page.locator('[data-testid=area-stat]').textContent()).includes(area))
    }
  })
  const unexpected=errors.filter(x=>!/net::ERR_FAILED|net::ERR_CONNECTION|Request has failed|底图/.test(x))
  assert.deepEqual(unexpected,[])
  const result={checks,evidence,observed_console_errors:errors,fullRun:runs.at(-1).id}
  if(output) await fs.writeFile(output+'/browser.json',JSON.stringify(result,null,2)+'\n',{flag:'wx'})
  console.log(JSON.stringify(result))
} finally { await browser?.close() }
