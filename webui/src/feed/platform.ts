export const platforms = { douyin: "抖音", tiktok: "TikTok", kuaishou: "快手", rednote: "小红书", weibo: "微博" };
export type Platform = keyof typeof platforms;
let current: Platform = "douyin";
try { const value = localStorage.getItem("feed-platform"); if (value && value in platforms) current = value as Platform; } catch {}
export const getPlatform = () => current;
export function setPlatform(value: Platform) { current = value; try { localStorage.setItem("feed-platform", value); } catch {} }
