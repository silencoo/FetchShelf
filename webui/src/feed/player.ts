/**
 * Recycled media elements for the feed.
 *
 * iOS allows audible playback only on an element that has started inside a user
 * gesture. Reusing a few "blessed" elements keeps sound on from swipe to swipe,
 * and also keeps us under the platform's limit on live video decoders.
 */

export type PlayerEvent = "loading" | "playing" | "paused" | "ended" | "error" | "meta" | "time";

export interface PlayerListener {
  (event: PlayerEvent, element: HTMLVideoElement): void;
}

export interface VideoBinding {
  key: string;
  src: string;
  host: HTMLElement;
  listener: PlayerListener;
}

const POOL_SIZE = 3;

function createVideo() {
  const video = document.createElement("video");
  video.className = "fa-video";
  video.playsInline = true;
  video.setAttribute("playsinline", "");
  video.setAttribute("webkit-playsinline", "");
  video.muted = true;
  video.defaultMuted = true;
  video.setAttribute("muted", "");
  video.loop = true;
  video.preload = "auto";
  video.disablePictureInPicture = true;
  video.setAttribute("disableremoteplayback", "");
  video.setAttribute("aria-hidden", "true");
  video.tabIndex = -1;
  return video;
}

class MediaPool {
  private videos: HTMLVideoElement[] = [];
  private owners = new Map<HTMLVideoElement, VideoBinding>();
  private activeKey: string | null = null;
  private music: HTMLAudioElement | null = null;
  private musicUrl = "";
  private wantMusic = false;
  private userPaused = false;
  private loopVideo = true;
  private soundWanted = true;
  private backgrounded = false;

  /** Audible playback has been allowed by a gesture on this page. */
  unlocked = false;
  /** The event that unlocked sound, so it is not also treated as a tap. */
  unlockEvent: Event | null = null;
  /** Autoplay was refused entirely, as in iOS Low Power Mode. */
  blocked = false;

  private ensureElements() {
    if (this.videos.length) {
      return;
    }
    for (let index = 0; index < POOL_SIZE; index += 1) {
      const video = createVideo();
      this.bindEvents(video);
      this.videos.push(video);
    }
    this.music = document.createElement("audio");
    this.music.loop = true;
    this.music.preload = "none";
    this.music.addEventListener("error", () => {
      // Remote soundtrack links expire; the photos stay watchable in silence.
      this.musicUrl = "";
    });
  }

  private bindEvents(video: HTMLVideoElement) {
    const forward = (event: PlayerEvent) => {
      const binding = this.owners.get(video);
      if (binding) {
        binding.listener(event, video);
      }
    };
    video.addEventListener("loadedmetadata", () => forward("meta"));
    video.addEventListener("waiting", () => forward("loading"));
    video.addEventListener("stalled", () => forward("loading"));
    video.addEventListener("playing", () => {
      video.dataset.ready = "1";
      forward("playing");
    });
    video.addEventListener("pause", () => forward("paused"));
    video.addEventListener("ended", () => forward("ended"));
    video.addEventListener("timeupdate", () => forward("time"));
    video.addEventListener("error", () => forward("error"));
  }

  private isActive(video: HTMLVideoElement) {
    return this.owners.get(video)?.key === this.activeKey && this.activeKey !== null;
  }

  private assign(video: HTMLVideoElement, binding: VideoBinding) {
    video.pause();
    delete video.dataset.ready;
    delete video.dataset.primed;
    delete video.dataset.priming;
    this.owners.set(video, binding);
    binding.host.appendChild(video);
    video.muted = true;
    video.playbackRate = 1;
    video.src = binding.src;
    video.load();
  }

  /** Give neighbouring slides an element; only the active one ever plays. */
  sync(bindings: VideoBinding[], activeKey: string | null, { prime = false } = {}) {
    this.ensureElements();
    const wanted = new Set(bindings.map((binding) => binding.key));
    const held = new Map<string, HTMLVideoElement>();
    for (const [video, binding] of this.owners) {
      if (wanted.has(binding.key)) {
        held.set(binding.key, video);
      } else {
        video.pause();
        this.owners.delete(video);
      }
    }
    const previousActive = this.activeKey;
    this.activeKey = activeKey;
    for (const binding of bindings) {
      const video = held.get(binding.key);
      if (video) {
        this.owners.set(video, binding);
        if (video.parentElement !== binding.host) {
          binding.host.appendChild(video);
        }
      } else {
        const free = this.videos.find((candidate) => !this.owners.has(candidate));
        if (free) {
          this.assign(free, binding);
        }
      }
    }
    for (const [video, binding] of this.owners) {
      if (binding.key === activeKey) {
        if (previousActive !== activeKey) {
          if (video.dataset.ready && video.currentTime > 0.05) {
            video.currentTime = 0;
          }
          video.playbackRate = 1;
        }
        video.loop = this.loopVideo;
        if (!this.userPaused) {
          void this.start(video);
        }
      } else {
        if (!video.dataset.priming) {
          video.pause();
        }
        if (prime) {
          this.prime(video);
        }
      }
    }
    if (activeKey !== previousActive) {
      this.blocked = false;
    }
  }

