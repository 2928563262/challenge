<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    tone?: "neutral" | "info" | "success" | "warning" | "error";
    title?: string;
  }>(),
  {
    tone: "neutral",
    title: "",
  },
);
</script>

<template>
  <article class="state-panel" :class="`state-panel--${props.tone}`">
    <strong v-if="props.title" class="state-panel__title">{{ props.title }}</strong>
    <div class="state-panel__body">
      <slot />
    </div>
  </article>
</template>
