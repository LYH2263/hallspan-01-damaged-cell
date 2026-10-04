<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>({})
const failed = ref('')
onMounted(async () => {
  try {
    s.value = await api('/seating/stats?hall_id=1')
  } catch (e: any) {
    try { failed.value = JSON.parse(e.message).detail || e.message } catch { failed.value = e.message }
  }
})
</script>
<template>
  <h1>统计</h1>
  <p class="sub">排座占用、损坏禁坐格与违规汇总（与排座图、未排名单同一套容量账）</p>
  <div v-if="failed" class="card hs-notice bad" style="white-space:pre-line">{{ failed }}
（整场排座失败，统计停在拒绝前，不增方案行。）</div>
  <template v-else>
    <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
      <div><div class="muted">已排座</div><div class="stat">{{ s.seated }}</div></div>
      <div><div class="muted">未排上</div><div class="stat">{{ s.unplaced }}</div></div>
      <div><div class="muted">违规数</div><div class="stat">{{ s.violations }}</div></div>
      <div><div class="muted">可坐容量</div><div class="stat">{{ s.capacity }}</div></div>
      <div><div class="muted">损坏禁坐格</div><div class="stat">{{ s.damaged }}</div></div>
      <div><div class="muted">总桌位</div><div class="stat">{{ s.total_seats }}</div></div>
    </div>
    <p class="muted">容量账：{{ s.total_seats }} 总桌位 − {{ s.damaged }} 损坏格 = {{ s.capacity }} 可坐容量；
      已排座 {{ s.seated }} + 未排上 {{ s.unplaced }} 与考生总数对齐。</p>
  </template>
</template>
