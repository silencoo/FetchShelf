import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import { api, avatarUrl, thumbUrl } from "./api";
import { formatCount, formatDuration, formatRelativeTime, initialOf } from "./format";
import { useMediaQuery } from "./hooks";
import {
  BackIcon,
  BookmarkIcon,
  CheckIcon,
  ExitIcon,
  ExternalIcon,
  HeartIcon,
  ImagesIcon,
  LiveIcon,
  PinIcon,
  PlusIcon,
  RefreshIcon,
  SearchIcon,
  UserIcon,
} from "./icons";
import { marks, preferences, PostList, toast, useObservable } from "./store";
import type {
  Account,
  AccountSort,
  AvatarSource,
  IndexStatus,
  KindFilter,
  MeSummary,
  Post,
  PostSource,
} from "./types";

export interface ViewActions {
  openPlayer(list: PostList, index: number): void;
  openProfile(account: { key: string; name?: string }): void;
  openSearch(query: { q: string; mode?: "search" | "tag" | "music" }): void;
  exit(): void;
  back(): void;
}

export function AccountAvatar({
  avatar,
  name,
  size,
}: {
  avatar: AvatarSource | null | undefined;
  name: string;
  size: number;
}) {
  const [failed, setFailed] = useState(false);
  const url = avatarUrl(avatar, Math.max(96, size * 2));
  useEffect(() => setFailed(false), [url]);
  return (
    <span className="fa-avatar" style={{ width: size, height: size }}>
      {url && !failed ? (
        <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <span className="fa-avatar-fallback" style={{ fontSize: size * 0.42 }}>
          {initialOf(name)}
        </span>
      )}
    </span>
  );
}

/** Windowed grid: long profiles keep only nearby tiles decoded on a phone. */
function VirtualGrid<T>({
  items,
  itemKey,
  renderItem,
  scrollerRef,
  minWidth,
  aspect,
  gap,
  extraHeight = 0,
  onNearEnd,
}: {
  items: T[];
  itemKey(item: T): string;
  renderItem(item: T, index: number): ReactNode;
  scrollerRef: RefObject<HTMLElement | null>;
  minWidth: number;
  aspect: number;
  gap: number;
  extraHeight?: number;
  onNearEnd?(): void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [range, setRange] = useState({ first: 0, last: 18 });

  const columns = Math.max(2, Math.floor((width + gap) / (minWidth + gap)));
  const tileWidth = width ? (width - gap * (columns - 1)) / columns : 0;
  const rowHeight = tileWidth / aspect + extraHeight + gap;
  const rows = Math.ceil(items.length / columns);

  const measure = useCallback(() => {
    const grid = gridRef.current;
    const scroller = scrollerRef.current;
    if (!grid || !scroller || !rowHeight) {
      return;
    }
    const top = grid.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    const firstRow = Math.max(0, Math.floor(-top / rowHeight) - 3);
    const lastRow = Math.ceil((scroller.clientHeight - top) / rowHeight) + 3;
    setRange((current) =>
      current.first === firstRow && current.last === lastRow
        ? current
        : { first: firstRow, last: lastRow },
    );
  }, [rowHeight, scrollerRef]);

  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) {
      return;
    }
    const update = () => setWidth(grid.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(grid);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      return;
    }
    let frame = 0;
    const onScroll = () => {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          measure();
        });
      }
    };
    measure();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [measure, scrollerRef, items.length]);

  useEffect(() => {
    if (onNearEnd && rows && range.last >= rows - 2) {
      onNearEnd();
    }
  }, [onNearEnd, range.last, rows]);

  const nodes: ReactNode[] = [];
  if (tileWidth) {
    const start = range.first * columns;
    const end = Math.min(items.length, (range.last + 1) * columns);
    for (let index = start; index < end; index += 1) {
      const row = Math.floor(index / columns);
      const column = index % columns;
      nodes.push(
        <div
          key={itemKey(items[index])}
          className="fa-grid-cell"
          style={{
            top: row * rowHeight,
            left: column * (tileWidth + gap),
            width: tileWidth,
            height: rowHeight - gap,
          }}
        >
          {renderItem(items[index], index)}
        </div>,
      );
    }
  }
  return (
    <div
      className="fa-grid"
      ref={gridRef}
      style={{ height: rows ? rows * rowHeight - gap : 0 }}
    >
      {nodes}
    </div>
  );
}

