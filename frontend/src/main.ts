import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import { i18n } from "./i18n";
import router from "./router";
import "./style.css";

const app = createApp(App);

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  console.error("Global Vue error:", err, info);
  // 可以在这里显示一个全局错误通知
};

app.use(createPinia());
app.use(i18n);
app.use(router);
app.mount("#app");
