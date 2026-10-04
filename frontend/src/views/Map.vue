<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const HALL_ID = 1
const hall = ref<any>(null)
const plan = ref<any>(null)
const damaged = ref<{ row: number; col: number }[]>([])   // 已保存名单（容量账基准）
const draft = ref<{ row: number; col: number }[]>([])     // 编辑中名单
const candidates = ref<any[]>([])
const violKeys = ref<Set<string>>(new Set())
const rowInput = ref<number>(0)
const colInput = ref<number>(0)
const notice = ref('')
const noticeKind = ref<'ok' | 'bad' | ''>('')
const saving = ref(false)

function setNotice(msg: string, kind: 'ok' | 'bad' | '' = '') {
  notice.value = msg; noticeKind.value = kind
}

const rows = computed(() => hall.value?.rows ?? plan.value?.rows ?? 0)
const cols = computed(() => hall.value?.cols ?? plan.value?.cols ?? 0)
const gridStyle = computed(() => ({ gridTemplateColumns: `repeat(${cols.value}, 72px)` }))

const damagedSet = computed(() => new Set(damaged.value.map(d => d.row + ',' + d.col)))
const draftSet = computed(() => new Set(draft.value.map(d => d.row + ',' + d.col)))

const cells = computed(() => {
  // 网格只按当前考室行列与已保存损坏名单出图；plan 为 null（割裂失败）时只剩空白与损坏格
  const map = new Map<string, any>()
  for (const a of plan.value?.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < rows.value; r++) {
    for (let c = 0; c < cols.value; c++) {
      const key = r + ',' + c
      out.push({
        row: r, col: c, key,
        damaged: damagedSet.value.has(key),
        pending: draftSet.value.has(key) && !damagedSet.value.has(key),
        seat: map.get(key) || null,
      })
    }
  }
  return out
})

const stats = computed(() => plan.value?.stats ?? null)
const dirty = computed(() => {
  const a = new Set(damaged.value.map(d => d.row + ',' + d.col))
  const b = draftSet.value
  return a.size !== b.size || [...a].some(k => !b.has(k))
})

async function refreshViolations() {
  try {
    const v = await api(`/seating/violations?hall_id=${HALL_ID}`)
    const keys = new Set<string>()
    for (const x of v.violations || []) {
      if (x.a_id != null) keys.add(String(x.a_id))
      if (x.b_id != null) keys.add(String(x.b_id))
    }
    violKeys.value = keys
  } catch { violKeys.value = new Set() }
}

async function run() {
  // 按保存当下名单出图；割裂时后端整场拒绝，不返回任何座位
  try {
    plan.value = await api(`/seating/run?hall_id=${HALL_ID}`, { method: 'POST' })
    setNotice('', '')
    return true
  } catch (e: any) {
    plan.value = null
    setNotice(e.message.includes('不连通') ? '损坏后考室不连通，整场排座失败' : extractError(e), 'bad')
    return false
  } finally {
    await refreshViolations()
  }
}

function extractError(e: any): string {
  try { return JSON.parse(e.message).detail || e.message } catch { return e.message }
}

async function saveList(seats: { row: number; col: number }[], okMsg: string) {
  saving.value = true
  try {
    const res = await api(`/halls/${HALL_ID}/damaged`, {
      method: 'PUT', body: JSON.stringify({ seats }),
    })
    damaged.value = res.seats
    draft.value = res.seats.map((s: any) => ({ ...s }))
    const ok = await run()
    if (ok) setNotice(okMsg, 'ok')
  } catch (e: any) {
    // 越界/重复整场拒绝：名单停在拒绝前，draft 回滚到已保存名单
    draft.value = damaged.value.map(s => ({ ...s }))
    setNotice(extractError(e), 'bad')
  } finally { saving.value = false }
}

function save() {
  // 客户端先挡一道，权威拒绝仍以后端为准
  const seen = new Set<string>()
  for (const s of draft.value) {
    const k = s.row + ',' + s.col
    if (s.row < 0 || s.row >= rows.value || s.col < 0 || s.col >= cols.value) {
      setNotice(`损坏格行列越界：第 ${s.row} 行第 ${s.col} 列不在 ${rows.value}×${cols.value} 考室内`, 'bad')
      return
    }
    if (seen.has(k)) { setNotice(`损坏格重复登记：第 ${s.row} 行第 ${s.col} 列`, 'bad'); return }
    seen.add(k)
  }
  return saveList(draft.value, '损坏名单已保存')
}

function clearAll() { return saveList([], '名单已清空，退回满格连通可坐') }

