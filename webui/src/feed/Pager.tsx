import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type MutableRefObject,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { api, avatarUrl, fileUrl, thumbUrl } from "./api";
import { formatCount, formatDuration, formatRelativeTime, initialOf, splitCaption } from "./format";
import {
  BookmarkIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  CommentIcon,
  FullscreenIcon,
  HeartIcon,
  MusicIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  ShareIcon,
} from "./icons";
import { mediaPool, type PlayerEvent, type PlayerListener, type VideoBinding } from "./player";
import { marks, preferences, useObservable, type PostList } from "./store";
import type { Post } from "./types";

const OVERSCAN = 2;
const LOAD_AHEAD = 4;
const IMAGE_SECONDS = 4;
const SETTLE_FRAMES = 6;
const SETTLE_FRAMES_MAX = 90;

const prefersTouch = () => window.matchMedia("(hover: none), (pointer: coarse)").matches;
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export interface PagerActions {
  openProfile(post: Post): void;
  openPanel(post: Post, tab: "comments" | "details"): void;
  openShare(post: Post): void;
  openTag(tag: string): void;
  openMusic(title: string): void;
}

export interface PagerHandle {
  next(): void;
  previous(): void;
  togglePause(): void;
  seek(delta: number): void;
  slide(delta: number): boolean;
  post(): Post | undefined;
}

/** Remembers the visible photo per post, for the download action. */
export const carouselPositions = new Map<string, number>();

interface SlideRegistration {
  host: HTMLElement;
  listener: PlayerListener;
}

type Register = (key: string, entry: SlideRegistration | null) => void;

function clampRatio(width: number | null | undefined, height: number | null | undefined) {
  if (!width || !height) {
    return null;
  }
  return Math.min(1.9, Math.max(0.5, width / height));
}

/** Tap, double tap and long press on the media surface. */
function useSurfaceGestures(options: {
  onTap(): void;
  onDoubleTap(x: number, y: number): void;
  onLongPress?(active: boolean): void;
}) {
  const latest = useRef(options);
  latest.current = options;
  const gesture = useRef({
    x: 0,
    y: 0,
    id: -1,
    pressed: false,
    moved: false,
    timer: 0,
    lastTap: 0,
    lastX: 0,
    lastY: 0,
    tapTimer: 0,
    suppressClick: false,
  });

  const endPress = useCallback(() => {
    const state = gesture.current;
    window.clearTimeout(state.timer);
    if (state.pressed) {
      state.pressed = false;
      state.suppressClick = true;
      latest.current.onLongPress?.(false);
    }
  }, []);

  useEffect(
    () => () => {
      window.clearTimeout(gesture.current.timer);
      window.clearTimeout(gesture.current.tapTimer);
    },
    [],
  );

  return {
    onPointerDown(event: ReactPointerEvent<HTMLElement>) {
      if (event.pointerType === "mouse" && event.button !== 0) {
        return;
      }
      const state = gesture.current;
      state.x = event.clientX;
      state.y = event.clientY;
      state.id = event.pointerId;
      state.moved = false;
      state.suppressClick = false;
      window.clearTimeout(state.timer);
      if (latest.current.onLongPress) {
        state.timer = window.setTimeout(() => {
          if (!state.moved) {
            state.pressed = true;
            latest.current.onLongPress?.(true);
          }
        }, 420);
      }
    },
    onPointerMove(event: ReactPointerEvent<HTMLElement>) {
      const state = gesture.current;
      if (event.pointerId !== state.id) {
        return;
      }
      if (Math.abs(event.clientX - state.x) > 10 || Math.abs(event.clientY - state.y) > 10) {
        state.moved = true;
        window.clearTimeout(state.timer);
      }
    },
    onPointerUp() {
      endPress();
      gesture.current.id = -1;
    },
    onPointerCancel() {
      endPress();
      gesture.current.id = -1;
    },
    onClick(event: ReactMouseEvent<HTMLElement>) {
      const state = gesture.current;
      if (state.suppressClick) {
        state.suppressClick = false;
        return;
      }
      if (event.nativeEvent === mediaPool.unlockEvent && preferences.sound) {
        // The first tap turned sound on; it should not also pause the video.
        return;
      }
      const now = performance.now();
      const near =
        Math.abs(event.clientX - state.lastX) < 48 && Math.abs(event.clientY - state.lastY) < 48;
      if (now - state.lastTap < 280 && near) {
        window.clearTimeout(state.tapTimer);
        state.lastTap = 0;
        latest.current.onDoubleTap(event.clientX, event.clientY);
        return;
      }
      state.lastTap = now;
      state.lastX = event.clientX;
      state.lastY = event.clientY;
      window.clearTimeout(state.tapTimer);
      state.tapTimer = window.setTimeout(() => latest.current.onTap(), 280);
    },
    onContextMenu(event: ReactMouseEvent<HTMLElement>) {
      if (prefersTouch()) {
        event.preventDefault();
      }
    },
  };
}

