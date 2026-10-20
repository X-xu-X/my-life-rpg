<script setup>
import RewardShop from './RewardShop.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'
import { useRedemption } from '../composables/useRedemption'
import { useExemptionPurchase } from '../composables/useExemptionPurchase'
import ConfirmDialog from './ui/ConfirmDialog.vue'
const redeemChoice=ref(null)
const redemption = useRedemption()
const exemptionPurchase = useExemptionPurchase()

// ============================================================
// v1.8 挑战 tab：挑战区 + 商店区
// 提交交互复用 v1.7 C 的成果：处理中显示「AI 正在分析…」+ 禁用 + 可取消
// ============================================================

const segment = ref('challenge') // challenge | shop
const error = ref('')
const loading = ref(false)

// ---- 金币 ----
const coins = ref(0)
const ledger = ref([])
const showLedger = ref(false)
const streakBusy = ref(false)
async function claimStreak() {
  if(streakBusy.value)return
  streakBusy.value=true
  try {const result=await api.checkStreak();await loadCoins();toast.success(result.granted.length?'连续记录奖励已入账':'目前没有新的连续记录奖励')}
  catch(e){error.value=e.message;toast.error(e.message)}
  finally{streakBusy.value=false}
}

// 金币非股票，刻意避开红/绿涨跌歧义：正值用绿色正向色、消耗用灰色
const SOURCE_META = {
  onboarding_bonus: { label: '启动资金', tone: 'in' },
  event_confirm: { label: '记录入账', tone: 'in' },
  journal_streak: { label: '连续写日记', tone: 'in' },
  challenge_reward: { label: '挑战奖励', tone: 'in' },
  achievement: { label: '成就奖励', tone: 'in' },
  challenge_deposit: { label: '挑战押金', tone: 'out' },
  challenge_refund: { label: '押金退回', tone: 'in' },
  challenge_forfeit: { label: '押金没收', tone: 'out' },
  shop_redeem: { label: '商店兑换', tone: 'out' },
}

function sourceLabel(s) {
  return SOURCE_META[s]?.label || s
}
function sourceTone(s) {
  return SOURCE_META[s]?.tone || 'in'
}
function signOf(d) {
  return d > 0 ? `+${d}` : `${d}`
}

// ---- 挑战 ----
const daily = ref([])
const weekly = ref([])
const notes = ref({}) // { [challengeId]: 一句话自述 }
const settled = ref({}) // { [challengeId]: 结算结果 }
const highlightId = ref(null)

const OUTCOME_META = {
  done: { label: '达成', cls: 'ok' },
  partial: { label: '部分达成', cls: 'warn' },
  excused: { label: '意外豁免', cls: 'info' },
  retreated: { label: '未完成', cls: 'bad' },
}
const STATUS_LABEL = {
  candidate: '待接受',
  accepted: '进行中',
  settled: '已结算',
  expired: '已过期',
  abandoned: '已放弃',
}

function outcomeLabel(o) {
  return OUTCOME_META[o]?.label || o || ''
}
function outcomeCls(o) {
  return OUTCOME_META[o]?.cls || ''
}
function isActive(c) {
  return c.status === 'candidate' || c.status === 'accepted'
}
function canSettle(c) {
  const confidence = c.judgment_confidence
  return typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0.8 && confidence <= 1
}
function isFinished(c) {
  return !isActive(c)
}
function difficultyStars(n) {
  return '★'.repeat(Math.max(0, Math.min(5, n || 0)))
}
function fmtTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ---- 商店 ----
const shopItems = ref([])
const redemptions = ref([])
const newItem = ref({ name: '', price_yuan: '' })
const pricingBusy = ref(false)

const pendingRedemptions = computed(() => redemptions.value.filter((r) => r.status === 'pending'))
const fulfilledRedemptions = computed(() => redemptions.value.filter((r) => r.status === 'fulfilled'))

// ---- 豁免券（v1.10 M2，放在商店分段内） ----
const exemptions = ref([])
const exemptionPresets = ref([])
const excForm = ref({ target_date: todayStr(), period: 'afternoon', start_time: '14:00', end_time: '16:00', reason: '' })
const excResult = ref(null)
const EXC_STATUS_LABEL = { active: '未使用', used: '已使用', expired: '已过期' }

