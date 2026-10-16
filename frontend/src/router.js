import { createRouter, createWebHashHistory } from 'vue-router'
import { rememberReturn } from './navigation'
const HomeView = () => import('./components/HomeView.vue')
const RecordList = () => import('./components/RecordList.vue')
const RecordDetail = () => import('./components/RecordDetail.vue')
const MyView = () => import('./components/MyView.vue')
const AttributePanel = () => import('./components/AttributePanel.vue')
const TodayCheckin = () => import('./components/TodayCheckin.vue')
const JudgmentList = () => import('./components/JudgmentList.vue')
const ChallengeView = () => import('./components/ChallengeView.vue')
const Onboarding = () => import('./components/Onboarding.vue')
const AnchorsView = () => import('./components/AnchorsView.vue')
const SettingsView = () => import('./components/SettingsView.vue')
const PendingView = () => import('./components/PendingView.vue')
const ReviewView = () => import('./components/ReviewView.vue')

export const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/', component: HomeView, meta: { section: 'today' } },
  { path: '/journal', component: RecordList, meta: { section: 'journal' } },
  { path: '/plans', component: () => import('./components/PlansView.vue'), meta: { section:'plans' } },
  { path: '/events/:id', component: RecordDetail, meta: { section: 'journal' } },
  { path: '/growth', component: AttributePanel, meta: { section: 'growth' } },
  { path: '/reports', component: () => import('./components/ReportHistory.vue'), meta: {section:'growth'} },
  { path: '/me', component: MyView, meta: { section: 'me' } },
  { path: '/checkin', component: TodayCheckin, meta: { section: 'plans' } },
  { path: '/pending', component: PendingView, meta: { section: 'today' } },
  { path: '/judgments', component: JudgmentList, meta: { section: 'today' } },
  { path: '/diary', component: () => import('./components/DiaryView.vue'), meta:{section:'today'} },
  { path: '/review', component: ReviewView, meta: { section: 'today' } },
  { path: '/challenges', component: ChallengeView, meta: { section: 'growth' } },
  { path: '/onboarding', component: Onboarding, meta: { section: 'me' } },
  { path: '/anchors', component: AnchorsView, meta: { section: 'me' } },
  { path: '/settings', component: SettingsView, meta: { section: 'me' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.afterEach((to,from)=>rememberReturn(router,to,from))
