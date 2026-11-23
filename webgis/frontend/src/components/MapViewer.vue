<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Viewer, Color, Rectangle, EllipsoidTerrainProvider,
  TileMapServiceImageryProvider, OpenStreetMapImageryProvider, buildModuleUrl,
  BoundingSphere, Cartesian3, Cartographic, HeadingPitchRange, Matrix4, SceneMode,
  ArcGisMapServerImageryProvider,
  GeoJsonDataSource, ClassificationType, SingleTileImageryProvider,
} from 'cesium'
import { loadDemTerrain } from '../demTerrain'
import { fetchCheckedJson } from '../analysisData'

const props = defineProps({ bbox: Array, basemap: { type: String, default: 'satellite' }, layer: Object,
  riverAsset: Object, showRivers: { type: Boolean, default: true }, effects: Object,
  reliefScale: { type: Number, required: true } })
const emit = defineEmits(['status', 'terrain-status', 'layer-status', 'river-status', 'effects-status'])
const container = ref(null)
let viewer
let basemapRevision = 0
let destroyed = false
let layerRevision = 0
let riverSource
let basemapLayer, reliefLayer
const layerCache = new Map()
let firstFloodView = true
let effectController, effectPromise, effectFailed = false
const scenarioSources = new Map()
const stillWater = Color.fromCssColorString('#526C61').withAlpha(.82)
const riverLine = Color.fromCssColorString('#a1b2a3').withAlpha(.78)

function syncRiverPath() {
  const river = riverSource?.entities.values.find(entity => entity.properties?.name?.getValue() === '邕江')
  effectController?.setRiverPath(river?.polyline?.positions.getValue(viewer.clock.currentTime))
}

// 地形由 Cesium 拉伸，定高水面是独立几何。两者都以 0 m 为基准。
function syncRelief() {
  if (!viewer || viewer.isDestroyed()) return
  const scale = viewer.scene.mode === SceneMode.SCENE3D ? props.reliefScale : 1
  viewer.scene.verticalExaggeration = scale
  if (reliefLayer) reliefLayer.show = props.basemap === 'satellite' && viewer.scene.mode === SceneMode.SCENE3D
  for (const [source, stage] of scenarioSources) {
    for (const entity of source.entities.values) {
      if (entity.polygon && entity.polygon.height?.getValue() !== stage * scale) {
        entity.polygon.height = stage * scale
      }
    }
  }
  viewer.scene.requestRender()
}

function syncEffects() {
  if (!viewer || viewer.isDestroyed() || destroyed) return
  const options = props.effects ?? { enabled: false, paused: false, speed: 1 }
  const scenarioMode = props.layer?.mode === 'scenario'
  const mode3d = viewer.scene.mode === SceneMode.SCENE3D
  const visible = scenarioMode && container.value.dataset.analysisLayer === props.layer?.id
  if (options.enabled && scenarioMode && mode3d && visible && !effectController && !effectPromise && !effectFailed) {
    emit('effects-status', { state: 'loading' })
    effectPromise = import('../waterEffects').then(({ createWaterEffects }) => {
      if (destroyed) return
      effectController = createWaterEffects(viewer, container.value)
      syncRiverPath()
      emit('effects-status', { state: 'ready' })
      syncEffects()
    }).catch(() => {
      if (!destroyed) {
        effectFailed = true
        container.value.dataset.waterState = 'error'
        emit('effects-status', { state: 'error' })
      }
    })
  }
  if (!effectController) return
  const useEffects = options.enabled && scenarioMode && mode3d
  for (const source of scenarioSources.keys()) {
    for (const entity of source.entities.values) {
      if (entity.polygon) entity.polygon.material = useEffects ? effectController.waterMaterial : stillWater
    }
  }
  for (const entity of riverSource?.entities.values ?? []) {
    if (entity.polyline) {
      entity.polyline.material = useEffects ? effectController.flowMaterial : riverLine
      entity.polyline.width = useEffects ? 3 : 2
    }
  }
  effectController.setState({ enabled: options.enabled, paused: options.paused,
    speed: Number(options.speed), visible, mode3d })
}