function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
const excCustom = computed(() => excForm.value.period === 'custom')
// 跨零点提示：结束早于或等于开始 → 区间延到次日
const excCrossMidnight = computed(
  () => excCustom.value && excForm.value.start_time && excForm.value.end_time
    && excForm.value.end_time <= excForm.value.start_time
)

// ---- 停滞问询 ----
const stagnation = ref([])
const stagnationBusy = ref(false)
const stagnationResult = ref(null)

// ============================================================
// 「AI 正在分析…」+ 防重复 + 可取消（复用 v1.7 C 的做法）
// ============================================================
// v1.9 F3：正在切换中的档位下标（仅用于给被点的那颗按钮显示「切换中…」）
const variantTarget = ref(null)
const busyId = ref(null)
const slowHintId = ref(null)
const SLOW_THRESHOLD_MS = 60000 // 判定常见 20~60s，超过 60s 给一句提示
let slowTimer = null
let actionToken = 0

function isBusy(id) {
  return busyId.value === id
}
const anyBusy = computed(() => busyId.value !== null)

function startBusy(id) {
  busyId.value = id
  slowHintId.value = null
  clearTimeout(slowTimer)
  slowTimer = setTimeout(() => {
    if (busyId.value === id) slowHintId.value = id
  }, SLOW_THRESHOLD_MS)
  actionToken += 1
  return actionToken
}
function endBusy() {
  busyId.value = null
  slowHintId.value = null
  clearTimeout(slowTimer)
  slowTimer = null
}
function cancelAction() {
  // 取消 = 放弃本次等待的展示：本地立即恢复可操作，服务端结果不再回填
  actionToken += 1
  endBusy()
}
function stillCurrent(token) {
  return token === actionToken
}

onBeforeUnmount(() => clearTimeout(slowTimer))

async function runAction(id, fn) {
  if (isBusy(id) || anyBusy.value) return // 防重复点击
  error.value = ''
  const token = startBusy(id)
  try {
    const res = await fn()
    if (!stillCurrent(token)) return // 已被取消
    return res
  } catch (e) {
    if (stillCurrent(token)) {
      error.value = e.message
      toast.error(e.message) // v1.9 F2：失败既留顶部横幅，也浮一次提示
    }
  } finally {
    if (stillCurrent(token)) endBusy()
  }
}

// ============================================================
// 数据加载
// ============================================================

async function loadCoins() {
  try {
    const data = await api.getCoins()
    coins.value = data.balance
    ledger.value = data.ledger || []
  } catch (e) {
    error.value = e.message
    toast.error(e.message) // F2-2：横幅 + 浮一次提示
  }
}

