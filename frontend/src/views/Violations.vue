<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const viols = ref<any[]>([])
const unplaced = ref<any[]>([])
const failed = ref('')
onMounted(async () => {
  try {
    const res = await api('/seating/violations?hall_id=1')
    viols.value = res.violations; unplaced.value = res.unplaced
  } catch (e: any) {
    try { failed.value = JSON.parse(e.message).detail || e.message } catch { failed.value = e.message }
  }
})
</script>
<template>
  <h1>违规</h1>
  <p class="sub">间距不足或同试卷四邻相邻；损坏格坐不下只进未排名单，按容量账说明</p>
  <div v-if="failed" class="card hs-notice bad" style="white-space:pre-line">{{ failed }}
（整场排座失败，名单与统计停在拒绝前，不增方案行。）</div>
  <template v-else>
    <div class="card">
      <table>
        <thead><tr><th>类型</th><th>考生A</th><th>考生B</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="(v,i) in viols" :key="i">
            <td>{{ v.kind }}</td><td>{{ v.a_id }}</td><td>{{ v.b_id }}</td><td>{{ v.detail }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!viols.length" class="muted">无违规</p>
    </div>
    <div class="card" v-if="unplaced.length">
      <h3>未排上</h3>
      <table>
        <thead><tr><th>考生</th><th>准考证</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="(u,i) in unplaced" :key="u.id ?? i">
            <td>{{ u.name }}</td><td>{{ u.ticket_no }}</td><td>{{ u.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
</template>
