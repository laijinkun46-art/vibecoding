import { Material, Event, Color, Cartesian4, buildModuleUrl } from 'cesium'
import { WaterClock, shouldAnimate } from './waterClock'
import { localOrigin, localEast, localNorth, makeRiverFlowField } from './riverFlowField'

const WATER_TYPE = 'YongjiangRiverSurface'
const FLOW_TYPE = 'YongjiangRiverLine'
export const baseWater = Color.fromCssColorString('#526C61')

// 两种尺度、旋转错开的法线纹理，沿局部河道切向平移。两相交叠使循环连续。
const waterShader = `
  uniform sampler2D normals;
  uniform sampler2D directions;
  uniform vec4 fieldBounds;
  uniform vec4 waterColor;
  uniform vec3 originWC;
  uniform vec3 eastWC;
  uniform vec3 northWC;
  uniform float elapsed;

  vec2 waves(vec2 p){
    const mat2 rot = mat2(0.84, 0.54, -0.54, 0.84);
    vec2 large = texture(normals, fract(p / 620.0)).rg * 2.0 - 1.0;
    vec2 small = texture(normals, fract(rot * p / 263.0 + vec2(.31,.67))).rg * 2.0 - 1.0;
    return .68 * large + .32 * transpose(rot) * small;
  }

  czm_material czm_getMaterial(czm_materialInput surface){
    czm_material water = czm_getDefaultMaterial(surface);
    vec3 world = (czm_inverseView * vec4(-surface.positionToEyeEC, 1.0)).xyz - originWC;
    vec2 p = vec2(dot(world, eastWC), dot(world, northWC));
    vec2 st = clamp((p - fieldBounds.xy) / fieldBounds.zw, 0.0, 1.0);
    vec2 direction = texture(directions, st).rg * 2.0 - 1.0;
    direction /= max(length(direction), .01);
    float phase = fract(elapsed / 9.0);
    float offsetPhase = fract(phase + .5);
    vec2 travel = direction * 44.0;
    vec2 n = mix(waves(p - travel * phase), waves(p - travel * offsetPhase), abs(2.0 * phase - 1.0));
    // 远景缓和细纹，抑制小于屏幕像素的高频闪烁。
    n *= 1.0 - .85 * smoothstep(2.5, 19.0, max(length(dFdx(p)),length(dFdy(p))));
    vec3 rippleEC = czm_viewRotation * (eastWC * n.x + northWC * n.y);
    water.normal = normalize(surface.normalEC + .58 * rippleEC);
    float crest = dot(n, vec2(.65, .35));
    float glint = smoothstep(.035, .22, crest);
    water.diffuse = waterColor.rgb * (1.0 + .4 * crest) + vec3(.044,.049,.045) * glint;
    water.alpha = .82 + .055 * crest;
    water.specular = .12;
    water.shininess = 32.0;
    return water;
  }`

const flowShader = `
  uniform float elapsed;
  czm_material czm_getMaterial(czm_materialInput inputValue){
    czm_material result=czm_getDefaultMaterial(inputValue);
    float lane=abs(inputValue.st.t-0.5)*2.0;
    float progress=fract(inputValue.st.s*28.0-elapsed*0.24);
    float head=1.0-smoothstep(0.03,0.12,abs(progress-0.5-lane*0.18));
    result.diffuse=mix(vec3(.37,.49,.43),vec3(.77,.82,.73),head);
    result.emission=vec3(.0);
    result.alpha=(0.25+head*0.7)*(1.0-smoothstep(0.75,1.0,lane));
    return result;
  }`

class VisualMaterialProperty {
  constructor(type, clock, uniforms = {}) {
    this.type = type
    this.clock = clock
    this.uniforms = uniforms
    this.definitionChanged = new Event()
    this.isConstant = false
  }
  getType() { return this.type }
  getValue(time, result = {}) {
    return Object.assign(result, this.uniforms, { elapsed: this.clock.seconds })
  }
  equals(other) { return this === other }
}

/** 输入 Cesium 视图与状态元素；返回水面材质、河道方向更新和动画控制器。 */
export function createWaterEffects(viewer, element) {
  const uniforms = {
    waterColor: baseWater, normals: buildModuleUrl('Assets/Textures/waterNormalsSmall.jpg'),
    directions: Material.DefaultImageId, fieldBounds: new Cartesian4(0, 0, 1, 1),
    originWC: localOrigin, eastWC: localEast, northWC: localNorth,
  }
  const template = new Material({ fabric: { type: WATER_TYPE, uniforms: { ...uniforms, elapsed: 0 },
    source: waterShader }, translucent: true })
  template.destroy()
  const flowTemplate = new Material({ fabric: { type: FLOW_TYPE, uniforms: { elapsed: 0 }, source: flowShader }, translucent: true })
  flowTemplate.destroy()
  const clock = new WaterClock()
  const waterMaterial = new VisualMaterialProperty(WATER_TYPE, clock, uniforms)
  const flowMaterial = new VisualMaterialProperty(FLOW_TYPE, clock)
  function setRiverPath(positions) {
    if (!positions?.length) return
    const field = makeRiverFlowField(positions)
    if (!field) return
    uniforms.directions = field.texture
    uniforms.fieldBounds = new Cartesian4(field.west, field.south, field.width, field.height)
    viewer.scene.requestRender()
  }
  let state = { enabled: false, paused: false, visible: false, mode3d: true, pageVisible: !document.hidden, speed: 1 }
  let raf, disposed = false, lastFrame = 0, frames = 0
  const targetInterval = 1000 / 24
  const report = () => {
    element.dataset.waterTime = clock.seconds.toFixed(4)
    element.dataset.waterFrames = String(frames)
    element.dataset.waterState = !state.enabled ? 'disabled' : !state.pageVisible || !state.visible || !state.mode3d ? 'suspended' : state.paused ? 'paused' : 'running'
  }
  function tick(now) {
    if (disposed || !clock.running) return
    if (now - lastFrame >= targetInterval) {
      clock.advance(now)
      lastFrame = now
      frames++
      viewer.scene.requestRender()
      report()
    }
    raf = requestAnimationFrame(tick)
  }
  function setState(next) {
    if (disposed) return
    state = { ...state, ...next, pageVisible: !document.hidden }
    clock.configure({ running: shouldAnimate(state), speed: state.speed }, performance.now())
    cancelAnimationFrame(raf)
    if (clock.running) { lastFrame = performance.now(); raf = requestAnimationFrame(tick) }
    report()
    viewer.scene.requestRender()
  }
  const onVisibility = () => setState({})
  document.addEventListener('visibilitychange', onVisibility)
  return {
    waterMaterial, flowMaterial, setState, setRiverPath,
    dispose() {
      disposed = true
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVisibility)
      clock.running = false
      element.dataset.waterState = 'disposed'
    },
  }
}
