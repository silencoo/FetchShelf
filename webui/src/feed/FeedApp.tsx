import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import brandMark from "@/assets/brand/fetchshelf-mark-48.png";

import { api, AuthRequiredError, onAuthRequired, signIn } from "./api";
import { useMediaQuery } from "./hooks";
import {
  BackIcon,
  BookmarkIcon,
  CompassIcon,
  ExitIcon,
  HeartIcon,
  HomeIcon,
  MutedIcon,
  SearchIcon,
  UserIcon,
  VolumeIcon,
} from "./icons";
import { Pager, type PagerActions, type PagerHandle } from "./Pager";
import { mediaPool } from "./player";
import { PostPanel, ShareSheet } from "./Sheets";
import { marks, PostList, preferences, toast, toaster, useObservable } from "./store";
import type { IndexStatus, Post } from "./types";
import {
  DiscoverView,
  IndexingNotice,
  LibraryView,
  MeView,
  ProfileView,
  SearchView,
  type ViewActions,
} from "./Views";

type Tab = "home" | "discover" | "likes" | "saves" | "me";
type HomeTab = "foryou" | "following" | "latest";

type Layer =
  | { id: number; type: "profile"; accountKey: string; name?: string }
  | { id: number; type: "player"; list: PostList; index: number }
  | { id: number; type: "search"; q: string; mode: "search" | "tag" | "music" };

type NewLayer =
  | { type: "profile"; accountKey: string; name?: string }
  | { type: "player"; list: PostList; index: number }
  | { type: "search"; q: string; mode: "search" | "tag" | "music" };

const NAV_ITEMS: Array<{ tab: Tab; label: string; icon: ReactNode }> = [
  { tab: "home", label: "首页", icon: <HomeIcon size={24} /> },
  { tab: "discover", label: "发现", icon: <CompassIcon size={24} /> },
  { tab: "likes", label: "喜欢", icon: <HeartIcon size={24} /> },
  { tab: "saves", label: "收藏", icon: <BookmarkIcon size={24} /> },
  { tab: "me", label: "我", icon: <UserIcon size={24} /> },
];

const HOME_TABS: Array<{ tab: HomeTab; label: string }> = [
  { tab: "following", label: "关注" },
  { tab: "foryou", label: "推荐" },
  { tab: "latest", label: "最新" },
];

function SoundButton() {
  useObservable(preferences);
  const on = preferences.sound;
  return (
    <button
      type="button"
      className="fa-icon-btn fa-sound-toggle"
      aria-label={on ? "静音" : "打开声音"}
      aria-pressed={on}
      onClick={() => preferences.setSound(!on)}
    >
      {on ? <VolumeIcon size={22} /> : <MutedIcon size={22} />}
    </button>
  );
}

/** A pushed screen that follows the finger when swiped back, as native stacks do. */
function LayerCard({
  kind,
  isTop,
  onBack,
  children,
}: {
  kind: Layer["type"];
  isTop: boolean;
  onBack(): void;
  children: ReactNode;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const drag = useRef({ id: -1, x: 0, y: 0, dx: 0, active: false });

  const settle = (leaving: boolean) => {
    const card = cardRef.current;
    if (!card) {
      return;
    }
    card.style.transition = "transform 0.18s ease-out";
    card.style.transform = leaving ? "translateX(100%)" : "";
    window.setTimeout(() => {
      if (leaving) {
        onBack();
      } else {
        card.style.transition = "";
      }
    }, 170);
  };

  return (
    <div
      ref={cardRef}
      className={`fa-layer fa-layer-${kind}`}
      aria-hidden={!isTop}
      onPointerDown={(event) => {
        const target = event.target as HTMLElement;
        if (event.pointerType === "mouse" || target.closest(".fa-chips, .fa-seek, .fa-carousel")) {
          return;
        }
        drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, dx: 0, active: false };
      }}
      onPointerMove={(event) => {
        const state = drag.current;
        if (event.pointerId !== state.id) {
          return;
        }
        state.dx = event.clientX - state.x;
        if (!state.active && state.dx > 16 && state.dx > Math.abs(event.clientY - state.y) * 1.5) {
          state.active = true;
        }
        if (state.active && cardRef.current) {
          cardRef.current.style.transition = "none";
          cardRef.current.style.transform = `translateX(${Math.max(0, state.dx)}px)`;
        }
      }}
      onPointerUp={(event) => {
        const state = drag.current;
        if (event.pointerId === state.id && state.active) {
          settle(state.dx > (cardRef.current?.clientWidth ?? 390) * 0.28);
        }
        state.id = -1;
        state.active = false;
      }}
      onPointerCancel={() => {
        if (drag.current.active) {
          settle(false);
        }
        drag.current.id = -1;
        drag.current.active = false;
      }}
    >
      {children}
    </div>
  );
}

