import { createI18n } from "vue-i18n";

import { zhCN } from "./locales/zh-CN";

const zhCNAnnotationOverrides = {
  totalCount: "共复核 {count} 条",
  searchPlaceholder: "搜索 record_id 或条文关键词",
  searchAction: "搜索",
  clearSearchAction: "清空",
  prevPage: "上一页",
  nextPage: "下一页",
  pageSummary: "第 {page} 页 / 共 {totalPages} 页",
};

export const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {
    "zh-CN": {
      ...zhCN,
      annotation: {
        ...zhCN.annotation,
        ...zhCNAnnotationOverrides,
      },
    },
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
