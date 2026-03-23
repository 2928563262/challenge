<script setup lang="ts">
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <RouterLink class="brand-mark" to="/">
          <span class="brand-kicker">{{ t("nav.brandKicker") }}</span>
          <strong>伤寒论知识图谱系统</strong>
        </RouterLink>

        <nav class="main-nav">
          <RouterLink to="/" class="nav-link">{{ t("nav.overview") }}</RouterLink>
          <RouterLink to="/explore" class="nav-link">{{ t("nav.explore") }}</RouterLink>
          <RouterLink to="/models" class="nav-link">{{ t("nav.models") }}</RouterLink>
          <RouterLink to="/annotations" class="nav-link">{{ t("nav.annotations") }}</RouterLink>
        </nav>
      </div>
    </header>

    <RouterView />
  </div>
</template>
