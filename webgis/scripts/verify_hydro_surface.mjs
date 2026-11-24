import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { makeSurfaceMesh } from '../frontend/src/hydroSurfaceGeometry.js'

const folder = new URL('../data/processed/hydrodynamics/runs/full_reach_v2/', import.meta.url)
const { cols, rows, cell_count: count } = JSON.parse(await fs.readFile(new URL('manifest.json', folder)))
const raw = await fs.readFile(new URL('web/index.bin', folder))
const lookup = new Uint32Array(raw.buffer, raw.byteOffset, raw.byteLength/4)
const { grid, owners, neighbors, triangles } = makeSurfaceMesh(lookup, cols, rows, count)
const x = i => grid[2*i], y = i => grid[2*i+1]
const key = i => 2*x(i) + (2*cols+1)*2*y(i)
const extents = Array.from({ length: count }, () => [cols, rows, 0, 0])
for (let j=0; j<rows; j++) for (let i=0; i<cols; i++) {
  const rect = extents[lookup[j*cols+i]]
  rect[0] = Math.min(rect[0],i)
  rect[1] = Math.min(rect[1],j)
  rect[2] = Math.max(rect[2],i+1)
  rect[3] = Math.max(rect[3],j+1)
}
const areaByCell = new Float64Array(count)
const edges = new Map()
const cornerStencils = new Map()
for (let i=0; i<owners.length; i++) {
  const [w,s,e,n] = extents[owners[i]]
  assert.ok(x(i)>=w && x(i)<=e && y(i)>=s && y(i)<=n)
  const stencil = Array.from(neighbors.subarray(4*i,4*i+4))
  assert.ok(stencil.includes(owners[i]))
  if (x(i)===w || x(i)===e || y(i)===s || y(i)===n) {
    if (cornerStencils.has(key(i))) assert.deepEqual(cornerStencils.get(key(i)),stencil)
    else cornerStencils.set(key(i),stencil)
  }
}
for (let i=0; i<triangles.length; i+=3) {
  const [a,b,c] = triangles.subarray(i,i+3)
  assert.equal(owners[a],owners[b])
  assert.equal(owners[a],owners[c])
  const area=((x(b)-x(a))*(y(c)-y(a))-(x(c)-x(a))*(y(b)-y(a)))/2
  assert.ok(area>0,'反向或退化三角形')
  areaByCell[owners[a]] += area
  for (const [m,n] of [[a,b],[b,c],[c,a]]) {
    const pair = [key(m),key(n)].sort((v,w)=>v-w).join(',')
    const edge = edges.get(pair) ?? { m,n,count:0 }
    edge.count++
    edges.set(pair,edge)
  }
}
for (let i=0; i<count; i++) {
  const [w,s,e,n] = extents[i]
  assert.equal(areaByCell[i],(e-w)*(n-s),'三角形没有完整覆盖原单元')
}
let perimeter=0
for (const {m,n,count: copies} of edges.values()) {
  const external=(x(m)===x(n) && [0,cols].includes(x(m))) || (y(m)===y(n) && [0,rows].includes(y(m)))
  assert.equal(copies,external ? 1 : 2,'模型网格内有裂缝、重叠或未匹配的粗细接缝')
  perimeter+=Number(external)
}
console.log(JSON.stringify({cells:count,vertices:owners.length,triangles:triangles.length/3,
  matchingInteriorEdges:edges.size-perimeter,perimeterEdges:perimeter,sharedStencils:cornerStencils.size}))

