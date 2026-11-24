import {
  BoundingSphere, Buffer, BufferUsage, Cartesian2, Cartesian3, ComponentDatatype, DrawCommand, Ellipsoid,
  EncodedCartesian3, IndexDatatype, NearFarScalar, PixelDatatype, PixelFormat, PointPrimitiveCollection, Color,
  Pass, RenderState, Resource, ShaderProgram, Texture, Sampler, TextureMinificationFilter,
  TextureMagnificationFilter, TextureWrap, VertexArray, BlendingState, SceneMode, PrimitiveType, buildModuleUrl,
} from 'cesium'
import { makeSurfaceMesh } from './hydroSurfaceGeometry'
import { waterStyle, waterVertex, waterFragment } from './hydroWaterShaders'

class WaterSurface {
  constructor(scene, data) {
    this.scene = scene
    this.data = data
    this.destroyed = false
    this.settings = {}
    this.uploads = 0
    Resource.fetchImage({ url: buildModuleUrl('Assets/Textures/waterNormalsSmall.jpg') }).then(image => {
      if (this.destroyed) return
      this.normalImage = image
      this.scene.requestRender()
    }).catch(() => {
      this.normalUnavailable = true
      if (!this.destroyed) this.scene.requestRender()
    })
  }
  isDestroyed() { return this.destroyed }
  create(context) {
    const { manifest, lookup } = this.data
    const { cols, rows, cell_count: count, bounds } = manifest
    const [west,south,east,north] = bounds
    const mesh = makeSurfaceMesh(lookup, cols, rows, count)
    const origin = new Cartesian2(west,south)
    const dimensions = new Cartesian2(cols,rows)
    const degrees = new Cartesian2((east-west)/cols,(north-south)/rows)
    const metres = new Cartesian2(degrees.x*111320*Math.cos((north+south)*Math.PI/360),degrees.y*110750)
    const waveScales = new Cartesian2(...waterStyle.waveScales)
    const shallowColor = new Cartesian3(...waterStyle.shallowColor)
    const deepColor = new Cartesian3(...waterStyle.deepColor)
    this.width = Math.min(256,count)
    this.height = Math.ceil(count/this.width)
    this.scratch = new Float32Array(this.width*this.height*4)
    const vertices = mesh.owners.length
    const high = new Float32Array(vertices*3), low = new Float32Array(vertices*3), up = new Float32Array(vertices*3)
    const p = new Cartesian3(), normal = new Cartesian3(), encode = new EncodedCartesian3()
    for (let i = 0; i < vertices; i++) {
      const lon = west + mesh.grid[2*i]*degrees.x
      const lat = south + mesh.grid[2*i+1]*degrees.y
      Cartesian3.fromDegrees(lon,lat,0,Ellipsoid.WGS84,p)
      Ellipsoid.WGS84.geodeticSurfaceNormal(p,normal)
      EncodedCartesian3.fromCartesian(p,encode)
      Cartesian3.pack(encode.high,high,3*i)
      Cartesian3.pack(encode.low,low,3*i)
      Cartesian3.pack(normal,up,3*i)
    }
    const arrays = [high,low,up,mesh.grid,mesh.neighbors,mesh.owners]
    const sizes = [3,3,3,2,4,1]
    const attributes = arrays.map((typedArray,index) => ({
      index, vertexBuffer: Buffer.createVertexBuffer({ context, typedArray, usage: BufferUsage.STATIC_DRAW }),
      componentsPerAttribute: sizes[index], componentDatatype: ComponentDatatype.FLOAT,
    }))
    const indexBuffer = Buffer.createIndexBuffer({ context, typedArray: mesh.triangles, usage: BufferUsage.STATIC_DRAW,
      indexDatatype: mesh.triangles instanceof Uint32Array ? IndexDatatype.UNSIGNED_INT : IndexDatatype.UNSIGNED_SHORT })
    this.array = new VertexArray({ context, attributes, indexBuffer })
    this.meshStats = { vertices, triangles: mesh.triangles.length/3,
      geometry_bytes: arrays.reduce((bytes, a) => bytes+a.byteLength, mesh.triangles.byteLength),
      frame_texture_bytes: 2*this.scratch.byteLength, lookup_texture_bytes: lookup.byteLength }
    this.shader = ShaderProgram.fromCache({ context, vertexShaderSource: waterVertex, fragmentShaderSource: waterFragment,
      attributeLocations: { high: 0, low: 1, up: 2, grid: 3, neighbors: 4, owner: 5 } })
    const corners = [Cartesian3.fromDegrees(west,south),Cartesian3.fromDegrees(east,south),
      Cartesian3.fromDegrees(west,north),Cartesian3.fromDegrees(east,north)]
    const boundingVolume = BoundingSphere.fromPoints(corners)
    boundingVolume.radius += 1000
    const sampler = new Sampler({ minificationFilter: TextureMinificationFilter.NEAREST, magnificationFilter: TextureMagnificationFilter.NEAREST })
    const frameTexture = () => new Texture({ context, width: this.width, height: this.height, pixelFormat: PixelFormat.RGBA,
      pixelDatatype: PixelDatatype.FLOAT, sampler, flipY: false })
    this.textures = [frameTexture(),frameTexture()]
    this.lookupTexture = new Texture({ context, width: cols, height: rows, pixelFormat: PixelFormat.RED,
      pixelDatatype: PixelDatatype.FLOAT, sampler, flipY: false,
      source: { arrayBufferView: new Float32Array(lookup), width: cols, height: rows } })
    this.resident = [null,null]
    this.command = new DrawCommand({ owner: this, vertexArray: this.array, shaderProgram: this.shader, boundingVolume,
      primitiveType: PrimitiveType.TRIANGLES, count: mesh.triangles.length, pass: Pass.TRANSLUCENT,
      renderState: RenderState.fromCache({ depthTest: { enabled: true }, depthMask: false, blending: BlendingState.ALPHA_BLEND }),
      uniformMap: {
        beforeFrame: () => this.textures[0], afterFrame: () => this.textures[1],
        frameWidth: () => this.width, fraction: () => this.pair.alpha, cellLookup: () => this.lookupTexture,
        latticeSize: () => dimensions, latticeMetres: () => metres, boundsOrigin: () => origin, latticeDegrees: () => degrees,
        relief: () => this.scene.verticalExaggeration, wetThreshold: () => manifest.wet_threshold_m,
        surfaceOffset: () => waterStyle.surfaceOffset, shallowFade: () => waterStyle.shallowFade, shoreWidth: () => waterStyle.shoreWidth,
        style: () => this.settings.style, visualTime: () => this.seconds*waterStyle.visualSecondsPerSecond,
        normalMap: () => this.normalTexture ?? context.defaultTexture, normalReady: () => !!this.normalTexture,
        lowQuality: () => this.settings.lowQuality, showMesh: () => this.settings.showMesh,
        shallowColor: () => shallowColor, deepColor: () => deepColor, waveScales: () => waveScales, waveTravel: () => waterStyle.waveTravel,
      } })
  }
  update(frameState) {
    if (frameState.mode !== SceneMode.SCENE3D || !frameState.passes.render || !this.pair) return
    if (!this.command) this.create(frameState.context)
    if (this.normalImage) {
      this.normalTexture = new Texture({ context: frameState.context, source: this.normalImage,
        sampler: new Sampler({ wrapS: TextureWrap.REPEAT, wrapT: TextureWrap.REPEAT,
          minificationFilter: TextureMinificationFilter.LINEAR_MIPMAP_LINEAR,
          magnificationFilter: TextureMagnificationFilter.LINEAR }) })
      this.normalTexture.generateMipmap()
      this.normalImage = undefined
    }
    const values = [this.pair.first,this.pair.second]
    if (this.resident[1] === values[0] && this.resident[0] !== values[0]) {
      this.resident.reverse()
      this.textures.reverse()
    }
    for (let i = 0; i < 2; i++) {
      if (this.resident[i] === values[i]) continue
      this.scratch.set(values[i])
      this.textures[i].copyFrom({ source: { arrayBufferView: this.scratch, width: this.width, height: this.height } })
      this.resident[i] = values[i]
      this.uploads++
    }
    frameState.commandList.push(this.command)
  }
  destroy() {
    this.array?.destroy()
    this.shader?.destroy()
    this.textures?.forEach(t => t.destroy())
    this.lookupTexture?.destroy()
    this.normalTexture?.destroy()
    this.normalImage = undefined
    this.destroyed = true
  }
}

