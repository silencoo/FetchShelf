/** Correct a backwards media-clock jump during resume, without seeking normally. */
export async function resumeVideo(video: HTMLVideoElement): Promise<void> {
  const position = video.currentTime;
  if (!video.paused || video.seeking || position < 0.1 ||
      !Number.isFinite(video.duration) || video.duration - position < 0.75) {
    return video.play();
  }
  const source = video.currentSrc || video.src;
  let frame = 0;
  let timer = 0;
  let cancelled = false;
  const stop = () => {
    cancelled = true;
    cancelAnimationFrame(frame);
    window.clearTimeout(timer);
    video.removeEventListener("seeking", stop);
    video.removeEventListener("pause", stop);
    video.removeEventListener("emptied", stop);
  };
  const check = () => {
    if (cancelled) return;
    if (video.paused || video.ended || video.seeking ||
        (video.currentSrc || video.src) !== source) {
      stop();
      return;
    }
    if (video.currentTime < position - 0.05) {
      stop();
      video.currentTime = position;
      return;
    }
    frame = requestAnimationFrame(check);
  };
  // Intentional seeks and element recycling must never restore an old position.
  video.addEventListener("seeking", stop);
  video.addEventListener("pause", stop);
  video.addEventListener("emptied", stop);
  timer = window.setTimeout(stop, 1000);
  try {
    await video.play();
    if (!cancelled) {
      window.clearTimeout(timer);
      timer = window.setTimeout(stop, 500);
      check();
    }
  } catch (error) {
    stop();
    throw error;
  }
}