async function loadChallenges() {
  try {
    const data = await api.getCurrentChallenges()
    daily.value = data.daily || []
    weekly.value = data.weekly || []
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function loadShop() {
  try {
    const data = await api.listShopItems()
    shopItems.value = data.items || []
    coins.value = data.balance ?? coins.value
    const rd = await api.listRedemptions()
    redemptions.value = rd.redemptions || []
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function loadExemptions() {
  try {
    const data = await api.listExemptions()
    exemptions.value = data.items || []
    if ((data.presets || []).length) exemptionPresets.value = data.presets
    coins.value = data.balance ?? coins.value
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function loadStagnation() {
  try {
    const data = await api.getStagnation()
    stagnation.value = data.items || []
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await loadCoins()
    await Promise.all([loadChallenges(), loadShop(), loadExemptions(), loadStagnation()])
  } finally {
    loading.value = false
  }
}

// ============================================================
// 挑战操作
// ============================================================

async function generate(scope, force) {
  const label = scope === 'weekly' ? '周挑战' : '日挑战'
  // v1.9 F2 修正：force 补位为 0 时后端会把**已有的**挑战原样返回，
  // 只看 res.challenges.length 会把"没生成"误报成"已生成 N 条"。
  // 因此先记下调用前已有的 id，用差集判断真正新增了哪几条。
  const before = new Set([...daily.value, ...weekly.value].map((c) => c.id))
  const res = await runAction(`gen-${scope}`, async () => {
    const data = await api.generateChallenges(scope, force)
    await loadChallenges()
    await loadCoins()
    return data
  })
  if (res) {
    const n = (res.challenges || []).filter((c) => !before.has(c.id)).length
    // v1.9 F2：generate 原先"按钮禁用但文案不变 + 成功静默"，是本轮第一个修复点
    if (n > 0) toast.success(`已生成 ${n} 条新${label}`)
    else toast.info(`${label}已是最新，没有空缺位置需要补充`)
  }
}

// ============================================================
// v1.9 F3：一卡多档
// ============================================================

/** 当前选中的档位下标：难度与顶层 difficulty 一致的那一档（档位难度唯一，可安全比对） */
function activeVariantIndex(c) {
  const vs = c.variants || []
  if (!vs.length) return -1
  return vs.findIndex((v) => v.difficulty === c.difficulty)
}

/** 只读文案：已接受 / 已结算的卡片显示「档位：5 项」 */
function activeVariantLabel(c) {
  const i = activeVariantIndex(c)
  return i >= 0 ? (c.variants[i].label || '') : ''
}

async function pickVariant(c, index) {
  variantTarget.value = index
  const label = c.variants[index]?.label || ''
  const res = await runAction(`variant-${c.id}`, async () => {
    const data = await api.switchChallengeVariant(c.id, index)
    await loadChallenges()
    return data
  })
  variantTarget.value = null
  if (res) toast.success(`已切换到「${label}」档`)
}

async function accept(c) {
  const res = await runAction(`accept-${c.id}`, async () => {
    const data = await api.acceptChallenge(c.id,c.updated_at)
    await loadChallenges()
    await loadCoins()
    return data
  })
  if (res) toast.success(`已接受「${c.title}」，扣除押金 ${c.deposit} 币`)
}

async function complete(c) {
  const note = (notes.value[c.id] || '').trim()
  if (!note) {
    error.value = '请先用一句话说明完成情况'
    return
  }
  const res = await runAction(`complete-${c.id}`, async () =>
    api.completeChallenge(c.id, note)
  )
  if (res) {
    settled.value = { ...settled.value, [c.id]: res }
    await loadChallenges()
    toast.info('AI 判定完成，请在卡片下方确认结算')
  }
}

async function settle(c) {
  const res = await runAction(`settle-${c.id}`, async () => api.settleChallenge(c.id,c.updated_at))
  if (res) {
    settled.value = { ...settled.value, [c.id]: { ...(settled.value[c.id] || {}), ...res } }
    await loadChallenges()
    await loadCoins()
    const d = res.coins_delta || 0
    toast.success(d ? `结算完成，金币 ${d > 0 ? '+' : ''}${d}` : '结算完成')
  }
}

async function abandon(c) {
  const note = (notes.value[c.id] || '').trim()
  const msg = note
    ? '放弃挑战并提交此说明（AI 会判断是否属于突发意外）？'
    : '不带说明直接放弃？押金将不退回，并按难度扣除相应属性点。'
  if (!confirm(msg)) return
  const res = await runAction(`abandon-${c.id}`, async () => api.abandonChallenge(c.id, note))
  if (res) {
    settled.value = { ...settled.value, [c.id]: res }
    await loadChallenges()
    await loadCoins()
    toast.info(res.outcome === 'excused' ? '已放弃：属意外情况，押金已退回' : '已放弃：押金不退')
  }
}

// ============================================================
// 商店操作
// ============================================================

async function addItem() {
  const name = newItem.value.name.trim()
  if (!name) {
    error.value = '请填写物品名称'
    return
  }
  const price = newItem.value.price_yuan === '' ? null : Number(newItem.value.price_yuan)
  pricingBusy.value = true
  error.value = ''
  try {
    const created = await api.createShopItem({ name, price_yuan: price })
    newItem.value = { name: '', price_yuan: '' }
    await loadShop()
    toast.success(`已添加「${created.name}」，AI 定价 ${created.coin_price} 币`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    pricingBusy.value = false
  }
}

async function reprice(it) {
  const res = await runAction(`reprice-${it.id}`, async () => {
    const data = await api.repriceShopItem(it.id)
    await loadShop()
    return data
  })
  if (res) toast.success(`已重新定价：${it.coin_price} → ${res.coin_price} 币`)
}

async function redeem(it,confirmed=false,source=null) {
  if (redemption.busy.value || anyBusy.value) return
  const recovering = redemption.pending.value?.state === 'unknown'
  if (!recovering && coins.value < it.coin_price) {
    error.value = `金币不足（需 ${it.coin_price} 币，当前 ${coins.value} 币）`
    return
  }
  const rest = coins.value - it.coin_price
  if (!recovering && !confirmed){source?.currentTarget?.focus();redeemChoice.value=it;return}
  const res = await runAction(`redeem-${it.id}`, () => redemption.send(it))
  if (res) {
    redeemChoice.value=null
    toast.success('兑换已成功，奖励券已保存。')
    segment.value = 'shop'
    // A failed read cannot turn a committed purchase back into an unknown operation.
    await Promise.allSettled([loadShop(), loadCoins()])
  }
}

async function buyExemption() {
  if(exemptionPurchase.busy.value || anyBusy.value)return
  const f = excForm.value
  if (!f.target_date && exemptionPurchase.pending.value?.state !== 'unknown') {
    error.value = '请选择豁免券的日期'
    return
  }
  if (f.period === 'custom' && (!f.start_time || !f.end_time)) {
    error.value = '自定义时段需要填写开始与结束时间'
    return
  }
  excResult.value = null
  const res = await runAction('exc-buy', async () => {
      const data = await exemptionPurchase.send({
      target_date: f.target_date,
      period: f.period,
      start_time: f.start_time,
      end_time: f.end_time,
      reason: f.reason,
    })
    await loadExemptions()
    await loadCoins()
    return data
  })
  if (res) {
    excResult.value = res
    excForm.value = { ...excForm.value, reason: '' }
    const cost = res.exemption?.coin_cost ?? 0
    toast.success(`已购买豁免券（${res.exemption?.label || ''}，-${cost} 币）`)
  }
}

async function fulfill(r) {
  const res = await runAction(`fulfill-${r.id}`, async () => {
    await api.fulfillRedemption(r.id, '')
    await loadShop()
    return true
  })
  if (res) toast.success(`「${r.item_name}」已标记为兑现`)
}

async function changePrice(it) {
  const input = prompt(`修改「${it.name}」的金币价（当前 ${it.coin_price}）`, String(it.coin_price))
  if (input === null) return
  const val = Number(input)
  if (!Number.isFinite(val) || val <= 0) {
    error.value = '金币价必须为正整数'
    return
  }
  const res = await runAction(`price-${it.id}`, async () => {
    await api.updateShopItem(it.id, { coin_price: Math.round(val) })
    await loadShop()
    return true
  })
  if (res) toast.success(`已把「${it.name}」的价格改为 ${Math.round(val)} 币`)
}

// ============================================================
// 停滞问询
// ============================================================

async function answerStagnation(item, stopped) {
  stagnationBusy.value = true
  error.value = ''
  try {
    const res = await api.answerStagnation(item.name, stopped, '', item.version)
    stagnationResult.value = res
    await loadStagnation()
    await loadChallenges()
    if (res.challenge) {
      // 跳转到挑战区并高亮新生成的补课挑战
      segment.value = 'challenge'
      highlightId.value = res.challenge.id
      setTimeout(() => (highlightId.value = null), 6000)
    }
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    stagnationBusy.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <header class="page-intro"><h1>挑战与奖励</h1></header>
  <div>
    <p v-if="exemptionPurchase.warning.value" class="error">{{ exemptionPurchase.warning.value }}</p>
    <p v-if="exemptionPurchase.pending.value?.state === 'unknown'" class="card">上次豁免购买结果待确认：{{ exemptionPurchase.pending.value.body.target_date }} · {{ exemptionPurchase.pending.value.body.period }}。<button class="btn" :disabled="anyBusy || exemptionPurchase.busy.value" @click="buyExemption">恢复购买结果</button></p>
    <p v-if="redemption.warning.value" class="error" role="alert">{{ redemption.warning.value }}</p>
    <p v-if="redemption.pending.value?.state === 'unknown'" class="card">上次兑换结果待确认：{{ redemption.pending.value.name }}。恢复会沿用同一操作标识。
      <button class="btn" :disabled="anyBusy || redemption.busy.value" @click="redeem({id:redemption.pending.value.item_id})">恢复兑换结果</button>
    </p>
    <!-- ============ 顶部金币条（两区常驻） ============ -->
    <div class="card coin-bar">
      <div class="coin-bar-top">
        <div class="coin-amount">
          <span class="coin-icon">🪙</span>
          <b>{{ coins }}</b>
          <span class="muted">金币</span>
        </div>
        <div class="action-group">
          <button class="btn small" @click="showLedger = !showLedger">
            {{ showLedger ? '收起流水' : '查看流水' }}
          </button>
          <button class="btn small" :disabled="loading" @click="loadAll">刷新</button>
          <button class="btn small" :disabled="streakBusy" @click="claimStreak">领取连续记录奖励</button>
        </div>
      </div>
      <p class="muted coin-hint">
        金币来自日常记录、连续写日记与挑战奖励；可在商店兑换现实中的小奖励。金币与属性点相互独立。
      </p>

      <div v-if="showLedger" class="ledger">
        <p v-if="ledger.length === 0" class="muted">暂无金币流水。</p>
        <div v-for="r in ledger" :key="r.id" class="ledger-row">
          <span class="ledger-delta" :class="sourceTone(r.source)">{{ signOf(r.delta) }}</span>
          <span class="ledger-reason">
            {{ r.reason || sourceLabel(r.source) }}
            <span class="muted ledger-tag">{{ sourceLabel(r.source) }}</span>
          </span>
          <span class="muted ledger-time">{{ fmtTime(r.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- ============ 停滞提示卡（中性、不指责） ============ -->
    <div v-if="stagnation.length" class="card stagnation-card">
      <div v-for="s in stagnation" :key="s.name" class="stagnation-row">
        <div>
          <b>{{ s.name }}已经 {{ s.days }} 天没有相关记录了</b>
          <span class="muted"> — 是真的停了，还是忘了记？</span>
        </div>
        <div class="action-group" style="margin-top: 8px">
          <button class="btn small" :disabled="stagnationBusy" @click="answerStagnation(s, false)">
            在学，只是没记
          </button>
          <button class="btn small danger" :disabled="stagnationBusy" @click="answerStagnation(s, true)">
            确实停了
          </button>
        </div>
      </div>
    </div>

    <!-- 停滞回答结果 -->
    <div v-if="stagnationResult" class="card" :class="stagnationResult.stopped ? 'stagnation-bad' : 'stagnation-ok'">
      <div v-if="stagnationResult.stopped">
        <b>已按你的确认记录：{{ stagnationResult.name }} {{ stagnationResult.deducted }}</b>
        <p class="muted" style="margin: 6px 0 0">
          这是你亲口确认"确实停了"才会发生的调整，系统不会因为你没记录而自动扣分。
        </p>
        <p v-if="stagnationResult.challenge" class="muted" style="margin: 6px 0 0">
          已为你生成一条补课挑战：<b>{{ stagnationResult.challenge.title }}</b>
        </p>
      </div>
      <div v-else>
        <b>好的，那就不扣分。</b>
        <p class="muted" style="margin: 6px 0 0">
          在学只是没记，说明这条线一直在走。随时可以去「记录事件」补记一笔，让数据跟上你。
        </p>
      </div>
      <button class="btn small" style="margin-top: 8px" @click="stagnationResult = null">知道了</button>
    </div>

    <!-- ============ 分段控件 ============ -->
    <div class="segmented">
      <button
        class="seg-btn"
        :class="{ active: segment === 'challenge' }"
        @click="segment = 'challenge'"
      >
        挑战
      </button>
      <button class="seg-btn" :class="{ active: segment === 'shop' }" @click="segment = 'shop'">
        商店
      </button>
    </div>

    <p v-if="error" class="conn-banner conn-error" style="margin-bottom: 12px">{{ error }}</p>

    <!-- ============================================================ -->
    <!-- 挑战区                                                        -->
    <!-- ============================================================ -->
    <template v-if="segment === 'challenge'">
      <div v-for="group in [{ scope: 'daily', label: '日挑战', list: daily }, { scope: 'weekly', label: '周挑战', list: weekly }]" :key="group.scope">
        <div class="card">
          <div class="action-group" style="align-items: center; justify-content: space-between">
            <h3 style="margin: 0">{{ group.label }}</h3>
            <button class="btn small" :disabled="anyBusy" @click="generate(group.scope, true)">
              <template v-if="isBusy(`gen-${group.scope}`)">
                <span class="spinner"></span>AI 正在生成…
              </template>
              <template v-else>{{ group.list.length ? '再来一批' : '生成挑战' }}</template>
            </button>
          </div>
          <p v-if="group.list.length === 0" class="muted" style="margin-top: 8px">
            本期还没有{{ group.label }}。点「生成挑战」让 AI 按你的短板定制。
          </p>

          <div
            v-for="c in group.list"
            :key="c.id"
            class="judgment-item challenge-card"
            :class="{ finished: isFinished(c), highlight: highlightId === c.id }"
          >
            <div class="action-group" style="align-items: center; margin-bottom: 6px">
              <b>{{ c.title }}</b>
              <span class="tag">{{ STATUS_LABEL[c.status] || c.status }}</span>
              <span class="difficulty" :title="`难度 ${c.difficulty}/5`">{{ difficultyStars(c.difficulty) }}</span>
              <span v-if="isFinished(c) && c.outcome" class="outcome-badge" :class="outcomeCls(c.outcome)">
                {{ outcomeLabel(c.outcome) }}
              </span>
            </div>

            <div class="muted">{{ c.description }}</div>

            <!-- C4-2：已接受 / 已结算的挑战只读显示档位（不可点，档位已锁定） -->
            <div
              v-if="c.status !== 'candidate' && (c.variants || []).length > 1"
              class="muted variant-note"
            >
              档位：{{ activeVariantLabel(c) }}
            </div>

            <!-- 候选期：金币提前显示、加点不预览 -->
            <template v-if="c.status === 'candidate'">
              <!-- C4-1：候选期的档位切换按钮组（只 1 档或旧挑战不渲染，行为与改造前一致） -->
              <div v-if="(c.variants || []).length > 1" class="variant-row">
                <button
                  v-for="(v, i) in c.variants"
                  :key="`${c.id}-v${i}`"
                  class="seg-btn"
                  :class="{ active: activeVariantIndex(c) === i }"
                  :disabled="anyBusy"
                  :title="v.description"
                  @click="pickVariant(c, i)"
                >
                  <template v-if="isBusy(`variant-${c.id}`) && variantTarget === i">
                    <span class="spinner"></span>切换中…
                  </template>
                  <template v-else>{{ v.label }}</template>
                </button>
              </div>
              <div class="action-group challenge-meta">
                <span class="reward">完成可得 +{{ c.coin_reward }} 币</span>
                <span class="muted">押金 {{ c.deposit }} 币</span>
              </div>
              <div v-if="c.ai_reason" class="ai-reason">
                <b>为什么给你这个：</b>{{ c.ai_reason }}
              </div>
              <div class="action-group" style="margin-top: 8px">
                <button class="btn small primary" :disabled="anyBusy" @click="accept(c)">
                  <template v-if="isBusy(`accept-${c.id}`)">接受中…</template>
                  <template v-else>接受挑战</template>
                </button>
                <span class="muted" style="align-self: center; font-size: 13px">
                  接受即承诺，会先扣 {{ c.deposit }} 币押金；完成后退回。
                </span>
              </div>
            </template>

            <!-- 已接受 -->
            <div v-if="c.status === 'accepted'">
              <div class="muted" style="margin-top: 6px">
                截止 {{ fmtTime(c.expires_at) }} ·
                <span class="reward">完成可得 +{{ c.coin_reward }} 币</span> · 押金 {{ c.deposit }} 币已扣
              </div>
              <div v-if="c.ai_reason" class="ai-reason"><b>为什么给你这个：</b>{{ c.ai_reason }}</div>

              <template v-if="!c.judgment_id">
                <textarea
                  v-model="notes[c.id]"
                  class="self-report"
                  rows="2"
                  placeholder="用一句话说明你完成得怎么样（AI 会据此判定是否达成）"
                  :disabled="isBusy(`complete-${c.id}`) || isBusy(`abandon-${c.id}`)"
                ></textarea>
                <div class="action-group">
                  <button
                    class="btn small primary"
                    :disabled="anyBusy"
                    @click="complete(c)"
                  >
                    <template v-if="isBusy(`complete-${c.id}`)">
                      <span class="spinner"></span>AI 正在分析…
                    </template>
                    <template v-else>我完成了</template>
                  </button>
                  <button class="btn small" :disabled="anyBusy" @click="abandon(c)">放弃</button>
                  <button
                    v-if="isBusy(`complete-${c.id}`) || isBusy(`abandon-${c.id}`)"
                    class="btn small"
                    @click="cancelAction"
                  >
                    取消
                  </button>
                </div>
                <p v-if="slowHintId" class="muted slow-hint">
                  ⏳ AI 响应较慢，可继续等待或点「取消」。
                </p>
              </template>

              <!-- 已判定待结算，可补充自述并原 id 重判 -->
              <template v-else>
                <textarea v-model="notes[c.id]" rows="2" placeholder="补充真实细节后重新判定" :disabled="anyBusy"></textarea>
                <button class="btn small" :disabled="anyBusy || !notes[c.id]?.trim()" @click="complete(c)">补充自述并重判</button>
                <div class="ai-reason">
                  <b>AI 判定（{{ outcomeLabel(c.outcome) }}）：</b>{{ c.outcome_note }}
                </div>
                <div v-if="c.judgment_changes?.length" class="muted" style="margin-top: 6px">
                  加点建议：
                  <span v-for="ch in c.judgment_changes" :key="ch.name" class="chip">
                    {{ ch.name }} {{ ch.delta > 0 ? '+' : '' }}{{ ch.delta }}
                  </span>
                </div>
                <div class="action-group" style="margin-top: 8px">
                  <button class="btn small primary" :disabled="anyBusy || !canSettle(c)" @click="settle(c)">
                    <template v-if="isBusy(`settle-${c.id}`)">
                      <span class="spinner"></span>入账中…
                    </template>
                    <template v-else>{{ canSettle(c) ? '确认结算' : '需补充信息' }}</template>
                  </button>
                  <button v-if="isBusy(`settle-${c.id}`)" class="btn small" @click="cancelAction">取消</button>
                </div>
              </template>
            </div>

            <!-- 已结算 / 已过期 / 已放弃：置灰 -->
            <div v-if="isFinished(c)">
              <div v-if="c.outcome_note" class="muted" style="margin-top: 6px">{{ c.outcome_note }}</div>
              <div v-if="settled[c.id]?.coins_delta !== undefined" class="muted" style="margin-top: 4px">
                金币变动：{{ signOf(settled[c.id].coins_delta) }}
              </div>
              <div v-if="c.judgment_final_changes?.length" class="muted" style="margin-top: 4px">
                实际入账：
                <span v-for="ch in c.judgment_final_changes" :key="ch.name" class="chip">
                  {{ ch.name }} {{ ch.delta > 0 ? '+' : '' }}{{ ch.delta }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============================================================ -->
    <!-- 商店区                                                        -->
    <!-- ============================================================ -->
    <template v-else>
      <RewardShop/>

      <!-- 豁免券（v1.10 M2）：时段券，绝不做万能券 -->
      <div class="card">
        <h3>豁免券 <span class="tag">时段券 · 过期作废</span></h3>
        <p class="muted" style="font-size: 13px">
          花金币买「一段时间内，计划内的事没完成也不扣分」的权利。<b>必须指定日期 + 时段</b>，
          过期作废——不是万能券。AI 会看你的理由判动机：正当紧急 → 正常价；明显逃避 → 提价或额外扣点。
        </p>

        <div class="form-grid">
        <div class="field">
            <label for="challengeview-field-3">日期</label>
            <input id="challengeview-field-3" v-model="excForm.target_date" type="date" :disabled="anyBusy" />
          </div>
          <div class="field">
            <label>时段</label>
            <div class="action-group" style="flex-wrap: wrap; gap: 6px">
              <button
                v-for="p in exemptionPresets"
                :key="p.key"
                class="btn small"
                :class="{ primary: excForm.period === p.key }"
                :disabled="anyBusy"
                @click="excForm.period = p.key"
              >
                {{ p.label }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="excCustom" class="action-group">
          <div class="field">
            <label for="challengeview-field-4">开始</label>
            <input id="challengeview-field-4" v-model="excForm.start_time" type="time" :disabled="anyBusy" />
          </div>
          <div class="field">
            <label for="challengeview-field-5">结束</label>
            <input id="challengeview-field-5" v-model="excForm.end_time" type="time" :disabled="anyBusy" />
          </div>
          <div v-if="excCrossMidnight" class="muted" style="align-self: flex-end; padding-bottom: 8px; font-size: 13px">
            结束早于开始 → 视为<b>跨零点</b>，区间延到次日
          </div>
        </div>

        <div class="field">
          <label for="challengeview-field-6">理由（会直接影响 AI 的定价与动机判断）</label>
          <input id="challengeview-field-6"
            v-model="excForm.reason"
            placeholder="例如：明天下午要陪家人去医院复查"
            :disabled="anyBusy"
          />
        </div>

        <button class="btn primary" :disabled="anyBusy" @click="buyExemption">
          <template v-if="isBusy('exc-buy')"><span class="spinner"></span>AI 正在评估动机与定价…</template>
          <template v-else>购买豁免券</template>
        </button>

        <div v-if="excResult" style="margin-top: 10px">
          <div class="worth-note" :class="{ warn: excResult.exemption?.motive === 'evasive' }">
            <b>{{ excResult.exemption?.motive === 'evasive' ? 'AI 判为「明显逃避」：' : 'AI 判为「正当紧急」：' }}</b>
            {{ excResult.exemption?.motive_note }}
          </div>
          <div v-if="excResult.penalty" class="muted" style="font-size: 13px; margin-top: 4px; color: var(--warn)">
            额外扣点已生效：{{ excResult.penalty.name }} {{ excResult.penalty.delta }}（购买时立刻扣）
          </div>
        </div>

        <div v-if="exemptions.length" style="margin-top: 12px">
          <div class="muted voucher-title">我的券（{{ exemptions.length }}）</div>
          <div
            v-for="e in exemptions"
            :key="e.id"
            class="voucher"
            :class="{ done: e.status !== 'active' }"
          >
            <b>{{ e.label }}</b>
            <span class="tag">{{ EXC_STATUS_LABEL[e.status] || e.status }}</span>
            <span v-if="e.cross_midnight" class="tag">跨零点</span>
            <span class="muted">消耗 {{ e.coin_cost }} 币<template v-if="e.extra_penalty > 0">，额外扣 {{ e.penalty_attribute }} {{ e.extra_penalty }}</template></span>
            <div v-if="e.motive_note" class="muted" style="font-size: 13px; margin-top: 2px">{{ e.motive_note }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>奖励券</h3>
        <div class="voucher-cols">
          <div>
            <div class="muted voucher-title">待兑现（{{ pendingRedemptions.length }}）</div>
            <p v-if="pendingRedemptions.length === 0" class="muted">暂无。</p>
            <div v-for="r in pendingRedemptions" :key="r.id" class="voucher">
              <b>{{ r.item_name }}</b>
              <span class="muted">消耗 {{ r.coin_spent }} 币 · {{ fmtTime(r.redeemed_at) }}</span>
              <button class="btn small primary" :disabled="anyBusy" @click="fulfill(r)">
                <template v-if="isBusy(`fulfill-${r.id}`)">处理中…</template>
                <template v-else>已兑现</template>
              </button>
            </div>
          </div>
          <div>
            <div class="muted voucher-title">已兑现（{{ fulfilledRedemptions.length }}）</div>
            <p v-if="fulfilledRedemptions.length === 0" class="muted">暂无。</p>
            <div v-for="r in fulfilledRedemptions" :key="r.id" class="voucher done">
              <b>{{ r.item_name }}</b>
              <span class="muted">{{ fmtTime(r.fulfilled_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
    <ConfirmDialog :open="!!redeemChoice" title="确认兑换奖励" :busy="redemption.busy.value || anyBusy" @cancel="redeemChoice=null" @confirm="redeem(redeemChoice,true)"><template v-if="redeemChoice"><p>{{ redeemChoice.name }}</p><p>花费 {{ redeemChoice.coin_price }} 币 · 兑换后余额 {{ coins-redeemChoice.coin_price }} 币</p><p class="muted">兑换成功会生成奖励券。之后标记兑现不会再次扣币。</p><p v-if="error" class="error" role="alert">{{ error }}</p></template></ConfirmDialog>
  </div>
</template>
