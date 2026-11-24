export const waterStyle = Object.freeze({
  surfaceOffset: 0.24, // Existing visual offset, in metres above exaggerated stage.
  shallowFade: 0.15,
  shoreWidth: 28,
  shallowColor: [0.24, 0.46, 0.44],
  deepColor: [0.10, 0.28, 0.31],
  waveScales: [26, 88],
  visualSecondsPerSecond: 1 / 1500,
  waveTravel: 10,
  particleCount: 320,
  lowParticleCount: 112,
})

const frameSampling = `
uniform sampler2D beforeFrame;
uniform sampler2D afterFrame;
uniform float fraction;
uniform int frameWidth;
vec4 sampleFrame(float id) {
  if (id < 0.0) return vec4(0.0);
  int index = int(id);
  ivec2 p = ivec2(index % frameWidth, index / frameWidth);
  return mix(texelFetch(beforeFrame,p,0),texelFetch(afterFrame,p,0),fraction);
}
`

export const waterVertex = `
in vec3 high;
in vec3 low;
in vec3 up;
in vec2 grid;
in vec4 neighbors;
in float owner;
uniform float relief;
uniform float surfaceOffset;
uniform float wetThreshold;
out vec2 lattice;
out vec3 eyePosition;
out vec3 upEC;
out vec3 eastEC;
out vec4 field;
flat out float ownerId;
flat out vec2 ownerDepthStage;
SAMPLE_FRAME

void main() {
  vec4 a = sampleFrame(neighbors.x), b = sampleFrame(neighbors.y);
  vec4 c = sampleFrame(neighbors.z), d = sampleFrame(neighbors.w);
  vec4 h = vec4(a.x,b.x,c.x,d.x);
  vec4 stage = vec4(a.y,b.y,c.y,d.y);
  vec4 wet = step(vec4(wetThreshold),h) * step(vec4(0.0),neighbors);
  // Adjacency follows the four face-connected sectors, so corner contacts alone
  // cannot bridge a dry cell. A face links only when both stages clear its higher bed.
  vec4 crest = max(stage-h, (stage-h).yzwx) + wetThreshold;
  vec4 sharedHeight = min(stage,stage.yzwx);
  vec4 edges = wet * wet.yzwx * step(crest,sharedHeight);
  vec4 connected = wet * vec4(equal(neighbors,vec4(owner)));
  for (int i=0; i<3; i++)
    connected = max(connected,max(connected.yzwx*edges,connected.wxyz*edges.wxyz));
  vec4 own = sampleFrame(owner);
  vec4 weights = connected * smoothstep(vec4(wetThreshold),vec4(wetThreshold+0.10),h);
  float total = dot(weights,vec4(1.0));
  vec3 reconstructed = weights.x*a.yzw + weights.y*b.yzw + weights.z*c.yzw + weights.w*d.yzw;
  vec4 bed = stage-h;
  field = total>0.0 ? vec4(reconstructed,dot(weights,bed))/total : vec4(own.yzw,own.y-own.x);
  ownerId = owner;
  ownerDepthStage = own.xy;
  lattice = grid;
  vec4 relative = czm_translateRelativeToEye(high,low+up*(field.x*relief+surfaceOffset));
  eyePosition = (czm_modelViewRelativeToEye*relative).xyz;
  upEC = czm_normal*up;
  eastEC = czm_normal*normalize(cross(vec3(0.0,0.0,1.0),up));
  gl_Position = czm_modelViewProjectionRelativeToEye*relative;
  czm_vertexLogDepth();
}
`.replace('SAMPLE_FRAME', frameSampling)