function viewFlood() {
  if (!viewer || viewer.isDestroyed()) return
  viewer.scene.morphTo3D(0)
  viewer.camera.viewBoundingSphere(new BoundingSphere(Cartesian3.fromDegrees(108.379, 22.783, 80 * props.reliefScale), 4000),
    new HeadingPitchRange(.72, -.39, 9300))
  viewer.camera.lookAtTransform(Matrix4.IDENTITY)
  container.value.dataset.sceneMode = String(viewer.scene.mode)
  viewer.scene.requestRender()
}

function viewWater() {
  if (!viewer || viewer.isDestroyed()) return
  const river = riverSource?.entities.values.find(entity => entity.polyline && entity.properties?.name?.getValue() === '邕江')
  const positions = river?.polyline.positions.getValue(viewer.clock.currentTime)
  if (!positions?.length) { viewFlood(); return }
  const point = Cartographic.fromCartesian(positions[Math.floor(positions.length / 2)])
  viewer.scene.morphTo3D(0)
  const center = Cartesian3.fromRadians(point.longitude, point.latitude, (props.layer?.waterLevel ?? 80) * props.reliefScale)
  viewer.camera.viewBoundingSphere(new BoundingSphere(center, 1500), new HeadingPitchRange(-.3, -.6, 4800))
  viewer.camera.lookAtTransform(Matrix4.IDENTITY)
  container.value.dataset.sceneMode = String(viewer.scene.mode)
  syncEffects()
  viewer.scene.requestRender()
}

async function updateLayer() {
  if (!viewer || viewer.isDestroyed()) return
  const revision = ++layerRevision
  container.value.dataset.analysisLayer = 'loading'
  syncEffects()
  if (!props.layer) {
    for (const source of layerCache.values()) source.show = false
    container.value.dataset.analysisLayer = 'hidden'
    emit('layer-status', { state: 'hidden' })
    syncEffects()
    viewer.scene.requestRender()
    return
  }
  const request = props.layer
  const key = request.id
  emit('layer-status', { state: 'loading', id: key })
  container.value.dataset.analysisLayer = 'loading'
  try {
    let source = layerCache.get(key)
    if (!source) {
      const data = await fetchCheckedJson(request.asset)
      source = await GeoJsonDataSource.load(data, { clampToGround: request.mode === 'change',
        fill: stillWater, strokeWidth: 0 })
      if (destroyed) { source.entities.removeAll(); return }
      for (const entity of source.entities.values) {
        if (!entity.polygon) continue
        entity.polygon.outline = false
        if (request.mode === 'scenario') {
          entity.polygon.height = request.waterLevel * viewer.scene.verticalExaggeration
          entity.polygon.perPositionHeight = false
          // 约330m的显示细分减少长三角面与地球曲面的弦高差，不改变分析边界。
          entity.polygon.granularity = Math.PI / 180 * .003
          entity.polygon.material = stillWater
        } else {
          const category = entity.properties.category.getValue()
          entity.polygon.material = Color.fromCssColorString({ 1: '#21c0d1', 2: '#246fbd', 3: '#e29036' }[category]).withAlpha(.82)
          entity.polygon.classificationType = ClassificationType.TERRAIN
        }
      }
      source.show = false
      await viewer.dataSources.add(source)
      if (destroyed) return
      // 只保留一份同名缓存；快速切换产生的晚到副本立即移除。
      if (layerCache.has(key)) { viewer.dataSources.remove(source, true); source = layerCache.get(key) }
      else {
        layerCache.set(key, source)
        if (request.mode === 'scenario') {
          scenarioSources.set(source, request.waterLevel)
          syncRelief()
        }
      }
    }
    if (destroyed || revision !== layerRevision) return
    for (const cached of layerCache.values()) if (cached !== source) cached.show = false
    source.show = true
    container.value.dataset.analysisLayer = key
    container.value.dataset.analysisEntities = String(source.entities.values.length)
    emit('layer-status', { state: 'ready', id: key })
    syncEffects()
    if (firstFloodView) {
      firstFloodView = false
      if (viewer.scene.mode === SceneMode.SCENE3D) viewFlood()
    }
    viewer.scene.requestRender()
  } catch (error) {
    if (!destroyed && revision === layerRevision) {
      for (const source of layerCache.values()) source.show = false
      container.value.dataset.analysisLayer = 'error'
      emit('layer-status', { state: 'error', message: '分析图层加载失败，请重试。', id: key })
    }
  }
}

