import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type MutableRefObject, type ReactNode } from "react";

import { fileUrl, thumbUrl } from "./api";
import { usePagedWheel } from "./hooks";
import { PlayIcon } from "./icons";
import { IMAGE_SECONDS, type PagerHandle } from "./Pager";
import { resumeVideo } from "./resumeVideo";
import { preferences, useObservable, type PostList } from "./store";
import type { MediaItem, Post } from "./types";
import { fitUltraBatch, packUltraBatches } from "./ultraLayout";

interface Tile {
  post: Post;
  index: number;
  aspect: number;
  media: MediaItem[];
}

const DOUBLE_TAP_MS = 300;

function hasPlayback({ media }: Tile) {
  return media.length > 1 || media[0]?.kind === "video";
}

function postAspect(post: Post) {
  const aspect = (post.width ?? 0) / (post.height ?? 0);
  return Number.isFinite(aspect) && aspect > 0 ? aspect : 2 / 3;
}

function playbackMedia(post: Post) {
  if (post.kind === "images") return post.media;
  const firstClip = post.media.findIndex((item) => item.kind === "video");
  if (post.kind === "video" && firstClip >= 0) return post.media.slice(firstClip, firstClip + 1);
  if (post.kind === "live" && firstClip > 0) {
    return [...post.media.slice(firstClip), ...post.media.slice(0, firstClip)];
  }
  return post.media;
}

function sampleMediaColor(image: HTMLImageElement) {
  if (!image.naturalWidth || !image.naturalHeight) return;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 8;
  const context = canvas.getContext("2d");
  if (!context) return;

  try {
    context.drawImage(image, 0, 0, 8, 8);
    const pixels = context.getImageData(0, 0, 8, 8).data;
    const color = [0, 0, 0];
    for (let pixel = 0; pixel < pixels.length; pixel += 4) {
      const alpha = pixels[pixel + 3] / 255;
      for (let channel = 0; channel < 3; channel++) color[channel] += pixels[pixel + channel] * alpha;
    }
    return `rgb(${color.map((value) => Math.round(7 + (value / 64) * 0.65)).join(", ")})`;
  } catch {
    return undefined;
  }
}

function UltraPreview({ path, current, original, onLoad }: {
  path: string;
  current: boolean;
  original: boolean;
  onLoad(image: HTMLImageElement): void;
}) {
  const [originalReady, setOriginalReady] = useState(false);

  return (
    <>
      {!originalReady && <img src={thumbUrl(path)} alt="" draggable={false} decoding="async"
        loading={current ? "eager" : "lazy"}
        onLoad={({ currentTarget }) => onLoad(currentTarget)} />}
      {original && <img src={fileUrl(path)} alt="" draggable={false} decoding="async"
        style={{ visibility: originalReady ? undefined : "hidden" }}
        onLoad={({ currentTarget }) => {
          setOriginalReady(true);
          onLoad(currentTarget);
        }} />}
    </>
  );
}

