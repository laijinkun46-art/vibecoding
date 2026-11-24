<script setup>
import { onBeforeUnmount,onMounted,ref } from 'vue'
import HydroControls from './HydroControls.vue'
import { listHydrodynamics } from '../hydroData'

defineProps({ map:Object,location:Object })
const runs=ref([]), selected=ref(''), failure=ref('')
let controller
async function load() {
  controller?.abort()
  controller=new AbortController()
  const signal=controller.signal
  failure.value=''
  try {
    const available=await listHydrodynamics(signal)
    if (signal.aborted) return
    runs.value=available
    selected.value=available.find(run=>run.id==='full_reach_v3')?.id
      ?? available.find(run=>run.id==='full_reach_v2')?.id ?? available[0]?.id ?? ''
    if (!selected.value) failure.value='没有可用的已验收水动力结果'
  } catch {
    if(!signal.aborted) failure.value='水动力运行列表暂不可用'
  }
}
onMounted(load)
onBeforeUnmount(()=>controller?.abort())
</script>

<template>
  <label v-if="selected" class="field-label">水动力情景
    <select v-model="selected">
      <option v-for="run in runs" :key="run.id" :value="run.id">{{run.id==='full_reach_v2'?'原方案 · v2':run.label+' · '+run.id}}</option>
    </select>
  </label>
  <p v-else-if="failure" class="panel-note error-text" role="alert">{{failure}} <button class="secondary-button" @click="load">重试</button></p>
  <p v-else class="panel-note" role="status">正在核对已验收的水动力情景…</p>
  <HydroControls v-if="selected" :key="selected" :run-id="selected" :map="map" :location="location"/>
</template>
