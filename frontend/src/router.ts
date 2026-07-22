import { createRouter, createWebHistory } from 'vue-router'
import BoardView from './views/BoardView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'board', component: BoardView },
    {
      path: '/p/:id',
      name: 'project',
      component: () => import('./views/ProjectView.vue'),
    },
    {
      path: '/styleguide',
      name: 'styleguide',
      component: () => import('./views/styleguide/StyleguideView.vue'),
    },
  ],
})

export default router
