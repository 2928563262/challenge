import { createI18n } from "vue-i18n";

import { zhCN } from "./locales/zh-CN";

export const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {
    "zh-CN": zhCN,
  },
});

function tryTranslate(key: string, fallback: string) {
  return i18n.global.te(key) ? i18n.global.t(key) : fallback;
}

export function formatEntityTypeLabel(entityType: string) {
  return tryTranslate(`entityTypes.${entityType}`, entityType);
}

export function formatRelationTypeLabel(relationType: string) {
  return tryTranslate(`relationTypes.${relationType}`, relationType);
}

export function formatSplitName(splitName: string) {
  return tryTranslate(`splitNames.${splitName}`, splitName);
}

export function formatStatusLabel(status: string) {
  return tryTranslate(`statusNames.${status}`, status);
}

export function formatBioLabel(label: string) {
  if (label === "O") {
    return "O";
  }
  const [prefix, entityType] = label.split("-");
  if (!prefix || !entityType) {
    return label;
  }
  return `${prefix}-${formatEntityTypeLabel(entityType)}`;
}
