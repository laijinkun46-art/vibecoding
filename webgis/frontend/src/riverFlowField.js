import { Cartesian3, Matrix4, Transforms } from 'cesium'
import { Vector2 } from 'three'

// 波纹用研究区中心的局部东、北坐标（米），在切换情景和移动相机时保持对齐。
export const localOrigin = Cartesian3.fromDegrees(108.335, 22.79)
const frame = Transforms.eastNorthUpToFixedFrame(localOrigin)
const toLocal = Matrix4.inverseTransformation(frame, new Matrix4())
export const localEast = Matrix4.multiplyByPointAsVector(frame, Cartesian3.UNIT_X, new Cartesian3())
export const localNorth = Matrix4.multiplyByPointAsVector(frame, Cartesian3.UNIT_Y, new Cartesian3())

/** 输入按源线顺序排列的地心坐标。输出可上传的方向纹理及其局部米制范围。 */
export function makeRiverFlowField(positions) {
  const points = positions.map(position => {
    const { x, y } = Matrix4.multiplyByPoint(toLocal, position, new Cartesian3())
    return new Vector2(x, y)
  })
  const segments = []
  for (let i = 1; i < points.length; i++) {
    const start = points[i - 1]
    const direction = points[i].clone().sub(start)
    const length = direction.length()
    if (length > 0) segments.push({ start, direction: direction.divideScalar(length), length })
  }
  if (!segments.length) return
  const west = Math.min(...points.map(p => p.x)) - 2000
  const south = Math.min(...points.map(p => p.y)) - 2000
  const width = Math.max(...points.map(p => p.x)) + 2000 - west
  const height = Math.max(...points.map(p => p.y)) + 2000 - south
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 80
  const context = canvas.getContext('2d')
  const pixels = context.createImageData(canvas.width, canvas.height)
  for (let row = 0; row < canvas.height; row++) {
    const y = south + height * (1 - (row + .5) / canvas.height)
    for (let col = 0; col < canvas.width; col++) {
      const x = west + width * (col + .5) / canvas.width
      let vx = 0, vy = 0
      for (const { start, direction, length } of segments) {
        const dx = x - start.x, dy = y - start.y
        const along = Math.max(0, Math.min(length, dx * direction.x + dy * direction.y))
        const distance2 = (dx - along * direction.x) ** 2 + (dy - along * direction.y) ** 2
        // 近处遵循河弯切向，远处平滑混合，仅作流向示意。
        const weight = length / (distance2 + 250 ** 2) ** 2
        vx += direction.x * weight
        vy += direction.y * weight
      }
      const norm = Math.hypot(vx, vy) || 1
      const offset = 4 * (row * canvas.width + col)
      pixels.data[offset] = 127.5 * (1 + vx / norm)
      pixels.data[offset + 1] = 127.5 * (1 + vy / norm)
      pixels.data[offset + 3] = 255
    }
  }
  context.putImageData(pixels, 0, 0)
  return { texture: canvas.toDataURL(), west, south, width, height }
}
