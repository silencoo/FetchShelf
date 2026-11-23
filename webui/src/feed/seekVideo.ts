interface SeekRequest {
  source: string;
  target: number;
  apply(commit: boolean): void;
  clear(): void;
}

const SEEK_TIMEOUT_MS = 1000;
const pending = new WeakMap<HTMLVideoElement, SeekRequest>();

/** Coalesce drag updates and submit the release position even during a seek. */
export function seekVideo(video: HTMLVideoElement, time: number, commit = false) {
  if (!Number.isFinite(video.duration) || !Number.isFinite(time)) return;
  const target = Math.max(0, Math.min(video.duration, time));
  const source = video.currentSrc || video.src;
  const existing = pending.get(video);
  if (existing?.source === source) {
    existing.target = target;
    if (commit) existing.apply(true);
    return;
  }
  existing?.clear();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let submittedTarget: number | undefined;

  const clear = () => {
    clearTimeout(timer);
    pending.delete(video);
    video.removeEventListener("seeked", advance);
    video.removeEventListener("emptied", clear);
    video.removeEventListener("error", clear);
  };

  const apply = (final: boolean) => {
    clearTimeout(timer);
    if ((video.currentSrc || video.src) !== source) {
      clear();
      return;
    }
    const atTarget = Math.abs(video.currentTime - request.target) < 0.01;
    const submitted = submittedTarget === request.target;
    if (!video.seeking && (atTarget || submitted)) {
      clear();
      return;
    }
    if (!atTarget && !submitted && (final || !video.seeking)) {
      submittedTarget = request.target;
      video.currentTime = request.target;
    }
    timer = setTimeout(() => {
      // A missed event must not leave later drags queued behind this one.
      if (video.seeking) clear();
      else advance();
    }, SEEK_TIMEOUT_MS);
  };

  const advance = () => apply(false);
  const request = { source, target, apply, clear };
  pending.set(video, request);
  video.addEventListener("seeked", advance);
  video.addEventListener("emptied", clear);
  video.addEventListener("error", clear);
  apply(commit);
}
