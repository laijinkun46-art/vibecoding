/** Validated offline runs. A bounded neighbourhood keeps playback and seeking responsive. */
async function response(url, signal) {
  const r = await fetch(url, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000) })
  if (!r.ok) throw new Error(`水动力数据请求失败（${r.status}）`)
  return r
}

export async function listHydrodynamics(signal) {
  return (await response('/api/hydrodynamics/runs',signal)).json()
}

export async function openHydrodynamics(signal,run) {
  const base = '/api/hydrodynamics/runs/' + encodeURIComponent(run)
  const manifest = await (await response(base + '/manifest', signal)).json()
  if (manifest.schema !== 1 || manifest.status !== 'ready' || manifest.frames.length < 2
    || !Number.isFinite(manifest.wet_threshold_m) || manifest.wet_threshold_m <= 0) throw new Error('水动力结果格式不符')
  const hash = bytes => Array.from(new Uint8Array(bytes), v => v.toString(16).padStart(2, '0')).join('')
  const asset = async (name, cancel) => {
    const entry = manifest.assets[name]
    if (!entry) throw new Error('结果未登记')
    const bytes = await (await response(base + '/assets/' + encodeURIComponent(name), cancel)).arrayBuffer()
    if (bytes.byteLength !== entry.bytes || hash(await crypto.subtle.digest('SHA-256', bytes)) !== entry.sha256) {
      throw new Error('结果帧完整性核查失败')
    }
    return bytes
  }
  const [cellsRaw, lookupRaw] = await Promise.all([asset('cells.bin', signal), asset('index.bin', signal)])
  const cells = new Float32Array(cellsRaw), lookup = new Uint32Array(lookupRaw)
  const { cols, rows, cell_count: count, bounds } = manifest
  if (cells.length !== count * 5 || lookup.length !== rows * cols || lookup.some(i => i >= count)) throw new Error('结果网格长度错误')
  const cache = new Map(), pending = new Map()
  let focus = 0
  const nearby = index => index >= focus - 2 && index <= focus + 4
  function ensure(index, cancel) {
    if (cache.has(index)) return Promise.resolve(cache.get(index))
    if (pending.has(index)) return pending.get(index)
    const promise = asset(manifest.frames[index].file, cancel).then(bytes => {
      const values = new Float32Array(bytes)
      if (values.length !== count * 4 || !values.every(Number.isFinite)) throw new Error('结果帧含无效数值')
      if (nearby(index)) cache.set(index, values)
      return values
    }).finally(() => pending.delete(index))
    pending.set(index, promise)
    return promise
  }
  function pair(t) {
    let i = 0, j = manifest.frames.length - 1
    while (j - i > 1) {
      const mid = (i + j) >> 1
      if (manifest.frames[mid].t_seconds <= t) i = mid
      else j = mid
    }
    const a = manifest.frames[i].t_seconds, b = manifest.frames[j].t_seconds
    return { i, j, alpha: Math.max(0, Math.min(1, (t - a) / (b - a))), first: cache.get(i), second: cache.get(j) }
  }
  function prune(i) {
    focus = i
    for (const key of cache.keys()) if (!nearby(key)) cache.delete(key)
  }
  function cellId(lon, lat) {
    const [w, s, e, n] = bounds
    if (!(lon >= w && lon <= e && lat >= s && lat <= n)) return -1
    const x = Math.min(cols - 1, Math.floor(cols * (lon - w) / (e - w)))
    const y = Math.min(rows - 1, Math.floor(rows * (lat - s) / (n - s)))
    return lookup[y * cols + x]
  }
  async function series(lon, lat, cancel) {
    return (await response(`${base}/series?lon=${lon}&lat=${lat}`, cancel)).json()
  }
  const cacheStats = () => ({ cache_count: cache.size, pending_count: pending.size, initial_frame_cached: cache.has(0) })
  // 固定以模拟开始时的湿区区分原有水面与后续新增淹没；不改变模型帧。
  const initialFrame = await ensure(0, signal)
  const initiallyWet = Uint8Array.from({ length: count }, (_, id) =>
    Number(initialFrame[4 * id] >= manifest.wet_threshold_m))
  let overbankWeights
  if (manifest.overbank) {
    const bytes=Uint8Array.from(atob(manifest.overbank.weights_base64),c=>c.charCodeAt(0))
    if (bytes.length!==count*8 || hash(await crypto.subtle.digest('SHA-256',bytes))!==manifest.overbank.weights_sha256)
      throw new Error('两岸面积权重完整性校验失败')
    overbankWeights=new Float64Array(bytes.buffer)
    if (overbankWeights.some(n=>!Number.isFinite(n)||n<0)) throw new Error('两岸面积权重无效')
  }
  return { manifest, cells, lookup, initiallyWet, overbankWeights, cellId, ensure, pair, prune, series, cacheStats }
}