function UltraTile({ tile, frame, style, current, expanded, covered, play, paused, pausePressed, showPause,
  onAdvance, onPreview, onMeasure, onTap, onOpen }: {
  tile: Tile;
  frame: number;
  style: CSSProperties;
  current: boolean;
  expanded?: boolean;
  covered: boolean;
  play: boolean;
  paused: boolean;
  pausePressed?: boolean;
  showPause: boolean;
  onAdvance(tile: Tile): void;
  onPreview(tile: Tile, image: HTMLImageElement, useAspect: boolean): void;
  onMeasure(tile: Tile, width: number, height: number): void;
  onTap(keyboard: boolean): void;
  onOpen(): void;
}) {
  const { post, media } = tile;
  const item = media[frame];
  const [failedPath, setFailedPath] = useState<string>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const path = play && item?.kind === "video" && item.path !== failedPath ? item.path : undefined;
  const preview = item && (item.kind === "image" || post.kind === "live" || frame > 0)
    ? item.path : post.cover || item?.path;
  const original = current && item?.kind === "image";
  const running = current && !covered && !paused;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (running) {
      video.muted = true;
      void resumeVideo(video).catch(() => undefined);
      return () => video.pause();
    } else {
      video.pause();
    }
  }, [path, running]);

  useEffect(() => {
    if (!running || media.length < 2 || path) return;
    const timer = window.setTimeout(() => onAdvance(tile), IMAGE_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [running, media.length, frame, path, onAdvance, tile]);

  return (
    <button type="button" className="fa-ultra-tile" inert={covered} style={style}
      aria-label={[post.author.name, post.caption].filter(Boolean).join(" · ") || "浏览作品"}
      aria-pressed={pausePressed} data-expanded={expanded || undefined} aria-keyshortcuts="Space Enter"
      onClick={(event) => onTap(event.detail === 0)}
      onKeyDown={(event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        if (!event.repeat) onOpen();
      }}>
      {preview && <UltraPreview key={`${preview}:${original}`} path={preview} current={current} original={original}
        onLoad={(image) => {
          if (frame === 0) onPreview(tile, image, !path);
        }} />}
      {path && <video key={path} ref={videoRef} src={fileUrl(path)} muted playsInline loop={media.length === 1} preload="metadata"
        onLoadedMetadata={({ currentTarget: video }) => {
          if (frame === 0) onMeasure(tile, video.videoWidth, video.videoHeight);
        }}
        onEnded={() => { if (running && media.length > 1) onAdvance(tile); }}
        onError={() => setFailedPath(path)} />}
      {showPause && <span className="fa-center-icon" aria-hidden="true"><PlayIcon size={36} /></span>}
    </button>
  );
}

export function UltraPager({
  list,
  current,
  handleRef,
  ariaLabel,
  onActivePost,
  openSingle,
  empty,
}: {
  list: PostList;
  current: boolean;
  handleRef: MutableRefObject<PagerHandle | null>;
  ariaLabel: string;
  onActivePost(post: Post): void;
  openSingle?(list: PostList, index: number): void;
  empty: ReactNode;
}) {
  useObservable(list);
  const scroller = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [position, setPosition] = useState(0);
  const [expanded, setExpanded] = useState<string>();
  const [batchPaused, setBatchPaused] = useState(false);
  const [pausedTiles, setPausedTiles] = useState(() => new Set<string>());
  const pendingTap = useRef<{ key: string; timeout: number; pause(): void } | undefined>(undefined);
  const [frames, setFrames] = useState<Record<string, number>>({});
  const [measuredAspects, setMeasuredAspects] = useState(() => new Map<string, number>());
  const [mediaColors, setMediaColors] = useState(() => new Map<string, string>());
  const openPlayer = preferences.ultraOpenSingle ? openSingle : undefined;
  const anchor = useRef<string | undefined>(undefined);
  const previousHeight = useRef(0);
  const wasCurrent = useRef(false);
  const columns = Math.min(preferences.ultraColumns, Math.max(1, Math.floor(size.width / 96)));
  const rows = Math.min(preferences.ultraRows, Math.max(1, Math.floor(size.height / 96)));
  const aspect = size.height > 0 ? size.width / size.height : 1;
  const strategy = preferences.ultraLayout;
  const limits = useMemo(() => ({ aspect, columns, rows, strategy }), [aspect, columns, rows, strategy]);
  const posts = useMemo(() => list.items.map((post, index): Tile => ({
    post, index, aspect: postAspect(post), media: playbackMedia(post),
  })), [list.items]);
  const batches = useMemo(() => packUltraBatches(posts.map((tile) => tile.aspect), limits), [posts, limits]);
  const active = Math.min(position, Math.max(0, batches.length - 1));
  const activeBatch = batches[active];
  const tiles = activeBatch ? posts.slice(activeBatch.start, activeBatch.start + activeBatch.count) : [];
  const expandedKey = openPlayer ? undefined : expanded;
  const selected = tiles.find(({ post }) => post.key === expandedKey);
  const activePost = selected?.post ?? tiles[0]?.post;
  const frameFor = (tile: Tile) => (frames[tile.post.key] ?? 0) % Math.max(1, tile.media.length);
  const videos = tiles.filter((tile) => tile.media[frameFor(tile)]?.kind === "video").slice(0, preferences.ultraVideos);
  if (selected && selected.media[frameFor(selected)]?.kind === "video" && !videos.includes(selected)) {
    videos[Math.min(videos.length, preferences.ultraVideos - 1)] = selected;
  }
  const videoKeys = new Set(videos.map(({ post }) => post.key));

  const cancelTap = useCallback(() => {
    if (pendingTap.current) window.clearTimeout(pendingTap.current.timeout);
    pendingTap.current = undefined;
  }, []);

  useLayoutEffect(() => cancelTap, [active, current, cancelTap]);

  const openTile = (tile: Tile) => {
    cancelTap();
    if (openPlayer) openPlayer(list, tile.index);
    else setExpanded((key) => key === tile.post.key ? undefined : tile.post.key);
  };

  const tapTile = (tile: Tile, keyboard: boolean) => {
    const key = tile.post.key;
    const previous = pendingTap.current;
    if (!keyboard && previous?.key === key) {
      openTile(tile);
      return;
    }
    cancelTap();
    // A tap on a different work is an independent pause, not a double tap.
    previous?.pause();
    const pause = () => {
      if (preferences.ultraPauseBatch) {
        setBatchPaused((value) => !value);
      } else if (hasPlayback(tile)) {
        setPausedTiles((value) => {
          const next = new Set(value);
          if (next.has(key)) next.delete(key);
          else next.add(key);
          return next;
        });
      }
    };
    if (keyboard) pause();
    else pendingTap.current = {
      key,
      pause,
      timeout: window.setTimeout(() => {
        pendingTap.current = undefined;
        pause();
      }, DOUBLE_TAP_MS),
    };
  };

  const advanceTile = useCallback(({ post, media }: Tile) => {
    setFrames((previous) => ({ ...previous, [post.key]: ((previous[post.key] ?? 0) + 1) % media.length }));
  }, []);

  const onMeasure = (tile: Tile, width: number, height: number) => {
    if (!width || !height) return;
    const aspect = width / height;
    setMeasuredAspects((previous) => {
      const currentAspect = previous.get(tile.post.key) ?? tile.aspect;
      if (Math.abs(aspect / currentAspect - 1) <= 0.01) return previous;
      return new Map(previous).set(tile.post.key, aspect);
    });
  };

  const onPreview = (tile: Tile, image: HTMLImageElement, useAspect: boolean) => {
    if (useAspect) onMeasure(tile, image.naturalWidth, image.naturalHeight);
    const color = sampleMediaColor(image);
    if (color) {
      setMediaColors((previous) => previous.get(tile.post.key) === color
        ? previous : new Map(previous).set(tile.post.key, color));
    }
  };

  useEffect(() => {
    if (openPlayer) setExpanded(undefined);
  }, [openPlayer]);

  useLayoutEffect(() => {
    const node = scroller.current;
    if (!node) return;
    const measure = () => {
      const { clientWidth: width, clientHeight: height } = node;
      if (width && height) setSize((previous) => previous.width === width && previous.height === height ? previous : { width, height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    const node = scroller.current;
    if (!node || !size.height) return;
    // Preserve the enlarged tile on resize, or repack around the leading post.
    const visibleKey = expandedKey ?? anchor.current;
    const visibleIndex = posts.findIndex(({ post }) => post.key === visibleKey);
    const match = batches.findIndex(({ start, count }) => visibleIndex >= start && visibleIndex < start + count);
    const next = match < 0 ? active : match;
    if (position !== next || previousHeight.current !== size.height || (current && !wasCurrent.current)) {
      setPosition(next);
      node.scrollTop = next * size.height;
    }
    wasCurrent.current = current;
    previousHeight.current = size.height;
    anchor.current = batches[next] ? posts[batches[next].start].post.key : undefined;
  }, [batches, posts, size.height, current]); // Ordinary scrolling changes the anchor directly.

  useEffect(() => {
    if (current && size.height && list.hasMore && !list.loading && !list.error && active >= batches.length - 2) {
      void list.load();
    }
  }, [current, active, batches.length, list, list.loading, list.hasMore, list.error, list.items, size.height]);

  useEffect(() => {
    if (current && activePost) onActivePost(activePost);
  }, [current, activePost, onActivePost]);

  const go = useCallback((delta: -1 | 1) => {
    const node = scroller.current;
    if (!current || !node) return;
    const index = Math.max(0, Math.min(active + delta, batches.length - 1));
    if (index !== active) node.scrollTop = index * node.clientHeight;
    else if (delta > 0 && list.error) void list.load();
  }, [current, active, batches.length, list]);
  usePagedWheel(scroller, go);

  useEffect(() => {
    if (!current) return;
    const node = scroller.current;
    const handle: PagerHandle = {
      next: () => go(1),
      previous: () => go(-1),
      togglePause: () => setBatchPaused((value) => !value),
      seek: (delta) => {
        const video = node?.querySelector("video");
        if (video && Number.isFinite(video.duration)) {
          video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta));
        }
      },
      slide: () => false,
      post: () => activePost,
      collapse: () => setExpanded(undefined),
    };
    handleRef.current = handle;
    return () => {
      if (handleRef.current === handle) handleRef.current = null;
    };
  }, [current, activePost, go, handleRef]);

  const onScroll = () => {
    const node = scroller.current;
    if (!current || !node || !size.height || node.clientHeight !== size.height) return;
    const next = Math.min(batches.length - 1, Math.max(0, Math.round(node.scrollTop / size.height)));
    if (next < 0 || next === active) return;
    anchor.current = posts[batches[next].start].post.key;
    setPosition(next);
    setExpanded(undefined);
    cancelTap();
    setBatchPaused(false);
    setPausedTiles(new Set());
    setFrames({});
  };

  const status = list.error ? (
    <div className="fa-state">
      <p>{list.error}</p>
      <button type="button" className="fa-btn" onClick={() => void list.load()}>重试</button>
    </div>
  ) : list.loading || list.hasMore ? (
    <span className="fa-spinner" aria-label="正在加载" />
  ) : empty;

  return (
    <div className="fa-pager-wrap">
      <div ref={scroller} className="fa-pager fa-ultra" role="feed" aria-label={ariaLabel}
        aria-busy={list.loading} onScroll={onScroll}>
        {batches.map((batch, batchIndex) => {
          const visible = current && batchIndex === active;
          if (Math.abs(batchIndex - active) > 1 || !size.width || !size.height) {
            return <div key={batchIndex} className="fa-ultra-batch" inert />;
          }
          const items = posts.slice(batch.start, batch.start + batch.count);
          const aspects = items.map((tile) => measuredAspects.get(tile.post.key) ?? tile.aspect);
          const layout = fitUltraBatch(aspects, batch, limits, size.width, size.height);
          const colors = items.flatMap(({ post }) => mediaColors.get(post.key) ?? []);
          const background = colors.length
            ? `linear-gradient(125deg, ${colors[0]}, ${colors[Math.floor(colors.length / 2)]} 55%, ${colors.at(-1)})`
            : undefined;
          return (
            <div key={batchIndex} className="fa-ultra-batch" inert={!visible}
              data-spanning={layout.spanning || undefined} style={{ background }}>
              {items.map((tile, index) => {
                const isExpanded = batchIndex === active && selected?.post.key === tile.post.key;
                const tilePaused = pausedTiles.has(tile.post.key);
                const covered = batchIndex === active && Boolean(selected) && !isExpanded;
                const bounds = layout.tiles[index];
                const style: CSSProperties = { backgroundColor: mediaColors.get(tile.post.key) };
                if (!isExpanded) {
                  style.left = `${100 * bounds.left / size.width}%`;
                  style.top = `${100 * bounds.top / size.height}%`;
                  style.width = `${100 * bounds.width / size.width}%`;
                  style.height = `${100 * bounds.height / size.height}%`;
                }
                return (
                  <UltraTile key={tile.post.key} tile={tile} style={style}
                    frame={visible ? frameFor(tile) : 0}
                    current={visible} expanded={isExpanded} covered={covered}
                    play={visible && videoKeys.has(tile.post.key)}
                    paused={batchPaused || tilePaused}
                    pausePressed={preferences.ultraPauseBatch ? batchPaused : hasPlayback(tile) ? tilePaused : undefined}
                    showPause={visible && !covered && !batchPaused && tilePaused && preferences.showPauseIcon}
                    onAdvance={advanceTile}
                    onPreview={onPreview}
                    onMeasure={onMeasure}
                    onTap={(keyboard) => tapTile(tile, keyboard)}
                    onOpen={() => openTile(tile)} />
                );
              })}
              {visible && batchPaused && preferences.showPauseIcon && (
                <span className="fa-center-icon" aria-hidden="true"><PlayIcon size={64} /></span>
              )}
            </div>
          );
        })}
        {(!batches.length || list.error) && <div className="fa-ultra-state">{status}</div>}
      </div>
    </div>
  );
}
