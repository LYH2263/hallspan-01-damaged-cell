<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const info = ref<Record<number, any>>({})
const editing = ref<Record<number, Set<string>>>({})
const errors = ref<Record<number, string>>({})

function errText(e: any): string {
  try {
    const j = JSON.parse(e?.message || '')
    return j.detail ?? e.message
  } catch { return e?.message || String(e) }
}

async function loadDamaged(hallId: number) {
  info.value[hallId] = await api(`/damaged?hall_id=${hallId}`)
  editing.value[hallId] = new Set((info.value[hallId].damaged || []).map((d: any) => d.row + ',' + d.col))
}

onMounted(async () => {
  rows.value = await api('/halls')
  for (const h of rows.value) await loadDamaged(h.id)
})

function hallCells(h: any) {
  const out: any[] = []
  for (let r = 0; r < h.rows; r++) for (let c = 0; c < h.cols; c++) out.push({ key: r + ',' + c, r, c })
  return out
}
function isDamaged(hallId: number, r: number, c: number) {
  return (editing.value[hallId] || new Set()).has(r + ',' + c)
}
function toggle(hallId: number, r: number, c: number) {
  const s = new Set(editing.value[hallId] || [])
  const k = r + ',' + c
  if (s.has(k)) s.delete(k); else s.add(k)
  editing.value[hallId] = s
}
async function save(hallId: number) {
  errors.value[hallId] = ''
  const cells = [...(editing.value[hallId] || [])].map((k) => {
    const [row, col] = k.split(',').map(Number)
    return { row, col }
  })
  try {
    info.value[hallId] = await api(`/damaged?hall_id=${hallId}`, { method: 'PUT', body: JSON.stringify({ cells }) })
    editing.value[hallId] = new Set(cells.map((c) => c.row + ',' + c.col))
  } catch (e: any) {
    // 整场拒绝：回到已保存名单，不保留本地改动
    errors.value[hallId] = errText(e)
    await loadDamaged(hallId)
  }
}
async function clearAll(hallId: number) {
  editing.value[hallId] = new Set()
  await save(hallId)
}
</script>
<template>
  <h1>考室</h1>
  <p class="sub">考室网格与最小曼哈顿间距 · 点击格子登记/取消损坏禁坐格</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>行</th><th>列</th><th>最小间距</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)"><td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.rows }}</td><td>{{ r.cols }}</td><td>{{ r.min_manhattan }}</td></tr>
      </tbody>
    </table>
  </div>
  <div class="card" v-for="h in rows" :key="'dmg-' + h.id">
    <h3 style="margin-top:0">{{ h.name }}（{{ h.code }}）损坏禁坐格</h3>
    <p class="muted" v-if="info[h.id]">
      {{ h.rows }}×{{ h.cols }} 共 {{ h.rows * h.cols }} 格 ·
      损坏 {{ info[h.id].damaged_count }} 格 ·
      可坐容量 {{ info[h.id].capacity }} ·
      <span class="badge" :class="info[h.id].connected ? 'badge-ok' : 'badge-bad'">
        {{ info[h.id].connected ? '四邻连通' : '损坏后不连通，排座将失败' }}
      </span>
    </p>
    <div class="grid-board" :style="{ gridTemplateColumns: `repeat(${h.cols}, 56px)` }">
      <div
        v-for="cell in hallCells(h)" :key="cell.key"
        class="seat" :class="{ damaged: isDamaged(h.id, cell.r, cell.c) }"
        @click="toggle(h.id, cell.r, cell.c)"
      >{{ isDamaged(h.id, cell.r, cell.c) ? '✕' : '' }}</div>
    </div>
    <div style="margin-top:0.6rem;display:flex;gap:0.5rem">
      <button class="btn" @click="save(h.id)">保存损坏名单</button>
      <button class="btn" @click="clearAll(h.id)">清空名单</button>
    </div>
    <p v-if="errors[h.id]" class="hs-err">{{ errors[h.id] }}</p>
  </div>
</template>
