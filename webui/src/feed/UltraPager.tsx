import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";

import { fileUrl, thumbUrl } from "./api";
import { usePagedWheel } from "./hooks";
import type { PagerHandle } from "./Pager";
import { preferences, useObservable, type PostList } from "./store";
import type { Post } from "./types";

interface Tile {
  post: Post;
  index: number;
  columns: number;
}

interface Row {
  tiles: Tile[];
  height: number;
}

function packPosts(posts: Post[], columns: number, rows: number): Row[][] {
  const batches: Row[][] = [];
  let index = 0;
  while (index < posts.length) {
    const batch: Row[] = [];
    while (batch.length < rows && index < posts.length) {
      const tiles: Tile[] = [];
      let used = 0;
      let width = 0;
      while (used < columns && index < posts.length) {
        const post = posts[index];
        const aspect = post.width && post.height ? post.width / post.height : 2 / 3;
        const span = Math.min(aspect > 1 ? 2 : 1, columns);
        if (used + span > columns) break;
        tiles.push({ post, index, columns: span });
        used += span;
        width += Math.min(2, Math.max(0.5, aspect));
        index += 1;
      }
      // Shorter rows suit wide media. Normalizing the row widths also fills
      // any spare column at the end of a row or the end of the feed.
      batch.push({ tiles, height: columns / Math.max(width, columns / 2) });
    }
    batches.push(batch);
  }
  return batches;
}

function videoPath(post: Post) {
  const media = post.media[0];
  return post.kind === "video" && media?.kind === "video" ? media.path : undefined;
}

function UltraTile({ tile, current, expanded, covered, play, onClick }: {
  tile: Tile;
  current: boolean;
  expanded?: boolean;
  covered: boolean;
  play: boolean;
  onClick(): void;
}) {
  const { post, columns } = tile;
  const [widePreview, setWidePreview] = useState(false);
  const path = play ? videoPath(post) : undefined;
  const preview = post.cover || post.media[0]?.path;
  const measure = (width: number, height: number) => {
    if ((!post.width || !post.height) && width && height) setWidePreview(width > height);
  };
  return (
    <button type="button" className="fa-ultra-tile" inert={covered} style={{ flexGrow: widePreview ? 2 : columns }}
      aria-label={[post.author.name, post.caption].filter(Boolean).join(" · ") || "浏览作品"}
      aria-pressed={expanded} onClick={onClick}>
      {preview && <img src={thumbUrl(preview)} alt="" draggable={false} decoding="async"
        loading={current ? "eager" : "lazy"}
        onLoad={({ currentTarget: image }) => measure(image.naturalWidth, image.naturalHeight)} />}
      {path && <video src={fileUrl(path)} muted playsInline autoPlay loop preload="metadata"
        onLoadedMetadata={({ currentTarget: video }) => measure(video.videoWidth, video.videoHeight)} />}
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
  const openPlayer = preferences.ultraOpenSingle ? openSingle : undefined;
  const anchor = useRef<string | undefined>(undefined);
  const previousHeight = useRef(0);
  const wasCurrent = useRef(false);
  const columns = Math.min(preferences.ultraColumns, Math.max(1, Math.floor(size.width / 96)));
  const rows = Math.min(preferences.ultraRows, Math.max(1, Math.floor(size.height / 96)));
  const batches = useMemo(() => packPosts(list.items, columns, rows), [list.items, columns, rows]);
  const active = Math.min(position, Math.max(0, batches.length - 1));
  const tiles = batches[active]?.flatMap((row) => row.tiles) ?? [];
  const expandedKey = openPlayer ? undefined : expanded;
  const selected = tiles.find(({ post }) => post.key === expandedKey);
  const activePost = selected?.post ?? tiles[0]?.post;
  const videos = tiles.filter(({ post }) => videoPath(post)).slice(0, preferences.ultraVideos);
  if (selected && videoPath(selected.post) && !videos.includes(selected)) {
    videos[Math.min(videos.length, preferences.ultraVideos - 1)] = selected;
  }
  const videoKeys = new Set(videos.map(({ post }) => post.key));

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
      batch.some((row) => row.tiles.some(({ post }) => post.key === visibleKey)));
    const next = match < 0 ? active : match;
    if (position !== next || previousHeight.current !== size.height || (current && !wasCurrent.current)) {
      setPosition(next);
      node.scrollTop = next * size.height;
    }
    wasCurrent.current = current;
    previousHeight.current = size.height;
    anchor.current = batches[next]?.[0].tiles[0].post.key;
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
    anchor.current = batches[next][0].tiles[0].post.key;
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
        {batches.map((batch, batchIndex) => (
          <div key={batchIndex} className="fa-ultra-batch" inert={batchIndex !== active || !current}>
            {Math.abs(batchIndex - active) <= 1 && batch.map((row, rowIndex) => (
              <div key={rowIndex} className="fa-ultra-row" style={{ flexGrow: row.height }}>
                {row.tiles.map((tile) => {
                  const isExpanded = batchIndex === active && selected?.post.key === tile.post.key;
                  const visible = current && batchIndex === active;
                  return (
                    <UltraTile key={tile.post.key} tile={tile} current={visible} expanded={openPlayer ? undefined : isExpanded}
                      covered={batchIndex === active && Boolean(selected) && !isExpanded}
                      play={visible && videoKeys.has(tile.post.key)}
                      onClick={() => openPlayer
                        ? openPlayer(list, tile.index)
                        : setExpanded(isExpanded ? undefined : tile.post.key)} />
                  );
                })}
              </div>
            ))}
          </div>
        ))}
        {(!batches.length || list.error) && <div className="fa-ultra-state">{status}</div>}
      </div>
    </div>
  );
}
