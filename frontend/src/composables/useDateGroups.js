import { ref, computed, watch } from 'vue'
import { storageKey as accountStorageKey, localDate } from '../session'

/**
 * 按日期分组 + 折叠状态（v1.6 B2 抽取为公共 composable）。
 *
 * 判定中心（JudgmentList）与手账本（TimelineView）共用同一套分组逻辑：
 * 今天 / 昨天 / 本周更早 / 更早（按「本周一 0 点」为界），组头含标签、日期范围、条数。
 * 展开状态按 storageKey 存 localStorage（默认只展开「今天」），组内保持传入顺序。
 *
 * 注意：搜索时强制展开属于消费者行为（依赖各自的搜索框），此处只提供
 * `expanded` / `toggleGroup` / `groups`，由消费者自行叠加搜索覆盖。
 *
 * @param {import('vue').Ref<Array>} items 源数据（响应式数组，需已按时间倒序）
 * @param {{storageKey: string, getTime?: (item: any) => string}} options
 */
export function useDateGroups(items, { storageKey, getTime = (item) => item.created_at }) {
  storageKey = accountStorageKey(storageKey)
  let cached = { today: true }
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || 'null')
    if (value && typeof value === 'object' && !Array.isArray(value)) cached = value
  } catch { /* 损坏或不可读的缓存使用默认展开状态 */ }
  const expanded = ref(cached)

  watch(
    expanded,
    () => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(expanded.value))
      } catch (e) {
        /* 忽略存储失败 */
      }
    },
    { deep: true }
  )

  function toggleGroup(key) {
    expanded.value[key] = !expanded.value[key]
  }

  const GROUPS = [
    { key: 'today', label: '今天' },
    { key: 'yesterday', label: '昨天' },
    { key: 'thisweek', label: '本周更早' },
    { key: 'earlier', label: '更早' },
  ]

  const fmt = (value) => localDate(value).slice(5)

  const groups = computed(() => {
    const today = localDate()
    const calendar = new Date(today + 'T00:00:00Z')
    const yesterday = new Date(calendar.getTime() - 86400000).toISOString().slice(0,10)
    calendar.setUTCDate(calendar.getUTCDate() - ((calendar.getUTCDay() + 6) % 7))
    const monday = calendar.toISOString().slice(0,10)

    const buckets = { today: [], yesterday: [], thisweek: [], earlier: [] }
    for (const item of items.value || []) {
      const d = localDate(getTime(item))
      if (d >= today) buckets.today.push(item)
      else if (d >= yesterday) buckets.yesterday.push(item)
      else if (d >= monday) buckets.thisweek.push(item)
      else buckets.earlier.push(item)
    }

    return GROUPS.map(({ key, label }) => {
      const list = buckets[key]
      if (!list.length) return null
      // 组头日期：今天/昨天显示当天日期；范围组显示首尾日期（组内按时间倒序）
      const dateRange =
        key === 'today' || key === 'yesterday'
          ? fmt(getTime(list[0]))
          : `${fmt(getTime(list[list.length - 1]))} ~ ${fmt(getTime(list[0]))}`
      return { key, label, items: list, dateRange }
    }).filter(Boolean)
  })

  return { groups, expanded, toggleGroup }
}