const PostTile = ({
  post,
  showName,
  onOpen,
}: {
  post: Post;
  showName?: boolean;
  onOpen(): void;
}) => {
  useObservable(marks);
  const likes = post.stats ? marks.displayCount(post.stats.likes, post, "like") : null;
  return (
    <button
      type="button"
      className="fa-tile"
      aria-label={post.caption || `${post.author.name} 的作品`}
      onClick={onOpen}
    >
      <img src={thumbUrl(post.cover, { w: 360 })} alt="" loading="lazy" decoding="async" />
      <span className="fa-tile-shade" />
      {post.pinned ? (
        <span className="fa-tile-pin">
          <PinIcon size={11} /> 置顶
        </span>
      ) : null}
      {post.kind !== "video" ? (
        <span className="fa-tile-kind" title={post.kind === "live" ? "实况" : "图文"}>
          {post.kind === "live" ? <LiveIcon size={16} /> : <ImagesIcon size={16} />}
        </span>
      ) : post.duration ? (
        <span className="fa-tile-kind fa-tile-duration">{formatDuration(post.duration)}</span>
      ) : null}
      <span className="fa-tile-meta">
        {showName ? <span className="fa-tile-name">{post.author.name}</span> : null}
        {likes !== null ? (
          <span className="fa-tile-likes">
            <HeartIcon size={12} />
            {formatCount(likes)}
          </span>
        ) : null}
      </span>
    </button>
  );
};

function PostGrid({
  list,
  scrollerRef,
  actions,
  showName,
  empty,
}: {
  list: PostList;
  scrollerRef: RefObject<HTMLElement | null>;
  actions: ViewActions;
  showName?: boolean;
  empty: ReactNode;
}) {
  useObservable(list);
  const compact = useMediaQuery("(max-width: 699px)");
  useEffect(() => {
    if (!list.items.length && list.hasMore) {
      void list.load();
    }
  }, [list]);
  const onNearEnd = useCallback(() => void list.load(), [list]);
  return (
    <>
      <VirtualGrid
        items={list.items}
        itemKey={(post) => post.key}
        scrollerRef={scrollerRef}
        minWidth={compact ? 112 : 176}
        aspect={3 / 4}
        gap={compact ? 2 : 10}
        onNearEnd={onNearEnd}
        renderItem={(post, index) => (
          <PostTile
            post={post}
            showName={showName}
            onOpen={() => actions.openPlayer(list, index)}
          />
        )}
      />
      {list.loading ? <span className="fa-spinner fa-spinner-inline" aria-label="正在加载" /> : null}
      {list.error ? (
        <div className="fa-state fa-state-small">
          <p>{list.error}</p>
          <button type="button" className="fa-btn" onClick={() => void list.load()}>
            重试
          </button>
        </div>
      ) : null}
      {!list.items.length && !list.loading && !list.error && !list.hasMore ? (
        <div className="fa-state fa-state-small">{empty}</div>
      ) : null}
    </>
  );
}