function addByInput() {
  const r = Number(rowInput.value), c = Number(colInput.value)
  if (!Number.isInteger(r) || !Number.isInteger(c) || r < 0 || r >= rows.value || c < 0 || c >= cols.value) {
    setNotice(`损坏格行列越界：第 ${r} 行第 ${c} 列不在 ${rows.value}×${cols.value} 考室内`, 'bad')
    return
  }
  if (draftSet.value.has(r + ',' + c)) { setNotice(`损坏格重复登记：第 ${r} 行第 ${c} 列`, 'bad'); return }
  draft.value = [...draft.value, { row: r, col: c }]
  setNotice('', '')
}

function toggleCell(cell: any) {
  const k = cell.row + ',' + cell.col
  if (draftSet.value.has(k)) draft.value = draft.value.filter(s => s.row + ',' + s.col !== k)
  else draft.value = [...draft.value, { row: cell.row, col: cell.col }]
  setNotice('', '')
}

function isViol(seat: any) {
  if (!seat) return false
  const id = seat.candidate_id ?? seat.id
  return id != null && violKeys.value.has(String(id))
}
function paperClass(pid: number) { return pid % 2 === 0 ? 'b' : 'a' }

onMounted(async () => {
  const halls = await api('/halls')
  hall.value = halls[0]
  candidates.value = await api('/candidates')
  const d = await api(`/halls/${HALL_ID}/damaged`)
  damaged.value = d.seats
  draft.value = d.seats.map((s: any) => ({ ...s }))
  try {
    plan.value = await api(`/seating/latest?hall_id=${HALL_ID}`)
  } catch (e: any) {
    plan.value = null
    setNotice(e.message.includes('不连通') ? '损坏后考室不连通，整场排座失败' : extractError(e), 'bad')
  }
  await refreshViolations()
})
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 左侧考生名册夹板 · 损坏格禁坐空白 · 剩余可坐格须四邻连通</p>

  <div class="hs-damage-bar">
    <div class="hs-damage-edit">
      <label>损坏格登记</label>
      <input v-model.number="rowInput" type="number" min="0" :max="rows - 1" aria-label="行" /> 行
      <input v-model.number="colInput" type="number" min="0" :max="cols - 1" aria-label="列" /> 列
      <button class="btn" @click="addByInput">登记</button>
      <button class="btn" @click="save" :disabled="saving || !dirty">保存名单并排座</button>
      <button class="btn btn-ghost" @click="clearAll" :disabled="saving">清空名单</button>
    </div>
    <div class="hs-damage-list">
      <span class="muted">当前已保存损坏格：</span>
      <template v-if="damaged.length">
        <span v-for="(d,i) in damaged" :key="i" class="hs-chip">第{{ d.row }}行第{{ d.col }}列</span>
      </template>
      <span v-else class="muted">无（满格可坐）</span>
    </div>
  </div>

  <p v-if="notice" class="hs-notice" :class="noticeKind === 'bad' ? 'bad' : 'ok'">{{ notice }}</p>

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
    <div>
      <button class="btn" @click="run">重新排座</button>
      <div class="hs-desk-stage" style="margin-top:0.6rem">
        <div class="hs-grid-board" :style="gridStyle">
          <div
            v-for="cell in cells" :key="cell.key"
            class="hs-desk"
            :class="{ damaged: cell.damaged, pending: cell.pending, empty: !cell.damaged && !cell.pending && !cell.seat, 'hs-viol': isViol(cell.seat) }"
            :title="`第${cell.row}行第${cell.col}列` + (cell.damaged ? '（损坏禁坐）' : '（点击标记损坏）')"
            @click="toggleCell(cell)"
          >
            <template v-if="cell.damaged">
              <span class="hs-damage-tag">损坏</span>
            </template>
            <template v-else-if="cell.seat">
              <span class="hs-paper-tag" :class="paperClass(cell.seat.paper_id)">卷{{ cell.seat.paper_id }}</span>
              <div>{{ cell.seat.name }}</div>
            </template>
            <template v-else-if="cell.pending">
              <span class="hs-damage-tag pending-tag">待保存</span>
            </template>
            <template v-else>·</template>
          </div>
        </div>
      </div>
      <div class="card" v-if="stats" style="margin-top:0.6rem;display:flex;gap:1.6rem;flex-wrap:wrap">
        <span><span class="muted">已排座 </span><b>{{ stats.seated }}</b></span>
        <span><span class="muted">未排上 </span><b>{{ stats.unplaced }}</b></span>
        <span><span class="muted">可坐容量 </span><b>{{ stats.capacity }}</b></span>
        <span><span class="muted">损坏格 </span><b>{{ stats.damaged }}</b></span>
        <span><span class="muted">总桌位 </span><b>{{ stats.total_seats }}</b></span>
      </div>
      <p v-else-if="noticeKind === 'bad'" class="muted" style="margin-top:0.6rem">
        整场排座失败：图中不展示任何座位，方案列表不增行。
      </p>
    </div>
  </div>
</template>