export const waterFragment = `
in vec2 lattice;
in vec3 eyePosition;
in vec3 upEC;
in vec3 eastEC;
in vec4 field;
flat in float ownerId;
flat in vec2 ownerDepthStage;
uniform sampler2D cellLookup;
uniform sampler2D normalMap;
uniform vec2 latticeSize;
uniform vec2 latticeMetres;
uniform vec2 boundsOrigin;
uniform vec2 latticeDegrees;
uniform vec3 shallowColor;
uniform vec3 deepColor;
uniform vec2 waveScales;
uniform float wetThreshold;
uniform float shallowFade;
uniform float shoreWidth;
uniform float visualTime;
uniform float waveTravel;
uniform int style;
uniform bool normalReady;
uniform bool lowQuality;
uniform bool showMesh;
SAMPLE_FRAME

float cellAt(ivec2 p) {
  if (any(lessThan(p,ivec2(0))) || any(greaterThanEqual(p,ivec2(latticeSize)))) return -1.0;
  return texelFetch(cellLookup,p,0).x;
}
float adjacentDry(ivec2 p) {
  float id = cellAt(p);
  return id == ownerId ? 0.0 : 1.0-step(wetThreshold,sampleFrame(id).x);
}
float shoreSide(ivec2 p, float distanceToFace, float width) {
  return distanceToFace >= width || adjacentDry(p)==0.0 ? width : distanceToFace;
}
float roundedCorner(vec2 d, vec2 side, ivec2 diagonal, float width) {
  if (max(d.x,d.y) >= width) return width;
  if (all(lessThan(side,vec2(width)))) return width-length(vec2(width)-d);
  if (all(equal(side,vec2(width))) && adjacentDry(diagonal)>0.0) return length(d);
  return width;
}
vec2 flowNormal(vec2 xy, vec2 velocity, float scale, float time) {
  // Each pass has zero weight when its phase wraps. Only a bounded displacement
  // depends on the current velocity, including when the user jumps in time.
  float activity = smoothstep(0.025,0.14,length(velocity));
  if (activity<=0.0) return texture(normalMap,xy/scale).rg*2.0-1.0;
  float a = fract(time/4.8);
  float b = fract(a+0.5);
  float weight = 1.0-abs(2.0*a-1.0);
  vec2 travel = velocity*(waveTravel*4.8);
  vec2 first = texture(normalMap,(xy-travel*a)/scale).rg;
  vec2 second = texture(normalMap,(xy-travel*b)/scale+vec2(0.28,0.61)).rg;
  vec2 blend = mix(second,first,weight);
  if (activity<1.0) blend = mix(texture(normalMap,xy/scale).rg,blend,activity);
  return blend*2.0-1.0;
}

void main() {
  if (ownerDepthStage.x < wetThreshold) discard;
  float ownerBed = ownerDepthStage.y-ownerDepthStage.x;
  float displayDepth = field.x-ownerBed;
  if (displayDepth < wetThreshold) discard;

  ivec2 p = clamp(ivec2(floor(lattice)),ivec2(0),ivec2(latticeSize)-1);
  vec2 position = clamp(lattice-vec2(p),0.0,1.0);
  vec4 distances = vec4(position.x,position.y,1.0-position.x,1.0-position.y)*latticeMetres.xyxy;
  float eyeDistance = length(eyePosition);
  float featherWidth = min(shoreWidth,max(17.0,eyeDistance*.0026));
  vec4 side = vec4(
    shoreSide(p+ivec2(-1,0),distances.x,featherWidth),
    shoreSide(p+ivec2(0,-1),distances.y,featherWidth),
    shoreSide(p+ivec2(1,0),distances.z,featherWidth),
    shoreSide(p+ivec2(0,1),distances.w,featherWidth));
  float outline = min(min(side.x,side.y),min(side.z,side.w));
  outline = min(outline,roundedCorner(distances.xy,side.xy,p+ivec2(-1,-1),featherWidth));
  outline = min(outline,roundedCorner(distances.yz,side.yz,p+ivec2(1,-1),featherWidth));
  outline = min(outline,roundedCorner(distances.zw,side.zw,p+ivec2(1,1),featherWidth));
  outline = min(outline,roundedCorner(distances.wx,side.wx,p+ivec2(-1,1),featherWidth));
  float waterDepth = max(0.0,field.x-field.w);
  float wetFade = smoothstep(wetThreshold,wetThreshold+shallowFade,waterDepth);
  float ownerFade = smoothstep(wetThreshold,wetThreshold+0.045,min(displayDepth,ownerDepthStage.x));
  float opacity = wetFade*ownerFade*smoothstep(0.0,featherWidth,outline);
  if (opacity < 0.005) discard;

  vec3 color;
  float maxAlpha = 0.83;
  if (style==1) {
    color = mix(vec3(0.15,0.73,0.88),vec3(0.025,0.25,0.51),smoothstep(0.0,10.0,waterDepth));
  } else if (style==2) {
    color = mix(vec3(0.11,0.47,0.76),vec3(0.97,0.89,0.28),smoothstep(0.0,2.5,length(field.yz)));
  } else {
    vec3 up = normalize(upEC);
    vec3 east = normalize(eastEC);
    vec3 north = normalize(cross(up,east));
    vec3 surf = normalize(cross(dFdx(eyePosition),dFdy(eyePosition)));
    surf = normalize(mix(up,dot(surf,up)<0.0?-surf:surf,0.28));
    vec3 viewDir = -normalize(eyePosition);
    vec2 normal = vec2(0.0);
    if (normalReady) {
      vec2 xy = lattice*latticeMetres;
      vec2 lonLat = boundsOrigin + lattice*latticeDegrees;
      float gamma = radians(lonLat.x-111.0)*sin(radians(lonLat.y));
      float cs = cos(gamma), sn = sin(gamma);
      vec2 flow = mat2(cs,-sn,sn,cs)*field.yz;
      mat2 rotation = mat2(0.90,-0.436,0.436,0.90);
      float coarse = (1.0-smoothstep(4300.0,16000.0,eyeDistance));
      normal = rotation*flowNormal(rotation*xy,rotation*flow,waveScales.y,visualTime)*coarse*0.26;
      if (!lowQuality) {
        float detail = 1.0-smoothstep(1250.0,7200.0,eyeDistance);
        normal += flowNormal(xy,flow,waveScales.x,visualTime)*detail*0.42;
      }
    }
    float movement = smoothstep(0.10,1.5,waterDepth);
    surf = normalize(surf + (east*normal.x+north*normal.y)*movement);
    float base = smoothstep(0.25,7.5,waterDepth);
    float sky = pow(clamp(1.0-max(0.0,dot(viewDir,surf)),0.0,1.0),3.0);
    vec3 light = normalize(czm_sunDirectionEC+viewDir);
    float glint = pow(max(dot(surf,light),0.0),38.0)*0.073;
    float sheen = (normal.x*0.105+normal.y*0.135)*movement;
    color = mix(shallowColor,deepColor,base)+vec3(0.085,0.105,0.11)*sky+glint+sheen;
    maxAlpha = mix(0.63,0.89,base);
  }
  if (showMesh) {
    float stroke = max(0.8,min(45.0,eyeDistance*0.001));
    bool border = (distances.x<stroke && cellAt(p+ivec2(-1,0))!=ownerId)
      || (distances.y<stroke && cellAt(p+ivec2(0,-1))!=ownerId)
      || (distances.z<stroke && cellAt(p+ivec2(1,0))!=ownerId)
      || (distances.w<stroke && cellAt(p+ivec2(0,1))!=ownerId);
    if (border) { color=mix(color,vec3(0.99,0.78,0.36),0.77); opacity=max(opacity,0.72); }
  }
  out_FragColor = vec4(color,opacity*maxAlpha);
  czm_writeLogDepth();
}
`.replace('SAMPLE_FRAME', frameSampling)

