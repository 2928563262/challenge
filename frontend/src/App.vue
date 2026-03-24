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
          <strong>{{ t("nav.brandTitle") }}</strong>
        </RouterLink>

        <nav class="main-nav">
          <RouterLink to="/" class="nav-link">{{ t("nav.overview") }}</RouterLink>
          <RouterLink to="/explore" class="nav-link">{{ t("nav.explore") }}</RouterLink>
          <RouterLink to="/qa" class="nav-link">问答</RouterLink>
          <RouterLink to="/stats" class="nav-link">统计</RouterLink>
          <RouterLink to="/models" class="nav-link">{{ t("nav.models") }}</RouterLink>
          <RouterLink to="/annotations" class="nav-link">{{ t("nav.annotations") }}</RouterLink>
        </nav>
      </div>
    </header>

    <RouterView />
  </div>
</template>