function AccountTile({ account, actions }: { account: Account; actions: ViewActions }) {
  useObservable(marks);
  const followed = marks.isFollowed(account);
  return (
    <article className="fa-account-tile">
      <button
        type="button"
        className="fa-account-open"
        aria-label={`打开 ${account.name} 的主页`}
        onClick={() => actions.openProfile({ key: account.key, name: account.name })}
      >
        {account.cover ? (
          <img
            className="fa-account-cover"
            src={thumbUrl(account.avatar?.scope === "download" ? account.avatar.path : account.cover, {
              w: 360,
              second: account.avatar?.scope === "download" ? account.avatar.second : 0,
            })}
            alt=""
            loading="lazy"
            decoding="async"
          />
        ) : null}
        <span className="fa-tile-shade" />
        <span className="fa-account-info">
          <AccountAvatar avatar={account.avatar} name={account.name} size={34} />
          <span>
            <strong>{account.name}</strong>
            <small>
              {account.stats.posts} 作品
              {account.stats.likes ? ` · ${formatCount(account.stats.likes)} 获赞` : ""}
            </small>
          </span>
        </span>
      </button>
      <button
        type="button"
        className={`fa-mini-follow${followed ? " is-on" : ""}`}
        aria-pressed={followed}
        aria-label={followed ? `取消关注 ${account.name}` : `关注 ${account.name}`}
        onClick={() => void marks.toggleFollow(account)}
      >
        {followed ? <CheckIcon size={13} /> : <PlusIcon size={13} />}
      </button>
    </article>
  );
}

