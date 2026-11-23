import { getPlatform } from "./platform";
import { useSyncExternalStore } from "react";

import { api, isUltraLayout, ultraDefaults, type FeedPreferences, type UltraLayout } from "./api";
import type { Author, Post, PostSource } from "./types";

type Listener = () => void;

/** The smallest observable: components re-render when `version` moves. */
class Observable {
  private listeners = new Set<Listener>();
  private version = 0;

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getVersion = () => this.version;

  protected emit() {
    this.version += 1;
    this.listeners.forEach((listener) => listener());
  }
}

export function useObservable<T extends Observable>(store: T): T {
  useSyncExternalStore(store.subscribe, store.getVersion);
  return store;
}

/** One paged list. Shared by a grid and the player opened from it. */
export class PostList extends Observable {
  items: Post[] = [];
  availableTotal: number | null = null;
  hasMore = true;
  loading = false;
  error = "";
  private cursor: string | null = null;
  private generation = 0;
  private seen = new Set<string>();

  constructor(
    readonly source: PostSource,
    readonly pageSize = 12,
  ) {
    super();
    this.source = { ...source, platform: source.platform ?? getPlatform() };
  }

  async load() {
    if (this.loading || !this.hasMore) {
      return;
    }
    const generation = this.generation;
    this.loading = true;
    this.error = "";
    this.emit();
    try {
      let page = await api.posts(this.source, this.cursor, this.pageSize);
      // A page can be entirely repeats near the end of a shuffle; step past it.
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (generation !== this.generation) {
          return;
        }
        if (page.available_total !== undefined) this.availableTotal = page.available_total;
        const fresh = page.items.filter((post) => !this.seen.has(post.key));
        fresh.forEach((post) => this.seen.add(post.key));
        this.items = this.items.concat(fresh);
        this.cursor = page.next_cursor;
        this.hasMore = page.next_cursor !== null;
        if (!this.hasMore && this.source.type === "arrivals") this.availableTotal = this.items.length;
        if (fresh.length || !this.hasMore) {
          break;
        }
        page = await api.posts(this.source, this.cursor, this.pageSize);
      }
    } catch (error) {
      if (generation === this.generation) {
        this.error = error instanceof Error ? error.message : "加载失败";
      }
    } finally {
      if (generation === this.generation) {
        this.loading = false;
        this.emit();
      }
    }
  }

  async reload() {
    this.generation += 1;
    this.items = [];
    this.availableTotal = null;
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.error = "";
    this.seen.clear();
    this.emit();
    await this.load();
  }

  removeAuthor(accountKey: string) {
    this.items = this.items.filter((post) => post.author.key !== accountKey);
    this.emit();
  }

  /** Metadata can arrive after a post is first shown; swap it in place. */
  replace(next: Post) {
    const index = this.items.findIndex((post) => post.key === next.key);
    if (index >= 0) {
      this.items = this.items.slice();
      this.items[index] = { ...this.items[index], ...next };
      this.emit();
    }
  }
}

class Marks extends Observable {
  likesRevision = 0;
  private liked = new Map<string, boolean>();
  private saved = new Map<string, boolean>();
  private followed = new Map<string, boolean>();

  isLiked = (post: Post) => this.liked.get(post.key) ?? post.liked;
  isSaved = (post: Post) => this.saved.get(post.key) ?? post.saved;
  isFollowed = (author: Pick<Author, "key" | "followed">) =>
    this.followed.get(author.key) ?? author.followed;

  /** A locally toggled mark moves the crawled count by one, as on the platform. */
  displayCount(base: number | null | undefined, post: Post, kind: "like" | "save") {
    const original = kind === "like" ? post.liked : post.saved;
    const current = kind === "like" ? this.isLiked(post) : this.isSaved(post);
    const count = base ?? 0;
    return Math.max(0, count + (current === original ? 0 : current ? 1 : -1));
  }

  private async write(
    map: Map<string, boolean>,
    kind: "like" | "save" | "follow",
    key: string,
    next: boolean,
  ) {
    const before = map.get(key);
    map.set(key, next);
    this.emit();
    try {
      await api.setMark(kind, key, next);
      if (kind === "like") {
        this.likesRevision += 1;
        this.emit();
      }
    } catch {
      if (before === undefined) {
        map.delete(key);
      } else {
        map.set(key, before);
      }
      this.emit();
      toast("操作失败，请检查网络后重试");
    }
  }

  toggleLike = (post: Post) => this.write(this.liked, "like", post.key, !this.isLiked(post));
  setLike = (post: Post, next: boolean) => this.write(this.liked, "like", post.key, next);
  toggleSave = (post: Post) => this.write(this.saved, "save", post.key, !this.isSaved(post));
  toggleFollow = (author: Pick<Author, "key" | "followed">) =>
    this.write(this.followed, "follow", author.key, !this.isFollowed(author));
}

