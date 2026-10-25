import { createRouter, createWebHashHistory } from 'vue-router'
import { account } from './session'
import { rememberReturn } from './navigation'
const RecordList = () => import('./components/RecordList.vue')
const RecordDetail = () => import('./components/RecordDetail.vue')
const MyView = () => import('./components/MyView.vue')
const TodayCheckin = () => import('./components/TodayCheckin.vue')
const JudgmentList = () => import('./components/JudgmentList.vue')
const ChallengeView = () => import('./components/ChallengeView.vue')
const AnchorsView = () => import('./components/AnchorsView.vue')
const SettingsView = () => import('./components/SettingsView.vue')
const PendingView = () => import('./components/PendingView.vue')
const ReviewView = () => import('./components/ReviewView.vue')

const scrolls=new Map()
export const router = createRouter({ history: createWebHashHistory(), scrollBehavior(to,from,saved){return saved||{top:scrolls.get(to.fullPath)||0}}, routes: [
  { path: '/', component: () => import('./components/PageHub.vue'), meta: { section: 'today' } },
  { path: '/journal', component: RecordList, meta: { section: 'journal' } },
  { path: '/plans', component: () => import('./components/PageHub.vue'), meta: { section:'plans' } },
  { path: '/events/:id', component: RecordDetail, meta: { section: 'journal' } },
  { path: '/growth', component: () => import('./components/PageHub.vue'), meta: { section: 'growth' } },
  { path: '/reports', component: () => import('./components/ReportHistory.vue'), meta: {section:'growth'} },
  { path: '/admin/security',component:()=>import('./components/AccountSecurity.vue'),meta:{section:'admin',workspace:'admin'} },
  { path: '/admin/:tab(overview|users|announcements|site|audit)?',component:()=>import('./components/AdminView.vue'),meta:{section:'admin',workspace:'admin'} },
  { path:'/phase',redirect:'/plans' },
  { path:'/timers',component:()=>import('./components/TimerView.vue'),meta:{section:'rewards'} },
  { path:'/care',redirect:'/plans' },
  { path:'/rewards',component:()=>import('./components/PageHub.vue'),meta:{section:'rewards'} },
  { path:'/special-vouchers',component:ChallengeView,meta:{section:'rewards'} },
  { path:'/personal-information',component:()=>import('./components/PersonalInformationView.vue'),meta:{section:'me'} },
  { path:'/important-days',component:()=>import('./components/ImportantDaysView.vue'),meta:{section:'me'} },
  { path:'/preferences',component:()=>import('./components/PreferencesView.vue'),meta:{section:'me'} },
  { path:'/returning',component:()=>import('./components/ReturnView.vue'),meta:{section:'today'} },
  { path:'/achievements',component:()=>import('./components/AchievementsView.vue'),meta:{section:'growth'} },
  { path:'/feedback',component:()=>import('./components/FeedbackView.vue'),meta:{section:'me'} },
  { path:'/admin/feedback',component:()=>import('./components/FeedbackView.vue'),meta:{section:'admin',workspace:'admin'} },
  { path: '/announcements',component:()=>import('./components/AnnouncementsView.vue'),meta:{section:'me'} },
  { path: '/security',component:()=>import('./components/AccountSecurity.vue'),meta:{section:'me'} },
  { path: '/me', component: () => import('./components/PageHub.vue'), meta: { section: 'me' } },
  { path: '/checkin', component: TodayCheckin, meta: { section: 'plans' } },
  { path: '/pending', component: PendingView, meta: { section: 'today' } },
  { path: '/judgments', component: JudgmentList, meta: { section: 'today' } },
  { path: '/diary', component: () => import('./components/DiaryView.vue'), meta:{section:'today'} },
  { path: '/review', component: ReviewView, meta: { section: 'today' } },
  { path: '/challenges', component: ChallengeView, meta: { section: 'plans' } },
  { path: '/onboarding', component:()=>import('./components/QuestionnaireView.vue'), meta: { section: 'me' } },
  { path: '/anchors', component: AnchorsView, meta: { section: 'me' } },
  { path: '/settings', component: SettingsView, meta: { section: 'me' } },
  {path:'/capture',component:()=>import('./components/SectionDetail.vue'),meta:{section:'today',detail:'capture',title:'记一件事'}},
  {path:'/plans/all',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'projects',title:'全部计划与项目'}},
  {path:'/plans/today',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'today-projects',title:'今日安排'}},
  {path:'/plans/care',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'care',title:'照顾自己的清单'}},
  {path:'/plans/item',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'project',title:'这项安排'}},
  {path:'/plans/goals',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'goals',title:'目标与进度'}},
  {path:'/plans/mainline',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'mainline',title:'当前主线'}},
  {path:'/plans/context',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'context',title:'近期阶段与背景'}},
  {path:'/plans/legacy',component:()=>import('./components/SectionDetail.vue'),meta:{section:'plans',detail:'legacy',title:'原有次数项目'}},
  {path:'/growth/attributes',component:()=>import('./components/SectionDetail.vue'),meta:{section:'growth',detail:'attributes',title:'能力详情'}},
  {path:'/growth/history',component:()=>import('./components/SectionDetail.vue'),meta:{section:'growth',detail:'history',title:'属性变化历史'}},
  {path:'/growth/calendar',component:()=>import('./components/SectionDetail.vue'),meta:{section:'growth',detail:'calendar',title:'记录日历与天数'}},
  {path:'/rewards/shop',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'shop',title:'选择自己的奖励'}},
  {path:'/rewards/manage',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'reward-management',title:'管理奖励'}},
  {path:'/rewards/vouchers',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'vouchers',title:'我的券'}},
  {path:'/rewards/history',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'redemptions',title:'兑换记录'}},
  {path:'/rewards/ledger',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'ledger',title:'金币收支'}},
  {path:'/rewards/rules',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'rules',title:'基础额度与首记领取'}},
  {path:'/rewards/agreements',component:()=>import('./components/SectionDetail.vue'),meta:{section:'rewards',detail:'agreements',title:'娱乐约定'}},
  {path:'/me/personal',component:()=>import('./components/SectionDetail.vue'),meta:{section:'me',detail:'personal',title:'个人资料与问卷'}},
  {path:'/plans/timer',component:()=>import('./components/TimerView.vue'),meta:{section:'plans',timerKind:'plan',title:'计划计时'}},
  {path:'/me/account',redirect:'/security'},
  {path:'/me/baseline',component:MyView,meta:{section:'me',title:'选择游戏起点'}},
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.afterEach((to,from)=>rememberReturn(router,to,from))

router.beforeEach((to,from)=>{scrolls.set(from.fullPath,window.scrollY)})
router.beforeEach(to=>{if(!account.value)return;const admin=account.value.role==='owner';if(admin&&to.meta.workspace!=='admin')return '/admin';if(!admin&&to.meta.workspace==='admin')return '/me'})
