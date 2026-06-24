/**
 * H5 兼容工具 — Loading 状态
 * Toast 已迁移至 utils/toast.ts
 */
import { ref } from "vue";

export const isLoading = ref(false);

export function showLoading() { isLoading.value = true; }
export function hideLoading() { isLoading.value = false; }
