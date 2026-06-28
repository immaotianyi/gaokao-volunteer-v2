/* eslint-env node */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:vue/vue3-recommended",
    "plugin:@typescript-eslint/recommended",
  ],
  parser: "vue-eslint-parser",
  parserOptions: {
    parser: "@typescript-eslint/parser",
    ecmaVersion: 2022,
    sourceType: "module",
  },
  rules: {
    // 与现有代码风格对齐：不强制分号、允许未使用 vars 在 .vue 文件中
    semi: ["warn", "never"],
    "vue/multi-word-component-names": "off",
    "@typescript-eslint/no-explicit-any": "off", // 渐进迁移，先关
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    "vue/no-v-html": "off", // Icon.vue 用 v-html 渲染内置 SVG path
    "vue/require-default-prop": "off", // TS 类型 + withDefaults 已处理
    "vue/attribute-hyphenation": "off", // 与现有 ariaLabel/aria-pressed 混用风格
  },
  ignorePatterns: ["dist/**", "node_modules/**", "*.config.ts", "env.d.ts"],
}
