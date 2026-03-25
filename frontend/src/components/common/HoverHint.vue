<script setup lang="ts">
withDefaults(
  defineProps<{
    text: string;
    ariaLabel?: string;
  }>(),
  {
    ariaLabel: "提示",
  },
);
</script>

<template>
  <span class="hover-hint" tabindex="0" :aria-label="ariaLabel">
    <span class="hover-hint__icon" aria-hidden="true">i</span>
    <span class="hover-hint__bubble">{{ text }}</span>
  </span>
</template>

<style scoped>
.hover-hint {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  border: 1px solid rgba(111, 74, 46, 0.25);
  background: rgba(125, 79, 43, 0.08);
  color: #7d4f2b;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: help;
  outline: none;
  z-index: 2600;
}

.hover-hint:hover,
.hover-hint:focus-visible {
  z-index: 3600;
}

.hover-hint__bubble {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: min(380px, calc(100vw - 48px));
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(111, 74, 46, 0.18);
  background: rgba(255, 252, 247, 0.98);
  box-shadow: 0 10px 28px rgba(95, 73, 46, 0.16);
  color: #5d4a38;
  line-height: 1.45;
  font-size: 0.84rem;
  z-index: 3700;
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease, visibility 0.15s ease;
}

.hover-hint:hover .hover-hint__bubble,
.hover-hint:focus-visible .hover-hint__bubble {
  visibility: visible;
  opacity: 1;
}
</style>
