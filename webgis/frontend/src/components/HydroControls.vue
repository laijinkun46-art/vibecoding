<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { openHydrodynamics } from '../hydroData'
import { waterPalette } from '../hydroWaterShaders'

use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])
const props = defineProps({ map: Object, location: Object, runId: { type:String, required:true } })
const state = ref('loading'), error = ref(''), loading = ref(false), playing = ref(false)
const shownTime = ref(0), speed = ref(1), particles = ref(!matchMedia('(prefers-reduced-motion: reduce)').matches)
const layer = ref('natural'), quality = ref('standard'), showMesh = ref(false)
const duration = ref(0), stats = ref(null), pendingTime = ref(null), frameError = ref(false)
const floodMetadata=ref(null)
const styles = { natural: 0, depth: 1, speed: 2 }
const chartRef = ref(null), point = ref(null), pickState = ref('idle'), current = ref(null)
let data, lifetime, query, seekVersion=0, animation, lastWall, actual=0, lastUi=0
let chart, resize, areaWeights, displayedPair
const rate = 1500 // 60 h of simulated time in 144 s at 1×.
const hours = seconds => (seconds / 3600).toFixed(1) + ' 小时'
const format = (x, places=2) => Number(x).toFixed(places)
const ended = computed(() => shownTime.value >= duration.value && duration.value > 0)
const pointText = computed(() => point.value ? `${format(point.value.lon,5)}° E · ${format(point.value.lat,5)}° N` : '')