  /** iOS ignores `preload` until playback; a silent start buffers the next post. */
  private prime(video: HTMLVideoElement) {
    if (video.dataset.primed || video.readyState >= 3) {
      return;
    }
    video.dataset.primed = "1";
    video.dataset.priming = "1";
    video.muted = true;
    const stop = () => {
      video.removeEventListener("playing", stop);
      delete video.dataset.priming;
      if (!this.isActive(video)) {
        video.pause();
        video.currentTime = 0;
      }
    };
    video.addEventListener("playing", stop);
    void video.play().catch(() => {
      video.removeEventListener("playing", stop);
      delete video.dataset.priming;
    });
  }

  private async start(video: HTMLVideoElement) {
    if (this.backgrounded) {
      return;
    }
    video.muted = !(this.unlocked && this.soundWanted);
    try {
      await video.play();
      this.blocked = false;
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== "NotAllowedError") {
        return;
      }
      if (!video.muted) {
        video.muted = true;
        try {
          await video.play();
          return;
        } catch {
          // Fall through: not even muted playback is allowed right now.
        }
      }
      this.blocked = true;
      this.owners.get(video)?.listener("paused", video);
    }
  }

  active() {
    for (const [video, binding] of this.owners) {
      if (binding.key === this.activeKey) {
        return video;
      }
    }
    return null;
  }

  isPaused() {
    return this.userPaused;
  }

  clearPause() {
    this.userPaused = false;
  }

  setUserPaused(paused: boolean) {
    this.userPaused = paused;
    const video = this.active();
    if (video) {
      if (paused) {
        video.pause();
      } else {
        void this.start(video);
      }
    }
    this.applyMusic();
  }

  setLoop(loop: boolean) {
    this.loopVideo = loop;
    const video = this.active();
    if (video) {
      video.loop = loop;
    }
  }

  setSoundWanted(wanted: boolean) {
    this.soundWanted = wanted;
    const video = this.active();
    if (video && this.unlocked) {
      video.muted = !wanted;
    }
    this.applyMusic();
  }

  /** Must run inside a real click or key press. Safe to call repeatedly. */
  unlock(event: Event | null = null) {
    this.ensureElements();
    if (this.unlocked) {
      return false;
    }
    this.unlocked = true;
    this.unlockEvent = event;
    for (const video of this.videos) {
      if (this.isActive(video)) {
        video.muted = !this.soundWanted;
        if (!this.userPaused) {
          void video.play().catch(() => undefined);
        }
      } else if (video.currentSrc) {
        // Starting and stopping in the gesture blesses the element for later.
        const wasPaused = video.paused;
        video.muted = false;
        void video.play().catch(() => undefined);
        if (wasPaused) {
          video.pause();
        }
        video.muted = true;
      } else {
        video.load();
      }
    }
    this.music?.load();
    this.applyMusic();
    return true;
  }

  /** Soundtrack for photo posts, which have no audio of their own. */
  setMusic(url: string) {
    this.ensureElements();
    this.wantMusic = Boolean(url);
    if (url !== this.musicUrl && this.music) {
      this.musicUrl = url;
      this.music.pause();
      if (url) {
        this.music.src = url;
        this.music.currentTime = 0;
      } else {
        this.music.removeAttribute("src");
        this.music.load();
      }
    }
    this.applyMusic();
  }

  private applyMusic() {
    const music = this.music;
    if (!music) {
      return;
    }
    if (
      this.wantMusic &&
      this.musicUrl &&
      this.unlocked &&
      this.soundWanted &&
      !this.userPaused &&
      !this.backgrounded
    ) {
      void music.play().catch(() => undefined);
    } else {
      music.pause();
    }
  }

  /** The app left the foreground: go quiet, then pick up where the viewer was. */
  setBackgrounded(hidden: boolean) {
    this.backgrounded = hidden;
    const video = this.active();
    if (video) {
      if (hidden) {
        video.pause();
      } else if (!this.userPaused) {
        void this.start(video);
      }
    }
    this.applyMusic();
  }

  /** Stop everything when the feed is hidden; elements stay blessed for return. */
  suspend() {
    this.activeKey = null;
    this.setMusic("");
    for (const video of this.videos) {
      video.pause();
    }
  }

  release() {
    this.suspend();
    this.owners.clear();
    for (const video of this.videos) {
      video.remove();
      video.removeAttribute("src");
      video.load();
    }
  }
}

export const mediaPool = new MediaPool();
