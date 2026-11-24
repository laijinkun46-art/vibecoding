<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import MapViewer from './components/MapViewer.vue'
import AnalysisCharts from './components/AnalysisCharts.vue'
import HydroRunSelector from './components/HydroRunSelector.vue'
import StageReplayControls from './components/StageReplayControls.vue'
import { loadAnalysis } from './analysisData'
const project=ref(null), data=ref(null), dataError=ref(''), connection=ref('checking')
const mapStatus=ref('loading'), mapError=ref(''), terrainStatus=ref('loading'), layerStatus=ref('loading'), riverStatus=ref('loading')
const map=ref(null), mode=ref('3D'), basemap=ref('satellite'), scenarioIndex=ref(0), layerMode=ref('scenario'), comparisonId=ref('S01_to_S02')
const hydroActive=ref(false), hydroLocation=ref(null), stageReplayActive=ref(false)
const staticActive=computed(()=>!hydroActive.value&&!stageReplayActive.value)
let openReplayOnReady=new URLSearchParams(window.location.search).get('demo')==='land-flood'
const showFlood=ref(true), showRivers=ref(true), playing=ref(false)
const reliefScale = ref(1.2)
const effectsEnabled=ref(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
const effectsPaused=ref(false), effectSpeed=ref(1), effectStatus=ref('idle')
const effects=computed(()=>({enabled:effectsEnabled.value,paused:effectsPaused.value,speed:Number(effectSpeed.value)}))
const SCENARIO_INTERVAL_MS = 1000
let playTimer
const connectionText=computed(()=>({checking:'正在连接服务',connected:'前后端已连接',error:'服务连接失败'}[connection.value]))
const scenario=computed(()=>data.value?.summary.scenarios[scenarioIndex.value])
const lastScenarioIndex=computed(()=>(data.value?.summary.scenarios.length ?? 1)-1)
const comparison=computed(()=>data.value?.summary.comparisons.find(row=>row.id===comparisonId.value))
const layer=computed(()=>{
  if(!staticActive.value || !data.value || !showFlood.value) return undefined
  const id=layerMode.value==='scenario'?scenario.value.id:comparisonId.value
  const stem=layerMode.value==='scenario'?`${id}_wet`:`${id}_change`
  return {id,mode:layerMode.value,waterLevel:scenario.value.water_level_m,asset:data.value.catalog.assets[stem]}
})
const selectedTitle=computed(()=>layerMode.value==='scenario'?`${scenario.value?.id??''} · 假设水位 ${scenario.value?.water_level_m??'—'} m`:`${comparison.value?.before??''} / ${comparison.value?.after??''} 两期对比`)
async function connect(){
  connection.value='checking'
  try{
    const responses=await Promise.all([fetch('/api/health',{signal:AbortSignal.timeout(6000)}),fetch('/api/project',{signal:AbortSignal.timeout(6000)})])
    if(responses.some(response=>!response.ok)) throw new Error('基础服务未就绪')
    const [health,info]=await Promise.all(responses.map(response=>response.json()))
    if(health.status!=='ok'||!Array.isArray(info.study_area?.bbox_wsen)) throw new Error('服务格式错误')
    project.value=info;connection.value='connected'
  }catch{connection.value='error'}
}
async function connectAnalysis(){dataError.value='';try{data.value=await loadAnalysis()}catch{dataError.value='分析成果暂时不可用，请检查本地成果文件后重试。'}}
function stopPlaying(){playing.value=false;clearTimeout(playTimer)}
function scheduleNext(){
  clearTimeout(playTimer)
  if(!playing.value||layerStatus.value!=='ready')return
  if(scenarioIndex.value>=lastScenarioIndex.value){stopPlaying();return}
  playTimer=setTimeout(()=>{scenarioIndex.value++},SCENARIO_INTERVAL_MS)
}
function togglePlaying(){
  if(playing.value){stopPlaying();return}
  layerMode.value='scenario';showFlood.value=true;playing.value=true
  if(scenarioIndex.value===lastScenarioIndex.value)scenarioIndex.value=0;else scheduleNext()
}
function onLayerStatus(value){layerStatus.value=value.state;clearTimeout(playTimer);if(value.state==='error')stopPlaying();else if(value.state==='ready')scheduleNext()}
function selectScenario(index){stopPlaying();scenarioIndex.value=Number(index)}
function selectScenarioById(id){
  const index=data.value.summary.scenarios.findIndex(row=>row.id===id)
  if(index>=0)selectScenario(index)
}
function selectLayerMode(value){stopPlaying();layerMode.value=value}
function changeMode(value){map.value?.setMode(value);mode.value=value}
function showTerrain(){map.value?.viewTerrain();mode.value='3D'}
function showFloodView(){map.value?.viewFlood();mode.value='3D'}
function showWater(){map.value?.viewWater();mode.value='3D'}
function switchHydro(value){
  openReplayOnReady=false
  stopPlaying();hydroLocation.value=null;stageReplayActive.value=false;hydroActive.value=value
  if(value)mode.value='3D'
}
function switchStageReplay(){
  openReplayOnReady=false
  stopPlaying();hydroLocation.value=null;hydroActive.value=false;stageReplayActive.value=true;mode.value='3D'
}
watch([terrainStatus,mapStatus], ([terrain,mapState])=>{
  if(openReplayOnReady && terrain==='ready' && mapState==='ready') switchStageReplay()
})
function onMapStatus(value){mapStatus.value=value.state;mapError.value=value.message??'';if(value.fallbackBasemap)basemap.value=value.fallbackBasemap}
watch([scenarioIndex,layerMode,showFlood],()=>{clearTimeout(playTimer);if(!showFlood.value)stopPlaying()})
onMounted(()=>{connect();connectAnalysis()})
onBeforeUnmount(stopPlaying)
</script>
<template>
<div class="app-shell">
  <header class="app-header"><div class="brand"><div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 40 40" fill="none"><path d="M6 13c8-9 14 9 28 0M6 21c8-9 14 9 28 0M6 29c8-9 14 9 28 0" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg></div><div><h1>邕江洪水 <span>WebGIS</span></h1><p>{{hydroActive ? '基于真实地形和假设参数的洪水动态情景模拟' : stageReplayActive ? '2024 年洪水事件背景 · 静态情景连续展示' : '真实地形与历史降雨 · 简化淹没情景分析'}}</p></div></div><div class="header-status"><span class="stage-tag">{{hydroActive ? "动态水动力" : stageReplayActive ? "陆地淹没" : "静态分析"}}</span><span class="connection-status" :class="connection" role="status"><i></i>{{connectionText}}</span></div></header>
  <main class="workspace">
    <aside class="sidebar" aria-label="情景分析与数据资料">
      <section class="study-section compact-study"><p class="eyebrow">南宁 · 邕江城区</p><h2>洪水情景工作台</h2><p v-if="hydroActive" class="muted">现有研究区 · 邕江全河段及两岸</p><p v-else class="muted">2024年9月事件背景 · {{project?project.study_area.area_km2.toFixed(2):'—'}} km² 研究区</p></section>
      <section v-if="connection==='error'" class="connection-error" role="alert"><p>基础服务未连接；本地分析成果仍可单独浏览。</p><button class="text-button" @click="connect">重新连接服务</button></section>
      <section v-if="dataError" class="connection-error" role="alert"><p>{{dataError}}</p><button class="text-button" @click="connectAnalysis">重新读取成果</button></section><p v-else-if="!data" class="panel-note">正在读取分析成果…</p>
      <div class="analysis-tabs" role="group" aria-label="情景类型">
        <button :aria-pressed="stageReplayActive" :disabled="terrainStatus!=='ready'||mapStatus!=='ready'" @click="switchStageReplay" data-testid="stage-replay-mode">陆地淹没</button>
        <button :aria-pressed="staticActive" @click="switchHydro(false)">静态情景</button>
        <button :aria-pressed="hydroActive" :disabled="terrainStatus!=='ready'||mapStatus!=='ready'" @click="switchHydro(true)" data-testid="hydro-mode">全河段模拟</button>
      </div>
      <HydroRunSelector v-if="hydroActive" :map="map" :location="hydroLocation"/>
      <StageReplayControls v-if="stageReplayActive" :map="map"/>
      <template v-if="data&&staticActive">
        <section class="analysis-section"><div class="section-title"><h3>图层与分析</h3><span>EGM2008</span></div>
          <div class="analysis-tabs" role="group" aria-label="分析方式"><button :aria-pressed="layerMode==='scenario'" @click="selectLayerMode('scenario')">水位情景</button><button :aria-pressed="layerMode==='change'" @click="selectLayerMode('change')">两期变化</button></div>
          <label v-if="layerMode==='scenario'" class="field-label">假设水位
            <select :value="scenario.id" @change="selectScenarioById($event.target.value)">
              <option v-for="row in data.summary.scenarios" :key="row.id" :value="row.id">
                {{row.id}} · {{row.water_level_m}} m{{row.phase || row.id==='S04' ? '（'+(row.phase || '退水')+'）' : ''}}
              </option>
            </select>
          </label>
          <label v-else class="field-label">比较情景<select v-model="comparisonId"><option v-for="row in data.summary.comparisons" :key="row.id" :value="row.id">{{row.before}} / {{row.after}}</option></select></label>
          <div class="layer-toggles"><label><input v-model="showFlood" type="checkbox">{{layerMode==='scenario'?'淹没水面':'变化分类'}}</label><label><input v-model="showRivers" type="checkbox">河流中心线</label></div>
          <label class="relief-control">三维地形拉伸
            <select v-model.number="reliefScale" :disabled="mode!=='3D'||terrainStatus!=='ready'">
              <option v-for="scale in [1, 1.1, 1.2, 1.3, 3]" :key="scale" :value="scale">{{scale}}×{{scale===1?'（原比例）':''}}</option>
            </select>
          </label>
          <p v-if="data.extensionError" class="panel-note" role="status">{{data.extensionError}}</p>
          <p v-if="riverStatus==='error'" class="panel-note error-text" role="alert">河流图层加载失败，请刷新重试。</p>
          <template v-if="layerMode==='scenario'"><div class="stat-feature"><span>连通湿区面积</span><strong data-testid="area-stat">{{scenario.area_km2.toFixed(4)}}<small> km²</small></strong></div><div class="stat-pair"><div><span>平均差值水深</span><strong>{{scenario.mean_depth_m.toFixed(2)}} m</strong></div><div><span>最大差值水深</span><strong>{{scenario.max_depth_m.toFixed(2)}} m</strong></div></div></template>
          <div v-else class="change-statistics" data-testid="change-stats"><p><i class="legend-dot added"></i>新增<strong>{{comparison.added_area_km2.toFixed(4)}} km²</strong></p><p><i class="legend-dot persistent"></i>持续<strong>{{comparison.persistent_area_km2.toFixed(4)}} km²</strong></p><p><i class="legend-dot receded"></i>退水<strong>{{comparison.receded_area_km2.toFixed(4)}} km²</strong></p></div>
          <p class="panel-note">面积含现有河道，不等于受灾陆地面积。假设水位未绑定历史日期，也未由降雨直接换算。</p><button class="primary-button" :disabled="mapStatus!=='ready'" @click="showFloodView">查看淹没范围</button>
          <section class="water-controls" aria-label="水流视觉效果">
            <div class="section-title"><h3>水流与波纹</h3><span>视觉示意</span></div>
            <label class="effect-toggle"><input v-model="effectsEnabled" type="checkbox">启用水流和波纹</label>
            <div class="effect-actions"><button class="secondary-button" :disabled="!effectsEnabled||effectStatus!=='ready'" @click="effectsPaused=!effectsPaused">{{effectsPaused?'继续水流':'暂停水流'}}</button><label>播放速度<select v-model="effectSpeed" :disabled="!effectsEnabled"><option :value="0.5">0.5×</option><option :value="1">1×</option><option :value="2">2×</option></select></label></div>
            <button class="secondary-button" :disabled="riverStatus!=='ready'" @click="showWater">查看水流近景</button>
            <p v-if="effectStatus==='loading'" class="panel-note" role="status">正在加载水面材质…</p><p v-if="effectStatus==='error'" class="panel-note error-text" role="alert">视觉效果初始化失败，仍可查看静态分析结果。</p>
            <p class="panel-note">方向沿线坐标顺序示意，速度不是实测流速；不改变水深和面积。变化检测、二维或隐藏水面时暂停刷新。</p>
          </section>
        </section>
        <AnalysisCharts :summary="data.summary" :rainfall="data.rainfall" :selected-id="scenario.id"/>
      </template>
      <section class="scope-note"><h3>地形与资料说明</h3><p role="status">{{terrainStatus==='ready'?'FABDEM 已加载':terrainStatus==='error'?'DEM 加载失败，当前为基础椭球。':'正在加载 DEM…'}}</p><button class="secondary-button" :disabled="terrainStatus!=='ready'" @click="showTerrain">查看地形近景</button><button class="secondary-button" :disabled="!project||mapStatus!=='ready'" @click="map?.resetView()">定位全研究区</button><p class="muted">三维地形与水面同步拉伸。源高程采用 EGM2008，未转换为椭球高，仅作课程形态预览。在线影像不代表2024年灾时影像。</p><p class="muted">{{hydroActive ? "主槽河床与边界为教学假设，流速由模型计算。" : stageReplayActive ? "陆地淹没由现有 30 米 DEM 和主河道连通性确定。" : "OSM 为当前河道。静态情景无流速和退水历时。"}}</p></section>
    </aside>
    <section class="map-panel" aria-label="三维地图工作区">
      <MapViewer ref="map" :bbox="project?.study_area.bbox_wsen" :basemap="basemap" :layer="layer" :river-asset="data?.catalog.assets.rivers_wgs84" :show-rivers="showRivers" :effects="effects" :relief-scale="reliefScale" @status="onMapStatus" @hydro-location="hydroLocation=$event" @terrain-status="terrainStatus=$event.state" @layer-status="onLayerStatus" @river-status="riverStatus=$event.state" @effects-status="effectStatus=$event.state"/>
      <div class="map-toolbar"><div class="view-switch" role="group" aria-label="地图视角"><button :aria-pressed="mode==='3D'" :disabled="mapStatus!=='ready'" @click="changeMode('3D')">三维</button><button :aria-pressed="mode==='2D'" :disabled="mapStatus!=='ready'||!staticActive" @click="changeMode('2D')">二维</button></div><label class="basemap-label">底图<select v-model="basemap" :disabled="mapStatus!=='ready'"><option value="satellite">卫星影像</option><option value="osm">在线街道</option><option value="local">本地概览</option></select></label></div>
      <div id="hydro-controls-slot"></div>
      <div class="scenario-notice">{{hydroActive ? "假设水动力情景 · 模拟地形" : stageReplayActive ? "教学假设水位 · 连通淹没范围" : "假设情景 · 非实测洪水或预报"}}<span v-if="mode==='3D'&&terrainStatus==='ready'"> · 地形 {{reliefScale}}×</span></div>
      <div v-if="data&&showFlood&&staticActive" class="flood-legend"><template v-if="layerMode==='scenario'"><i class="legend-dot water"></i>连通淹没水面</template><template v-else><span><i class="legend-dot added"></i>新增</span><span><i class="legend-dot persistent"></i>持续</span><span><i class="legend-dot receded"></i>退水</span></template></div>
      <div v-if="mapStatus==='loading'" class="map-message" role="status"><span class="loading-ring"></span>正在准备三维地图…</div>
      <div v-if="mapStatus==='error'" class="map-message map-error" role="alert"><strong>地图暂时不可用</strong><p>{{mapError}}</p></div>
      <div v-if="mapError&&mapStatus==='ready'" class="map-warning" role="alert">{{mapError}}<button @click="basemap='local'">使用本地概览</button></div>
      <div v-if="staticActive&&data&&layerStatus==='loading'&&showFlood" class="layer-loading" role="status">正在加载分析图层…</div>
      <div v-if="staticActive&&layerStatus==='error'" class="map-message map-error" role="alert"><p>分析图层加载失败。</p><button class="secondary-button" @click="map?.retryLayer()">重试分析图层</button></div>
      <section v-if="data&&staticActive" class="scenario-timeline" aria-label="假设情景时间轴">
        <div class="timeline-heading">
          <strong>{{selectedTitle}}</strong>
          <span v-if="layerMode==='scenario'">{{scenarioIndex+1}} / {{data.summary.scenarios.length}} 档 · 无真实时间间隔</span>
          <span v-else>新增 / 持续 / 退水</span>
        </div>
        <template v-if="layerMode==='scenario'">
          <div class="timeline-control">
            <button :disabled="layerStatus==='error'" @click="togglePlaying">{{playing?'暂停':scenarioIndex===lastScenarioIndex?'重新播放':'播放'}}</button>
            <input :value="scenarioIndex" type="range" min="0" :max="lastScenarioIndex" step="1" aria-label="选择假设情景" @input="selectScenario($event.target.value)">
          </div>
          <div class="scenario-steps">
            <button v-for="(row,index) in data.summary.scenarios" :key="row.id" :aria-pressed="scenarioIndex===index"
              :title="row.id+' · '+row.water_level_m+' m'" @click="selectScenario(index)">{{row.id}}</button>
          </div>
        </template>
        <p v-else class="timeline-help">切换左侧比较情景查看空间变化；面积统计使用原始30 m分析网格。</p>
      </section>
    </section>
  </main>
  <footer class="status-bar"><span>南宁邕江研究工作区</span><span>DEM / 水位：EGM2008</span><span>课程假设情景 · 不用于真实洪水预报</span></footer>
</div>
</template>

