/** 视觉动画时钟。时间单位秒，速度仅为播放倍率，不代表米/秒。 */
export class WaterClock {
  constructor() {
    this.seconds = 0
    this.last = undefined
    this.running = false
    this.speed = 1
  }
  advance(now) {
    if (!Number.isFinite(now)) throw new Error('动画时间必须为有限数')
    if (this.running && this.last !== undefined) {
      // 后台或长任务返回后不补算整段时间，避免视觉突然跳跃。
      this.seconds += Math.min(.1, Math.max(0, (now - this.last) / 1000)) * this.speed
    }
    this.last = now
    return this.seconds
  }
  configure({ running, speed }, now) {
    if (![.5, 1, 2].includes(Number(speed))) throw new Error('不支持的视觉速度倍率')
    this.advance(now)
    this.running = Boolean(running)
    this.speed = Number(speed)
  }
}

/** 输入可见性和用户选项，决定是否需要连续刷新；与分析计算没有联系。 */
export function shouldAnimate({ enabled, paused, visible, mode3d, pageVisible }) {
  return Boolean(enabled && !paused && visible && mode3d && pageVisible)
}
