<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const candidates = ref<any[]>([])
const violKeys = ref<Set<string>>(new Set())
const err = ref('')

function errText(e: any): string {
  try {
    const j = JSON.parse(e?.message || '')
    return j.detail ?? e.message
  } catch { return e?.message || String(e) }
}

async function refreshViol() {
  try {
    const v = await api('/seating/violations?hall_id=1')
    const keys = new Set<string>()
    for (const x of v.violations || []) {
      if (x.a_id != null) keys.add(String(x.a_id))
      if (x.b_id != null) keys.add(String(x.b_id))
    }
    violKeys.value = keys
  } catch { violKeys.value = new Set() }
}

async function run() {
  err.value = ''
  try {
    // 按保存当下的损坏名单重新出图
    data.value = await api('/seating/run?hall_id=1', { method: 'POST' })
  } catch (e: any) {
    // 整场失败（如损坏后不连通）：方案不增行，展示停留在上一份方案
    err.value = errText(e)
    try { data.value = await api('/seating/latest?hall_id=1') } catch { /* 保留当前显示 */ }
  }
  await refreshViol()
}
onMounted(async () => {
  candidates.value = await api('/candidates')
  await run()
})
const gridStyle = computed(() => data.value ? ({ gridTemplateColumns: `repeat(${data.value.cols}, 72px)` }) : {})
const damagedSet = computed(() => new Set((data.value?.damaged || []).map((d: any) => d.row + ',' + d.col)))
const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      const key = r + ',' + c
      if (damagedSet.value.has(key)) out.push({ damaged: true, row: r, col: c })
      else out.push(map.get(key) || { empty: true, row: r, col: c })
    }
  }
  return out
})
function isViol(cell: any) {
  if (cell.empty || cell.damaged) return false
  const id = cell.candidate_id ?? cell.id
  return id != null && violKeys.value.has(String(id))
}
function paperClass(pid: number) {
  return pid % 2 === 0 ? 'b' : 'a'
}
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 左侧考生名册夹板 · 违规课桌高亮 · 损坏格空白禁坐</p>
  <button class="btn" @click="run">重新排座</button>
  <span v-if="data" class="muted" style="margin-left:0.75rem;font-size:0.82rem">
    损坏 {{ data.stats?.damaged ?? 0 }} 格 · 可坐容量 {{ data.stats?.capacity }} / {{ data.stats?.capacity_total }}
  </span>
  <p v-if="err" class="hs-err">{{ err }}</p>
  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row">
        <div>
          <div>{{ c.name }}</div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
        </div>
        <div>卷{{ c.paper_id }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="data">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{ empty: cell.empty, damaged: cell.damaged, 'hs-viol': isViol(cell) }"
        >
          <template v-if="cell.damaged"></template>
          <template v-else-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else>·</template>
        </div>
      </div>
    </div>
  </div>
</template>
