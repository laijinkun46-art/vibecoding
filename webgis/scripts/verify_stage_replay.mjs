import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const host = process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:5173'
const root = process.env.STAGE_REPLAY_OUTPUT
assert.ok(root,'需设置独立验收目录 STAGE_REPLAY_OUTPUT')
const output = join(root, process.env.STAGE_REPLAY_CAPTURE || 'browser')
await fs.mkdir(output)
const manifest = JSON.parse(await fs.readFile(new URL('../frontend/public/analysis/stage_replay_v1/manifest.json',import.meta.url)))
const hash = value=>createHash('sha256').update(value).digest('hex')
for(const [filename,digest] of Object.entries(manifest.sources_sha256)) assert.equal(hash(await fs.readFile(filename)),digest)
const errors = []
const browser = await chromium.launch({channel:'msedge',headless:true,args:['--enable-webgl','--ignore-gpu-blocklist']})
try {
  const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'})
  page.on('pageerror',e=>errors.push(String(e)))
  page.on('console',m=>{if(m.type()==='error') errors.push(m.text().slice(0,600))})
  await page.goto(host+'/?demo=land-flood',{waitUntil:'domcontentloaded'})
  const timeline=page.getByRole('region',{name:'陆地淹没时间轴'})
  const map=page.locator('.cesium-map')
  const canvas=page.locator('.cesium-widget canvas')
  const play=page.getByTestId('replay-play')
  const slider=page.getByRole('slider',{name:'演示进度'})
  const stage=page.getByTestId('replay-stage')
  const added=page.getByTestId('replay-added')
  await timeline.waitFor({timeout:20000})
  await page.waitForFunction(()=>{
    const e=document.querySelector('.cesium-map')
    return e.dataset.stageReplay==='ready' && e.dataset.basemap==='satellite' && e.dataset.pendingTiles==='0'
  },null,{timeout:55000})
  const seek=async t=>slider.evaluate((e,n)=>{e.value=n;e.dispatchEvent(new Event('input',{bubbles:true}))},t)
  const readBlue=async png=>page.evaluate(async b64=>{
    const b=Uint8Array.from(atob(b64),c=>c.charCodeAt(0))
    const image=await createImageBitmap(new Blob([b],{type:'image/png'}))
    const screen=new OffscreenCanvas(image.width,image.height)
    const ctx=screen.getContext('2d')
    ctx.drawImage(image,0,0)
    const sample=ctx.getImageData(0,0,image.width,image.height).data
    let blue=0
    for(let i=0;i<sample.length;i+=4)
      if(sample[i+2]>sample[i]+40 && sample[i+2]>sample[i+1]+17) blue++
    return blue
  },png.toString('base64'))
  const states={}
  const area=(id)=> (manifest.validated_scenarios[id].wet_km2-manifest.validated_scenarios.S01.wet_km2).toFixed(2)
  for(const [name,t,level,scenario] of [['base',0,75,'S01'],['rising',3.84,80,'S02'],['peak',7.2,85,'S03'],['recession',12,78,'S04']]){
    await seek(t)
    await page.waitForTimeout(170)
    assert.equal(await stage.textContent(),level.toFixed(2)+' m')
    assert.equal(parseFloat(await added.textContent()).toFixed(2),area(scenario))
    const blue=await readBlue(await canvas.screenshot())
    states[name]={t,level,added_km2:Number(area(scenario)),blue_canvas_pixels:blue}
    await fs.writeFile(join(output,name+'.png'),await page.screenshot(),{flag:'wx'})
  }
  console.log('取色面积',JSON.stringify(states))
  assert.ok(states.peak.blue_canvas_pixels>states.base.blue_canvas_pixels+55000,'洪峰新增范围没有明显绘出')
  assert.ok(states.peak.blue_canvas_pixels>states.recession.blue_canvas_pixels+25000,'退水未明显缩小蓝色范围')
  await seek(1.75)
  const middle=await stage.textContent()
  assert.ok(parseFloat(middle)>75 && parseFloat(middle)<80)
  const paused=await canvas.screenshot()
  await page.waitForTimeout(350)
  assert.ok(paused.equals(await canvas.screenshot()),'暂停时地形水纹仍在变化')

  await seek(0)
  const started=performance.now()
  await page.evaluate(()=>{
    const stream=document.querySelector('.cesium-widget canvas').captureStream(30)
    const capture=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:2900000})
    const parts=[]
    capture.ondataavailable=e=>{if(e.data.size)parts.push(e.data)}
    window.finishReplayClip=()=>new Promise(resolve=>{
      capture.onstop=()=>{
        stream.getTracks().forEach(t=>t.stop())
        const reader=new FileReader()
        reader.onload=()=>resolve(reader.result.split(',')[1])
        window.stageReplayClip=new Blob(parts,{type:'video/webm'})
        reader.readAsDataURL(window.stageReplayClip)
      }
      capture.stop()
    })
    capture.start(500)
  })
  await play.click()
  await page.waitForFunction(()=>document.querySelector('[data-testid="replay-play"]')?.textContent==='重播',null,{timeout:25000})
  const duration=(performance.now()-started)/1000
  await page.waitForTimeout(350)
  const movie=Buffer.from(await page.evaluate(()=>window.finishReplayClip()),'base64')
  assert.ok(movie.length>80000)
  await fs.writeFile(join(output,'stage-replay.webm'),movie,{flag:'wx'})
  const preview=await page.evaluate(async()=>{
    const url=URL.createObjectURL(window.stageReplayClip)
    const video=document.createElement('video')
    video.src=url
    await new Promise((resolve,reject)=>{
      video.addEventListener('loadeddata',resolve,{once:true})
      video.addEventListener('error',reject,{once:true})
    })
    const result={width:video.videoWidth,height:video.videoHeight}
    URL.revokeObjectURL(url)
    return result
  })
  assert.ok(duration>=11.6 && duration<15,duration)
  await page.getByLabel('演示倍率').selectOption('2')
  const fast=performance.now()
  await play.click()
  await page.waitForFunction(()=>document.querySelector('[data-testid="replay-play"]')?.textContent==='重播',null,{timeout:14000})
  const durationFast=(performance.now()-fast)/1000
  assert.ok(durationFast>=5.7 && durationFast<8,durationFast)
  await page.getByRole('button',{name:'静态情景',exact:true}).click()
  await page.getByTestId('area-stat').waitFor()
  assert.match(await page.getByTestId('area-stat').textContent(),/23\.7168/)
  assert.equal(await map.getAttribute('data-stage-replay'),null)
  await page.getByTestId('hydro-mode').click()
  await page.getByRole('combobox',{name:'水动力情景'}).selectOption('full_reach_v2')
  await page.getByTestId('hydro-play').waitFor({timeout:15000})
  assert.deepEqual(await page.getByLabel('模拟播放倍率').locator('option').evaluateAll(opts=>opts.map(o=>o.value)),['0.5','1','2','4','8'])
  assert.equal(await map.getAttribute('data-stage-replay'),null)
  const unexpected=errors.filter(x=>!x.includes('net::ERR_ABORTED'))
  assert.deepEqual(unexpected,[])
  const result={states,duration,durationFast,preview,videoBytes:movie.length,staticAndHydroRestored:true,errors}
  await fs.writeFile(join(output,'checks.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'})
  console.log(JSON.stringify(result))
} finally { await browser.close() }
