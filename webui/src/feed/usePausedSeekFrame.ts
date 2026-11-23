import { useCallback, useLayoutEffect, useRef } from "react";

import { seekFrameUrl } from "./api";
import { seekVideo } from "./seekVideo";

const PREVIEW_INTERVAL_MS = 90;
const NATIVE_FRAME_TOLERANCE = 0.05;

function trackPausedSeek(
  video: HTMLVideoElement, path: string, preview: HTMLDivElement, clear: () => void,
) {
  const source = video.currentSrc || video.src;
  let target: { time: number; url: string; commit: boolean };
  let lastRequested: string | undefined;
  let lastPresented = Number.NEGATIVE_INFINITY;
  let previewTime: number | undefined;
  const initialTime = video.currentTime;
  let callback: number | undefined;
  let timer: number | undefined;
  let loading: HTMLImageElement | undefined;
  let stopped = false;
  const current = () => !stopped && video.isConnected && video.paused &&
    (video.currentSrc || video.src) === source;
  const nativeMatches = () => Math.abs(lastPresented - target.time) <= NATIVE_FRAME_TOLERANCE;

  function schedule() {
    if (!current() || loading || timer !== undefined || target.url === lastRequested ||
        (!preview.firstChild && nativeMatches())) return;
    timer = window.setTimeout(requestFrame, target.commit ? 0 : PREVIEW_INTERVAL_MS);
  }

  function requestFrame() {
    timer = undefined;
    if (!current() || (!preview.firstChild && nativeMatches())) return;
    const { time, url } = target;
    lastRequested = url;
    const image = new Image();
    loading = image;
    image.alt = "";
    image.className = "fa-paused-frame";

    const finish = (ready: boolean) => {
      if (!current()) return;
      loading = undefined;
      image.onload = null;
      image.onerror = null;
      const shown = previewTime ?? (Number.isFinite(lastPresented) ? lastPresented : initialTime);
      const onDragPath = !target.commit &&
        time > Math.min(shown, target.time) && time < Math.max(shown, target.time);
      // Keep the previous frame on screen while loading. Once the user releases
      // the bar, only the final seek frame can replace it.
      if (ready && (target.url === url || onDragPath) && (preview.firstChild || !nativeMatches())) {
        preview.replaceChildren(image);
        previewTime = time;
      }
      schedule();
    };
    image.onload = () => { void image.decode().then(() => finish(true), () => finish(true)); };
    image.onerror = () => finish(false);
    image.src = url;
  }

  const presented: VideoFrameRequestCallback = (_now, metadata) => {
    callback = undefined;
    if (!current()) return;
    lastPresented = metadata.mediaTime;
    if (target.commit && nativeMatches()) clear();
    else callback = video.requestVideoFrameCallback(presented);
  };

  return {
    video,
    source,
    move(time: number, commit: boolean) {
      const bounded = Math.max(0, Math.min(time, video.duration));
      // FFmpeg needs a position before EOF to return the last frame.
      const frameTime = bounded === video.duration ? Math.max(0, bounded - 0.1) : bounded;
      target = { time: bounded, url: seekFrameUrl(path, frameTime), commit };
      if (commit && nativeMatches()) {
        clear();
        return;
      }
      callback ??= video.requestVideoFrameCallback?.(presented);
      if (commit) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      schedule();
    },
    stop() {
      stopped = true;
      window.clearTimeout(timer);
      if (callback !== undefined) video.cancelVideoFrameCallback?.(callback);
      if (loading) {
        loading.onload = null;
        loading.onerror = null;
        loading.removeAttribute("src");
      }
    },
  };
}

export function usePausedSeekFrame(path: string, active: boolean) {
  const previewRef = useRef<HTMLDivElement>(null);
  const session = useRef<ReturnType<typeof trackPausedSeek> | undefined>(undefined);
  const clear = useCallback(() => {
    session.current?.stop();
    session.current = undefined;
    previewRef.current?.replaceChildren();
  }, []);

  useLayoutEffect(() => clear, [path, active, clear]);

  const seek = useCallback((video: HTMLVideoElement, time: number, commit = false) => {
    const preview = previewRef.current;
    if (active && preview && video.paused && Number.isFinite(time) && Number.isFinite(video.duration)) {
      const source = video.currentSrc || video.src;
      if (session.current?.video !== video || session.current.source !== source) {
        clear();
        session.current = trackPausedSeek(video, path, preview, clear);
      }
      session.current.move(time, commit);
    }
    seekVideo(video, time, commit);
  }, [active, clear, path]);

  return { previewRef, seek, clear };
}