function noSchedule() {
  cancelAnimationFrame(animation)
  animation = undefined
  lastWall = undefined
}
function pause() {
  playing.value = false
  noSchedule()
  shownTime.value = actual
  if (displayedPair && state.value==='ready') report(displayedPair,actual)
}
function inFlight(i) {
  const j = Math.min(data.manifest.frames.length-1,i+1)
  return Promise.all([data.ensure(i,lifetime.signal),data.ensure(j,lifetime.signal)])
}
function prefetch(i) {
  data.prune(i)
  for (let k=i+2; k <= Math.min(data.manifest.frames.length-1,i+3); k++)
    data.ensure(k,lifetime.signal).catch(() => {}) // Retry and surface errors if a required frame is missing.
}
function makeWeights() {
  let total=0
  const weights = new Float64Array(data.manifest.cell_count)
  for (let i=0; i<weights.length; i++) {
    const [w,s,e,n] = data.cells.subarray(5*i,5*i+4)
    weights[i]=(e-w)*(n-s)*Math.cos((s+n)*Math.PI/360)
    total+=weights[i]
  }
  const adjust=data.manifest.mesh_area_km2/total
  for (let i=0; i<weights.length; i++) weights[i]*=adjust
  return weights
}
function report(pair,seconds) {
  shownTime.value=seconds
  if (!pair.first || !pair.second) return
  const at = (cell,k) => pair.first[4*cell+k]*(1-pair.alpha)+pair.second[4*cell+k]*pair.alpha
  const threshold = data.manifest.wet_threshold_m
  let area=0, maxDepth=0, maxSpeed=0, overbank=0
  for (let i=0;i<areaWeights.length;i++) {
    const h=at(i,0)
    if (h>=threshold) {
      area+=areaWeights[i]
      if (data.overbankWeights && !data.initiallyWet[i]) overbank+=data.overbankWeights[i]/1e6
      maxDepth=Math.max(maxDepth,h)
      maxSpeed=Math.max(maxSpeed,Math.hypot(at(i,2),at(i,3)))
    }
  }
  const exact = pair.alpha===0 ? data.manifest.frames[pair.i] : pair.alpha===1 ? data.manifest.frames[pair.j] : null
  stats.value = { area: exact?.wet_km2 ?? area, maxDepth, maxSpeed, overbank:exact?.overbank_added_km2 ?? overbank }
  if (point.value) {
    const id = point.value.cell
    current.value = { depth: at(id,0), stage:at(id,1), speed: Math.hypot(at(id,2),at(id,3)) }
  }
}
let priorIndex=-1
function present(pair, seconds, ui) {
  displayedPair = pair
  props.map.updateHydro(pair, seconds, { style: styles[layer.value], particles: particles.value,
    lowQuality: quality.value==='low', showMesh: showMesh.value })
  if (ui) report(pair, seconds)
}
function render(seconds, ui=false) {
  const pair=data.pair(seconds)
  if (!pair.first || !pair.second) return false
  if (priorIndex!==pair.i) { priorIndex=pair.i; prefetch(pair.i) }
  present(pair,seconds,ui)
  return true
}
function fail(reason) {
  pause()
  state.value='error'
  error.value=reason?.message || '无法读取模拟成果'
  props.map?.disableHydro()
}
function holdFrame(seconds) {
  pendingTime.value=seconds
  loading.value=true
  frameError.value=false
  const index=data.pair(seconds).i
  data.prune(index)
  return inFlight(index)
}
function frameFailure(seconds) {
  pause()
  loading.value=false
  pendingTime.value=seconds
  frameError.value=true
}
function tick(now) {
  animation=undefined
  if (!playing.value || document.hidden || state.value!=='ready') return
  const simulationRate=speed.value==='quick' ? duration.value/18 : rate*speed.value
  const proposed=Math.min(duration.value,actual+Math.min(50,lastWall===undefined ? 0 : now-lastWall)*simulationRate/1000)
  const updateUi=now-lastUi>120 || proposed===duration.value
  if (!render(proposed,updateUi)) {
    lastWall=undefined
    const request=seekVersion
    holdFrame(proposed).then(() => {
      if (lifetime.signal.aborted || request!==seekVersion) return
      loading.value=false
      pendingTime.value=null
      if (playing.value && !document.hidden && !animation) animation=requestAnimationFrame(tick)
    }).catch(() => { if (!lifetime.signal.aborted && request===seekVersion) frameFailure(proposed) })
    return
  }
  actual=proposed
  if (updateUi) lastUi=now
  lastWall=now
  if (actual>=duration.value) pause()
  else animation=requestAnimationFrame(tick)
}
async function seek(seconds) {
  pause()
  const request=++seekVersion
  const target=Math.min(duration.value,Math.max(0,seconds))
  pendingTime.value=target
  loading.value=true
  frameError.value=false
  // Coalesce rapid slider inputs before touching the frame cache.
  await new Promise(resolve=>setTimeout(resolve,28))
  if (request!==seekVersion || lifetime.signal.aborted) return
  try {
    await holdFrame(target)
    if (request!==seekVersion || lifetime.signal.aborted) return
    props.map.resetHydroParticles()
    actual=target
    render(actual,true)
    pendingTime.value=null
    loading.value=false
  } catch {
    if (!lifetime.signal.aborted && request===seekVersion) frameFailure(target)
  }
}
async function toggle() {
  if (playing.value) return pause()
  if (ended.value) await seek(0)
  if (frameError.value || loading.value) return
  if (state.value!=='ready' || document.hidden) return
  playing.value=true
  if (!animation) animation=requestAnimationFrame(tick)
}
function visibility() {
  if (document.hidden) pause()
}
async function load() {
  lifetime?.abort()
  lifetime=new AbortController()
  const signal=lifetime.signal
  state.value='loading'
  try {
    data=await openHydrodynamics(signal,props.runId)
    await inFlight(0)
    if (signal.aborted) return
    areaWeights=makeWeights()
    await props.map.enableHydro(data,signal)
    if (signal.aborted) return
    state.value='ready'
    duration.value=data.manifest.duration_seconds
    floodMetadata.value=data.manifest.overbank ?? null
    speed.value=floodMetadata.value?'quick':1
    actual=0
    priorIndex=-1
    render(0,true)
  } catch (reason) { if (!signal.aborted) fail(reason) }
}
function drawChart() {
  if (!chartRef.value || !data) return
  if (!chart) {
    chart=init(chartRef.value)
    resize=new ResizeObserver(() => chart?.resize())
    resize.observe(chartRef.value)
  }
  const area=data.manifest.frames.map(f=>[f.t_seconds/3600,f.wet_km2])
  const rows=point.value?.series
  const series=rows ? [
    { name:'水深 m', type:'line', symbol:'none', data: rows.map(r=>[r.t_seconds/3600,r.depth_m]) },
    { name:'流速 m/s', type:'line', symbol:'none', yAxisIndex:1, data: rows.map(r=>[r.t_seconds/3600,r.speed_mps]) },
  ] : [{ name:'湿区面积 km²', type:'line', symbol:'none', areaStyle:{ opacity:.13 }, data:area }]
  if (!rows && floodMetadata.value) series.push({ name:'两岸新增 km²', type:'line', symbol:'none',
    data:data.manifest.frames.map(f=>[f.t_seconds/3600,f.overbank_added_km2]) })
  series[0].markLine={ symbol:'none', label:{ show:false }, lineStyle:{ color:'#b36c10',type:'dashed' }, data:[{xAxis:shownTime.value/3600}] }
  chart.setOption({ animation:false, color:['#087d90','#bd7b22'], tooltip:{trigger:'axis'},
    legend:{ top:0, textStyle:{fontSize:11} }, grid:{ left:35,right:rows ? 38 : 14,top:34,bottom:31 },
    xAxis:{type:'value',name:'h',max:duration.value/3600,minInterval:1},
    yAxis:rows ? [{type:'value',min:0},{type:'value',min:0,splitLine:{show:false}}] : [{type:'value',min:0}],
    series }, {notMerge:true})
}
async function pick(location) {
  if (!location || state.value!=='ready') return
  query?.abort()
  query=new AbortController()
  const signal=query.signal
  pickState.value='loading'
  try {
    const record=await data.series(location.lon,location.lat,signal)
    if (signal.aborted) return
    point.value=record.state==='ok'?record:null
    current.value=null
    pickState.value=record.state
    if (point.value && displayedPair) report(displayedPair,actual)
    drawChart()
  } catch { if (!signal.aborted) pickState.value='error' }
}
function focusWitness(marker) {
  props.map.viewHydroLocation(marker.lon,marker.lat)
  pick(marker)
}
function clearPoint() {
  query?.abort()
  point.value=null
  current.value=null
  pickState.value='idle'
  drawChart()
}
onMounted(() => { document.addEventListener('visibilitychange',visibility); load() })
watch(() => props.location,pick)
watch([particles,layer,quality,showMesh],() => { if (state.value==='ready' && displayedPair) present(displayedPair,actual,false) })
watch(state,async value => { if(value==='ready') { await nextTick(); drawChart() } })
watch(shownTime,() => {
  chart?.setOption({ series:[{markLine:{data:[{xAxis:shownTime.value/3600}]}}] })
})
onBeforeUnmount(() => {
  pause()
  lifetime?.abort()
  query?.abort()
  document.removeEventListener('visibilitychange',visibility)
  resize?.disconnect()
  chart?.dispose()
  props.map?.disableHydro()
})
</script>