async function updateRivers() {
  if (!viewer || viewer.isDestroyed() || !props.riverAsset) return
  try {
    if (!riverSource) {
      const data = await fetchCheckedJson(props.riverAsset)
      const source = await GeoJsonDataSource.load(data, { clampToGround: true,
        stroke: riverLine, strokeWidth: 2,
        credit: '© OpenStreetMap contributors · ODbL · 当前河道中心线' })
      if (destroyed) return
      await viewer.dataSources.add(source)
      riverSource = source
      syncRiverPath()
    }
    if (destroyed) return
    riverSource.show = props.showRivers
    container.value.dataset.riverVisible = String(props.showRivers)
    emit('river-status', { state: 'ready' })
    syncEffects()
    viewer.scene.requestRender()
  } catch (error) {
    if (!destroyed) emit('river-status', { state: 'error' })
  }
}

function viewTerrain() {
  if (!viewer || viewer.isDestroyed()) return
  viewer.scene.morphTo3D(0)
  const target = new BoundingSphere(Cartesian3.fromDegrees(108.3939, 22.7908, 200 * props.reliefScale), 1000)
  viewer.camera.viewBoundingSphere(target, new HeadingPitchRange(Math.PI / 6, -Math.PI / 8, 3300))
  viewer.camera.lookAtTransform(Matrix4.IDENTITY)
  container.value.dataset.cameraPitch = String(viewer.camera.pitch)
  container.value.dataset.sceneMode = String(viewer.scene.mode)
  viewer.scene.requestRender()
}

async function updateTerrain() {
  emit('terrain-status', { state: 'loading' })
  try {
    const { provider, metadata } = await loadDemTerrain()
    if (destroyed) return
    viewer.terrainProvider = provider
    container.value.dataset.terrain = 'fabdem'
    syncRelief()
    viewer.scene.requestRender()
    emit('terrain-status', { state: 'ready' })
    if (viewer.scene.mode === SceneMode.SCENE3D) {
      if (props.layer) viewFlood()
      else viewTerrain()
    }
    // 阴影是独立的可选显示层。加载失败时保留已经就绪的真实地形。
    try {
      const shade = await SingleTileImageryProvider.fromUrl('/terrain/relief_shade.png', {
        rectangle: Rectangle.fromDegrees(...metadata.bounds_wsen),
      })
      if (destroyed) return
      reliefLayer = viewer.imageryLayers.addImageryProvider(shade)
      syncRelief()
    } catch {
      if (!destroyed) console.warn('地形明暗图未加载，继续使用卫星底图与 DEM。')
    }
  } catch (error) {
    if (!destroyed) emit('terrain-status', { state: 'error', message: '真实 DEM 加载失败，当前显示基础椭球。' })
  }
}

function resetView() {
  if (!viewer || viewer.isDestroyed() || !props.bbox) return
  const [west, south, east, north] = props.bbox
  if (viewer.scene.mode === SceneMode.SCENE3D) {
    const sphere = BoundingSphere.fromPoints([
      Cartesian3.fromDegrees(west, south), Cartesian3.fromDegrees(east, north),
      Cartesian3.fromDegrees(west, north), Cartesian3.fromDegrees(east, south),
    ])
    viewer.camera.viewBoundingSphere(sphere, new HeadingPitchRange(0, -Math.PI / 4, sphere.radius * 3.2))
    viewer.camera.lookAtTransform(Matrix4.IDENTITY)
  } else {
    viewer.camera.setView({ destination: Rectangle.fromDegrees(west - 0.04, south - 0.04, east + 0.04, north + 0.04) })
  }
  container.value.dataset.cameraPitch = String(viewer.camera.pitch)
  container.value.dataset.sceneMode = String(viewer.scene.mode)
  viewer.scene.requestRender()
}

