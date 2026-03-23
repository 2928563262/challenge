declare module "vue-i18n" {
  export function createI18n(options: any): any;
  export function useI18n(): {
    t: (key: string) => string;
    te: (key: string) => boolean;
  };
}
