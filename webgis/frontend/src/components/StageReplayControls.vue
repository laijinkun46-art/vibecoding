<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ map: Object })
const replay = ref(null)
const error = ref('')
const elapsed = ref(0)
const stage = ref(0)
const addedArea = ref(0)
const playing = ref(false)
const speed = ref(1)
const phase = ref('基流')
let controller, frame, previous

const duration = computed(()=>replay.value?.data.duration_s || 12)
const peakTime = computed(()=>(replay.value?.data.stages[2][0] ?? .6)*duration.value)
const finished = computed(()=>elapsed.value>=duration.value)
const timeText = computed(()=>elapsed.value.toFixed(1) + ' / '+duration.value+' 秒')

function display(seconds) {
  const active = replay.value
  if (!active) return
  const [[start,base],[mid,rise],[peak,maximum],[finish,end]] = active.data.stages
  const t = seconds/duration.value
  const hold = Math.min(peak+.06,finish)
  const interpolate = (a,b,from,to)=>a+(b-a)*(t-from)/(to-from)
  const level = t<=mid ? interpolate(base,rise,start,mid)
    : t<peak ? interpolate(rise,maximum,mid,peak)
    : t<=hold ? maximum : interpolate(maximum,end,hold,finish)
  elapsed.value = seconds
  stage.value = level
  addedArea.value = active.areaAt(level)-active.areaAt(base)
  phase.value = t===0 ? '基流' : t<peak ? '涨水' : t<=hold ? '洪峰' : '退水'
  props.map.updateStageReplay(level,seconds,t<peak)
}
function pause() {
  playing.value=false
  cancelAnimationFrame(frame)
  previous=undefined
}
function tick(now) {
  if(!playing.value || document.hidden) return
  const delta=previous===undefined ? 0 : Math.min((now-previous)/1000,.1)
  previous=now
  display(Math.min(duration.value,elapsed.value+delta*speed.value))
  if(finished.value) pause()
  else frame=requestAnimationFrame(tick)
}
function toggle() {
  if(playing.value) { pause(); return }
  if(finished.value) display(0)
  playing.value=true
  frame=requestAnimationFrame(tick)
}
function seek(seconds) {
  pause()
  display(seconds)
}
async function load() {
  controller?.abort()
  controller=new AbortController()
  const signal=controller.signal
  error.value=''
  try {
    const active=await props.map.enableStageReplay(signal)
    if(signal.aborted) return
    replay.value=active
    display(0)
    if(!document.hidden && !matchMedia('(prefers-reduced-motion: reduce)').matches) toggle()
  } catch (reason) {
    if(!signal.aborted) error.value=reason.message
  }
}
function visibility() {
  if(document.hidden) pause()
}
onMounted(()=>{
  document.addEventListener('visibilitychange',visibility)
  load()
})
onBeforeUnmount(()=>{
  pause()
  controller?.abort()
  document.removeEventListener('visibilitychange',visibility)
  props.map?.disableStageReplay()
})
</script>

<template>
  <section class="analysis-section replay-panel" aria-label="洪水连续演示">
    <h3>2024 年洪水情景演示</h3>
    <p class="panel-note">以 2024 年 9 月洪水为背景，按原静态假设水位连续展示。时间轴为演示时长。</p>
    <p v-if="!replay&&!error" class="panel-note" role="status">正在读取地形淹没阈值…</p>
    <p v-if="error" class="panel-note error-text" role="alert">{{error}} <button class="secondary-button" @click="load">重试</button></p>
    <template v-if="replay">
      <div class="stat-feature">
        <span>初始水面范围外 · 当前淹没</span>
        <strong data-testid="replay-added">{{addedArea.toFixed(2)}}<small> km²</small></strong>
      </div>
      <div class="stat-pair">
        <div><span>假设水位 · EGM2008</span><strong data-testid="replay-stage">{{stage.toFixed(2)}} m</strong></div>
        <div><span>当前阶段</span><strong data-testid="replay-phase">{{phase}}</strong></div>
      </div>
      <div class="replay-legend" role="group" aria-label="淹没图例">
        <span><i></i>初始湿区</span><span><i class="new-water"></i>新增淹没</span>
      </div>
      <button class="secondary-button" @click="map.viewStageReplay()">查看全域</button>
      <button class="secondary-button" @click="map.viewFlood()">查看城区</button>
    </template>
  </section>
  <Teleport to="#hydro-controls-slot">
    <section v-if="replay" class="scenario-timeline replay-timeline" aria-label="陆地淹没时间轴">
      <div class="timeline-heading"><strong>{{phase}} · {{stage.toFixed(2)}} m</strong><span data-testid="replay-time">{{timeText}}</span></div>
      <div class="timeline-control">
        <button data-testid="replay-play" @click="toggle">{{playing?'暂停':finished?'重播':'播放'}}</button>
        <input type="range" min="0" :max="duration" step="0.01" :value="elapsed" aria-label="演示进度" @input="seek(Number($event.target.value))">
        <select v-model.number="speed" aria-label="演示倍率"><option :value=".5">0.5×</option><option :value="1">1×</option><option :value="2">2×</option></select>
      </div>
      <div class="scenario-steps">
        <button :aria-pressed="elapsed===0" @click="seek(0)">基流</button>
        <button :aria-pressed="phase==='洪峰'" @click="seek(peakTime)">洪峰</button>
        <button :aria-pressed="finished" @click="seek(duration)">退水</button>
      </div>
    </section>
  </Teleport>
</template>

<style scoped>
.replay-legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:20px;color:#375760;font-size:13px}
.replay-legend span{display:inline-flex;align-items:center;gap:6px}
.replay-legend i{display:inline-block;width:14px;height:10px;border-radius:2px;background:#295954}
.replay-legend .new-water{background:#36b6dc}
.replay-timeline .scenario-steps{grid-template-columns:repeat(3,1fr)}
.replay-timeline select{background:#fff;border:1px solid #c8dcde;color:#24515e;border-radius:5px;padding:5px}
</style>