/**
 * A left swipe anywhere on a slide opens the author, including from the action
 * rail, which is exactly where a right thumb tends to start.
 */
function useSwipeLeft(onSwipe: () => void) {
  const latest = useRef(onSwipe);
  latest.current = onSwipe;
  const gesture = useRef({ id: -1, x: 0, y: 0, horizontal: false });
  return {
    onPointerDown(event: ReactPointerEvent<HTMLElement>) {
      if (event.pointerType !== "mouse") {
        gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, horizontal: false };
      }
    },
    onPointerMove(event: ReactPointerEvent<HTMLElement>) {
      const state = gesture.current;
      if (event.pointerId === state.id) {
        const dx = event.clientX - state.x;
        if (Math.abs(dx) > 14 && Math.abs(dx) > Math.abs(event.clientY - state.y) * 1.6) {
          state.horizontal = true;
        }
      }
    },
    onPointerUp(event: ReactPointerEvent<HTMLElement>) {
      const state = gesture.current;
      if (event.pointerId === state.id && state.horizontal && event.clientX - state.x < -56) {
        latest.current();
      }
      state.id = -1;
    },
    onPointerCancel() {
      gesture.current.id = -1;
    },
  };
}

interface Burst {
  id: number;
  x: number;
  y: number;
  tilt: number;
}

function useHeartBursts() {
  const [bursts, setBursts] = useState<Burst[]>([]);
  const counter = useRef(0);
  const add = useCallback((x: number, y: number) => {
    counter.current += 1;
    const id = counter.current;
    setBursts((current) => [...current, { id, x, y, tilt: Math.random() * 40 - 20 }]);
    window.setTimeout(() => {
      setBursts((current) => current.filter((burst) => burst.id !== id));
    }, 800);
  }, []);
  return { bursts, add };
}

function Bursts({ bursts, box }: { bursts: Burst[]; box: HTMLElement | null }) {
  if (!bursts.length || !box) {
    return null;
  }
  const rect = box.getBoundingClientRect();
  return (
    <>
      {bursts.map((burst) => (
        <span
          key={burst.id}
          className="fa-burst"
          style={
            {
              left: burst.x - rect.left,
              top: burst.y - rect.top,
              "--tilt": `${burst.tilt}deg`,
            } as CSSProperties
          }
        >
          <HeartIcon size={96} />
        </span>
      ))}
    </>
  );
}

function Avatar({ post, size = 48 }: { post: Post; size?: number }) {
  const [failed, setFailed] = useState(false);
  const url = avatarUrl(post.author.avatar);
  return (
    <span className="fa-avatar" style={{ width: size, height: size }}>
      {url && !failed ? (
        <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <span className="fa-avatar-fallback">{initialOf(post.author.name)}</span>
      )}
    </span>
  );
}

