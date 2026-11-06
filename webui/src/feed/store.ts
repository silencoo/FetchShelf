import { useSyncExternalStore } from "react";

import { api } from "./api";
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
        const fresh = page.items.filter((post) => !this.seen.has(post.key));
        fresh.forEach((post) => this.seen.add(post.key));
        this.items = this.items.concat(fresh);
        this.cursor = page.next_cursor;
        this.hasMore = page.next_cursor !== null;
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
      this.items[index] = next;
      this.emit();
    }
  }
}

class Marks extends Observable {
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

function writePreference(key: string, value: boolean) {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // The setting still applies for this session when storage is blocked.
  }
}

/** Per-device playback settings; these differ between a phone and a desk. */
class Preferences extends Observable {
  sound = readPreference("feed.sound", true);
  autoNext = readPreference("feed.autonext", false);

  setSound(value: boolean) {
    this.sound = value;
    writePreference("feed.sound", value);
    this.emit();
  }

  setAutoNext(value: boolean) {
    this.autoNext = value;
    writePreference("feed.autonext", value);
    this.emit();
  }
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
