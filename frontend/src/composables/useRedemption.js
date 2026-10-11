import { ref } from 'vue'
import { account, accountEpoch } from '../session'
import { api } from '../api'

// Durable operation identity is kept across logout, strictly inside its owner's namespace.
export function useRedemption() {
  const owner = account.value?.id || 'local'
  const epoch = accountEpoch
  const key = `gol-receipts:${owner}:redeem`
  const pending = ref(null), busy = ref(false), warning = ref('')
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null')
    if (value && value.owner === owner && value.body?.request_key && value.body?.expected_version) pending.value = value
    else if (value) throw new Error('INVALID_PENDING')
  } catch { warning.value = '兑换恢复记录不可读。请先核对奖励券和金币流水，勿直接再次兑换。' }
  function current() {
    if (epoch !== accountEpoch || owner !== (account.value?.id || 'local')) throw new Error('账号已切换，请重新打开商店。')
  }
  function persist(value) {
    localStorage.setItem(key, JSON.stringify(value))
    if (localStorage.getItem(key) !== JSON.stringify(value)) throw new Error('无法持久保存兑换标识，请开启浏览器存储后再兑换。')
    pending.value = value
  }
  async function send(item) {
    if (busy.value) return
    current()
    if (warning.value) throw new Error(warning.value)
    busy.value = true
    try {
      let operation = pending.value
      if (operation?.state === 'unknown' && operation.item_id !== item.id) throw new Error('请先恢复上一次兑换的结果。')
      if (!operation || operation.state !== 'unknown') {
        operation = {owner, item_id:item.id, name:item.name, state:'unknown',
          body:{note:'', expected_version:item.updated_at, request_key:crypto.randomUUID()}}
        // Do not send any financial request unless its identity is recoverable after refresh.
        persist(operation)
      }
      let result
      try { result = await api.redemptionSubmission(operation.item_id, operation.body.request_key) }
      catch (error) { if (error.status !== 404) throw error }
      if (!result) {
        try { result = await api.redeemShopItem(operation.item_id, operation.body) }
        catch (error) {
          if ([400,409,422].includes(error.status)) {current();persist({...operation,state:'rejected'})}
          throw error
        }
      }
      current()
      const completed = {...operation, state:'complete', result}
      pending.value = completed
      try { persist(completed) }
      catch { warning.value = '兑换已成功，结果恢复记录未能写入；请核对奖励券后再进行下一次兑换。' }
      return result
    } finally { busy.value = false }
  }
  return {pending, busy, warning, send}
}
