import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const url = process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:5173'
const root = process.env.HYDRO_TEST_OUTPUT
assert.ok(root,'为配色验收设置独立的 HYDRO_TEST_OUTPUT')
const output = join(root, process.env.HYDRO_PALETTE_CAPTURE || 'verification')
await fs.mkdir(output)
const run = new URL('../data/processed/hydrodynamics/runs/full_reach_v2/', import.meta.url)
const manifest = JSON.parse(await fs.readFile(new URL('manifest.json',run)))
const ids = [4730,4748,4762,4750,-1]
const threshold = manifest.wet_threshold_m
const matches = id => id >= 0 && id < manifest.cell_count
const fileFor = seconds => manifest.frames.find(row => row.t_seconds===seconds)
const field = async seconds => fs.readFile(new URL('web/'+fileFor(seconds).file,run))
const initial = await field(0)
const depth = (buffer,id) => buffer.readFloatLE(16*id)
const errors = []
const browser = await chromium.launch({channel:'msedge',headless:true,args:['--enable-webgl','--ignore-gpu-blocklist']})
const evidence = { frames: {}, basemaps: {}, resources: {} }
try {
  const page = await browser.newPage({viewport:{width:1920,height:1080}})
  page.on('pageerror',err=>errors.push(err.message))
  page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())})
  await page.goto(url+'/?measureHydro=1',{waitUntil:'domcontentloaded'})
  const map = page.locator('.cesium-map')
  const canvas = page.locator('.cesium-widget canvas')
  const style = page.getByRole('combobox',{name:'水面着色'})
  const basemap = page.locator('.basemap-label select')
  const hydroButton = page.getByTestId('hydro-mode')
  const play = page.getByTestId('hydro-play')
  const slider = page.getByRole('slider',{name:'模拟时刻'})
  const legend = page.getByRole('group',{name:'动态水面图例'})
  const inspect = () => map.evaluate((el,cells)=>{
    el.dispatchEvent(new CustomEvent('hydro-inspect',{detail:{cells}}))
    return JSON.parse(el.dataset.hydroStats)
  },ids)
  const waitMap = async (kind, tiles=true) => {
    await page.waitForFunction(k=>document.querySelector('.cesium-map').dataset.basemap===k,kind,{timeout:30000})
    if (tiles) await page.waitForFunction(()=>document.querySelector('.cesium-map').dataset.pendingTiles==='0',null,{timeout:50000})
    await page.waitForTimeout(230)
  }
  const seek = async seconds => {
    await slider.evaluate((el,t)=>{el.value=t;el.dispatchEvent(new Event('input',{bubbles:true}))},seconds)
    await page.waitForFunction(()=>!document.querySelector('[data-testid=hydro-play]')?.disabled)
    assert.equal((await inspect()).seconds,seconds)
  }
  const checked = async seconds => {
    const probe = await inspect()
    const expected = await field(seconds)
    for(const [i,id] of ids.entries()) {
      const cell=probe.cells[i]
      if(!matches(id)) { assert.equal(cell,null); continue }
      assert.equal(cell.depth,depth(expected,id),id)
      assert.equal(cell.stage,expected.readFloatLE(16*id+4),id)
      assert.equal(cell.originally_wet,depth(initial,id)>=threshold,id)
      cell.expected_class=cell.depth<threshold ? 'dry' : cell.originally_wet ? 'initial' : 'flood'
    }
    const expectedArea=fileFor(seconds).wet_km2.toFixed(2)
    assert.equal(parseFloat(await page.getByTestId('hydro-area').textContent()).toFixed(2),expectedArea)
    probe.wet_area_km2=expectedArea
    return probe
  }
  const pixels = async (png, probes) => page.evaluate(async ({b64,probes})=>{
    const rgba = Uint8Array.from(atob(b64),x=>x.charCodeAt(0))
    const bitmap = await createImageBitmap(new Blob([rgba],{type:'image/png'}))
    const scratch = new OffscreenCanvas(bitmap.width,bitmap.height)
    const ctx = scratch.getContext('2d')
    ctx.drawImage(bitmap,0,0)
    return probes.map(record=>{
      if (!record?.pixel) return null
      const x=Math.round(record.pixel.x), y=Math.round(record.pixel.y)
      if (x<2 || y<2 || x>=bitmap.width-2 || y>=bitmap.height-2) return null
      const bytes=ctx.getImageData(x-1,y-1,3,3).data
      return [0,1,2].map(c=>Array.from({length:9},(_,i)=>bytes[4*i+c]).sort((a,b)=>a-b)[4])
    })
  },{b64:png.toString('base64'),probes})
  await page.getByTestId('area-stat').waitFor()
  assert.match(await page.getByTestId('area-stat').textContent(),/23\.7168/)
  await waitMap('satellite',false)
  evidence.basemaps.originalSatellite=(await inspect()).basemap
  await hydroButton.click()
  await page.getByRole('combobox',{name:'水动力情景'}).selectOption('full_reach_v2')
  await play.waitFor()
  await legend.getByText('初始水面',{exact:true}).waitFor()
  await legend.getByText('新增淹没',{exact:true}).waitFor()
  await page.getByText('以预热结束后的首个展示时刻（0 小时）为基准。',{exact:true}).waitFor()
  await page.waitForFunction(()=>{
    const el=document.querySelector('.cesium-map')
    el.dispatchEvent(new Event('hydro-inspect'))
    return JSON.parse(el.dataset.hydroStats).normal_ready
  })
  await page.getByRole('button',{name:'漫岸近景',exact:true}).click()
  await waitMap('satellite')
  evidence.basemaps.naturalSatellite=(await inspect()).basemap
  assert.equal(evidence.basemaps.naturalSatellite.saturation,0.6)

  for(const [name,t] of [['base',0],['rise',57600],['peak',81000],['recession',216000]]) {
    await seek(t)
    await waitMap('satellite')
    const values=await checked(t)
    values.rgb=await pixels(await canvas.screenshot(),values.cells)
    evidence.frames[name]=values
    await fs.writeFile(join(output,name+'.png'),await page.screenshot(),{flag:'wx'})
  }
  for (const value of Object.values(evidence.frames)) {
    assert.deepEqual(value.camera,evidence.frames.base.camera,'四张截图需使用同一镜头')
    assert.equal(value.context_lost,false)
  }
  assert.equal(evidence.frames.base.initial_frame_cached,true)
  assert.equal(evidence.frames.peak.initial_frame_cached,false)
  assert.equal(evidence.frames.recession.initial_frame_cached,false)
  assert.equal(evidence.frames.base.cells[0].expected_class,'initial')
  assert.equal(evidence.frames.peak.cells[2].expected_class,'flood')
  assert.equal(evidence.frames.recession.cells[2].expected_class,'dry')
  assert.ok(evidence.frames.base.rgb[0][1]>evidence.frames.base.rgb[0][2],JSON.stringify(evidence.frames.base.rgb))
  assert.ok(evidence.frames.peak.rgb[2][2]-evidence.frames.peak.rgb[2][0]>60,JSON.stringify(evidence.frames.peak.rgb))
  assert.ok(evidence.frames.recession.rgb[2][2]-evidence.frames.recession.rgb[2][0]<25,JSON.stringify(evidence.frames.recession.rgb))
  evidence.resources.active=await inspect()

  await play.click()
  await page.waitForFunction(()=>{
    const m=document.querySelector('.cesium-map')
    m.dispatchEvent(new Event('hydro-inspect'))
    const seconds=JSON.parse(m.dataset.hydroStats).seconds
    return seconds>=0 && seconds<1800
  })
  await page.waitForFunction(()=>document.querySelector('[data-testid="hydro-play"]').textContent==='暂停')
  await play.click()
  const stopped=(await inspect()).seconds
  const pauseImage=await canvas.screenshot()
  await page.waitForTimeout(500)
  assert.equal((await inspect()).seconds,stopped)
  assert.ok(pauseImage.equals(await canvas.screenshot()))
  await seek(81000)
  await waitMap('satellite')
  evidence.returnedPeak=await checked(81000)
  assert.equal(evidence.returnedPeak.initial_frame_cached,false)
  assert.deepEqual(evidence.returnedPeak.cells.map(c=>c?.expected_class),evidence.frames.peak.cells.map(c=>c?.expected_class))

  for(const [layer,text] of [['depth','10 m+'],['speed','2.5 m/s+']]) {
    await style.selectOption(layer)
    await page.getByText(text,{exact:true}).waitFor()
    assert.equal(await legend.count(),0)
    assert.deepEqual((await inspect()).basemap,evidence.basemaps.originalSatellite)
  }
  await style.selectOption('natural')
  await legend.waitFor()
  assert.deepEqual((await inspect()).basemap,evidence.basemaps.naturalSatellite)
  await basemap.selectOption('local')
  await waitMap('local')
  evidence.basemaps.naturalLocal=(await inspect()).basemap
  assert.equal(evidence.basemaps.naturalLocal.saturation,0.72)
  await style.selectOption('depth')
  evidence.basemaps.analysisLocal=(await inspect()).basemap
  assert.equal(evidence.basemaps.analysisLocal.saturation,1)
  await style.selectOption('natural')
  await basemap.selectOption('satellite')
  await waitMap('satellite')
  assert.deepEqual((await inspect()).basemap,evidence.basemaps.naturalSatellite)

  await page.getByRole('button',{name:'静态情景',exact:true}).click()
  await page.getByTestId('area-stat').waitFor()
  const staticState=await inspect()
  assert.equal(staticState.initial_vertex_bytes,undefined)
  assert.equal(staticState.textures,undefined)
  assert.equal(staticState.primitives,evidence.resources.active.primitives-2)
  assert.deepEqual(staticState.basemap,evidence.basemaps.originalSatellite)
  assert.equal(staticState.context_lost,false)
  evidence.resources.afterExit=staticState
  const scenario=page.getByRole('combobox',{name:/假设水位/})
  assert.equal(await scenario.locator('option').count(),11)
  await scenario.selectOption('S04')
  await page.waitForFunction(()=>document.querySelector('.cesium-map').dataset.analysisLayer==='S04')
  assert.match(await page.getByTestId('area-stat').textContent(),/80\.4600/)
  await page.getByText('真实历史降雨 · CHM_PRE',{exact:true}).waitFor()
  assert.deepEqual(errors,[])
  evidence.errors=errors
  await fs.writeFile(join(output,'checks.json'),JSON.stringify(evidence,null,2)+'\n',{flag:'wx'})
  console.log(JSON.stringify({pixelColors:Object.fromEntries(Object.entries(evidence.frames).map(([k,v])=>[k,v.rgb])),
    cacheEvicted:true, restored:staticState.basemap, controls:'passed'}))
} finally {
  await browser.close()
}