export function createHydroRender(viewer, data) {
  const scene = viewer.scene
  const water = scene.primitives.add(new WaterSurface(scene, data))
  const cloud = scene.primitives.add(new PointPrimitiveCollection())
  const particles = Array.from({ length: waterStyle.particleCount }, () => ({ point: cloud.add({ show: false, pixelSize: 3 }),
    position: new Cartesian3(), tint: new Color(), age: 0, lon: 0, lat: 0 }))
  const [west,south,east,north] = data.manifest.bounds
  const radians = Math.PI / 180
  const particleTint = Color.fromCssColorString('#d7f2e9')
  const particleScale = new NearFarScalar(600, 1.15, 23000, 0.60)
  let previousTime, currentPair, seedCells = [], scale = scene.verticalExaggeration
  const value = (pair,id,c) => pair.first[4*id+c] * (1-pair.alpha) + pair.second[4*id+c] * pair.alpha
  const wet = (pair,id) => id >= 0 && value(pair,id,0) >= data.manifest.wet_threshold_m
  const reset = () => { previousTime = undefined; for (const p of particles) p.age = 0 }
  function seed(p,pair) {
    if (!seedCells.length) return false
    for (let attempt = 0; attempt < 4; attempt++) {
      const i = seedCells[Math.floor(Math.random()*seedCells.length)]
      if (!wet(pair,i)) continue
      const k = 5*i
      p.lon = data.cells[k] + (data.cells[k+2]-data.cells[k])*(.15+Math.random()*.7)
      p.lat = data.cells[k+1] + (data.cells[k+3]-data.cells[k+1])*(.15+Math.random()*.7)
      p.age = 80 + Math.random()*1000
      return true
    }
    return false
  }
  function update(pair, seconds, settings) {
    water.pair = pair
    water.seconds = seconds
    water.settings = settings
    const { particles: showParticles, lowQuality } = settings
    cloud.show = showParticles
    if (currentPair !== pair.i) {
      currentPair = pair.i
      seedCells = []
      for (let i = 0; i < data.manifest.cell_count; i++) if (Math.max(pair.first[4*i],pair.second[4*i]) > .12) seedCells.push(i)
    }
    const delta = previousTime === undefined ? 0 : seconds - previousTime
    if (delta < 0 || delta > 250) reset()
    const elapsed = previousTime === undefined ? 0 : delta
    previousTime = seconds
    scale = scene.verticalExaggeration
    if (showParticles) for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      if (lowQuality && i >= waterStyle.lowParticleCount) { p.point.show = false; continue }
      p.age -= elapsed
      if (p.age <= 0 && !seed(p,pair)) { p.point.show = false; continue }
      let id = data.cellId(p.lon,p.lat)
      if (!wet(pair,id)) { p.age = 0; p.point.show = false; continue }
      let speed = 0, travel = elapsed, steps = 0
      while (travel > 0 && steps++ < 24) {
        const u = value(pair,id,2), v = value(pair,id,3)
        speed = Math.hypot(u,v)
        if (speed < .025) break
        const step = Math.min(travel, 12/speed)
        // UTM grid convergence: rotate projected u/v into local east/north.
        const gamma = (p.lon - 111) * radians * Math.sin(p.lat*radians)
        const eastM = u*Math.cos(gamma)+v*Math.sin(gamma)
        const northM = -u*Math.sin(gamma)+v*Math.cos(gamma)
        const lon = p.lon + step*eastM/(111320*Math.cos(p.lat*radians))
        const lat = p.lat + step*northM/110750
        id = data.cellId(lon,lat)
        if (!wet(pair,id) || !wet(pair,data.cellId((lon+p.lon)/2,(lat+p.lat)/2))) {
          p.age = 0
          break
        }
        p.lon = lon
        p.lat = lat
        travel -= step
      }
      if (!p.age || !wet(pair,id)) { p.point.show = false; continue }
      speed = Math.hypot(value(pair,id,2),value(pair,id,3))
      p.point.show = speed >= .03
      if (!p.point.show) continue
      p.point.position = Cartesian3.fromDegrees(p.lon,p.lat,value(pair,id,1)*scale+.85,undefined,p.position)
      p.point.pixelSize = 1.6 + Math.min(2.2,speed*1.35)
      p.point.scaleByDistance = particleScale
      p.point.color = Color.fromAlpha(particleTint, Math.min(.75,.28+speed*.36),p.tint)
    }
    scene.requestRender()
  }
  const contains = (lon,lat) => lon >= west && lon <= east && lat >= south && lat <= north
  return { update, reset, diagnostics: () => ({ ...water.meshStats, uploads: water.uploads,
    textures: water.textures ? 3 + Number(!!water.normalTexture) : 0, normal_ready: !!water.normalTexture,
    normal_unavailable: !!water.normalUnavailable, seconds: water.seconds, animation_style: water.settings.style,
    low_quality: water.settings.lowQuality, ...data.cacheStats() }), height(lon,lat) {
    const id = contains(lon,lat) ? data.cellId(lon,lat) : -1
    return id < 0 ? undefined : data.cells[5*id+4]
  }, dispose() { scene.primitives.remove(water); scene.primitives.remove(cloud); scene.requestRender() } }
}
