import { useCallback, useEffect, useEffectEvent, useRef, useState, type RefObject } from "react";

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export function usePagedWheel(scroller: RefObject<HTMLElement | null>, navigate: (delta: -1 | 1) => void) {
  const navigateByWheel = useEffectEvent(navigate);
  useEffect(() => {
    const node = scroller.current;
    if (!node) return;
    let lastEvent = 0;
    let lastNavigation = -Infinity;
    let lastMagnitude = 0;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) return;
      event.preventDefault();
      if (node.querySelector("[data-zoom-active]")) return;
      const now = performance.now();
      const delta = event.deltaY * (event.deltaMode === 1 ? 40 : 1);
      const magnitude = Math.abs(delta);
      const freshGesture =
        now - lastEvent > 180 ||
        (magnitude > lastMagnitude * 1.6 && magnitude > 20) ||
        (now - lastNavigation > 700 && magnitude >= 40);
      lastEvent = now;
      lastMagnitude = magnitude;
      if (freshGesture && magnitude >= 4 && now - lastNavigation > 280) {
        lastNavigation = now;
        navigateByWheel(delta > 0 ? 1 : -1);
      }
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [scroller]);
}

export function useMediaFullscreen(root: RefObject<HTMLElement | null>, available: boolean) {
  const [fullscreen, setFullscreen] = useState(false);
  const [exitVisible, setExitVisible] = useState(false);
  const timer = useRef(0);
  const requested = useRef(false);

  const revealExit = useCallback(() => {
    window.clearTimeout(timer.current);
    setExitVisible(true);
    timer.current = window.setTimeout(() => setExitVisible(false), 2200);
  }, []);

  const leave = useCallback(() => {
    requested.current = false;
    window.clearTimeout(timer.current);
    setFullscreen(false);
    setExitVisible(false);
    if (root.current && document.fullscreenElement === root.current) {
      void document.exitFullscreen().catch(() => undefined);
    }
  }, [root]);

  const enter = () => {
    const node = root.current;
    if (!available || !node) return;
    requested.current = true;
    setFullscreen(true);
    revealExit();
    // iPhone Safari can still fill the app viewport without native element fullscreen.
    if (document.fullscreenEnabled && !document.fullscreenElement && node.requestFullscreen) {
      void node.requestFullscreen().then(() => {
        if (!requested.current && document.fullscreenElement === node) {
          return document.exitFullscreen();
        }
      }).catch(() => undefined);
    }
  };

  useEffect(() => {
    const node = root.current;
    if (!node) return;
    let native = document.fullscreenElement === node;
    const onChange = () => {
      const wasNative = native;
      native = document.fullscreenElement === node;
      if (wasNative && !native) leave();
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      requested.current = false;
      window.clearTimeout(timer.current);
      if (document.fullscreenElement === node) void document.exitFullscreen().catch(() => undefined);
    };
  }, [root, leave]);

  useEffect(() => {
    if (!available && fullscreen) leave();
  }, [available, fullscreen, leave]);

  return { fullscreen: available && fullscreen, exitVisible, revealExit, enter, leave };
}
