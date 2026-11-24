import { Cartesian4, Material, TextureMinificationFilter, TextureMagnificationFilter } from 'cesium'

const source = `
vec2 replayUtm(vec3 world) {
  float meridian = radians(111.0);
  float longitude = atan(world.y,world.x);
  float radius = length(world.xy);
  // Bowring latitude on WGS84, followed by the UTM 49N forward series.
  float theta = atan(world.z*1.00336409,radius);
  float sinTheta = sin(theta), cosTheta = cos(theta);
  float latitude = atan(world.z+42841.31*sinTheta*sinTheta*sinTheta,
                        radius-42697.67*cosTheta*cosTheta*cosTheta);
  if (longitude < radians(108.15) || longitude > radians(108.51)
      || latitude < radians(22.66) || latitude > radians(22.91)) return vec2(-1.0);
  float e2 = 0.00669437999;
  float sinLat = sin(latitude), cosLat = cos(latitude), tanLat = tan(latitude);
  float radiusN = 6378137.0/sqrt(1.0-e2*sinLat*sinLat);
  float t = tanLat*tanLat, c = 0.00673949674*cosLat*cosLat;
  float a = cosLat*(longitude-meridian), a2 = a*a, a4 = a2*a2;
  float m = 6378137.0*(0.99832429845*latitude-0.00251460706*sin(2.0*latitude)
                        +0.00000263905*sin(4.0*latitude)-0.00000000342*sin(6.0*latitude));
  return vec2(500000.0+0.9996*radiusN*a*(1.0+(1.0-t+c)*a2/6.0
                +(5.0-18.0*t+t*t+72.0*c-0.39089081)*a4/120.0),
              0.9996*(m+radiusN*tanLat*a2*(0.5+(5.0-t+9.0*c+4.0*c*c)*a2/24.0
                +(61.0-58.0*t+t*t+600.0*c-2.1846781)*a4/720.0)));
}
czm_material czm_getMaterial(czm_materialInput sampleInput) {
  czm_material result = czm_getDefaultMaterial(sampleInput);
  result.alpha = 0.0;
  vec3 world = (czm_inverseView*vec4(-sampleInput.positionToEyeEC,1.0)).xyz;
  vec2 utm = replayUtm(world);
  vec2 uv = (utm-gridBounds.xy)/(gridBounds.zw-gridBounds.xy);
  if (any(lessThan(uv,vec2(0.0))) || any(greaterThanEqual(uv,vec2(1.0)))) return result;
  vec3 rgb = floor(texture(activationMap,uv).rgb*255.0+0.5);
  float threshold = 32.0+dot(rgb,vec3(65536.0,256.0,1.0))/262144.0;
  if (threshold >= stageM) return result;
  float newlyWet = step(initialStageM,threshold);
  float stageAboveCrest = stageM-threshold;
  vec3 river = vec3(0.16,0.35,0.33);
  vec3 shallow = vec3(0.21,0.76,0.91), deep = vec3(0.06,0.43,0.69);
  vec3 flooded = mix(shallow,deep,smoothstep(0.0,5.0,stageAboveCrest));
  float rim = (1.0-smoothstep(0.05,0.45,stageAboveCrest))*rising;
  flooded = mix(flooded,vec3(0.68,0.91,0.99),0.24*rim);
  // Local ripple shading only. The underlying flooded cell is selected by the crest threshold.
  float ripple = sin(utm.x*0.10+utm.y*0.12-animationTime*5.0)*0.018
    +sin(utm.x*0.23-utm.y*0.09-animationTime*7.0)*0.012;
  result.diffuse = mix(river,flooded,newlyWet)+ripple;
  result.alpha = mix(0.54,0.83,newlyWet)*smoothstep(0.0,0.11,stageAboveCrest);
  return result;
}
`

async function checkedBytes(asset, signal) {
  const response = await fetch(asset.url,{signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])})
  if (!response.ok) throw new Error('连续淹没成果读取失败')
  const bytes = await response.arrayBuffer()
  const computed = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
    n=>n.toString(16).padStart(2,'0')).join('')
  if (bytes.byteLength!==asset.bytes || computed!==asset.sha256) throw new Error('连续淹没成果指纹不一致')
  return bytes
}

async function loadImage(bytes) {
  const image = new Image()
  const url = URL.createObjectURL(new Blob([bytes],{type:'image/png'}))
  try {
    image.src = url
    await image.decode()
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function createStageReplay(viewer, signal) {
  const response = await fetch('/analysis/stage_replay_v1/manifest.json',{signal:AbortSignal.any([signal,AbortSignal.timeout(12000)])})
  if (!response.ok) throw new Error('未找到连续淹没成果清单')
  const data = await response.json()
  if (data.kind!=='static_connected_stage_replay' || data.crs!=='EPSG:32649' || data.encoding.origin_m!==32
    || data.encoding.ticks_per_m!==262144 || data.stages.length!==4) {
    throw new Error('连续淹没成果格式不符')
  }
  const [image,table] = await Promise.all([
    checkedBytes(data.assets['activation.png'],signal).then(loadImage),
    checkedBytes(data.assets['areas.bin'],signal),
  ])
  signal.throwIfAborted()
  if (image.width!==data.cols || image.height!==data.rows || !table.byteLength || table.byteLength%8) {
    throw new Error('淹没纹理和面积表尺寸不符')
  }

  const bins = new DataView(table)
  function areaAt(stage) {
    let lo=0, hi=bins.byteLength/8
    const level=Math.fround(stage)
    while(lo<hi) {
      const mid=(lo+hi)>>>1
      if(bins.getFloat32(8*mid,true)<level) lo=mid+1
      else hi=mid
    }
    return lo ? bins.getUint32(8*(lo-1)+4,true)*data.cell_area_m2/1e6 : 0
  }

  const initial = data.stages[0][1]
  const scene = viewer.scene
  const previousMaterial = scene.globe.material
  const active = new Material({
    fabric: { uniforms: { activationMap:image, gridBounds:new Cartesian4(...data.grid_bounds),
      stageM:initial,initialStageM:initial, rising:1.0,animationTime:0.0 }, source },
    minificationFilter:TextureMinificationFilter.NEAREST,
    magnificationFilter:TextureMagnificationFilter.NEAREST,
  })
  scene.globe.material = active
  scene.requestRender()
  return {
    data, areaAt,
    update(stage,elapsed,ascending) {
      active.uniforms.stageM = stage
      active.uniforms.animationTime = elapsed
      active.uniforms.rising = Number(ascending)
      scene.requestRender()
    },
    dispose() {
      if(scene.globe.material===active) scene.globe.material=previousMaterial
      active.destroy()
      scene.requestRender()
    },
  }
}
