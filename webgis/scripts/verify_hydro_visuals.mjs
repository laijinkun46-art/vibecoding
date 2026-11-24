import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const baseline = process.env.HYDRO_VISUAL_BASELINE || 'http://127.0.0.1:5174'
const current = process.env.WEBGIS_FRONTEND_URL || 'http://127.0.0.1:5173'
const root = process.env.HYDRO_TEST_OUTPUT
assert.ok(root,'需要独立验收输出目录 HYDRO_TEST_OUTPUT')
const movie = process.argv.includes('--record')
const browser = await chromium.launch({ channel:'msedge', headless:true, args:['--enable-webgl','--ignore-gpu-blocklist'] })
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms))
const scenario = ['base','peak','recession']
const cameras = [['full','全河段'],['bend','河弯斜视'],['bank','漫岸近景']]
const prefix = '/api/hydrodynamics/runs/full_reach_v2'
const manifest = await (await fetch(current+prefix+'/manifest')).json()
const peak = manifest.frames.reduce((a,b)=>a.overbank_km2>=b.overbank_km2 ? a : b)
const times = [0,peak.t_seconds,manifest.duration_seconds]
const errors = []

async function open(url, isOld=false, basemap='local') {
  const page = await browser.newPage({viewport:{width:1920,height:1080}})
  page.on('pageerror',e=>errors.push(String(e)))
  page.on('console',m=>{if (m.type()==='error' && !/net::ERR_|底图/.test(m.text())) errors.push(m.text())})
  if (basemap==='local') {
    await page.route(/https:\/\/(services\.arcgisonline\.com|tile\.openstreetmap\.org)\//,r=>r.abort())
  }
  if (isOld) {
    // Preserve the baseline renderer. Add a camera-only probe to the copied build in this test page.
    await page.route(/\/assets\/index-[^/]+\.js$/, async route=>{
      const res=await route.fetch()
      const code=await res.text()
      const probe=/([\w$]+)\.scene\.postRender\.addEventListener\(\(\)=>\{[\w$]+&&([\w$]+)\.value\?\.dispatchEvent\(new Event\(`hydro-render`\)\)\}\)/
      const match=code.match(probe)
      assert.ok(match,'仅对原始基准构建启用相机对照探针')
      const [original, viewer, element]=match
      const add=[
        '('+original+',',
        element+'.value.addEventListener("hydro-match-camera",ev=>{',
        'const cam='+viewer+'.camera, xyz=([x,y,z])=>({x,y,z}), c=ev.detail;',
        'cam.setView({destination:xyz(c.position),orientation:{direction:xyz(c.direction),up:xyz(c.up)}});',
        element+'.value.dataset.cameraMatch=JSON.stringify({position:[cam.positionWC.x,cam.positionWC.y,cam.positionWC.z],',
        'direction:[cam.directionWC.x,cam.directionWC.y,cam.directionWC.z],up:[cam.upWC.x,cam.upWC.y,cam.upWC.z]});',
        viewer+'.scene.requestRender();}))',
      ].join('')
      await route.fulfill({response:res,body:code.replace(probe,()=>add)})
    })
  }
  await page.goto(url+'/?measureHydro=1',{waitUntil:'domcontentloaded'})
  await page.locator('.basemap-label select').selectOption(basemap,{timeout:30000})
  await page.locator('[data-testid=hydro-mode]').click({timeout:30000})
  const slider=page.getByRole('slider',{name:'模拟时刻'})
  const play=page.locator('[data-testid=hydro-play]')
  const map=page.locator('.cesium-map')
  const style=page.getByLabel('水面着色')
  await play.waitFor({timeout:30000})
  const inspect=()=>map.evaluate(e=>{e.dispatchEvent(new Event('hydro-inspect'));return JSON.parse(e.dataset.hydroStats||'{}')})
  const idle=async()=> {
    await sleep(420)
    await page.waitForFunction(()=>document.querySelector('.cesium-map')?.dataset.pendingTiles==='0',{}, {timeout:30000})
  }
  const input=t=>slider.evaluate((e,n)=>{e.value=n;e.dispatchEvent(new Event('input',{bubbles:true}))},t)
  const seek=async t=>{
    await input(t)
    await page.waitForFunction(()=>!document.querySelector('[data-testid=hydro-play]')?.disabled)
    assert.equal(Number(await slider.inputValue()),t)
    if (!isOld) assert.equal((await inspect()).seconds,t)
  }
  return {page,slider,play,map,style,idle,input,seek,inspect}
}

async function save(path,data) {
  await fs.writeFile(path,data,{flag:'wx'})
}

try {
  if (movie) {
    const {page,slider,play,seek,idle}=await open(current,false,'satellite')
    await page.waitForTimeout(1200)
    await page.getByLabel('模拟播放倍率').selectOption('2')
    const started=performance.now()
    const record=await page.evaluate(()=>{
      const canvas=document.querySelector('.cesium-widget canvas')
      const stream=canvas.captureStream(30)
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:3400000})
      const chunks=[]
      recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)}
      window.finishWaterVideo=()=>new Promise(resolve=>{
        recorder.onstop=()=>{
          stream.getTracks().forEach(t=>t.stop())
          const reader=new FileReader()
          reader.onload=()=>resolve(reader.result.split(',')[1])
          window.recordedWaterVideo=new Blob(chunks,{type:'video/webm'})
          reader.readAsDataURL(window.recordedWaterVideo)
        }
        recorder.stop()
      })
      recorder.start(1000)
      return { width:canvas.width,height:canvas.height,basemap:document.querySelector('.basemap-label select').value }
    })
    await play.click()
    await page.waitForFunction(()=>Number(document.querySelector('[aria-label="模拟时刻"]').value)>=39600,{}, {timeout:60000})
    await page.getByRole('button',{name:'河弯斜视',exact:true}).click()
    await page.waitForFunction(()=>Number(document.querySelector('[aria-label="模拟时刻"]').value)>=64800,{}, {timeout:60000})
    await page.getByRole('button',{name:'漫岸近景',exact:true}).click()
    await page.waitForFunction(()=>Number(document.querySelector('[aria-label="模拟时刻"]').value)>=111600,{}, {timeout:60000})
    await page.getByRole('button',{name:'全河段',exact:true}).click()
    await page.waitForFunction(()=>document.querySelector('[data-testid=hydro-play]')?.textContent==='重播',{}, {timeout:120000})
    assert.equal(Number(await slider.inputValue()),manifest.duration_seconds)
    await sleep(600)
    const video=Buffer.from(await page.evaluate(()=>window.finishWaterVideo()),'base64')
    assert.ok(video.length>100000)
    await save(join(root,'全河段涨水漫岸退水.webm'),video)
    const wallSeconds=(performance.now()-started)/1000
    const decoded=await page.evaluate(async()=>{
      const video=document.createElement('video')
      video.muted=true
      video.preload='auto'
      const asset=URL.createObjectURL(window.recordedWaterVideo)
      video.src=asset
      const read=(event)=>new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('video '+event+' timeout')),10000)
        video.addEventListener(event,()=>{clearTimeout(timer);resolve()},{once:true})
      })
      await read('loadeddata')
      const probe=document.createElement('canvas')
      probe.width=96
      probe.height=58
      const ctx=probe.getContext('2d')
      const samples=[]
      for (const t of [2,24,45,61]) {
        const changed=read('seeked')
        video.currentTime=t
        await changed
        ctx.drawImage(video,0,0,probe.width,probe.height)
        const rgba=ctx.getImageData(0,0,probe.width,probe.height).data
        let sum=0, squares=0
        for(let i=0;i<rgba.length;i+=4) {
          const value=(rgba[i]+rgba[i+1]+rgba[i+2])/3
          sum+=value
          squares+=value*value
        }
        const length=rgba.length/4, mean=sum/length
        samples.push({seconds:video.currentTime,mean,sd:Math.sqrt(squares/length-mean*mean)})
      }
      URL.revokeObjectURL(asset)
      return {width:video.videoWidth,height:video.videoHeight,samples}
    })
    assert.ok(decoded.samples.every(s=>s.mean>5 && s.sd>10),'录屏出现空帧或无法读取')
    await save(join(root,'video.json'),JSON.stringify({...record,bytes:video.length,record_wall_seconds:wallSeconds,
      model_seconds:manifest.duration_seconds,speed:2,decoded},null,2))
    await seek(peak.t_seconds)
    for (const [name,label] of cameras) {
      await page.getByRole('button',{name:label,exact:true}).click()
      await idle()
      await save(join(root,'satellite-'+name+'-peak.png'),await page.screenshot())
    }
    console.log('录屏已解码校验',JSON.stringify({wallSeconds,bytes:video.length,decoded}))
  } else {
    const folder=join(root,process.env.HYDRO_COMPARISON_DIR || 'comparison')
    await fs.mkdir(folder)
    const after=await open(current)
    const positions={}
    const bench={}
    for (const [view,label] of cameras) {
      await after.page.getByRole('button',{name:label,exact:true}).click()
      await after.idle()
      positions[view]=(await after.inspect()).camera
      for (let i=0;i<times.length;i++) {
        await after.seek(times[i])
        const name=view+'-'+scenario[i]
        bench[name]={time:times[i],after:await after.page.locator('[data-testid=hydro-area]').innerText()}
        await save(join(folder,'after-'+name+'.png'),await after.page.screenshot())
      }
    }
    await after.seek(peak.t_seconds)
    await after.page.getByLabel('原单元边界').check()
    await save(join(folder,'after-bank-grid.png'),await after.page.screenshot())
    await after.page.getByLabel('原单元边界').uncheck()
    await after.style.selectOption('depth')
    await after.page.getByText('10 m+', {exact:true}).waitFor()
    await save(join(folder,'after-bank-depth.png'),await after.page.screenshot())
    await after.style.selectOption('speed')
    await after.page.getByText('2.5 m/s+', {exact:true}).waitFor()
    await save(join(folder,'after-bank-speed.png'),await after.page.screenshot())
    await after.style.selectOption('natural')
    await after.page.getByLabel('水面画质').selectOption('low')
    assert.equal((await after.inspect()).low_quality,true)
    await after.page.getByLabel('水面画质').selectOption('standard')
    await after.idle()
    const patch = {x:1180,y:655,width:245,height:112}
    const paused=await after.page.screenshot({clip:patch})
    await sleep(800)
    assert.ok(paused.equals(await after.page.screenshot({clip:patch})),'暂停时水面或粒子变化')
    await after.play.click()
    await sleep(700)
    assert.ok(!paused.equals(await after.page.screenshot({clip:patch})),'播放时未检测到水面变化')
    await after.play.click()

    const unavailable=manifest.frames[109]
    await after.page.route('**/assets/'+unavailable.file, r=>r.abort(), {times:1})
    const previous=(await after.inspect()).seconds
    await after.input(unavailable.t_seconds)
    await after.page.getByRole('button',{name:/该帧加载失败/}).waitFor()
    assert.equal((await after.inspect()).seconds,previous)
    await after.page.getByRole('button',{name:/该帧加载失败/}).click()
    await after.page.waitForFunction(()=>!document.querySelector('[data-testid=hydro-play]')?.disabled)
    assert.equal((await after.inspect()).seconds,unavailable.t_seconds)
    const slow = manifest.frames[36], latest=manifest.frames[61]
    await after.page.route('**/assets/'+slow.file,async r=>{await sleep(250);await r.continue()},{times:1})
    await after.input(slow.t_seconds)
    await sleep(58)
    await after.seek(latest.t_seconds)
    await sleep(300)
    const final=await after.inspect()
    assert.equal(final.seconds,latest.t_seconds)
    assert.ok(final.cache_count<=7)
    await after.page.close()

    const before=await open(baseline,true)
    for (const [view] of cameras) {
      const actual=await before.map.evaluate((e,c)=>{
        e.dispatchEvent(new CustomEvent('hydro-match-camera',{detail:c}))
        return JSON.parse(e.dataset.cameraMatch)
      },positions[view])
      for(const key of ['position','direction','up']) for(let j=0;j<3;j++)
        assert.ok(Math.abs(actual[key][j]-positions[view][key][j])<1e-6,view+' 镜头差异')
      await before.idle()
      for(let i=0;i<times.length;i++) {
        await before.seek(times[i])
        const name=view+'-'+scenario[i]
        bench[name].before=await before.page.locator('[data-testid=hydro-area]').innerText()
        assert.equal(bench[name].before,bench[name].after,name)
        await save(join(folder,'before-'+name+'.png'),await before.page.screenshot())
      }
    }
    await before.page.close()
    assert.deepEqual(errors,[])
    await save(join(folder,'comparison.json'),JSON.stringify({basemap:'local',viewport:[1920,1080],relief:1.2,
      positions,bench,checks:['same ECEF camera','same model area','freeze and play','missing frame retries',
        'ignore out-of-order response','fixed analysis legends','quality switch and original mesh overlay'],resources:final},null,2))
    console.log('18 张同视角对照及画质、资料一致性和异常帧恢复通过')
  }
} finally { await browser.close() }