function AccountGrid({
  query,
  sort,
  scope,
  scrollerRef,
  actions,
  empty,
}: {
  query: string;
  sort: "recent" | "posts" | "likes" | "name";
  scope: "all" | "following";
  scrollerRef: RefObject<HTMLElement | null>;
  actions: ViewActions;
  empty: ReactNode;
}) {
  const compact = useMediaQuery("(max-width: 699px)");
  const [items, setItems] = useState<Account[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const generation = useRef(0);

  const load = useCallback(
    async (offset: number, reset = false) => {
      if (busy.current && !reset) {
        return;
      }
      busy.current = true;
      const current = ++generation.current;
      setLoading(true);
      setError("");
      try {
        const page = await api.accounts({ q: query, sort, scope, limit: 36, offset });
        if (current !== generation.current) {
          return;
        }
        setItems((existing) => (reset ? page.items : existing.concat(page.items)));
        setNextOffset(page.next_offset);
      } catch (cause) {
        if (current === generation.current) {
          setError(cause instanceof Error ? cause.message : "加载失败");
        }
      } finally {
        if (current === generation.current) {
          busy.current = false;
          setLoading(false);
        }
      }
    },
    [query, scope, sort],
  );

  useEffect(() => {
    setItems([]);
    void load(0, true);
  }, [load]);

  const onNearEnd = useCallback(() => {
    if (nextOffset !== null && nextOffset > 0) {
      void load(nextOffset);
    }
  }, [load, nextOffset]);

  return (
    <>
      <VirtualGrid
        items={items}
        itemKey={(account) => account.key}
        scrollerRef={scrollerRef}
        minWidth={compact ? 160 : 200}
        aspect={3 / 4}
        gap={compact ? 6 : 12}
        onNearEnd={onNearEnd}
        renderItem={(account) => <AccountTile account={account} actions={actions} />}
      />
      {loading ? <span className="fa-spinner fa-spinner-inline" aria-label="正在加载" /> : null}
      {error ? (
        <div className="fa-state fa-state-small">
          <p>{error}</p>
          <button type="button" className="fa-btn" onClick={() => void load(0, true)}>
            重试
          </button>
        </div>
      ) : null}
      {!items.length && !loading && !error ? <div className="fa-state fa-state-small">{empty}</div> : null}
    </>
  );
}

function ViewHeader({
  title,
  onBack,
  trailing,
}: {
  title: ReactNode;
  onBack?(): void;
  trailing?: ReactNode;
}) {
  return (
    <header className="fa-view-head">
      {onBack ? (
        <button type="button" className="fa-icon-btn" aria-label="返回" onClick={onBack}>
          <BackIcon size={22} />
        </button>
      ) : (
        <span className="fa-view-head-spacer" />
      )}
      <h2>{title}</h2>
      <div className="fa-view-head-trailing">{trailing}</div>
    </header>
  );
}

function Chips<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange(value: T): void;
  label: string;
}) {
  return (
    <div className="fa-chips" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

type ProfileTab = "posts" | "likes" | "saves";

export function ProfileView({
  accountKey,
  initialName,
  actions,
}: {
  accountKey: string;
  initialName?: string;
  actions: ViewActions;
}) {
  useObservable(marks);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<ProfileTab>("posts");
  const [sort, setSort] = useState<AccountSort>("latest");
  const [kind, setKind] = useState<KindFilter>("all");

  useEffect(() => {
    let stale = false;
    setError("");
    api
      .account(accountKey)
      .then((payload) => {
        if (!stale) {
          setAccount(payload);
        }
      })
      .catch((cause) => {
        if (!stale) {
          setError(cause instanceof Error ? cause.message : "账号加载失败");
        }
      });
    return () => {
      stale = true;
    };
  }, [accountKey]);

  const list = useMemo(() => {
    const source: PostSource =
      tab === "posts"
        ? { type: "account", account: accountKey, sort, kind }
        : { type: tab, account: accountKey };
    return new PostList(source, 30);
  }, [accountKey, kind, sort, tab]);

  const name = account?.name ?? initialName ?? "";
  const followed = account ? marks.isFollowed(account) : false;
  const coverUrl = account?.cover ? thumbUrl(account.avatar?.scope === "download" ? account.avatar.path : account.cover, { w: 480, second: account.avatar?.scope === "download" ? account.avatar.second : 0 }) : "";
  const lastChecked = account?.last_checked_at ? new Date(account.last_checked_at) : null;
  return (
    <div className="fa-view fa-profile" ref={scrollerRef}>
      <ViewHeader
        title={name}
        onBack={actions.back}
        trailing={
          account?.url ? (
            <a
              className="fa-icon-btn"
              href={account.url}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="打开平台主页"
            >
              <ExternalIcon size={20} />
            </a>
          ) : null
        }
      />
      <section className="fa-hero">
        {coverUrl ? <img className="fa-hero-cover" src={coverUrl} alt="" /> : null}
        <div className="fa-hero-body">
          <AccountAvatar avatar={account?.avatar} name={name} size={92} />
          <h3>{name}</h3>
          {account?.handle ? <p className="fa-hero-handle">@{account.handle}</p> : null}
          {account?.nickname && account.nickname !== name ? (
            <p className="fa-hero-handle">平台昵称：{account.nickname}</p>
          ) : null}
          {account ? (
            <dl className="fa-hero-stats">
              <div>
                <dd>{formatCount(account.stats.posts) || 0}</dd>
                <dt>作品</dt>
              </div>
              <div>
                <dd>{formatCount(account.stats.likes) || 0}</dd>
                <dt>获赞</dt>
              </div>
              <div>
                <dd>{formatCount(account.stats.videos) || 0}</dd>
                <dt>视频</dt>
              </div>
              <div>
                <dd>{formatCount(account.stats.images) || 0}</dd>
                <dt>图文</dt>
              </div>
            </dl>
          ) : null}
          {account ? (
            <button
              type="button"
              className={`fa-btn fa-btn-primary${followed ? " is-on" : ""}`}
              aria-pressed={followed}
              onClick={() => void marks.toggleFollow(account)}
            >
              {followed ? "已关注" : "关注"}
            </button>
          ) : null}
          {account?.bio ? <p className="fa-hero-bio">{account.bio}</p> : null}
          {account?.latest_ts ? (
            <p className="fa-hero-note">
              最新作品 {formatRelativeTime(account.latest_ts)}
              {lastChecked && !Number.isNaN(lastChecked.getTime())
                ? ` · 最近采集 ${formatRelativeTime(lastChecked.getTime() / 1000)}`
                : ""}
            </p>
          ) : null}
          {error ? <p className="fa-hero-note">{error}</p> : null}
        </div>
      </section>
      <div className="fa-tabs" role="tablist" aria-label="主页内容">
        <button type="button" role="tab" aria-selected={tab === "posts"} onClick={() => setTab("posts")}>
          <UserIcon size={16} /> 作品
        </button>
        <button type="button" role="tab" aria-selected={tab === "likes"} onClick={() => setTab("likes")}>
          <HeartIcon size={16} /> 喜欢{account?.liked ? ` ${account.liked}` : ""}
        </button>
        <button type="button" role="tab" aria-selected={tab === "saves"} onClick={() => setTab("saves")}>
          <BookmarkIcon size={16} /> 收藏{account?.saved ? ` ${account.saved}` : ""}
        </button>
      </div>
      {tab === "posts" ? (
        <div className="fa-filters">
          <Chips<AccountSort>
            label="排序"
            value={sort}
            onChange={setSort}
            options={[
              { value: "latest", label: "最新" },
              { value: "popular", label: "最热" },
              { value: "oldest", label: "最早" },
            ]}
          />
          <Chips<KindFilter>
            label="类型"
            value={kind}
            onChange={setKind}
            options={[
              { value: "all", label: "全部" },
              { value: "video", label: "视频" },
              { value: "images", label: "图文" },
            ]}
          />
        </div>
      ) : null}
      <div className="fa-grid-wrap">
        <PostGrid
          key={`${tab}:${sort}:${kind}`}
          list={list}
          scrollerRef={scrollerRef}
          actions={actions}
          empty={<p>{tab === "posts" ? "这个账号还没有下载的作品" : tab === "likes" ? "你还没有喜欢这个账号的作品" : "你还没有收藏这个账号的作品"}</p>}
        />
      </div>
    </div>
  );
}

export function LibraryView({ kind, actions }: { kind: "likes" | "saves"; actions: ViewActions }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const list = useMemo(() => new PostList({ type: kind }, 30), [kind]);
  const isLikes = kind === "likes";
  return (
    <div className="fa-view" ref={scrollerRef}>
      <ViewHeader title={isLikes ? "我的喜欢" : "我的收藏"} />
      <div className="fa-grid-wrap">
        <PostGrid
          list={list}
          scrollerRef={scrollerRef}
          actions={actions}
          showName
          empty={
            <>
              <span className="fa-empty-icon">
                {isLikes ? <HeartIcon size={34} /> : <BookmarkIcon size={34} />}
              </span>
              <p>{isLikes ? "双击作品或点爱心，喜欢的内容会出现在这里" : "点收藏按钮，把想再看的作品存在这里"}</p>
            </>
          }
        />
      </div>
    </div>
  );
}

type DiscoverTab = "accounts" | "popular" | "topics";

export function DiscoverView({ actions }: { actions: ViewActions }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState<DiscoverTab>("accounts");
  const [sort, setSort] = useState<"recent" | "posts" | "likes">("recent");
  const [text, setText] = useState("");
  const [tags, setTags] = useState<Array<{ tag: string; count: number }> | null>(null);
  const popular = useMemo(() => new PostList({ type: "popular" }, 30), []);

  useEffect(() => {
    if (tab === "topics" && tags === null) {
      api
        .tags()
        .then((payload) => setTags(payload.items))
        .catch(() => setTags([]));
    }
  }, [tab, tags]);

  return (
    <div className="fa-view" ref={scrollerRef}>
      <ViewHeader title="发现" />
      <form
        className="fa-search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) {
            actions.openSearch({ q: text.trim() });
          }
        }}
      >
        <SearchIcon size={18} />
        <input
          type="search"
          value={text}
          enterKeyHint="search"
          placeholder="搜索账号、文案或话题"
          aria-label="搜索账号、文案或话题"
          onChange={(event) => setText(event.target.value)}
        />
      </form>
      <div className="fa-tabs" role="tablist" aria-label="发现内容">
        <button type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>
          账号
        </button>
        <button type="button" role="tab" aria-selected={tab === "popular"} onClick={() => setTab("popular")}>
          热门作品
        </button>
        <button type="button" role="tab" aria-selected={tab === "topics"} onClick={() => setTab("topics")}>
          话题
        </button>
      </div>
      {tab === "accounts" ? (
        <>
          <div className="fa-filters">
            <Chips<"recent" | "posts" | "likes">
              label="账号排序"
              value={sort}
              onChange={setSort}
              options={[
                { value: "recent", label: "最近更新" },
                { value: "posts", label: "作品最多" },
                { value: "likes", label: "获赞最多" },
              ]}
            />
          </div>
          <div className="fa-grid-wrap fa-grid-pad">
            <AccountGrid
              key={sort}
              query=""
              sort={sort}
              scope="all"
              scrollerRef={scrollerRef}
              actions={actions}
              empty={<p>媒体库里还没有账号</p>}
            />
          </div>
        </>
      ) : null}
      {tab === "popular" ? (
        <div className="fa-grid-wrap">
          <PostGrid
            list={popular}
            scrollerRef={scrollerRef}
            actions={actions}
            showName
            empty={<p>互动数据还在整理中，稍后再来看看</p>}
          />
        </div>
      ) : null}
      {tab === "topics" ? (
        <div className="fa-topics">
          {tags === null ? <span className="fa-spinner fa-spinner-inline" aria-label="正在加载" /> : null}
          {tags?.map((item) => (
            <button
              key={item.tag}
              type="button"
              onClick={() => actions.openSearch({ q: item.tag, mode: "tag" })}
            >
              <strong>#{item.tag}</strong>
              <small>{formatCount(item.count)} 个作品</small>
            </button>
          ))}
          {tags?.length === 0 ? (
            <div className="fa-state fa-state-small">
              <p>话题数据还在整理中</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function SearchView({
  query,
  mode,
  actions,
}: {
  query: string;
  mode: "search" | "tag" | "music";
  actions: ViewActions;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState<"posts" | "accounts">("posts");
  const list = useMemo(() => new PostList({ type: mode, q: query }, 30), [mode, query]);
  const title = mode === "tag" ? `#${query}` : mode === "music" ? `音乐：${query}` : `搜索：${query}`;
  return (
    <div className="fa-view" ref={scrollerRef}>
      <ViewHeader title={title} onBack={actions.back} />
      {mode === "search" ? (
        <div className="fa-tabs" role="tablist" aria-label="搜索结果">
          <button type="button" role="tab" aria-selected={tab === "posts"} onClick={() => setTab("posts")}>
            作品
          </button>
          <button type="button" role="tab" aria-selected={tab === "accounts"} onClick={() => setTab("accounts")}>
            账号
          </button>
        </div>
      ) : null}
      {tab === "posts" ? (
        <div className="fa-grid-wrap">
          <PostGrid
            list={list}
            scrollerRef={scrollerRef}
            actions={actions}
            showName
            empty={<p>没有找到相关作品</p>}
          />
        </div>
      ) : (
        <div className="fa-grid-wrap fa-grid-pad">
          <AccountGrid
            query={query}
            sort="recent"
            scope="all"
            scrollerRef={scrollerRef}
            actions={actions}
            empty={<p>没有找到相关账号</p>}
          />
        </div>
      )}
    </div>
  );
}

function indexDescription(status: IndexStatus) {
  if (status.error) {
    return "上次扫描未完成，稍后会自动重试";
  }
  if (status.phase === "listing") {
    return "正在读取账号列表…";
  }
  if (status.phase === "scanning") {
    return `正在扫描媒体 ${status.done}/${status.total}`;
  }
  if (status.phase === "enriching") {
    return `正在整理互动数据 ${status.metadata_done}/${status.metadata_total}`;
  }
  return `${status.accounts} 个账号 · ${status.posts} 个作品`;
}

export function MeView({ actions, visible }: { actions: ViewActions; visible: boolean }) {
  useObservable(preferences);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [me, setMe] = useState<MeSummary | null>(null);
  const [section, setSection] = useState<"following" | "likes" | "saves">("following");
  const likes = useMemo(() => new PostList({ type: "likes" }, 30), []);
  const saves = useMemo(() => new PostList({ type: "saves" }, 30), []);

  const refresh = useCallback(() => {
    api
      .me()
      .then(setMe)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!visible) {
      return;
    }
    refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh, visible]);

  const standalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;

  return (
    <div className="fa-view fa-me" ref={scrollerRef}>
      <ViewHeader title="我" />
      <section className="fa-me-card">
        <div className="fa-me-stats">
          <button type="button" aria-pressed={section === "following"} onClick={() => setSection("following")}>
            <strong>{me?.following ?? "—"}</strong>
            <span>关注</span>
          </button>
          <button type="button" aria-pressed={section === "likes"} onClick={() => setSection("likes")}>
            <strong>{me?.likes ?? "—"}</strong>
            <span>喜欢</span>
          </button>
          <button type="button" aria-pressed={section === "saves"} onClick={() => setSection("saves")}>
            <strong>{me?.saves ?? "—"}</strong>
            <span>收藏</span>
          </button>
        </div>
      </section>

      <section className="fa-settings" aria-label="播放设置">
        <label className="fa-switch-row">
          <span>声音<small>默认打开作品声音</small></span>
          <input
            type="checkbox"
            role="switch"
            checked={preferences.sound}
            onChange={(event) => preferences.setSound(event.target.checked)}
          />
        </label>
        <label className="fa-switch-row">
          <span>自动连播<small>看完后自动切到下一个</small></span>
          <input
            type="checkbox"
            role="switch"
            checked={preferences.autoNext}
            onChange={(event) => preferences.setAutoNext(event.target.checked)}
          />
        </label>
        <div className="fa-setting-row">
          <span>
            媒体库
            <small>{me ? indexDescription(me.index) : "读取中…"}</small>
          </span>
          <button
            type="button"
            className="fa-icon-btn"
            aria-label="重新扫描媒体库"
            onClick={() => {
              api
                .refresh()
                .then(() => {
                  toast("已开始扫描");
                  refresh();
                })
                .catch(() => toast("暂时无法开始扫描"));
            }}
          >
            <RefreshIcon size={20} />
          </button>
        </div>
        {me?.hidden ? (
          <div className="fa-setting-row">
            <span>
              不看的账号
              <small>已隐藏 {me.hidden} 个账号，它们不会出现在推荐和最新里</small>
            </span>
            <button
              type="button"
              className="fa-btn"
              onClick={() => {
                api
                  .clearMarks("hide")
                  .then(() => {
                    toast("已全部恢复");
                    refresh();
                  })
                  .catch(() => toast("恢复失败，请重试"));
              }}
            >
              全部恢复
            </button>
          </div>
        ) : null}
        {!standalone ? (
          <div className="fa-setting-row">
            <span>
              添加到主屏幕
              <small>在 Safari 分享菜单中选择“添加到主屏幕”，打开后没有浏览器栏，体验和 App 一样</small>
            </span>
          </div>
        ) : null}
        <button type="button" className="fa-setting-row fa-setting-link" onClick={actions.exit}>
          <span>返回控制台<small>任务、账号与设置</small></span>
          <ExitIcon size={20} />
        </button>
      </section>
      <p className="fa-key-hint">
        键盘：↑ ↓ 切换作品 · 空格 暂停 · ← → 快退快进或翻图 · M 静音 · L 喜欢 · S 收藏 · C 评论
      </p>

      <div className="fa-grid-wrap" key={section}>
        {section === "following" ? (
          <div className="fa-grid-pad">
            <AccountGrid
              query=""
              sort="recent"
              scope="following"
              scrollerRef={scrollerRef}
              actions={actions}
              empty={<p>在作品或主页点“关注”，账号会出现在这里</p>}
            />
          </div>
        ) : (
          <PostGrid
            list={section === "likes" ? likes : saves}
            scrollerRef={scrollerRef}
            actions={actions}
            showName
            empty={<p>{section === "likes" ? "还没有喜欢的作品" : "还没有收藏的作品"}</p>}
          />
        )}
      </div>
    </div>
  );
}

export function IndexingNotice({ status }: { status: IndexStatus | null }) {
  const progress =
    status && status.total ? Math.round((Math.min(status.done, status.total) / status.total) * 100) : 0;
  return (
    <div className="fa-state">
      <span className="fa-spinner" />
      <p>正在整理媒体库，第一次打开需要一点时间</p>
      {status?.phase === "scanning" ? (
        <>
          <div className="fa-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
          <small>
            {status.done} / {status.total} 个账号 · 已发现 {status.posts} 个作品
          </small>
        </>
      ) : null}
    </div>
  );
}
