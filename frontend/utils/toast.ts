/**
 * Toast 提示 — 轻量级纯 CSS 驱动，替代 alert()
 *
 * 用法:
 *   import { toast } from "../utils/toast"
 *   toast("保存成功")
 *   toast.success("通过")
 *   toast.error("失败")
 *   toast.warning("需注意")
 */
let toastContainer: HTMLDivElement | null = null;

function ensureContainer() {
  if (toastContainer) return;
  toastContainer = document.createElement("div");
  toastContainer.id = "toast-root";
  document.body.appendChild(toastContainer);

  const style = document.createElement("style");
  style.textContent = `
    #toast-root { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; display: flex; flex-direction: column; align-items: center; gap: 8px; pointer-events: none; }
    .toast-msg { padding: 10px 22px; border-radius: 10px; font-size: 13px; font-weight: 600; box-shadow: 0 8px 24px rgba(0,0,0,0.35); animation: toastIn 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275); pointer-events: auto; }
    .toast-info    { background: rgba(56,189,248,0.9); color: #fff; }
    .toast-success { background: rgba(34,197,94,0.9); color: #fff; }
    .toast-error   { background: rgba(239,68,68,0.9); color: #fff; }
    .toast-warning { background: rgba(251,191,36,0.95); color: #111; }
    @keyframes toastIn { from { opacity: 0; transform: translateY(-12px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
  `;
  document.head.appendChild(style);
}

/** 最大同时堆叠条数，超过则移除最旧的（#m15） */
const MAX_TOAST_STACK = 3;

function toastImpl(msg: string, cls = "toast-info") {
  ensureContainer();
  const el = document.createElement("div");
  el.className = `toast-msg ${cls}`;
  el.textContent = msg;
  toastContainer!.appendChild(el);
  // 堆叠超限：移除最旧的（firstChild 可能是文本节点，循环跳过）
  while (toastContainer!.childElementCount > MAX_TOAST_STACK) {
    const first = toastContainer!.firstElementChild;
    if (!first) break;
    first.remove();
  }
  setTimeout(() => el.remove(), 2500);
}

export function toast(msg: string) { toastImpl(msg, "toast-info"); }
toast.success = (msg: string) => toastImpl(msg, "toast-success");
toast.error   = (msg: string) => toastImpl(msg, "toast-error");
toast.warning = (msg: string) => toastImpl(msg, "toast-warning");