function TokenGate({ onDone }: { onDone(): void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="fa-gate">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            await signIn(value);
            onDone();
          } catch {
            setError("令牌无效，请检查后重试");
          } finally {
            setBusy(false);
          }
        }}
      >
        <img src={brandMark} alt="" width={48} height={48} />
        <h2>输入访问令牌</h2>
        <p>和控制台使用同一个 FETCHSHELF_API_TOKEN，只需要输入一次。</p>
        <input
          type="password"
          autoComplete="current-password"
          value={value}
          aria-label="访问令牌"
          onChange={(event) => setValue(event.target.value)}
        />
        {error ? <p className="fa-gate-error" role="alert">{error}</p> : null}
        <button type="submit" className="fa-btn fa-btn-primary" disabled={busy || !value.trim()}>
          {busy ? "验证中…" : "进入"}
        </button>
      </form>
    </div>
  );
}

export function FeedApp({ active, onExit }: { active: boolean; onExit(): void }) {
  useObservable(preferences);
  useObservable(toaster);
  const docked = useMediaQuery("(min-width: 1100px)");
  const [tab, setTab] = useState<Tab>("home");
  const [homeTab, setHomeTab] = useState<HomeTab>("foryou");
  const [visited, setVisited] = useState<Set<HomeTab>>(() => new Set<HomeTab>(["foryou"]));
  const [layers, setLayers] = useState<Layer[]>([]);
  const [panel, setPanel] = useState<{ post: Post; tab: "comments" | "details" } | null>(null);
  const [share, setShare] = useState<Post | null>(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [soundUnlocked, setSoundUnlocked] = useState(mediaPool.unlocked);
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const handleRef = useRef<PagerHandle | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const layerSeed = useRef(0);
  const layersRef = useRef(layers);
  layersRef.current = layers;

  const homeLists = useMemo(
    () => ({
      foryou: new PostList({ type: "foryou" }, 8),
      following: new PostList({ type: "following" }, 8),
      latest: new PostList({ type: "latest" }, 8),
    }),
    [],
  );

  useEffect(() => onAuthRequired(() => setNeedsToken(true)), []);

  useEffect(() => {
    mediaPool.setSoundWanted(preferences.sound);
  }, [preferences.sound]);

  useEffect(() => {
    const update = () => mediaPool.setBackgrounded(document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  // Offer the first gesture to the media pool before anything else sees it.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const unlock = (event: Event) => {
      if (mediaPool.unlock(event)) {
        setSoundUnlocked(true);
      }
    };
    root.addEventListener("click", unlock, true);
    window.addEventListener("keydown", unlock, true);
    return () => {
      root.removeEventListener("click", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    };
  }, []);

  // Watch the index until the library is ready, then fill the first feed.
  useEffect(() => {
    if (!active || needsToken) {
      return;
    }
    let stopped = false;
    let timer = 0;
    const poll = async () => {
      try {
        const next = await api.status();
        if (stopped) {
          return;
        }
        setStatus(next);
        const indexing = next.phase === "listing" || next.phase === "scanning";
        const foryou = homeLists.foryou;
        if (next.posts > 0 && !foryou.hasMore && foryou.items.length < 8) {
          void foryou.reload();
        }
        if (indexing || next.posts === 0) {
          timer = window.setTimeout(poll, 1500);
        }
      } catch (error) {
        if (!stopped && !(error instanceof AuthRequiredError)) {
          timer = window.setTimeout(poll, 5000);
        }
      }
    };
    void poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [active, homeLists, needsToken]);

  const pushLayer = useCallback((layer: NewLayer) => {
    layerSeed.current += 1;
    const depth = layersRef.current.length + 1;
    history.pushState({ feedDepth: depth }, "");
    // Otherwise Space would re-activate the tile now hidden under this screen.
    (document.activeElement as HTMLElement | null)?.blur?.();
    setLayers((current) => [...current, { ...layer, id: layerSeed.current } as Layer]);
  }, []);

  const clearLayers = useCallback(() => {
    if (layersRef.current.length) {
      history.go(-layersRef.current.length);
    }
  }, []);

  const exit = useCallback(() => {
    clearLayers();
    setPanel(null);
    setShare(null);
    onExit();
  }, [clearLayers, onExit]);

  const back = useCallback(() => {
    if (layersRef.current.length) {
      history.back();
    }
  }, []);

  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const depth = typeof event.state?.feedDepth === "number" ? event.state.feedDepth : 0;
      setLayers((current) => current.slice(0, depth));
      setPanel(null);
      setShare(null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const openProfile = useCallback(
    (account: { key: string; name?: string }) => {
      const top = layersRef.current[layersRef.current.length - 1];
      if (top?.type === "profile" && top.accountKey === account.key) {
        return;
      }
      setPanel(null);
      pushLayer({ type: "profile", accountKey: account.key, name: account.name });
    },
    [pushLayer],
  );

  const openSearch = useCallback(
    ({ q, mode = "search" }: { q: string; mode?: "search" | "tag" | "music" }) => {
      setPanel(null);
      pushLayer({ type: "search", q, mode });
    },
    [pushLayer],
  );

  const pagerActions = useMemo<PagerActions>(
    () => ({
      openProfile: (post) => openProfile({ key: post.author.key, name: post.author.name }),
      openPanel: (post, panelTab) => setPanel({ post, tab: panelTab }),
      openShare: (post) => setShare(post),
      openTag: (tag) => openSearch({ q: tag, mode: "tag" }),
      openMusic: (title) => openSearch({ q: title, mode: "music" }),
    }),
    [openProfile, openSearch],
  );

  const viewActions = useMemo<ViewActions>(
    () => ({
      openPlayer: (list, index) => pushLayer({ type: "player", list, index }),
      openProfile,
      openSearch,
      exit,
      back,
    }),
    [back, exit, openProfile, openSearch, pushLayer],
  );

  const onActivePost = useCallback((post: Post) => {
    setPanel((current) => (current && current.post.key !== post.key ? { ...current, post } : current));
  }, []);

  const hideAuthor = useCallback(
    (post: Post) => {
      api
        .setMark("hide", post.author.key, true)
        .then(() => {
          Object.values(homeLists).forEach((list) => list.removeAuthor(post.author.key));
          toast(`不再推荐 ${post.author.name}，可在“我”里恢复`);
        })
        .catch(() => toast("操作失败，请重试"));
    },
    [homeLists],
  );

  const selectHomeTab = (next: HomeTab) => {
    const list = homeLists[next];
    // Tapping the open feed asks for a fresh one; follows may also have changed.
    if ((next === homeTab || next === "following") && visited.has(next)) {
      void list.reload();
    }
    setHomeTab(next);
    setVisited((current) => new Set(current).add(next));
  };

  const selectTab = (next: Tab) => {
    if (next === "home" && tab === "home" && !layersRef.current.length) {
      void homeLists[homeTab].reload();
    }
    clearLayers();
    setTab(next);
  };

  const topLayer = layers[layers.length - 1];
  const homeCurrent = active && tab === "home" && !layers.length;

  // Keyboard control for desks and iPad keyboards.
  useEffect(() => {
    if (!active) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) {
        return;
      }
      if (event.key === "Escape") {
        if (share) {
          setShare(null);
        } else if (panel) {
          setPanel(null);
        } else if (layersRef.current.length) {
          back();
        }
        return;
      }
      const pagerVisible = homeCurrent || topLayer?.type === "player";
      if (!pagerVisible) {
        return;
      }
      const handle = handleRef.current;
      const post = handle?.post();
      let handled = true;
      switch (event.key) {
        case "ArrowDown":
        case "j":
        case "PageDown":
          handle?.next();
          break;
        case "ArrowUp":
        case "k":
        case "PageUp":
          handle?.previous();
          break;
        case " ":
          // Keyboard users keep Space on a focused control; a mouse click's
          // leftover focus must not turn Space into a second like.
          if (event.target instanceof HTMLButtonElement && event.target.matches(":focus-visible")) {
            return;
          }
          handle?.togglePause();
          break;
        case "ArrowLeft":
          if (!handle?.slide(-1)) {
            handle?.seek(-5);
          }
          break;
        case "ArrowRight":
          if (!handle?.slide(1)) {
            handle?.seek(5);
          }
          break;
        case "m":
          preferences.setSound(!preferences.sound);
          break;
        case "l":
          if (post) {
            void marks.toggleLike(post);
          }
          break;
        case "s":
          if (post) {
            void marks.toggleSave(post);
          }
          break;
        case "c":
          if (post) {
            setPanel((current) => (current ? null : { post, tab: "comments" }));
          }
          break;
        default:
          handled = false;
      }
      if (handled) {
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, back, homeCurrent, panel, share, topLayer?.type]);

  const panelIsDocked = Boolean(panel && docked);
  const needsSoundTap = active && preferences.sound && !soundUnlocked;

  const followingEmpty = (
    <div className="fa-state">
      <span className="fa-empty-icon">
        <UserIcon size={34} />
      </span>
      <p>还没有关注的账号</p>
      <small>在作品的头像上点“+”，或到发现页挑选账号</small>
      <button type="button" className="fa-btn fa-btn-primary" onClick={() => setTab("discover")}>
        去发现
      </button>
    </div>
  );

  return (
    <div
      ref={rootRef}
      className={`fa${panelIsDocked ? " has-docked-panel" : ""}`}
      data-layers={layers.length}
    >
      <aside className="fa-nav" aria-label="沉浸浏览导航">
        <div className="fa-brand">
          <img src={brandMark} alt="" width={30} height={30} />
          <strong>FetchShelf</strong>
        </div>
        <button
          type="button"
          className="fa-nav-search"
          aria-label="搜索"
          onClick={() => {
            clearLayers();
            setTab("discover");
          }}
        >
          <SearchIcon size={18} />
          <span>搜索</span>
        </button>
        <nav>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.tab}
              type="button"
              aria-label={item.label}
              aria-current={tab === item.tab ? "page" : undefined}
              onClick={() => selectTab(item.tab)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <button type="button" className="fa-nav-exit" aria-label="返回控制台" onClick={exit}>
          <ExitIcon size={22} />
          <span>返回控制台</span>
        </button>
      </aside>

      <main className="fa-main">
        <div className="fa-tab-content">
          <section className="fa-home" hidden={tab !== "home"} aria-label="首页">
            {HOME_TABS.filter((item) => visited.has(item.tab)).map((item) => (
              <div key={item.tab} className="fa-home-pane" hidden={homeTab !== item.tab}>
                <Pager
                  list={homeLists[item.tab]}
                  current={homeCurrent && homeTab === item.tab}
                  actions={pagerActions}
                  handleRef={handleRef}
                  ariaLabel={`${item.label}作品流`}
                  onActivePost={onActivePost}
                  empty={
                    item.tab === "following" ? (
                      followingEmpty
                    ) : !status ? (
                      <span className="fa-spinner" aria-label="正在加载" />
                    ) : status.phase !== "idle" ? (
                      <IndexingNotice status={status} />
                    ) : (
                      <div className="fa-state">
                        <p>媒体库里还没有作品</p>
                        <small>完成一次账号采集后，作品会自动出现在这里</small>
                      </div>
                    )
                  }
                />
              </div>
            ))}
            <div className="fa-topbar">
              <span className="fa-topbar-side" />
              <div className="fa-home-tabs" role="tablist" aria-label="作品流">
                {HOME_TABS.map((item) => (
                  <button
                    key={item.tab}
                    type="button"
                    role="tab"
                    aria-selected={homeTab === item.tab}
                    onClick={() => selectHomeTab(item.tab)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <span className="fa-topbar-side fa-topbar-end">
                <button
                  type="button"
                  className="fa-icon-btn fa-topbar-search"
                  aria-label="搜索"
                  onClick={() => setTab("discover")}
                >
                  <SearchIcon size={22} />
                </button>
                <SoundButton />
              </span>
            </div>
          </section>
          <div className="fa-tab-pane" hidden={tab !== "discover"}>
            {tab === "discover" ? <DiscoverView actions={viewActions} /> : null}
          </div>
          <div className="fa-tab-pane" hidden={tab !== "likes"}>
            {tab === "likes" ? <LibraryView kind="likes" actions={viewActions} /> : null}
          </div>
          <div className="fa-tab-pane" hidden={tab !== "saves"}>
            {tab === "saves" ? <LibraryView kind="saves" actions={viewActions} /> : null}
          </div>
          <div className="fa-tab-pane" hidden={tab !== "me"}>
            {tab === "me" ? <MeView actions={viewActions} visible={active} /> : null}
          </div>
        </div>

        <nav className="fa-tabbar" aria-label="沉浸浏览导航">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.tab}
              type="button"
              aria-label={item.label}
              aria-current={tab === item.tab ? "page" : undefined}
              onClick={() => selectTab(item.tab)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        {layers.map((layer, index) => {
          const isTop = index === layers.length - 1;
          return (
            <LayerCard key={layer.id} kind={layer.type} isTop={isTop} onBack={back}>
              {layer.type === "profile" ? (
                <ProfileView
                  accountKey={layer.accountKey}
                  initialName={layer.name}
                  actions={viewActions}
                />
              ) : layer.type === "search" ? (
                <SearchView query={layer.q} mode={layer.mode} actions={viewActions} />
              ) : (
                <>
                  <Pager
                    list={layer.list}
                    initialIndex={layer.index}
                    current={active && isTop}
                    actions={pagerActions}
                    handleRef={handleRef}
                    ariaLabel="作品播放"
                    onActivePost={onActivePost}
                  />
                  <div className="fa-topbar fa-topbar-player">
                    <button type="button" className="fa-icon-btn" aria-label="返回" onClick={back}>
                      <BackIcon size={24} />
                    </button>
                    <SoundButton />
                  </div>
                </>
              )}
            </LayerCard>
          );
        })}

        {needsSoundTap && (homeCurrent || topLayer?.type === "player") ? (
          <button type="button" className="fa-sound-chip">
            <MutedIcon size={16} /> 点一下开启声音
          </button>
        ) : null}

        {panel ? (
          <PostPanel
            post={panel.post}
            tab={panel.tab}
            docked={docked}
            onTab={(next) => setPanel((current) => (current ? { ...current, tab: next } : current))}
            onClose={() => setPanel(null)}
            onTag={(tag) => openSearch({ q: tag, mode: "tag" })}
          />
        ) : null}
        {share ? (
          <ShareSheet post={share} onClose={() => setShare(null)} onHideAuthor={hideAuthor} />
        ) : null}
        {toaster.message ? (
          <div className="fa-toast" role="status">
            {toaster.message}
          </div>
        ) : null}
      </main>

      {needsToken ? (
        <TokenGate
          onDone={() => {
            setNeedsToken(false);
            Object.values(homeLists)
              .filter((list) => !list.items.length)
              .forEach((list) => void list.reload());
          }}
        />
      ) : null}
    </div>
  );
}