export const marks = new Marks();

function readPreference(key: string, fallback: boolean) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

function readLimit(key: string, fallback: number) {
  try {
    const value = Number(localStorage.getItem(key));
    return Number.isSafeInteger(value) && value >= 1 ? value : fallback;
  } catch {
    return fallback;
  }
}

function readUltraLayout(key: string): UltraLayout {
  try {
    const value = localStorage.getItem(key);
    return isUltraLayout(value) ? value : "adaptive";
  } catch {
    return "adaptive";
  }
}

function writePreference(key: string, value: FeedPreferences[keyof FeedPreferences]) {
  try {
    localStorage.setItem(key, String(typeof value === "boolean" ? Number(value) : value));
  } catch {
    // The setting still applies for this session when storage is blocked.
  }
}

const preferenceKeys: Record<keyof FeedPreferences, string> = {
  sound: "feed.sound",
  autoNext: "feed.autonext",
  showPauseIcon: "feed.pause_icon",
  pinchZoom: "feed.pinch_zoom",
  ultraImmersive: "feed.ultra_immersive",
  ultraPauseBatch: "feed.ultra_pause_batch",
  ultraOpenSingle: "feed.ultra_open_single",
  ultraColumns: "feed.ultra_columns",
  ultraRows: "feed.ultra_rows",
  ultraVideos: "feed.ultra_videos",
  ultraLayout: "feed.ultra_layout",
};
const preferenceNames = Object.keys(preferenceKeys) as (keyof FeedPreferences)[];

/** Shared server preferences, with a local cache for instant/offline rendering. */
class Preferences extends Observable implements FeedPreferences {
  sound = readPreference(preferenceKeys.sound, true);
  autoNext = readPreference(preferenceKeys.autoNext, false);
  showPauseIcon = readPreference(preferenceKeys.showPauseIcon, true);
  pinchZoom = readPreference(preferenceKeys.pinchZoom, true);
  ultraImmersive = readPreference(preferenceKeys.ultraImmersive, false);
  ultraPauseBatch = readPreference(preferenceKeys.ultraPauseBatch, false);
  ultraOpenSingle = readPreference(preferenceKeys.ultraOpenSingle, true);
  ultraColumns = readLimit(preferenceKeys.ultraColumns, ultraDefaults.ultraColumns);
  ultraRows = readLimit(preferenceKeys.ultraRows, ultraDefaults.ultraRows);
  ultraVideos = readLimit(preferenceKeys.ultraVideos, ultraDefaults.ultraVideos);
  ultraLayout = readUltraLayout(preferenceKeys.ultraLayout);
  syncState: "loading" | "saved" | "pending" | "error" = "loading";
  private pending: Partial<FeedPreferences> = {};
  private syncing = false;

  private apply<K extends keyof FeedPreferences>(key: K, value: FeedPreferences[K]) {
    const state: FeedPreferences = this;
    state[key] = value;
    writePreference(preferenceKeys[key], value);
  }

  change<K extends keyof FeedPreferences>(key: K, value: FeedPreferences[K]) {
    this.apply(key, value);
    this.pending[key] = value;
    this.syncState = "pending";
    this.emit();
    void this.sync();
  }

  async sync() {
    if (this.syncing) return;
    this.syncing = true;
    const changes = this.pending;
    this.pending = {};
    let succeeded = false;
    try {
      let values = await api.preferences(Object.keys(changes).length ? changes : undefined);
      const missing: Partial<FeedPreferences> = {};
      for (const key of preferenceNames) {
        if (values[key] === undefined) Object.assign(missing, { [key]: this[key] });
      }
      if (Object.keys(missing).length) values = await api.preferences(missing, true);
      for (const key of preferenceNames) {
        const value = values[key];
        if (key === "ultraLayout" && !isUltraLayout(value)) continue;
        if (!(key in this.pending) && value !== undefined && typeof value === typeof this[key]) this.apply(key, value);
      }
      succeeded = true;
      this.syncState = Object.keys(this.pending).length ? "pending" : "saved";
    } catch {
      this.pending = { ...changes, ...this.pending };
      this.syncState = "error";
    } finally {
      this.syncing = false;
      this.emit();
      if (succeeded && Object.keys(this.pending).length) void this.sync();
    }
  }

  setSound(value: boolean) { this.change("sound", value); }
  setAutoNext(value: boolean) { this.change("autoNext", value); }
  setShowPauseIcon(value: boolean) { this.change("showPauseIcon", value); }
  setPinchZoom(value: boolean) { this.change("pinchZoom", value); }
}

export const preferences = new Preferences();

class Toaster extends Observable {
  message = "";
  private timer = 0;

  show(message: string) {
    this.message = message;
    this.emit();
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.message = "";
      this.emit();
    }, 2200);
  }
}

export const toaster = new Toaster();

export function toast(message: string) {
  toaster.show(message);
}