const Caption = memo(function Caption({
  post,
  isActive,
  actions,
}: {
  post: Post;
  isActive: boolean;
  actions: PagerActions;
}) {
  const [expanded, setExpanded] = useState(false);
  const parts = useMemo(() => splitCaption(post.caption), [post.caption]);
  const time = formatRelativeTime(post.published_ts);
  useEffect(() => {
    if (!isActive) {
      setExpanded(false);
    }
  }, [isActive]);
  return (
    <div className={`fa-caption${expanded ? " is-expanded" : ""}`}>
      <div className="fa-caption-head">
        <button type="button" className="fa-caption-name" onClick={() => actions.openProfile(post)}>
          @{post.author.name}
        </button>
        {time ? <span className="fa-caption-time">· {time}</span> : null}
      </div>
      {parts.length ? (
        <p className="fa-caption-text">
          {parts.map((part, index) =>
            part.tag ? (
              <button
                key={index}
                type="button"
                className="fa-tag"
                onClick={() => actions.openTag(part.tag ?? "")}
              >
                {part.text}
              </button>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </p>
      ) : null}
      {post.caption.length > 42 ? (
        <button type="button" className="fa-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起" : "展开"}
        </button>
      ) : null}
      {post.music?.title ? (
        <button
          type="button"
          className="fa-music-line"
          onClick={() => actions.openMusic(post.music?.title ?? "")}
        >
          <MusicIcon size={14} />
          <span className="fa-marquee">
            <span className={isActive ? "is-running" : ""}>
              {post.music.title}
              {post.music.author ? ` · ${post.music.author}` : ""}
            </span>
          </span>
        </button>
      ) : null}
    </div>
  );
});

const Rail = memo(function Rail({
  post,
  isActive,
  actions,
}: {
  post: Post;
  isActive: boolean;
  actions: PagerActions;
}) {
  useObservable(marks);
  const liked = marks.isLiked(post);
  const saved = marks.isSaved(post);
  const followed = marks.isFollowed(post.author);
  const likes = marks.displayCount(post.stats?.likes, post, "like");
  const saves = marks.displayCount(post.stats?.saves, post, "save");
  return (
    <div className="fa-rail">
      <div className="fa-rail-author">
        <button
          type="button"
          className="fa-rail-avatar"
          aria-label={`打开 ${post.author.name} 的主页`}
          onClick={() => actions.openProfile(post)}
        >
          <Avatar post={post} />
        </button>
        <button
          type="button"
          className={`fa-follow-badge${followed ? " is-on" : ""}`}
          aria-pressed={followed}
          aria-label={followed ? "取消关注" : "关注"}
          onClick={() => void marks.toggleFollow(post.author)}
        >
          {followed ? <CheckIcon size={12} /> : <PlusIcon size={12} />}
        </button>
      </div>
      <button
        type="button"
        className={`fa-rail-btn fa-like${liked ? " is-on" : ""}`}
        aria-pressed={liked}
        aria-label={liked ? "取消喜欢" : "喜欢"}
        onClick={() => void marks.toggleLike(post)}
      >
        <span className="fa-rail-icon">
          <HeartIcon size={30} />
        </span>
        <span className="fa-rail-count">{likes ? formatCount(likes) : "喜欢"}</span>
      </button>
      <button
        type="button"
        className="fa-rail-btn"
        aria-label="评论"
        onClick={() => actions.openPanel(post, "comments")}
      >
        <span className="fa-rail-icon">
          <CommentIcon size={28} />
        </span>
        <span className="fa-rail-count">
          {post.stats?.comments ? formatCount(post.stats.comments) : "评论"}
        </span>
      </button>
      <button
        type="button"
        className={`fa-rail-btn fa-save${saved ? " is-on" : ""}`}
        aria-pressed={saved}
        aria-label={saved ? "取消收藏" : "收藏"}
        onClick={() => void marks.toggleSave(post)}
      >
        <span className="fa-rail-icon">
          <BookmarkIcon size={28} />
        </span>
        <span className="fa-rail-count">{saves ? formatCount(saves) : "收藏"}</span>
      </button>
      <button
        type="button"
        className="fa-rail-btn"
        aria-label="分享与更多操作"
        onClick={() => actions.openShare(post)}
      >
        <span className="fa-rail-icon">
          <ShareIcon size={28} />
        </span>
        <span className="fa-rail-count">
          {post.stats?.shares ? formatCount(post.stats.shares) : "分享"}
        </span>
      </button>
      {post.music ? (
        <button
          type="button"
          className={`fa-disc${isActive ? " is-spinning" : ""}`}
          aria-label={post.music.title ? `音乐：${post.music.title}` : "音乐"}
          onClick={() => post.music?.title && actions.openMusic(post.music.title)}
        >
          <Avatar post={post} size={28} />
        </button>
      ) : null}
    </div>
  );
});

function VideoSlide({
  post,
  isActive,
  register,
  actions,
  onEnded,
  surfaceRef,
}: {
  post: Post;
  isActive: boolean;
  register: Register;
  actions: PagerActions;
  onEnded(): void;
  surfaceRef: MutableRefObject<SlideControls | null>;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [paused, setPaused] = useState(false);
  const [fast, setFast] = useState(false);
  const [landscape, setLandscape] = useState(
    Boolean(post.width && post.height && post.width > post.height),
  );
  const [scrubbing, setScrubbing] = useState(false);
  const [scrubLabel, setScrubLabel] = useState("");
  const scrubbingRef = useRef(false);
  const { bursts, add } = useHeartBursts();
  const activeRef = useRef(isActive);
  activeRef.current = isActive;
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  const listener = useCallback<PlayerListener>((event: PlayerEvent, video) => {
    if (event === "meta") {
      const box = boxRef.current;
      if (box && video.videoWidth) {
        setLandscape(video.videoWidth > video.videoHeight);
        const ratio = clampRatio(video.videoWidth, video.videoHeight);
        if (ratio) {
          box.closest<HTMLElement>(".fa-slide")?.style.setProperty("--ar", String(ratio));
        }
      }
      return;
    }
    if (event === "error") {
      setStatus("error");
      return;
    }
    if (!activeRef.current) {
      return;
    }
    if (event === "loading") {
      setStatus((current) => (current === "error" ? current : "loading"));
    } else if (event === "playing") {
      setStatus("ready");
      setPaused(false);
    } else if (event === "paused") {
      setPaused(mediaPool.isPaused() || mediaPool.blocked);
    } else if (event === "ended") {
      onEndedRef.current();
    }
  }, []);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) {
      return;
    }
    register(post.key, { host, listener });
    return () => register(post.key, null);
  }, [listener, post.key, register]);

  useEffect(() => {
    if (!isActive) {
      setPaused(false);
      setFast(false);
      return;
    }
    let frame = 0;
    const tick = () => {
      const video = mediaPool.active();
      const bar = barRef.current;
      if (video && bar && !scrubbingRef.current && video.duration) {
        bar.style.transform = `scaleX(${Math.min(1, video.currentTime / video.duration)})`;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [isActive]);

  const togglePause = useCallback(() => {
    const next = mediaPool.blocked ? false : !mediaPool.isPaused();
    mediaPool.setUserPaused(next);
    setPaused(next);
  }, []);

  useEffect(() => {
    if (isActive) {
      surfaceRef.current = {
        togglePause,
        seek(delta) {
          const video = mediaPool.active();
          if (video) {
            video.currentTime = Math.max(0, video.currentTime + delta);
          }
        },
        slide() {
          return false;
        },
      };
    }
  }, [isActive, surfaceRef, togglePause]);

  const gestures = useSurfaceGestures({
    onTap: togglePause,
    onDoubleTap(x, y) {
      add(x, y);
      void marks.setLike(post, true);
    },
    onLongPress(active) {
      const video = mediaPool.active();
      if (video) {
        video.playbackRate = active ? 2 : 1;
      }
      setFast(active);
    },
  });

  const scrubTo = (event: ReactPointerEvent<HTMLElement>) => {
    const video = mediaPool.active();
    const rect = event.currentTarget.getBoundingClientRect();
    if (!video || !video.duration || !rect.width) {
      return;
    }
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    video.currentTime = ratio * video.duration;
    if (barRef.current) {
      barRef.current.style.transform = `scaleX(${ratio})`;
    }
    setScrubLabel(`${formatDuration(ratio * video.duration)} / ${formatDuration(video.duration)}`);
  };

  const enterFullscreen = () => {
    const video = mediaPool.active() as
      | (HTMLVideoElement & { webkitEnterFullscreen?: () => void })
      | null;
    if (!video) {
      return;
    }
    if (video.webkitEnterFullscreen && !document.fullscreenEnabled) {
      video.webkitEnterFullscreen();
    } else {
      void hostRef.current?.requestFullscreen?.();
    }
  };

  return (
    <div className={`fa-stage${scrubbing ? " is-scrubbing" : ""}`} ref={boxRef}>
      <img className="fa-poster" src={thumbUrl(post.cover)} alt="" decoding="async" />
      <div className="fa-video-host" ref={hostRef} />
      <div className="fa-surface fa-surface-video" {...gestures} />
      {paused ? (
        <span className="fa-center-icon">
          <PlayIcon size={72} />
        </span>
      ) : null}
      {status === "loading" && isActive ? <span className="fa-spinner fa-center-spinner" /> : null}
      {status === "error" ? <span className="fa-media-error">这条视频暂时无法播放</span> : null}
      {fast ? <span className="fa-speed-chip">2 倍速播放中</span> : null}
      {landscape && isActive ? (
        <button type="button" className="fa-fullscreen" onClick={enterFullscreen}>
          <FullscreenIcon size={15} /> 全屏观看
        </button>
      ) : null}
      <Bursts bursts={bursts} box={boxRef.current} />
      <div
        className="fa-seek"
        aria-hidden="true"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          scrubbingRef.current = true;
          setScrubbing(true);
          scrubTo(event);
        }}
        onPointerMove={(event) => {
          if (scrubbingRef.current) {
            scrubTo(event);
          }
        }}
        onPointerUp={() => {
          scrubbingRef.current = false;
          setScrubbing(false);
        }}
        onPointerCancel={() => {
          scrubbingRef.current = false;
          setScrubbing(false);
        }}
      >
        <div className="fa-seek-track">
          <div className="fa-seek-bar" ref={barRef} />
        </div>
      </div>
      {scrubbing && scrubLabel ? <span className="fa-seek-time">{scrubLabel}</span> : null}
    </div>
  );
}

interface SlideControls {
  togglePause(): void;
  seek(delta: number): void;
  slide(delta: number): boolean;
}

function CarouselItem({
  post,
  index,
  current,
  isActive,
}: {
  post: Post;
  index: number;
  current: number;
  isActive: boolean;
}) {
  const item = post.media[index];
  const near = Math.abs(index - current) <= 1;
  const playing = item.kind === "video" && isActive && index === current;
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = videoRef.current;
    if (video && playing) {
      video.muted = true;
      void video.play().catch(() => undefined);
    }
  }, [playing]);
  if (!near) {
    return <div className="fa-carousel-item" />;
  }
  return (
    <div className="fa-carousel-item">
      {item.kind === "image" ? (
        <img
          src={fileUrl(item.path)}
          alt=""
          decoding="async"
          draggable={false}
          onLoad={(event) => {
            const image = event.currentTarget;
            const ratio = clampRatio(image.naturalWidth, image.naturalHeight);
            if (index === 0 && ratio) {
              image.closest<HTMLElement>(".fa-slide")?.style.setProperty("--ar", String(ratio));
            }
          }}
        />
      ) : playing ? (
        <video
          ref={videoRef}
          src={fileUrl(item.path)}
          poster={thumbUrl(item.path)}
          muted
          loop
          playsInline
          preload="auto"
        />
      ) : (
        <img src={thumbUrl(item.path)} alt="" decoding="async" draggable={false} />
      )}
    </div>
  );
}