async function updateBasemap() {
  if (!viewer || viewer.isDestroyed()) return
  const revision = ++basemapRevision
  try {
    let provider
    if (props.basemap === 'satellite') {
      provider = await ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
        { enablePickFeatures: false },
      )
    } else if (props.basemap === 'osm') {
      provider = new OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' })
    } else {
      provider = await TileMapServiceImageryProvider.fromUrl(buildModuleUrl('Assets/Textures/NaturalEarthII'), { credit: 'Natural Earth · Cesium 本地概览' })
    }
    if (destroyed || revision !== basemapRevision) return
    provider.errorEvent.addEventListener(() => {
      if (!destroyed && revision === basemapRevision) emit('status', { state: 'ready', message: '部分底图影像未能加载，可切换其他底图或使用本地概览。' })
    })
    if (basemapLayer) viewer.imageryLayers.remove(basemapLayer)
    container.value.dataset.pendingTiles = 'loading'
    const imagery = viewer.imageryLayers.addImageryProvider(provider, 0)
    basemapLayer = imagery
    if (reliefLayer) reliefLayer.show = props.basemap === 'satellite' && viewer.scene.mode === SceneMode.SCENE3D
    if (props.basemap === 'satellite') {
      imagery.brightness = .97
      imagery.saturation = .91
      imagery.contrast = 1.05
    }
    container.value.dataset.basemap = props.basemap
    viewer.scene.requestRender()
    emit('status', { state: 'ready' })
  } catch (error) {
    if (!destroyed && revision === basemapRevision) {
      emit('status', {
        state: props.basemap !== 'local' || viewer.imageryLayers.length ? 'ready' : 'error',
        message: '底图资源加载失败，请检查网络连接。已尝试使用本地概览。',
        fallbackBasemap: props.basemap !== 'local' ? 'local' : undefined,
      })
    }
  }
}

function setMode(mode) {
  if (!viewer || viewer.isDestroyed()) return
  if (mode === '2D') viewer.scene.morphTo2D(0)
  else viewer.scene.morphTo3D(0)
  resetView()
  syncEffects()
}

onMounted(async () => {
  try {
    viewer = new Viewer(container.value, {
      animation: false, timeline: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, baseLayerPicker: false,
      baseLayer: false, terrainProvider: new EllipsoidTerrainProvider(),
      infoBox: false, selectionIndicator: false, fullscreenButton: false,
      requestRenderMode: true, maximumRenderTimeChange: Infinity,
    })
    viewer.scene.globe.baseColor = Color.fromCssColorString('#49665e')
    viewer.scene.globe.depthTestAgainstTerrain = true
    viewer.scene.morphComplete.addEventListener(() => { syncRelief(); syncEffects() })
    syncRelief()
    viewer.scene.globe.tileLoadProgressEvent.addEventListener((pending) => {
      if (container.value) {
        container.value.dataset.pendingTiles = String(pending)
        const height = viewer.scene.globe.getHeight(Cartographic.fromDegrees(108.3939, 22.7908))
        if (height !== undefined) container.value.dataset.terrainProbeHeight = String(height)
      }
    })
    viewer.scene.renderError.addEventListener(() => {
      if (!destroyed) emit('status', { state: 'error', message: '三维渲染失败。请检查浏览器 WebGL 支持，或重新打开页面。' })
    })
    resetView()
    await Promise.all([updateBasemap(), updateTerrain(), updateLayer(), updateRivers()])
  } catch (error) {
    if (!destroyed) emit('status', { state: 'error', message: '无法创建三维地图。请使用支持 WebGL 2 的新版浏览器。' })
  }
})

watch(() => props.bbox, resetView)
watch(() => props.basemap, updateBasemap)
watch(() => props.reliefScale, syncRelief)
watch(() => props.layer, updateLayer)
watch(() => props.effects, syncEffects, { deep: true })
watch(() => props.riverAsset, updateRivers)
watch(() => props.showRivers, () => {
  if (!riverSource) return
  riverSource.show = props.showRivers
  container.value.dataset.riverVisible = String(props.showRivers)
  viewer?.scene.requestRender()
})
onBeforeUnmount(() => {
  destroyed = true
  basemapRevision++
  layerRevision++
  effectController?.dispose()
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
})
defineExpose({ resetView, setMode, viewTerrain, viewFlood, viewWater, retryLayer: updateLayer })
</script>

<template><div ref="container" class="cesium-map" aria-label="Cesium 地图画布"></div></template>