<template>
  <section class="analysis-section hydro-panel" aria-label="全河段水动力">
    <h3>全河段水动力</h3>
    <p class="panel-note">基于真实地形和假设参数的洪水动态情景模拟</p>
    <p v-if="state==='loading'" class="panel-note" role="status">正在加载全河段结果…</p>
    <div v-else-if="state==='error'" role="alert" class="panel-note error-text">{{error}} <button class="secondary-button" @click="load">重试</button></div>
    <template v-else>
      <div class="stat-feature"><span>全域湿区面积</span><strong data-testid="hydro-area">{{format(stats?.area ?? 0)}} <small>km²</small></strong></div>
      <div v-if="floodMetadata" class="stat-pair"><div><span>两岸新增淹没</span><strong data-testid="hydro-overbank">{{format(stats?.overbank ?? 0)}} km²</strong></div></div>
      <div class="stat-pair"><div><span>最大水深</span><strong>{{format(stats?.maxDepth ?? 0)}} m</strong></div><div><span>最大湿区流速</span><strong>{{format(stats?.maxSpeed ?? 0)}} m/s</strong></div></div>
      <label class="field-label">水面着色<select v-model="layer"><option value="natural">自然水面</option><option value="depth">水深</option><option value="speed">流速</option></select></label>
      <div v-if="layer==='natural'" class="hydro-water-legend" role="group" aria-label="动态水面图例">
        <span><i :style="{background:waterPalette.initial}"></i>初始水面</span>
        <span><i :style="{background:waterPalette.floodShallow}"></i>新增淹没</span>
      </div>
      <p v-if="layer==='natural'" class="panel-note">以预热结束后的首个展示时刻（0 小时）为基准。</p>
      <p v-if="layer!=='natural'" class="hydro-scale" :class="{ velocity:layer==='speed' }"><span>0</span><i></i><span>{{layer==='speed'?'2.5 m/s':'10 m'}}+</span></p>
      <label class="field-label">水面画质<select v-model="quality"><option value="standard">标准</option><option value="low">节能</option></select></label>
      <div class="layer-toggles"><label><input type="checkbox" v-model="particles">显示流动跟踪点</label><label><input type="checkbox" v-model="showMesh">原单元边界</label></div>
      <div class="hydro-views" role="group" aria-label="水动力视角">
        <button class="secondary-button" @click="map.viewHydro('full')">全河段</button>
        <button class="secondary-button" @click="map.viewHydro('bend')">河弯斜视</button>
        <button class="secondary-button" @click="map.viewHydro('bank')">漫岸近景</button>
      </div>
      <div class="hydro-query">
        <h4>{{point ? '点位过程' : '湿区面积过程'}}</h4>
        <p v-if="pickState==='loading'" role="status">正在查询位置…</p>
        <p v-else-if="pickState==='outside'">所选位置超出计算域。</p>
        <p v-else-if="pickState==='error'">位置查询失败，请重试。</p>
        <p v-else-if="point" data-testid="hydro-point">{{pointText}} · {{format(current?.depth ?? 0)}} m · {{format(current?.speed ?? 0)}} m/s</p>
        <p v-else>点击地图查询模型单元的水深、流速及其变化。</p>
        <p v-if="point && pickState==='ok'" data-testid="hydro-stage">水面高程 {{format(current?.stage ?? 0)}} m · EGM2008</p>
        <button v-for="marker in floodMetadata?.witnesses ?? []" :key="marker.cell" class="secondary-button"
          @click="focusWitness(marker)">{{marker.label}}</button>
        <div class="stat-chart hydro-chart" ref="chartRef" role="img" aria-label="水动力过程图"></div>
        <button v-if="point" class="text-button" @click="clearPoint">返回面积过程</button>
      </div>
    </template>
  </section>
  <Teleport to="#hydro-controls-slot">
    <section v-if="state==='ready'" class="scenario-timeline" aria-label="全河段模拟时间轴">
      <div class="timeline-heading">
        <strong>模拟历时 <span data-testid="hydro-time">{{hours(shownTime)}} / {{hours(duration)}}</span></strong>
        <button v-if="frameError" class="text-button" @click="seek(pendingTime)">该帧加载失败 · 重试</button>
        <span v-else-if="loading" role="status">正在加载该时刻…</span>
        <span v-else-if="ended && floodMetadata" class="hydro-end-note" data-testid="hydro-end-note">退水末帧 · 新增湿区仍有 {{format(stats?.overbank ?? 0)}} km²</span>
        <span v-else>从预热结束起算</span>
      </div>
      <div class="timeline-control">
        <button @click="toggle" :disabled="loading" data-testid="hydro-play">{{playing?'暂停':ended?'重播':'播放'}}</button>
        <input type="range" min="0" :max="duration" step="30" :value="pendingTime ?? shownTime" @input="seek(Number($event.target.value))" aria-label="模拟时刻">
        <select v-model.number="speed" aria-label="模拟播放倍率"><option v-if="floodMetadata" value="quick">快速 · 约 18 秒</option><option :value="0.5">0.5×</option><option :value="1">1×</option><option :value="2">2×</option><option :value="4">4×</option><option :value="8">8×</option></select>
      </div>
      <button v-if="floodMetadata" class="secondary-button hydro-peak" @click="seek(floodMetadata.peak_seconds)">跳到漫岸洪峰</button>
    </section>
  </Teleport>
