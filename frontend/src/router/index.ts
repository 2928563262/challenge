import { createRouter, createWebHistory } from "vue-router";

import AnnotationReviewView from "../views/AnnotationReviewView.vue";
import GraphExplorerView from "../views/GraphExplorerView.vue";
import HomeView from "../views/HomeView.vue";
import ModelWorkbenchView from "../views/ModelWorkbenchView.vue";
import QAPageView from "../views/QAPageView.vue";
import StatisticsView from "../views/StatisticsView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: HomeView,
    },
    {
      path: "/explore",
      name: "explore",
      component: GraphExplorerView,
    },
    {
      path: "/qa",
      name: "qa",
      component: QAPageView,
    },
    {
      path: "/stats",
      name: "stats",
      component: StatisticsView,
    },
    {
      path: "/models",
      name: "models",
      component: ModelWorkbenchView,
    },
    {
      path: "/annotations",
      name: "annotations",
      component: AnnotationReviewView,
    },
  ],
});

export default router;
