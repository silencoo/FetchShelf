/** Coalesce drag targets so each requested frame gets a chance to decode. */
const pending = new WeakMap<HTMLVideoElement, { target: number }>();

export function seekVideo(video: HTMLVideoElement, time: number) {
  if (!Number.isFinite(video.duration) || !Number.isFinite(time)) return;
  const target = Math.max(0, Math.min(video.duration, time));
  const existing = pending.get(video);
  if (existing) {
    existing.target = target;
    return;
  }
  const request = { target };
  const source = video.currentSrc || video.src;
  pending.set(video, request);
  const clear = () => {
    pending.delete(video);
    video.removeEventListener("seeked", advance);
    video.removeEventListener("emptied", clear);
    video.removeEventListener("error", clear);
  };
  const advance = () => {
    if ((video.currentSrc || video.src) !== source) { clear(); return; }
    if (video.seeking) return;
    if (Math.abs(video.currentTime - request.target) < 0.01) { clear(); return; }
    video.currentTime = request.target;
  };
  video.addEventListener("seeked", advance);
  video.addEventListener("emptied", clear);
  video.addEventListener("error", clear);
  advance();
}
