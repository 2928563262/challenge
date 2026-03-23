import { createRouter, createWebHistory } from "vue-router";

import AnnotationReviewView from "../views/AnnotationReviewView.vue";
import GraphExplorerView from "../views/GraphExplorerView.vue";
import HomeView from "../views/HomeView.vue";
import ModelWorkbenchView from "../views/ModelWorkbenchView.vue";
// import QAPageView from "../views/QAPageView.vue"; // Temporarily disabled due to missing QA types

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
      path: "/models",
      name: "models",
      component: ModelWorkbenchView,
    },
    {
      path: "/annotations",
      name: "annotations",
      component: AnnotationReviewView,
    },
    // {
    //   path: "/qa",
    //   name: "qa",
    //   component: QAPageView,
    // },
  ],
});

export default router;
