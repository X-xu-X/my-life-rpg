<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { api } from '../api'
import { storageKey } from '../session'
import { toast } from '../composables/useToast'

const emit = defineEmits(['created'])

// phase: init(未开始) / asking(问答中) / done(首次面板已生成) / completed(已完成，可补充)
const phase = ref('init')
const messages = ref([]) // {role:'ai'|'user', text}
const currentQuestions = ref([])
const answerInputs = ref({})
const panel = ref(null)
const summary = ref('')
// v1.9 F1：启动资金（老档案快照里没有该键 → 为 null，模板据此不渲染该行）
const initialCoins = ref(null)
const initialCoinsReason = ref('')
const confidence = ref(0)
const busy = ref(false)
const error = ref('')
const chatEl = ref(null)

// 补充长期信息相关
const supplementText = ref('')
const pendingAdjustment = ref(null)
const supplementNote = ref('')

// ============ 草稿缓存：问卷作答写一半不丢 ============
const CACHE_KEY = storageKey('game_of_life_onboarding_draft')

onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
    if (saved && saved.answerInputs) {
      answerInputs.value = saved.answerInputs
    }
  } catch (e) { /* 忽略损坏缓存 */ }
})

watch(answerInputs, () => {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ answerInputs: answerInputs.value }))
  } catch (e) { /* 忽略 */ }
}, { deep: true })

async function scrollToBottom() {
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}