</template>

<style scoped>
.hydro-panel .panel-note{margin:.6rem 0;color:#566e76}
.hydro-water-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;color:#365760;font-size:12px}
.hydro-water-legend span{display:inline-flex;align-items:center;gap:6px}
.hydro-water-legend i{width:13px;height:9px;border-radius:2px}
.hydro-views{display:flex;flex-wrap:wrap;gap:6px;margin-top:.6rem}
.hydro-views button{flex:1 0 auto;padding:.35rem .45rem;font-size:12px}
.hydro-query{margin-top:1rem;padding-top:1rem;border-top:1px solid #dce7e9}
.hydro-query p{font-size:13px;color:#536e75;margin:.4rem 0}
.hydro-chart{height:170px}
.hydro-scale{display:flex;align-items:center;gap:6px;color:#536e75;font-size:12px;margin-top:6px}
.hydro-scale i{display:block;width:106px;height:7px;border-radius:3px;background:linear-gradient(90deg,#26badf,#064082)}
.hydro-scale.velocity i{background:linear-gradient(90deg,#1c78c2,#f7e347)}
.timeline-control select{color:#24515e;background:white;border:1px solid #c8dcde;border-radius:5px;padding:5px}
.timeline-heading strong span{font-size:inherit;color:inherit}
.timeline-heading .hydro-end-note{color:#365b65;font-variant-numeric:tabular-nums}
.hydro-peak{background:#edf7f6;color:#0e6466;border-color:#a9d0cd}
.hydro-peak:hover{background:#dff0ee}
</style>
