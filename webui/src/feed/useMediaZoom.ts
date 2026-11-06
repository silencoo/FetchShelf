import { useEffect, useRef, useState, type RefObject } from "react";

const MAX_SCALE = 5;
const FIT_THRESHOLD = 1.03;
const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));

/** Own only multi-touch and zoomed panning; fitted one-finger scrolling stays native. */
export function useMediaZoom(
  stageRef: RefObject<HTMLDivElement | null>,
  enabled: boolean,
  active: boolean,
  mediaKey: string,
) {
  const [engaged, setEngaged] = useState(false);
  const locked = useRef(false);
  const blockedUntil = useRef(0);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !enabled || !active) return;
    const pager = stage.closest<HTMLElement>(".fa-pager");
    let scale = 1, x = 0, y = 0;
    let pinching = false;
    let handling = false;
    let scrollTop = 0;
    let start: { distance: number; scale: number; x: number; y: number; cx: number; cy: number } | null = null;
    let pan: { id: number; cx: number; cy: number; x: number; y: number } | null = null;

    const limitPan = () => {
      const media = stage.querySelector<HTMLImageElement | HTMLVideoElement>(
        ".fa-video-host video, .fa-carousel-item[data-current='true'] img, .fa-carousel-item[data-current='true'] video",
      );
      const width = stage.clientWidth, height = stage.clientHeight;
      const naturalWidth = media instanceof HTMLVideoElement ? media.videoWidth : media?.naturalWidth;
      const naturalHeight = media instanceof HTMLVideoElement ? media.videoHeight : media?.naturalHeight;
      const fit = naturalWidth && naturalHeight ? Math.min(width / naturalWidth, height / naturalHeight) : 1;
      x = clamp(x, Math.max(0, ((naturalWidth || width) * fit * scale - width) / 2));
      y = clamp(y, Math.max(0, ((naturalHeight || height) * fit * scale - height) / 2));
    };

    const render = () => {
      limitPan();
      const zoomed = scale >= FIT_THRESHOLD;
      const next = zoomed || pinching || handling;
      if (next && !locked.current) scrollTop = pager?.scrollTop ?? 0;
      locked.current = next;
      setEngaged(next);
      stage.toggleAttribute("data-zoom-active", next);
      stage.toggleAttribute("data-zoomed", zoomed);
      stage.style.setProperty("--media-zoom", `translate3d(${x}px, ${y}px, 0) scale(${scale})`);
    };

    const point = (touch: Touch) => {
      const rect = stage.getBoundingClientRect();
      return { x: touch.clientX - rect.left - rect.width / 2, y: touch.clientY - rect.top - rect.height / 2 };
    };

    const begin = (touches: TouchList) => {
      if (touches.length >= 2) {
        const a = point(touches[0]), b = point(touches[1]);
        start = { distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), scale, x, y,
          cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
        pinching = true;
        handling = true;
        pan = null;
      } else if (touches.length === 1 && handling) {
        const touch = touches[0], p = point(touch);
        pan = { id: touch.identifier, cx: p.x, cy: p.y, x, y };
        pinching = false;
        start = null;
      }
      render();
    };

    const prevent = (event: TouchEvent) => {
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();
    };

    const onStart = (event: TouchEvent) => {
      if ((event.target as Element).closest("button, .fa-seek")) return;
      if (event.touches.length >= 2 || scale >= FIT_THRESHOLD) {
        prevent(event);
        handling = true;
        begin(event.touches);
      }
    };

    const onMove = (event: TouchEvent) => {
      if (!handling) return;
      prevent(event);
      if (event.touches.length >= 2 && start) {
        const a = point(event.touches[0]), b = point(event.touches[1]);
        scale = Math.max(1, Math.min(MAX_SCALE, start.scale * Math.hypot(a.x - b.x, a.y - b.y) / start.distance));
        const ratio = scale / start.scale;
        x = (a.x + b.x) / 2 - (start.cx - start.x) * ratio;
        y = (a.y + b.y) / 2 - (start.cy - start.y) * ratio;
      } else if (pan && event.touches.length === 1 && event.touches[0].identifier === pan.id) {
        const p = point(event.touches[0]);
        x = pan.x + p.x - pan.cx;
        y = pan.y + p.y - pan.cy;
      }
      render();
    };

    const onEnd = (event: TouchEvent) => {
      if (!handling) return;
      prevent(event);
      if (event.touches.length) {
        begin(event.touches);
        return;
      }
      pinching = handling = false;
      start = pan = null;
      blockedUntil.current = performance.now() + 350;
      if (scale < FIT_THRESHOLD) { scale = 1; x = y = 0; }
      render();
    };

    const reset = () => {
      scale = 1; x = y = 0;
      pinching = handling = false;
      start = pan = null;
      blockedUntil.current = performance.now() + 350;
      render();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && locked.current) {
        event.preventDefault(); event.stopPropagation(); reset();
      }
    };
    const onScroll = () => {
      if (locked.current && pager && pager.scrollTop !== scrollTop) pager.scrollTop = scrollTop;
    };
    const onGesture = (event: Event) => { if (event.cancelable) event.preventDefault(); };
    stage.addEventListener("touchstart", onStart, { passive: false });
    stage.addEventListener("touchmove", onMove, { passive: false });
    stage.addEventListener("touchend", onEnd, { passive: false });
    stage.addEventListener("touchcancel", reset);
    // Safari also emits gesture events; keep its page zoom out of this surface.
    stage.addEventListener("gesturestart", onGesture, { passive: false });
    stage.addEventListener("gesturechange", onGesture, { passive: false });
    pager?.addEventListener("scroll", onScroll);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", reset);
    return () => {
      stage.removeEventListener("touchstart", onStart);
      stage.removeEventListener("touchmove", onMove);
      stage.removeEventListener("touchend", onEnd);
      stage.removeEventListener("touchcancel", reset);
      stage.removeEventListener("gesturestart", onGesture);
      stage.removeEventListener("gesturechange", onGesture);
      pager?.removeEventListener("scroll", onScroll);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("resize", reset);
      stage.removeAttribute("data-zoom-active");
      stage.removeAttribute("data-zoomed");
      stage.style.removeProperty("--media-zoom");
      locked.current = false;
      setEngaged(false);
    };
  }, [stageRef, enabled, active, mediaKey]);

  return { engaged, isBlocked: () => locked.current || performance.now() < blockedUntil.current };
}
