import { createRouter, createWebHistory } from 'vue-router'
import DiscoveryWorkbench from '../views/DiscoveryWorkbench.vue'
import DiscoveryReportView from '../views/DiscoveryReportView.vue'

const routes = [
  {
    path: '/',
    redirect: '/discovery'
  },
  {
    path: '/discovery',
    name: 'DiscoveryWorkbench',
    component: DiscoveryWorkbench,
    meta: {
      title: '多智能体规则发现工作台'
    }
  },
  {
    path: '/discovery/report/:taskId',
    name: 'DiscoveryReport',
    component: DiscoveryReportView,
    props: true,
    meta: {
      title: '多智能体规则发现报告'
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.afterEach((to) => {
  const title = typeof to.meta?.title === 'string' ? to.meta.title : '多智能体规则发现工作台'
  document.title = title
})

export default router
