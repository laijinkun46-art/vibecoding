/** 加载真实分析清单；校验失败时不给出伪造默认统计。 */
export async function fetchCheckedJson(asset) {
  const response = await fetch(asset.url, { signal: AbortSignal.timeout(20000) })
  if (!response.ok || !response.headers.get('content-type')?.includes('json')) throw new Error('分析成果不可用：' + asset.url)
  const buffer = await response.arrayBuffer()
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))].map(value => value.toString(16).padStart(2, '0')).join('')
  if (hash !== asset.sha256) throw new Error('分析成果完整性校验失败')
  return JSON.parse(new TextDecoder().decode(buffer))
}

export async function loadAnalysis() {
  const response = await fetch('/analysis/catalog.json', { signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error('分析成果清单不可用')
  const catalog = await response.json()
  const [summary, rainfall] = await Promise.all([
    fetchCheckedJson(catalog.assets.summary), fetchCheckedJson(catalog.assets.rainfall_timeseries),
  ])
  if (summary.kind !== 'hypothetical_scenario_not_observation' || !summary.scenarios?.length || rainfall.daily.length !== 8) throw new Error('分析成果格式不符合当前项目')
  try {
    const response = await fetch('/analysis/expanded_v1/catalog.json', { signal: AbortSignal.timeout(10000) })
    if (!response.ok) throw new Error('扩展情景清单不可用')
    const expanded = await response.json()
    const { summary: expandedSummary, ...assets } = expanded.assets
    const added = await fetchCheckedJson(expandedSummary)
    const rows = [...summary.scenarios, ...added.scenarios]
    const byId = new Map(rows.map(row => [row.id, row]))
    const order = expanded.playback_order
    if (added.kind !== summary.kind || added.vertical_datum !== summary.vertical_datum
      || byId.size !== rows.length || order.length !== rows.length || new Set(order).size !== rows.length
      || order.some(id => !byId.has(id) || !(assets[id + '_wet'] || catalog.assets[id + '_wet']))
      || added.comparisons.some(row => !assets[row.id + '_change'] || !byId.has(row.before) || !byId.has(row.after))) {
      throw new Error('扩展情景与原成果不匹配')
    }
    const comparisons = [...summary.comparisons, ...added.comparisons]
    return { catalog: { ...catalog, assets: { ...catalog.assets, ...assets } },
      summary: { ...summary, scenarios: order.map(id => byId.get(id)), comparisons }, rainfall }
  } catch {
    return { catalog, summary, rainfall, extensionError: '扩展情景暂不可用，当前显示原有四档水位。' }
  }
}
