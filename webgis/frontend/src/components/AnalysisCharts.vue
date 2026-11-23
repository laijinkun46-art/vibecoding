<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { init, use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
const props = defineProps({ summary: Object, rainfall: Object, selectedId: String })
const areaContainer = ref(null), rainContainer = ref(null)
let areaChart, rainChart, observer
function update() {
  if (!areaChart || !props.summary || !props.rainfall) return
  const scenarios = props.summary.scenarios
  areaChart.setOption({
    animation: false, tooltip: { trigger: 'axis', valueFormatter: value => `${Number(value).toFixed(4)} km²` },
    grid: { left: 48, right: 15, top: 25, bottom: 30 },
    xAxis: { type: 'category', data: scenarios.map(row => row.id) },
    yAxis: { type: 'value', name: 'km²', splitLine: { lineStyle: { color: '#e7eeee' } } },
    series: [{ type: 'bar', barMaxWidth: 32, data: scenarios.map(row => ({ value: row.area_km2,
      itemStyle: { color: row.id === props.selectedId ? '#087b88' : '#a1cbd1', borderRadius: [3, 3, 0, 0] } })) }],
  })
  rainChart.setOption({
    animation: false, color: ['#318eae', '#c58232'],
    tooltip: { trigger: 'axis', valueFormatter: value => `${Number(value).toFixed(2)} mm` },
    legend: { data: ['单日', '累计'], top: 0, textStyle: { color: '#536e75' } },
    grid: { left: 40, right: 40, top: 40, bottom: 35 },
    xAxis: { type: 'category', data: props.rainfall.daily.map(row => row.date_label.slice(5)), axisLabel: { interval: 1 } },
    yAxis: [{ type: 'value', name: 'mm', splitLine: { lineStyle: { color: '#e7eeee' } } },
      { type: 'value', name: '累计mm', splitLine: { show: false } }],
    series: [{ name: '单日', type: 'bar', data: props.rainfall.daily.map(row => row.mean_precip_mm) },
      { name: '累计', type: 'line', yAxisIndex: 1, data: props.rainfall.daily.map(row => row.cumulative_precip_mm), symbolSize: 5 }],
  })
}
onMounted(() => {
  areaChart = init(areaContainer.value)
  rainChart = init(rainContainer.value)
  observer = new ResizeObserver(() => { areaChart.resize(); rainChart.resize() })
  observer.observe(areaContainer.value)
  observer.observe(rainContainer.value)
  update()
})
watch(() => [props.summary, props.rainfall, props.selectedId], update)
onBeforeUnmount(() => { observer?.disconnect(); areaChart?.dispose(); rainChart?.dispose() })
</script>

<template>
  <section class="chart-section">
    <h3>假设情景面积</h3>
    <div ref="areaContainer" class="stat-chart" role="img" aria-label="四个假设水位情景的连通湿区面积柱状图"></div>
    <details><summary>查看面积数据</summary><table><thead><tr><th>情景</th><th>面积 km²</th></tr></thead><tbody><tr v-for="row in summary.scenarios" :key="row.id"><td>{{ row.id }} · {{ row.water_level_m }} m</td><td>{{ row.area_km2.toFixed(4) }}</td></tr></tbody></table></details>
    <h3 class="rain-chart-title">真实历史降雨 · CHM_PRE</h3>
    <div ref="rainContainer" class="stat-chart rain-chart" role="img" aria-label="2024年9月6日至13日逐日及累计研究区面平均降雨图"></div>
    <p class="panel-note">累计 {{ rainfall.total_precip_mm.toFixed(2) }} mm；气象日为前日20时至当日20时。降雨未换算为情景水位。</p>
    <details><summary>查看逐日降雨数据</summary><table><thead><tr><th>日期</th><th>单日 mm</th><th>累计 mm</th></tr></thead><tbody><tr v-for="row in rainfall.daily" :key="row.date_label"><td>{{ row.date_label.slice(5) }}</td><td>{{ row.mean_precip_mm.toFixed(2) }}</td><td>{{ row.cumulative_precip_mm.toFixed(2) }}</td></tr></tbody></table></details>
  </section>
</template>
