import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const root=process.env.HYDRO_TEST_OUTPUT
assert.ok(root,'需要指定验收输出目录 HYDRO_TEST_OUTPUT')
const folder=join(root,process.env.OVERBANK_CAPTURE || 'browser')
await fs.mkdir(folder)
const host=process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:5173'
const endpoint='/api/hydrodynamics/runs/full_reach_v3'
const manifest=await (await fetch(host+endpoint+'/manifest')).json()
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-webgl','--ignore-gpu-blocklist']})
const page=await browser.newPage({viewport:{width:1920,height:1080}})
const errors=[]
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const evidence={frames:{},lands:[],modes:{}}
const write=(name,buf)=>fs.writeFile(join(folder,name),buf,{flag:'wx'})
page.on('pageerror',e=>errors.push(e.message))
page.on('console',e=>{if(e.type()==='error')errors.push(e.text().slice(0,500))})
try {
  await page.goto(host+'/?measureHydro=1',{waitUntil:'domcontentloaded'})
  const map=page.locator('.cesium-map')
  const canvas=page.locator('.cesium-widget canvas')
  const play=page.getByTestId('hydro-play')
  const slider=page.getByRole('slider',{name:'模拟时刻'})
  const speed=page.getByRole('combobox',{name:'模拟播放倍率'})
  const select=page.getByRole('combobox',{name:'水动力情景'})
  const basemap=page.locator('.basemap-label select')
  const inspect=()=>map.evaluate(e=>{e.dispatchEvent(new Event('hydro-inspect'));return JSON.parse(e.dataset.hydroStats||'{}')})
  const input=t=>slider.evaluate((e,n)=>{e.value=n;e.dispatchEvent(new Event('input',{bubbles:true}))},t)
  const waitClock=async t=>page.waitForFunction(n=>{
    const e=document.querySelector('.cesium-map')
    e.dispatchEvent(new Event('hydro-inspect'))
    return JSON.parse(e.dataset.hydroStats).seconds===n && !document.querySelector('[data-testid="hydro-play"]')?.disabled
  },t)
  const seek=async t=>{await input(t);await waitClock(t)}
  const settle=async kind=>{
    await page.waitForFunction(k=>{
      const e=document.querySelector('.cesium-map')
      return e.dataset.basemap===k && e.dataset.pendingTiles==='0'
    },kind,{timeout:55000})
    await sleep(180)
  }
  const ready=async()=>{await play.waitFor({timeout:20000});await page.waitForFunction(()=>{
    const e=document.querySelector('.cesium-map')
    e.dispatchEvent(new Event('hydro-inspect'))
    return JSON.parse(e.dataset.hydroStats).normal_ready===true
  })}
  await page.getByTestId('hydro-mode').click({timeout:20000})
  await ready()
  assert.equal(await select.inputValue(),'full_reach_v3')
  assert.equal(await speed.inputValue(),'quick')
  await settle('satellite')
  const peak=manifest.overbank.peak_seconds
  for(const [name,t] of [['base',0],['rising',57600],['peak',peak],['recession',manifest.duration_seconds]]){
    await seek(t)
    const model=manifest.frames.find(f=>f.t_seconds===t)
    const overbank=parseFloat(await page.getByTestId('hydro-overbank').textContent())
    assert.equal(overbank,Number(model.overbank_added_km2.toFixed(2)))
    const camera=(await inspect()).camera
    const rgba=await page.evaluate(async png=>{
      const raw=Uint8Array.from(atob(png),v=>v.charCodeAt(0))
      const im=await createImageBitmap(new Blob([raw],{type:'image/png'}))
      const scratch=new OffscreenCanvas(im.width,im.height),ctx=scratch.getContext('2d')
      ctx.drawImage(im,0,0)
      const data=ctx.getImageData(0,0,im.width,im.height).data
      let blue=0
      for(let k=0;k<data.length;k+=4)
        if(data[k+2]>data[k]+49 && data[k+2]>data[k+1]+16) blue++
      return blue
    },(await canvas.screenshot()).toString('base64'))
    evidence.frames[name]={time:t,overbank,camera,blue_pixels:rgba}
    await write(name+'.png',await page.screenshot())
  }
  assert.deepEqual(evidence.frames.base.camera,evidence.frames.peak.camera)
  assert.deepEqual(evidence.frames.base.camera,evidence.frames.recession.camera)
  assert.ok(evidence.frames.peak.blue_pixels>evidence.frames.base.blue_pixels+14000)
  assert.ok(evidence.frames.peak.blue_pixels>evidence.frames.recession.blue_pixels+8000)
  assert.equal((await inspect()).initial_frame_cached,false)

  for(const marker of manifest.overbank.witnesses){
    const series=await (await fetch(host+endpoint+'/series?lon='+marker.lon+'&lat='+marker.lat)).json()
    assert.equal(series.cell,marker.cell)
    assert.equal(series.series[0].wet,false)
    const row=series.series.find(s=>s.t_seconds===peak)
    assert.ok(row.depth_m>=.10)
    await seek(0)
    await page.getByRole('button',{name:marker.label,exact:true}).click()
    await page.getByTestId('hydro-point').waitFor()
    await settle('satellite')
    assert.match(await page.getByTestId('hydro-point').textContent(),new RegExp(series.series[0].depth_m.toFixed(2)+' m'))
    await write('land-'+marker.cell+'-base.png',await page.screenshot())
    await seek(peak)
    const s=await page.getByTestId('hydro-point').textContent()
    assert.ok(s.includes(row.depth_m.toFixed(2)+' m') && s.includes(row.speed_mps.toFixed(2)+' m/s'))
    assert.ok((await page.getByTestId('hydro-stage').textContent()).includes(row.stage_m.toFixed(2)+' m'))
    await write('land-'+marker.cell+'-peak.png',await page.screenshot())
    evidence.lands.push({marker,base:series.series[0],peak:row,end:series.series.at(-1)})
    await page.getByRole('button',{name:'返回面积过程',exact:true}).click()
  }
  await page.getByRole('button',{name:'全河段',exact:true}).click()
  await settle('satellite')
  await seek(peak)
  const still=await canvas.screenshot()
  await sleep(500)
  assert.ok(still.equals(await canvas.screenshot()),'暂停时水面不应变化')

  // Fail one uncached frame and confirm timeline and surface wait at the last valid time.
  const delayed=manifest.frames.find(f=>f.t_seconds===162000)
  await page.route('**/assets/'+delayed.file,r=>r.abort(),{times:1})
  await input(delayed.t_seconds)
  const retry=page.getByRole('button',{name:/该帧加载失败/})
  await retry.waitFor()
  assert.equal((await inspect()).seconds,peak)
  await retry.click()
  await waitClock(delayed.t_seconds)
  assert.equal((await inspect()).initial_frame_cached,false)

  await seek(0)
  await speed.selectOption('quick')
  const started=performance.now()
  await page.evaluate(()=>{
    const canvas=document.querySelector('.cesium-widget canvas')
    const stream=canvas.captureStream(30)
    const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:3200000})
    const clips=[]
    recorder.ondataavailable=e=>{if(e.data.size)clips.push(e.data)}
    window.finishOverbank=()=>new Promise(resolve=>{
      recorder.onstop=()=>{
        stream.getTracks().forEach(t=>t.stop())
        window.overbankClip=new Blob(clips,{type:'video/webm'})
        const r=new FileReader()
        r.onload=()=>resolve(r.result.split(',')[1])
        r.readAsDataURL(window.overbankClip)
      }
      recorder.stop()
    })
    recorder.start(500)
  })
  await play.click()
  await page.waitForFunction(()=>document.querySelector('[data-testid=hydro-play]')?.textContent==='重播',null,{timeout:38000})
  evidence.fast_seconds=(performance.now()-started)/1000
  assert.ok(evidence.fast_seconds>=15 && evidence.fast_seconds<=24,evidence.fast_seconds)
  await sleep(300)
  const clip=Buffer.from(await page.evaluate(()=>window.finishOverbank()),'base64')
  await write('overbank-replay.webm',clip)
  evidence.video=await page.evaluate(async()=>{
    const video=document.createElement('video')
    const url=URL.createObjectURL(window.overbankClip)
    const loaded=new Promise((resolve,reject)=>{
      video.addEventListener('loadeddata',resolve,{once:true})
      video.addEventListener('error',reject,{once:true})
    })
    video.src=url
    await loaded
    URL.revokeObjectURL(url)
    return {width:video.videoWidth,height:video.videoHeight,bytes:window.overbankClip.size}
  })
  await basemap.selectOption('local')
  await settle('local')
  await seek(0)
  await speed.selectOption('1')
  await page.evaluate(()=>{
    window.measured=[]
    document.querySelector('.cesium-map').addEventListener('hydro-render',()=>window.measured.push(performance.now()))
  })
  await play.click()
  await sleep(3500)
  await page.evaluate(()=>{window.measured.length=0})
  await sleep(120000)
  const times=await page.evaluate(()=>window.measured)
  const gaps=times.slice(1).map((t,i)=>t-times[i])
  evidence.performance={fps:1000*(times.length-1)/(times.at(-1)-times[0]),frames:times.length,
    longestMs:Math.max(...gaps),width:1920,height:1080,basemap:'local'}
  assert.ok(evidence.performance.fps>=30,evidence.performance)
  await play.click()
  await select.selectOption('full_reach_v2')
  await ready()
  assert.equal(await page.getByTestId('hydro-overbank').count(),0)
  evidence.modes.v2=(await inspect()).primitives
  await select.selectOption('full_reach_v3')
  await ready()
  assert.equal(parseFloat(await page.getByTestId('hydro-overbank').textContent()),0)
  evidence.modes.v3=(await inspect()).primitives
  assert.equal(evidence.modes.v2,evidence.modes.v3)
  await page.getByRole('button',{name:'静态情景',exact:true}).click()
  await page.getByTestId('area-stat').waitFor()
  assert.equal(await page.getByRole('combobox',{name:/假设水位/}).locator('option').count(),11)
  await page.getByText('真实历史降雨 · CHM_PRE',{exact:true}).waitFor()
  evidence.modes.static=(await inspect()).primitives
  assert.equal(evidence.modes.static,evidence.modes.v3-2)
  await page.getByTestId('stage-replay-mode').click()
  await page.getByRole('region',{name:'陆地淹没时间轴'}).waitFor()
  assert.equal(await page.getByRole('slider',{name:'演示进度'}).getAttribute('max'),'12')
  assert.equal((await inspect()).context_lost,false)
  assert.deepEqual(errors.filter(x=>!x.includes('net::ERR_FAILED')&&!x.includes('net::ERR_ABORTED')),[])
  evidence.errors=errors
  await write('checks.json',JSON.stringify(evidence,null,2)+'\n')
  console.log(JSON.stringify({quick_s:evidence.fast_seconds,performance:evidence.performance,lands:evidence.lands,modes:evidence.modes}))
} finally { await browser.close() }