async function loadStatus() {
  try {
    const st = await api.getOnboardingStatus()
    if (st.onboarding_completed) {
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = '你已完成首次属性建档，可随时补充长期信息。'
      initialCoins.value = st.initial_coins ?? null
      initialCoinsReason.value = st.initial_coins_reason || ''
    } else if (st.in_progress) {
      await resume()
    }
    // 否则保持 init，等待用户点「开始」
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function start() {
  busy.value = true
  error.value = ''
  try {
    const data = await api.startOnboarding()
    if (data.completed) {
      // 已完成（理论上不会走到这里，兜底）
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = data.message || ''
      return
    }
    if (data.done && data.panel) {
      panel.value = data.panel
      summary.value = data.summary || ''
      initialCoins.value = data.initial_coins ?? null
      initialCoinsReason.value = data.initial_coins_reason || ''
      phase.value = 'done'
    } else {
      phase.value = 'asking'
      currentQuestions.value = data.questions || []
      confidence.value = data.confidence || 0
      messages.value.push({ role: 'ai', text: data.hint || '你好，我们来聊聊你的情况吧。' })
      currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    }
    await scrollToBottom()
  } catch (e) {
    toast.error(e.message)
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function resume() {
  busy.value = true
  try {
    const data = await api.startOnboarding()
    if (data.completed) {
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = data.message || ''
      return
    }
    if (data.done && data.panel) {
      panel.value = data.panel
      summary.value = data.summary || ''
      initialCoins.value = data.initial_coins ?? null
      initialCoinsReason.value = data.initial_coins_reason || ''
      phase.value = 'done'
      return
    }
    phase.value = 'asking'
    currentQuestions.value = data.questions || []
    confidence.value = data.confidence || 0
    messages.value.push({ role: 'ai', text: data.hint || '我们继续刚才的问答。' })
    currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function submit() {
  const answers = currentQuestions.value
    .map((q) => ({ question: q, answer: answerInputs.value[q] || '' }))
    .filter((a) => a.answer.trim() !== '')
  if (answers.length === 0) {
    error.value = '请先回答本轮问题。'
    return
  }
  answers.forEach((a) => messages.value.push({ role: 'user', text: a.answer }))
  answerInputs.value = {}
  currentQuestions.value = []

  busy.value = true
  error.value = ''
  try {
    const data = await api.submitAnswers(answers)
    if (data.done && data.panel) {
      // 把握度达标，自动生成面板
      panel.value = data.panel
      summary.value = data.summary || ''
      initialCoins.value = data.initial_coins ?? null
      initialCoinsReason.value = data.initial_coins_reason || ''
      confidence.value = data.confidence || 100
      phase.value = 'done'
      messages.value.push({ role: 'ai', text: `信息够了（把握度 ${data.confidence}%），已为你生成初始属性面板。` })
      toast.success('初始属性面板已生成')
      emit('created')
    } else {
      phase.value = 'asking'
      currentQuestions.value = data.questions || []
      confidence.value = data.confidence || 0
      currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    }
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function submitSupplement() {
  if (!supplementText.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.supplementProfile(supplementText.value.trim())
    pendingAdjustment.value = data
    supplementNote.value = data.explanation || ''
    supplementText.value = ''
    toast.info('AI 已给出调整建议，请确认或忽略')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function confirmSupplement() {
  busy.value = true
  error.value = ''
  try {
    const data = await api.confirmSupplement()
    pendingAdjustment.value = null
    supplementNote.value = data.message || '调整已生效。'
    const attr = await api.getAttributes()
    panel.value = attr.attributes || []
    toast.success('调整已生效')
    emit('created')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

function ignoreSupplement() {
  pendingAdjustment.value = null
  supplementNote.value = '已忽略本次调整建议。'
}


// ============================================================
// v1.10 M1：成就墙
// ============================================================
const achievements = ref([])
const achSummary = ref({ unlocked: 0, total: 0 })

async function loadAchievements() {
  try {
    const data = await api.getAchievements()
    achievements.value = data.items || []
    achSummary.value = { unlocked: data.unlocked_count || 0, total: data.total_count || 0 }
  } catch (e) {
    // 成就墙加载失败不影响角色档案主流程
    console.warn('成就墙加载失败', e)
  }
}

function fmtDate(t) {
  if (!t) return ''
  return new Date(t).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

onMounted(() => {
  loadAchievements()
})
onMounted(loadStatus)
</script>

<template>
  <div class="card">
    <h1>角色档案</h1>
    <p class="muted">
      首次使用时 AI 会持续提问，直到对你有足够把握（≥95%）才自动生成初始属性面板；之后只能补充长期信息。
    </p>

    <!-- 未开始 -->
    <button v-if="phase === 'init'" class="btn primary" :disabled="busy" @click="start">
      <template v-if="busy"><span class="spinner"></span>AI 正在准备问题…</template>
      <template v-else>开始建立角色档案</template>
    </button>

    <!-- 对话流 -->
    <div v-if="phase === 'asking'" class="chat" ref="chatEl">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.text }}</div>
      </div>
    </div>

    <!-- 把握度进度 -->
    <div v-if="phase === 'asking'" style="margin: 8px 0">
      <div class="muted" style="margin-bottom: 4px">AI 对你画像的把握度：{{ confidence }}%</div>
      <div class="track"><div class="fill" :style="{ width: confidence + '%' }"></div></div>
    </div>

    <!-- 作答区 -->
    <div v-if="phase === 'asking' && currentQuestions.length" class="card" style="margin-top: 12px">
      <div v-for="q in currentQuestions" :key="q" class="field">
        <label :for="'onboarding-answer-'+currentQuestions.indexOf(q)">{{ q }}</label>
        <input :id="'onboarding-answer-'+currentQuestions.indexOf(q)" v-model="answerInputs[q]" placeholder="你的回答…" @keyup.enter="submit" />
      </div>
      <button class="btn primary" :disabled="busy" @click="submit">
        <template v-if="busy"><span class="spinner"></span>AI 正在评估…</template>
        <template v-else>提交</template>
      </button>
    </div>

    <!-- 属性面板展示（首次生成 / 已完成） -->
    <div v-if="phase === 'done' || phase === 'completed'" class="card" style="margin-top: 12px">
      <h3>当前属性面板</h3>
      <div v-for="a in panel" :key="a.name" class="attr-bar">
        <div class="head">
          <span><b>{{ a.name }}</b></span>
          <span>{{ a.value }} / 100</span>
        </div>
        <div class="track"><div class="fill" :style="{ width: a.value + '%' }"></div></div>
        <div class="muted">{{ a.reason || a.description }}</div>
      </div>
      <!-- v1.9 F1：启动资金（老档案无 initial_coins 键时不显示） -->
      <div v-if="initialCoins" class="coins-grant">
        <b>🎁 启动资金 +{{ initialCoins }} 币</b>
        <div v-if="initialCoinsReason" class="muted">为什么给你这个数：{{ initialCoinsReason }}</div>
      </div>

      <p v-if="summary" class="muted">{{ summary }}</p>


      <!-- 补充长期信息入口（仅首次完成后） -->
      <div v-if="phase === 'completed'" class="card" style="margin-top: 12px">
        <h3>补充长期信息</h3>
        <p class="muted">补充你的长期特质（性格、习惯、能力自评等），AI 会结合客观记录客观评估是否需要调整属性。</p>
        <div class="field">
          <textarea v-model="supplementText" rows="2" placeholder="例如：我性格偏内向，但自控力其实比看起来强…"></textarea>
        </div>
        <button class="btn primary" :disabled="busy" @click="submitSupplement">
          <template v-if="busy"><span class="spinner"></span>AI 正在评估…</template>
          <template v-else>提交补充</template>
        </button>

        <!-- 调整建议 -->
        <div v-if="pendingAdjustment" class="card" style="margin-top: 12px">
          <h4>AI 评估建议</h4>
          <p class="muted">{{ supplementNote }}</p>
          <div v-for="adj in pendingAdjustment.adjustments" :key="adj.name" class="judgment-item">
            <span class="attr-name">{{ adj.name }}</span>
            <span :class="adj.delta >= 0 ? 'positive' : 'negative'">{{ adj.delta >= 0 ? '+' : '' }}{{ adj.delta }}</span>
            <div class="muted">{{ adj.reason }}</div>
            <div class="evidence">依据：{{ adj.evidence }}</div>
          </div>
          <div v-if="pendingAdjustment.adjustments.length" class="action-group" style="margin-top: 8px">
            <button class="btn primary" :disabled="busy" @click="confirmSupplement">
              <template v-if="busy">应用中…</template>
              <template v-else>确认调整</template>
            </button>
            <button class="btn" :disabled="busy" @click="ignoreSupplement">忽略</button>
          </div>
          <div v-else class="action-group" style="margin-top: 8px">
            <button class="btn" @click="ignoreSupplement">知道了</button>
          </div>
        </div>
      </div>
    </div>

    <!-- v1.10 M1：成就墙（已解锁彩色 / 未解锁灰态 + 进度） -->
    <div v-if="phase === 'done' || phase === 'completed'" class="card" style="margin-top: 12px">
      <h3>
        成就墙
        <span class="muted" style="font-size: 13px; font-weight: 400">
          已解锁 {{ achSummary.unlocked }} / {{ achSummary.total }}
        </span>
      </h3>
      <p class="muted" style="font-size: 13px">
        徽章只发金币、不发属性点——点数只能靠真实行为挣。AI 发现值得纪念的里程碑时会提议追授，由你决定是否接受。
      </p>
      <div class="ach-grid">
        <div
          v-for="a in achievements"
          :key="a.code"
          class="ach-badge"
          :class="{ locked: !a.unlocked }"
          :title="a.description"
        >
          <div class="ach-icon">{{ a.icon }}</div>
          <div class="ach-body">
            <div class="ach-name">
              {{ a.name }}
              <span v-if="a.kind === 'discovered'" class="tag" style="margin-left: 4px">AI 追授</span>
            </div>
            <div class="muted" style="font-size: 13px">
              <template v-if="a.unlocked">解锁于 {{ fmtDate(a.unlocked_at) }} · +{{ a.coin_reward }} 币</template>
              <template v-else>{{ a.description }}（{{ a.current }}/{{ a.target }}）</template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>
  </div>
</template>
