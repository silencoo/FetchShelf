import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";

import { fileUrl, thumbUrl } from "./api";
import { usePagedWheel } from "./hooks";
import type { PagerHandle } from "./Pager";
import { preferences, useObservable, type PostList } from "./store";
import type { Post } from "./types";

interface Tile {
  post: Post;
  index: number;
  aspect: number;
}

type Row = Tile[];

function postAspect(post: Post) {
  const aspect = (post.width ?? 0) / (post.height ?? 0);
  return Number.isFinite(aspect) && aspect > 0 ? aspect : 2 / 3;
}

function packPosts(posts: Post[], columns: number, rows: number, targetAspect: number): Row[][] {
  const batches: Row[][] = [];
  let index = 0;
  while (index < posts.length) {
    const batch: Row[] = [];
    while (batch.length < rows && index < posts.length) {
      const row: Row = [];
      let width = 0;
      while (row.length < columns && index < posts.length) {
        const post = posts[index];
        const aspect = postAspect(post);
        // Give wide media more room on tall screens by ending the row
        // once another tile would move farther from its target height.
        if (width >= targetAspect || (width > 0 && width * (width + aspect) > targetAspect ** 2)) break;
        row.push({ post, index, aspect });
        width += aspect;
        index += 1;
      }
      batch.push(row);
    }
    batches.push(batch);
  }
  return batches;
}

function videoPath(post: Post) {
  const media = post.media[0];
  return post.kind === "video" && media?.kind === "video" ? media.path : undefined;
}

function UltraTile({ tile, widthShare, current, expanded, covered, play, onMeasure, onClick }: {
  tile: Tile;
  widthShare: number;
  current: boolean;
  expanded?: boolean;
  covered: boolean;
  play: boolean;
  onMeasure(tile: Tile, width: number, height: number): void;
  onClick(): void;
}) {
  const { post } = tile;
  const path = play ? videoPath(post) : undefined;
  const preview = post.cover || post.media[0]?.path;
  return (
    <button type="button" className="fa-ultra-tile" inert={covered} style={{ flexGrow: widthShare }}
      aria-label={[post.author.name, post.caption].filter(Boolean).join(" · ") || "浏览作品"}
      aria-pressed={expanded} onClick={onClick}>
      {preview && <img src={thumbUrl(preview)} alt="" draggable={false} decoding="async"
        loading={current ? "eager" : "lazy"}
        onLoad={({ currentTarget: image }) => {
          if (!path) onMeasure(tile, image.naturalWidth, image.naturalHeight);
        }} />}
      {path && <video src={fileUrl(path)} muted playsInline autoPlay loop preload="metadata"
        onLoadedMetadata={({ currentTarget: video }) => onMeasure(tile, video.videoWidth, video.videoHeight)} />}
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
  const [measuredAspects, setMeasuredAspects] = useState(() => new Map<string, number>());
  const openPlayer = preferences.ultraOpenSingle ? openSingle : undefined;
  const anchor = useRef<string | undefined>(undefined);
  const previousHeight = useRef(0);
  const wasCurrent = useRef(false);
  const columns = Math.min(preferences.ultraColumns, Math.max(1, Math.floor(size.width / 96)));
  const rows = Math.min(preferences.ultraRows, Math.max(1, Math.floor(size.height / 96)));
  const targetAspect = (size.width * rows) / size.height || 1;
  const batches = useMemo(() => packPosts(list.items, columns, rows, targetAspect), [list.items, columns, rows, targetAspect]);
  const active = Math.min(position, Math.max(0, batches.length - 1));
  const tiles = batches[active]?.flat() ?? [];
  const expandedKey = openPlayer ? undefined : expanded;
  const selected = tiles.find(({ post }) => post.key === expandedKey);
  const activePost = selected?.post ?? tiles[0]?.post;
  const videos = tiles.filter(({ post }) => videoPath(post)).slice(0, preferences.ultraVideos);
  if (selected && videoPath(selected.post) && !videos.includes(selected)) {
    videos[Math.min(videos.length, preferences.ultraVideos - 1)] = selected;
  }
  const videoKeys = new Set(videos.map(({ post }) => post.key));

  const onMeasure = (tile: Tile, width: number, height: number) => {
    if (!width || !height) return;
    const aspect = width / height;
    setMeasuredAspects((previous) => {
      const currentAspect = previous.get(tile.post.key) ?? tile.aspect;
      if (Math.abs(aspect / currentAspect - 1) <= 0.01) return previous;
      return new Map(previous).set(tile.post.key, aspect);
    });
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
    const match = visibleKey === undefined ? -1 : batches.findIndex((batch) =>
      batch.some((row) => row.some(({ post }) => post.key === visibleKey)));
    const next = match < 0 ? active : match;
    if (position !== next || previousHeight.current !== size.height || (current && !wasCurrent.current)) {
      setPosition(next);
      node.scrollTop = next * size.height;
    }
    wasCurrent.current = current;
    previousHeight.current = size.height;
    anchor.current = batches[next]?.[0][0].post.key;
  }, [batches, size.height, current]); // Ordinary scrolling changes the anchor directly.

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
      togglePause: () => {
        const players = Array.from(node?.querySelectorAll("video") ?? []);
        if (players.some((video) => !video.paused)) players.forEach((video) => video.pause());
        else players.forEach((video) => void video.play().catch(() => undefined));
      },
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
    anchor.current = batches[next][0][0].post.key;
    setPosition(next);
    setExpanded(undefined);
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
          const nearby = Math.abs(batchIndex - active) <= 1;
          const aspects = nearby ? batch.map((row) => row.map((tile) => measuredAspects.get(tile.post.key) ?? tile.aspect)) : [];
          const heights = aspects.map((row) => 1 / row.reduce((sum, aspect) => sum + aspect, 0));
          // Fit the rows as a single block. Each row has the same width and
          // retains its natural height, so tiles meet without cropping.
          const width = Math.min(size.width, size.height / heights.reduce((sum, height) => sum + height, 0));
          return (
            <div key={batchIndex} className="fa-ultra-batch" inert={!visible}>
              {nearby && batch.map((row, rowIndex) => (
                <div key={rowIndex} className="fa-ultra-row" style={{ width, height: width * heights[rowIndex] }}>
                  {row.map((tile, columnIndex) => {
                    const isExpanded = batchIndex === active && selected?.post.key === tile.post.key;
                    return (
                      <UltraTile key={tile.post.key} tile={tile}
                        widthShare={aspects[rowIndex][columnIndex] * heights[rowIndex]}
                        current={visible} expanded={openPlayer ? undefined : isExpanded}
                        covered={batchIndex === active && Boolean(selected) && !isExpanded}
                        play={visible && videoKeys.has(tile.post.key)}
                        onMeasure={onMeasure}
                        onClick={() => openPlayer
                          ? openPlayer(list, tile.index)
                          : setExpanded(isExpanded ? undefined : tile.post.key)} />
                    );
                  })}
                </div>
              ))}
            </div>
          );
        })}
        {(!batches.length || list.error) && <div className="fa-ultra-state">{status}</div>}
      </div>
    </div>
  );
}