function ImageSlide({
  post,
  isActive,
  onEnded,
  surfaceRef,
}: {
  post: Post;
  isActive: boolean;
  onEnded(): void;
  surfaceRef: MutableRefObject<SlideControls | null>;
}) {
  useObservable(preferences);
  const boxRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [current, setCurrent] = useState(0);
  const [paused, setPaused] = useState(false);
  const { bursts, add } = useHeartBursts();
  const count = post.media.length;
  const currentRef = useRef(0);
  currentRef.current = current;

  const goTo = useCallback(
    (index: number, smooth = true) => {
      const scroller = scrollerRef.current;
      if (!scroller) {
        return;
      }
      const target = Math.max(0, Math.min(count - 1, index));
      scroller.scrollTo({
        left: target * scroller.clientWidth,
        behavior: smooth && !reducedMotion() ? "smooth" : "auto",
      });
    },
    [count],
  );

  useEffect(() => {
    carouselPositions.set(post.key, current);
  }, [current, post.key]);

  useEffect(() => {
    if (!isActive) {
      setPaused(false);
      return;
    }
    if (paused) {
      return;
    }
    const timer = window.setTimeout(() => {
      const next = current + 1;
      if (next < count) {
        goTo(next);
      } else if (preferences.autoNext) {
        onEnded();
      } else if (count > 1) {
        goTo(0);
      }
    }, IMAGE_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [count, current, goTo, isActive, onEnded, paused]);

  const togglePause = useCallback(() => {
    const next = !mediaPool.isPaused();
    mediaPool.setUserPaused(next);
    setPaused(next);
  }, []);

  useEffect(() => {
    if (isActive) {
      surfaceRef.current = {
        togglePause,
        seek() {},
        slide(delta) {
          if (count < 2) {
            return false;
          }
          goTo(currentRef.current + delta);
          return true;
        },
      };
    }
  }, [count, goTo, isActive, surfaceRef, togglePause]);

  const gestures = useSurfaceGestures({
    onTap: togglePause,
    onDoubleTap(x, y) {
      add(x, y);
      void marks.setLike(post, true);
    },
  });

  return (
    <div className="fa-stage" ref={boxRef}>
      <div
        className="fa-carousel"
        ref={scrollerRef}
        {...gestures}
        onScroll={(event) => {
          const element = event.currentTarget;
          const index = Math.round(element.scrollLeft / Math.max(1, element.clientWidth));
          if (index !== currentRef.current) {
            setCurrent(index);
          }
        }}
      >
        {post.media.map((item, index) => (
          <CarouselItem
            key={item.path}
            post={post}
            index={index}
            current={current}
            isActive={isActive}
          />
        ))}
      </div>
      {paused ? (
        <span className="fa-center-icon">
          <PauseIcon size={64} />
        </span>
      ) : null}
      {count > 1 ? (
        <>
          <button
            type="button"
            className="fa-carousel-arrow is-left"
            aria-label="上一张"
            disabled={current === 0}
            onClick={() => goTo(current - 1)}
          >
            <ChevronLeftIcon size={22} />
          </button>
          <button
            type="button"
            className="fa-carousel-arrow is-right"
            aria-label="下一张"
            disabled={current === count - 1}
            onClick={() => goTo(current + 1)}
          >
            <ChevronRightIcon size={22} />
          </button>
          <span className="fa-carousel-count">
            {current + 1}/{count}
          </span>
          {count <= 16 ? (
            <div className="fa-dots" aria-hidden="true">
              {post.media.map((item, index) => (
                <span key={item.path} className={index === current ? "is-on" : ""} />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      <Bursts bursts={bursts} box={boxRef.current} />
    </div>
  );
}

const Slide = memo(function Slide({
  post,
  index,
  height,
  isActive,
  register,
  actions,
  onEnded,
  surfaceRef,
}: {
  post: Post;
  index: number;
  height: number;
  isActive: boolean;
  register: Register;
  actions: PagerActions;
  onEnded(): void;
  surfaceRef: MutableRefObject<SlideControls | null>;
}) {
  const ratio = clampRatio(post.width, post.height) ?? (post.kind === "video" ? 0.5625 : 0.75);
  const swipe = useSwipeLeft(() => actions.openProfile(post));
  return (
    <article
      className={`fa-slide${isActive ? " is-active" : ""}`}
      style={{ top: index * height, height, "--ar": ratio } as CSSProperties}
      aria-label={`${post.author.name} 的作品`}
      aria-current={isActive ? "true" : undefined}
      {...(post.kind === "video" ? swipe : undefined)}
    >
      <img className="fa-backdrop" src={thumbUrl(post.cover)} alt="" decoding="async" />
      <div className="fa-slide-inner">
        <div className="fa-stage-wrap">
          {post.kind === "video" ? (
            <VideoSlide
              post={post}
              isActive={isActive}
              register={register}
              actions={actions}
              onEnded={onEnded}
              surfaceRef={surfaceRef}
            />
          ) : (
            <ImageSlide
              post={post}
              isActive={isActive}
              onEnded={onEnded}
              surfaceRef={surfaceRef}
            />
          )}
          <Caption post={post} isActive={isActive} actions={actions} />
        </div>
        <Rail post={post} isActive={isActive} actions={actions} />
      </div>
    </article>
  );
});

export function Pager({
  list,
  initialIndex = 0,
  current,
  actions,
  handleRef,
  empty,
  ariaLabel,
  onActivePost,
}: {
  list: PostList;
  initialIndex?: number;
  current: boolean;
  actions: PagerActions;
  handleRef: MutableRefObject<PagerHandle | null>;
  empty?: ReactNode;
  ariaLabel: string;
  onActivePost?(post: Post): void;
}) {
  useObservable(list);
  useObservable(preferences);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  const heightRef = useRef(0);
  heightRef.current = height;
  const settlingRef = useRef(false);
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const activeRef = useRef(initialIndex);
  activeRef.current = activeIndex;
  const registrations = useRef(new Map<string, SlideRegistration>());
  const [registrationVersion, setRegistrationVersion] = useState(0);
  const surfaceRef = useRef<SlideControls | null>(null);
  const lastActiveKey = useRef<string | null>(null);
  const items = list.items;
  const count = items.length;
  const hasFooter = list.loading || Boolean(list.error) || (!list.hasMore && count > 0);

  const register = useCallback<Register>((key, entry) => {
    if (entry) {
      registrations.current.set(key, entry);
    } else {
      registrations.current.delete(key);
    }
    setRegistrationVersion((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!list.items.length) {
      void list.load();
    }
  }, [list]);

  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      return;
    }
    const measure = () => {
      if (scroller.clientHeight > 0) {
        setHeight(scroller.clientHeight);
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  // An emptied list is a new list: it starts from the top, not the old position.
  useLayoutEffect(() => {
    if (count === 0) {
      activeRef.current = 0;
      setActiveIndex(0);
    }
  }, [count]);

  // A size change moves every snap point, and the browser then re-snaps to the
  // point nearest the OLD offset, which is a different post. One write cannot win
  // that race, so hold the right position with snapping off until it stays put.
  // Rotation, hidden tabs and opening from a grid all rely on this.
  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || height <= 0) {
      return;
    }
    const target = () => activeRef.current * height;
    settlingRef.current = true;
    scroller.style.scrollSnapType = "none";
    scroller.scrollTop = target();
    let frames = 0;
    let stableFrames = 0;
    let frame = requestAnimationFrame(function hold() {
      frames += 1;
      if (Math.abs(scroller.scrollTop - target()) > 1) {
        scroller.scrollTop = target();
        stableFrames = 0;
      } else {
        stableFrames += 1;
      }
      if (stableFrames >= SETTLE_FRAMES || frames >= SETTLE_FRAMES_MAX) {
        scroller.style.scrollSnapType = "";
        settlingRef.current = false;
      } else {
        frame = requestAnimationFrame(hold);
      }
    });
    return () => {
      cancelAnimationFrame(frame);
      scroller.style.scrollSnapType = "";
      settlingRef.current = false;
    };
  }, [height, count > 0]);

  const goTo = useCallback((index: number) => {
    const scroller = scrollerRef.current;
    if (!scroller || !scroller.clientHeight) {
      return;
    }
    scroller.scrollTo({
      top: Math.max(0, index) * scroller.clientHeight,
      behavior: reducedMotion() ? "auto" : "smooth",
    });
  }, []);

  const next = useCallback(() => {
    if (activeRef.current < list.items.length - 1) {
      goTo(activeRef.current + 1);
    }
  }, [goTo, list]);
  const previous = useCallback(() => goTo(activeRef.current - 1), [goTo]);

  useEffect(() => {
    if (!current) {
      return;
    }
    handleRef.current = {
      next,
      previous,
      togglePause: () => surfaceRef.current?.togglePause(),
      seek: (delta) => surfaceRef.current?.seek(delta),
      slide: (delta) => surfaceRef.current?.slide(delta) ?? false,
      post: () => list.items[activeRef.current],
    };
  }, [current, handleRef, list, next, previous]);

  // Desktop wheels and trackpads: one gesture moves exactly one post.
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      return;
    }
    let lastEvent = 0;
    let lastNavigation = 0;
    let lastMagnitude = 0;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) {
        return;
      }
      event.preventDefault();
      const now = performance.now();
      const delta = event.deltaY * (event.deltaMode === 1 ? 40 : 1);
      const magnitude = Math.abs(delta);
      const gap = now - lastEvent;
      const freshGesture =
        gap > 180 ||
        (magnitude > lastMagnitude * 1.6 && magnitude > 20) ||
        (now - lastNavigation > 700 && magnitude >= 40);
      lastEvent = now;
      lastMagnitude = magnitude;
      if (freshGesture && magnitude >= 4 && now - lastNavigation > 280) {
        lastNavigation = now;
        if (delta > 0) {
          next();
        } else {
          previous();
        }
      }
    };
    scroller.addEventListener("wheel", onWheel, { passive: false });
    return () => scroller.removeEventListener("wheel", onWheel);
  }, [next, previous]);

  const onScroll = useMemo(() => {
    let frame = 0;
    return () => {
      if (frame) {
        return;
      }
      frame = requestAnimationFrame(() => {
        frame = 0;
        const scroller = scrollerRef.current;
        // Mid-rotation the old offset means nothing against the new height.
        if (
          !scroller ||
          !scroller.clientHeight ||
          scroller.clientHeight !== heightRef.current ||
          settlingRef.current
        ) {
          return;
        }
        const index = Math.round(scroller.scrollTop / scroller.clientHeight);
        const bounded = Math.max(0, Math.min(list.items.length - 1, index));
        if (bounded !== activeRef.current && bounded >= 0) {
          setActiveIndex(bounded);
        }
      });
    };
  }, [list]);

  useEffect(() => {
    if (count && activeIndex >= count - LOAD_AHEAD) {
      void list.load();
    }
  }, [activeIndex, count, list]);

  // A page can arrive while the viewer rests on the loading placeholder; no
  // scroll event follows, so activate whatever is on screen now.
  useEffect(() => {
    const scroller = scrollerRef.current;
    const measured = heightRef.current;
    // Before the first measurement the offset is still zero, not a position.
    if (scroller && count && measured > 0 && !settlingRef.current) {
      const index = Math.round(scroller.scrollTop / measured);
      const bounded = Math.max(0, Math.min(count - 1, index));
      if (bounded !== activeRef.current) {
        setActiveIndex(bounded);
      }
    }
  }, [count]);

  const activePost = items[activeIndex];
  useEffect(() => {
    if (current && activePost) {
      onActivePost?.(activePost);
    }
  }, [activePost, current, onActivePost]);

  const neighbours = [activeIndex, activeIndex + 1, activeIndex - 1]
    .map((index) => items[index]?.key ?? "")
    .join("|");

  // Bind media after commit, when neighbouring slides have registered hosts.
  useEffect(() => {
    if (!current) {
      return;
    }
    const bindings: VideoBinding[] = [];
    for (const index of [activeIndex, activeIndex + 1, activeIndex - 1]) {
      const post = list.items[index];
      if (post?.kind !== "video") {
        continue;
      }
      const registration = registrations.current.get(post.key);
      if (registration) {
        bindings.push({
          key: post.key,
          src: fileUrl(post.media[0].path),
          host: registration.host,
          listener: registration.listener,
        });
      }
    }
    const active = list.items[activeIndex];
    if (active?.key !== lastActiveKey.current) {
      lastActiveKey.current = active?.key ?? null;
      mediaPool.clearPause();
    }
    mediaPool.setLoop(!preferences.autoNext);
    mediaPool.sync(bindings, active?.kind === "video" ? active.key : null, { prime: prefersTouch() });
    mediaPool.setMusic(active && active.kind !== "video" ? (active.music?.url ?? "") : "");
  }, [activeIndex, current, list, neighbours, preferences.autoNext, registrationVersion]);

  // Only leaving the screen stops playback; a new page of posts must not.
  useEffect(() => {
    if (!current) {
      return;
    }
    return () => mediaPool.suspend();
  }, [current]);

  // Warm the next photos so a swipe lands on a sharp image.
  useEffect(() => {
    const upcoming = items[activeIndex + 1];
    if (upcoming && upcoming.kind !== "video") {
      const image = new Image();
      image.src = upcoming.media[0].kind === "image"
        ? fileUrl(upcoming.media[0].path)
        : thumbUrl(upcoming.media[0].path);
    }
  }, [activeIndex, items]);

  // Counts for a post can land shortly after it is first shown.
  useEffect(() => {
    if (!current || !activePost?.meta_pending) {
      return;
    }
    let attempts = 0;
    let timer = 0;
    let stopped = false;
    const check = async () => {
      attempts += 1;
      try {
        const fresh = await api.post(activePost.key);
        if (stopped) {
          return;
        }
        if (!fresh.meta_pending) {
          list.replace(fresh);
          return;
        }
      } catch {
        return;
      }
      if (attempts < 4) {
        timer = window.setTimeout(check, 1500);
      }
    };
    timer = window.setTimeout(check, 900);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [activePost?.key, activePost?.meta_pending, current, list]);

  const onEnded = useCallback(() => {
    if (preferences.autoNext) {
      next();
    }
  }, [next]);

  const slides: ReactNode[] = [];
  if (height > 0) {
    const first = Math.max(0, activeIndex - OVERSCAN);
    const last = Math.min(count - 1, activeIndex + OVERSCAN);
    for (let index = first; index <= last; index += 1) {
      const post = items[index];
      slides.push(
        <Slide
          key={post.key}
          post={post}
          index={index}
          height={height}
          isActive={current && index === activeIndex}
          register={register}
          actions={actions}
          onEnded={onEnded}
          surfaceRef={surfaceRef}
        />,
      );
    }
  }

  const showEmpty = !count && !list.loading && !list.error && !list.hasMore;
  return (
    <div className="fa-pager-wrap">
      <div
        className="fa-pager"
        ref={scrollerRef}
        role="feed"
        aria-label={ariaLabel}
        aria-busy={list.loading}
        onScroll={onScroll}
      >
        <div
          className="fa-pager-track"
          style={{ height: Math.max(1, count + (hasFooter ? 1 : 0)) * height }}
        >
          {slides}
          {hasFooter && height > 0 ? (
            <div className="fa-slide fa-slide-end" style={{ top: count * height, height }}>
              {list.error ? (
                <div className="fa-state">
                  <p>{list.error}</p>
                  <button type="button" className="fa-btn" onClick={() => void list.load()}>
                    重试
                  </button>
                </div>
              ) : list.loading ? (
                <span className="fa-spinner" aria-label="正在加载" />
              ) : (
                <div className="fa-state">
                  <p>已经看完了</p>
                  <button type="button" className="fa-btn" onClick={() => goTo(0)}>
                    回到开头
                  </button>
                </div>
              )}
            </div>
          ) : null}
        </div>
        {showEmpty && empty ? <div className="fa-pager-empty">{empty}</div> : null}
      </div>
      {count > 1 ? (
        <div className="fa-pager-arrows">
          <button type="button" aria-label="上一个" disabled={activeIndex <= 0} onClick={previous}>
            <ChevronUpIcon size={22} />
          </button>
          <button type="button" aria-label="下一个" disabled={activeIndex >= count - 1} onClick={next}>
            <ChevronDownIcon size={22} />
          </button>
        </div>
      ) : null}
    </div>
  );
}
