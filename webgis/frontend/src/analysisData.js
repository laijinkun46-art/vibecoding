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
  if (summary.kind !== 'hypothetical_scenario_not_observation' || summary.scenarios.length !== 4 || rainfall.daily.length !== 8) throw new Error('分析成果格式不符合当前项目')
  return { catalog, summary, rainfall }
}
