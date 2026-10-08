import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const noop = () => {}
const storage = () => ({ getItem: () => null, setItem: noop, removeItem: noop })
function evaluate(file, expose, api = {}, localStorage = storage()) {
  const source = fs.readFileSync(file, 'utf8')
  let code = source.includes('<script setup>') ? source.match(/<script setup>([\s\S]*?)<\/script>/)[1] : source
  code = code.replace(/^import .*$/gm, '').replace(/^export /gm, '')
  const context = vm.createContext({
    api, ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }),
    watch: noop, onMounted: noop, onBeforeUnmount: noop, defineEmits: () => noop,
    defineProps: () => ({}), toast: { success: noop, error: noop, info: noop },
    localStorage, sessionStorage: storage(), setTimeout: () => 0, clearTimeout: noop,
    console, Date, Promise,
  })
  vm.runInContext(code + '\n globalThis.exposed = { ' + expose + ' }', context)
  return context.exposed
}

for (const value of ['{{{', 'null', '[1,2]', '{"today":false,"earlier":true}']) {
  const module = evaluate('frontend/src/composables/useDateGroups.js', 'useDateGroups', {}, { ...storage(), getItem: () => value })
  const grouped = module.useDateGroups({ value: [] }, { storageKey: 'test' })
  assert.equal(grouped.expanded.value.today, value.startsWith('{"') ? false : true)
}
const inaccessible = evaluate('frontend/src/composables/useDateGroups.js', 'useDateGroups', {}, {
  ...storage(), getItem() { throw new Error('denied') },
})
assert.equal(inaccessible.useDateGroups({value:[]}, {storageKey:'test'}).expanded.value.today, true)

let created = 0, judged = 0, fail = true
const api = {
  createEvent: async () => ({ id: ++created }),
  judgeEvent: async () => { judged++; if (fail) throw new Error('模型失败'); return { status: 'pending' } },
  listItems: async () => [], getItemsStats: async () => [], listGoals: async () => [],
}
const today = evaluate('frontend/src/components/TodayCheckin.vue', 'drafts, rowState, submitOne', api)
today.drafts.value[1] = '运动'
await Promise.all([today.submitOne({id:1,name:'运动'}), today.submitOne({id:1,name:'运动'})])
assert.equal(created, 1); assert.equal(judged, 1)
assert.equal(today.rowState.value[1].eventId, 1)
assert.equal(today.drafts.value[1], '运动')
await today.submitOne({id:1,name:'运动'})
assert.equal(created, 1)
today.drafts.value[1] = '运动的新描述'
await today.submitOne({id:1,name:'运动'})
assert.equal(created, 2)
fail = false
await today.submitOne({id:1,name:'运动'})
assert.equal(created, 2); assert.equal(today.drafts.value[1], '')
assert.equal(today.rowState.value[1].eventId, null)

for (const mode of ['form', 'journal']) {
  created = 0; judged = 0; fail = true
  const form = evaluate('frontend/src/components/EventForm.vue', 'form, mode, journalContent, submit, savedSubmission', api)
  form.mode.value = mode
  form.form.value.content = '运动'
  form.journalContent.value = '生活日记'
  await Promise.all([form.submit(), form.submit()])
  assert.equal(created, 1); assert.equal(judged, 1)
  await form.submit(); assert.equal(created, 1)
  if (mode === 'form') form.form.value.content = '新的正文'
  else form.journalContent.value = '新的日记'
  await form.submit(); assert.equal(created, 2)
  fail = false
  await form.submit(); assert.equal(created, 2)
  assert.equal(form.savedSubmission.value, null)
}
const challenge = evaluate('frontend/src/components/ChallengeView.vue', 'canSettle', api)
for (const value of [null, undefined, true, '0.9', NaN, Infinity, 0.5, 1.1]) {
  assert.equal(challenge.canSettle({judgment_confidence:value}), false)
}
for (const value of [0.8, 0.9, 1]) assert.equal(challenge.canSettle({judgment_confidence:value}), true)
console.log('PASS: cache corruption/storage failure; TodayCheckin retry/double-click/edit; form/journal retry; challenge confidence gates')

for (const completed of [false, true]) {
  const app = evaluate('frontend/src/App.vue', 'refreshProfile, hasProfile', {
    getAttributes: async () => ({attributes:Array(13).fill({name:'主维度'})}),
    getOnboardingStatus: async () => ({onboarding_completed:completed}),
  })
  await app.refreshProfile()
  assert.equal(app.hasProfile.value, completed)
}
console.log('PASS: thirteen placeholder attributes do not imply completed onboarding')
