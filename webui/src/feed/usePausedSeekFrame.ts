import { useCallback, useEffect, useRef, useState } from "react";

import { seekFrameUrl } from "./api";
import { seekVideo } from "./seekVideo";

const FRAME_WAIT_MS = 450;
const FRAME_TIME_TOLERANCE = 0.125;

/** Keep a paused seek visible even if the native video never presents its new frame. */
export function usePausedSeekFrame(path: string, active: boolean) {
  const [frame, setFrame] = useState<string>();
  const pending = useRef<(() => void) | undefined>(undefined);

  const clear = useCallback(() => {
    pending.current?.();
    setFrame(undefined);
  }, []);

  useEffect(() => {
    clear();
    return () => pending.current?.();
  }, [path, active, clear]);

  const seek = useCallback((video: HTMLVideoElement, time: number, commit = false) => {
    clear();
    if (video.paused && Number.isFinite(time) && Number.isFinite(video.duration)) {
      const target = Math.max(0, Math.min(time, video.duration));
      const source = video.currentSrc || video.src;
      const current = () => video.isConnected && video.paused && (video.currentSrc || video.src) === source;
      const timer = window.setTimeout(() => {
        if (pending.current === stop && current()) {
          // FFmpeg needs a frame before EOF when the progress bar is at its end.
          setFrame(seekFrameUrl(path, Math.max(0, Math.min(target, video.duration - 0.1))));
        }
      }, FRAME_WAIT_MS);
      let callback: number | undefined;
      const stop = () => {
        window.clearTimeout(timer);
        if (callback !== undefined) video.cancelVideoFrameCallback?.(callback);
        pending.current = undefined;
      };
      const presented: VideoFrameRequestCallback = (_now, metadata) => {
        if (pending.current !== stop) return;
        callback = undefined;
        if (!current()) {
          stop();
        } else if (Math.abs(metadata.mediaTime - target) <= FRAME_TIME_TOLERANCE) {
          clear();
        } else {
          callback = video.requestVideoFrameCallback(presented);
        }
      };
      pending.current = stop;
      callback = video.requestVideoFrameCallback?.(presented);
    }
    seekVideo(video, time, commit);
  }, [clear, path]);

  return { frame, seek, clear };
}
