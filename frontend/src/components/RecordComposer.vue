<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { account, storageKey, localDate } from '../session'
const emit = defineEmits(['saved'])
const router = useRouter()
const key = storageKey('record-draft')
let cached = {}
try { const value = JSON.parse(localStorage.getItem(key) || '{}'); if (value && typeof value === 'object' && !Array.isArray(value)) cached = value } catch {}
const content = ref(typeof cached.content === 'string' ? cached.content : '')
const occurred = ref(cached.occurred || '')
const occurredOn = ref(cached.occurredOn || localDate())
const timeOpen=ref(!!cached.occurred),timeInput=ref(null)
async function openTime(){timeOpen.value=true;await nextTick();timeInput.value?.focus()}
const intent = ref(['now','later','never'].includes(cached.intent) ? cached.intent : 'later')
const receiptKey = ref(cached.receiptKey || '')
const submitted = ref(cached.submitted || null)
const busy = ref(false)
const uncertain = ref(!!submitted.value)
const status = ref(uncertain.value ? '上次保存结果尚未确认，请继续查询这次提交。' : '')
const error = ref('')
const savedId = ref(null)
function cache() {
  try { localStorage.setItem(key, JSON.stringify({ content:content.value, occurred:occurred.value, occurredOn:occurredOn.value, intent:intent.value, receiptKey:receiptKey.value, submitted:submitted.value })) } catch {}
}
watch([content, occurred, occurredOn, intent], cache)
async function save() {
  if (busy.value || !content.value.trim()) return
  busy.value = true; error.value = ''; savedId.value = null
  if (!submitted.value) {
    receiptKey.value = crypto.randomUUID()
    submitted.value = { content:content.value, source:'form', intent:intent.value,
      client_request_id:receiptKey.value, timezone:account.value?.timezone || 'Asia/Shanghai',
      ...(occurred.value ? {occurred_at:occurred.value, time_precision:'minute'} : {occurred_on:occurredOn.value,time_precision:'date'}) }
    cache()
  }
  status.value = '正在保存原文…'
  try {
    let event
    if (uncertain.value) {
      status.value = '尚未确认保存，正在查询这次提交…'
      try { event = await api.submission(receiptKey.value) } catch (e) { if (e.status !== 404) throw e }
    }
    if (!event) event = await api.createEvent(submitted.value)
    const chosen = submitted.value.intent
    savedId.value = event.id; uncertain.value = false
    content.value = ''; occurred.value = ''; occurredOn.value=localDate(); timeOpen.value=false; submitted.value = null; receiptKey.value = ''
    try { localStorage.removeItem(key) } catch {}
    status.value = chosen === 'never' ? '已保存 · 不分析' : '已保存 · 稍后处理'
    emit('saved', event)
    if (chosen === 'now') {
      status.value = '原文已保存，正在提交分析…'
      try {
        if (account.value?.mode === 'local') await api.judgeEvent(event.id)
        else await api.submitJob(event.id, { request_key:crypto.randomUUID(), event_version:event.content_version, operation:'judge' })
        status.value = account.value?.mode === 'local' ? '已保存 · 分析结果可查看' : '已保存 · 分析已排队，可离开页面'
      } catch (e) { status.value = '记录已保存，分析未完成。'; error.value = e.message }
    }
  } catch (e) {
    uncertain.value = ![400, 409, 422].includes(e.status)
    if (!uncertain.value) { submitted.value = null; receiptKey.value = '' }
    cache()
    status.value = uncertain.value ? '尚未确认云端保存；本机草稿仍保留。' : '保存未完成，请修改后重试；本机草稿仍保留。'
    error.value = e.message
  } finally { busy.value = false }
}
</script>
<template>
  <form class="record-composer" @submit.prevent="save">
    <label class="composer-label" for="new-record">记一下：今天发生了什么？</label>
    <textarea id="new-record" v-model="content" rows="4" maxlength="20000" aria-describedby="record-help record-status record-error" :aria-invalid="!!error" :disabled="busy || uncertain" placeholder="一件小事、一段感受，或者想留住的一句话。也可以用手机输入法语音转文字。" />
    <div class="composer-options">
      <div><div class="composer-time"><span>发生于：{{ occurred || occurredOn }}{{ occurred ? '' : ' · 仅日期' }}</span><button type="button" class="btn" :disabled="busy || uncertain" :aria-expanded="timeOpen" @click="openTime">其他日期 / 精确时间</button></div><div v-if="timeOpen"><label>发生日期<input ref="timeInput" v-model="occurredOn" type="date" :disabled="busy || uncertain || !!occurred" /></label><label>精确时间（可留空）<input v-model="occurred" type="datetime-local" :disabled="busy || uncertain" /></label><button type="button" class="btn" :disabled="busy || uncertain" @click="occurred='';occurredOn=localDate();timeOpen=false">使用今天 · 仅日期</button></div></div>
      <label class="composer-analysis">分析<select v-model="intent" :disabled="busy || uncertain"><option value="later">稍后处理</option><option value="now">现在分析</option><option value="never">不分析</option></select></label>
    </div>
    <p id="record-help" class="muted small">原文先保存，分析由你决定。没有模型也能记录。</p><p v-if="intent==='now'" class="muted">原文先保存；随后提交分析，供应商可能计费。</p>
    <div class="save-line"><span id="record-status" role="status" aria-live="polite">{{ status || (content ? '本机草稿 · 尚未云端保存' : '先留下一句话') }}</span><button class="btn primary" :disabled="busy || !content.trim()">{{ busy ? '保存中…' : uncertain ? '查询并重试本次保存' : '保存记录' }}</button></div>
    <p v-if="error" id="record-error" class="error" role="alert">{{ error }}</p>
    <RouterLink v-if="savedId" :to="'/events/' + savedId">查看这条记录 →</RouterLink>
  </form>
</template>
