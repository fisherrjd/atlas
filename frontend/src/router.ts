import { createRouter, createWebHistory } from 'vue-router'
import ProjectsView from './views/ProjectsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectsView },
    {
      path: '/p/:id',
      name: 'project',
      component: () => import('./views/ProjectView.vue'),
    },
    {
      path: '/wizard',
      name: 'wizard',
      component: () => import('./views/WizardView.vue'),
    },
    { path: '/heimdall', redirect: '/wizard' }, // pre-rename bookmarks

    {
      path: '/styleguide',
      name: 'styleguide',
      component: () => import('./views/styleguide/StyleguideView.vue'),
    },
  ],
})

export default router
