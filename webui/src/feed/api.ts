import { platformFilter } from "./platform";
import { state } from "../legacy/state.js";
import { establishWebUiSession, persistToken } from "../legacy/runtime.js";

import type {
  Account,
  AccountPage,
  AvatarSource,
  CommentPage,
  IndexStatus,
  MeSummary,
  Post,
  PostPage,
  PostSource,
} from "./types";

export const ACCOUNT_BLOCK_CHANGED = "fetchshelf:account-block-changed";

export async function setAccountBlocked(target: string, on: boolean) {
  await api.setMark("block", target, on);
  state.accountBoardDirty = true;
  window.dispatchEvent(new CustomEvent(ACCOUNT_BLOCK_CHANGED, { detail: { target, on } }));
}

export class AuthRequiredError extends Error {
  constructor() {
    super("需要访问令牌");
  }
}

const authListeners = new Set<() => void>();

export function onAuthRequired(listener: () => void) {
  authListeners.add(listener);
  return () => {
    authListeners.delete(listener);
  };
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (state.token) {
    headers.set("token", state.token);
  }
  const response = await fetch(url, { ...init, headers });
  if (response.status === 403) {
    authListeners.forEach((listener) => listener());
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep the status text when the body is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function query(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  return params.toString();
}

export interface FeedPreferences {
  sound: boolean;
  autoNext: boolean;
  showPauseIcon: boolean;
  pinchZoom: boolean;
}

async function preferenceRequest(values?: Partial<FeedPreferences>, initialize = false) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 10000);
  try {
    return await request<Partial<FeedPreferences>>(`/ui/api/feed/preferences${initialize ? "?initialize=true" : ""}`, {
      signal: controller.signal,
      ...(values ? { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) } : {}),
    });
  } finally { window.clearTimeout(timer); }
}

export const api = {
  preferences: preferenceRequest,
  status: () => request<IndexStatus>("/ui/api/feed/status"),
  refresh: (force = false) =>
    request<IndexStatus>(`/ui/api/feed/refresh?force=${force}`, { method: "POST" }),
  posts(source: PostSource, cursor: string | null, limit: number) {
    const params: Record<string, string | number | undefined> = {
      source: source.type,
      platform: platformFilter(source.platform),
      cursor: cursor ?? undefined,
      limit,
    };
    if (source.type === "arrivals") {
      params.task_id = source.taskId;
    } else if (source.type === "account") {
      params.account = source.account;
      params.sort = source.sort;
      params.kind = source.kind;
    } else if (source.type === "likes" || source.type === "saves") {
      params.account = source.account;
    } else if (source.type === "search" || source.type === "tag" || source.type === "music") {
      params.q = source.q;
    }
    return request<PostPage>(`/ui/api/feed/posts?${query(params)}`);
  },
  post: (key: string) => request<Post>(`/ui/api/feed/post?${query({ key })}`),
  account: (key: string) => request<Account>(`/ui/api/feed/account?${query({ key })}`),
  accounts: (options: {
    q?: string;
    sort?: "recent" | "posts" | "likes" | "name";
    scope?: "all" | "following";
    limit?: number;
    offset?: number;
  }) => request<AccountPage>(`/ui/api/feed/accounts?${query({ ...options, platform: platformFilter() })}`),
  tags: () =>
    request<{ items: Array<{ tag: string; count: number }> }>(`/ui/api/feed/tags?platform=${platformFilter()}`),
  me: () => request<MeSummary>(`/ui/api/feed/me?platform=${platformFilter()}`),
  setMark: (kind: "like" | "save" | "follow" | "hide" | "block", target: string, on: boolean) =>
    request("/ui/api/feed/marks", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, target, on }),
    }),
  clearMarks: (kind: "hide") =>
    request(`/ui/api/feed/marks?kind=${kind}`, { method: "DELETE" }),
  comments: (key: string, cursor: number, replyTo = "", signal?: AbortSignal) =>
    request<CommentPage>(
      `/ui/api/feed/comments?${query({ key, cursor, reply_to: replyTo || undefined })}`,
      { signal },
    ),
  pinCover: (platform: string, url: string, path: string) =>
    request("/ui/api/accounts/board/pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform, url, path }),
    }),
};

export async function signIn(token: string) {
  const previous = state.token;
  state.token = token.trim();
  try {
    await establishWebUiSession();
    persistToken(state.token);
  } catch (error) {
    state.token = previous;
    throw error;
  }
}

export function fileUrl(path: string, scope: "download" | "project" = "download") {
  return `/ui/api/file?scope=${scope}&path=${encodeURIComponent(path)}`;
}

const VIDEO_PATH = /\.(mp4|m4v|mov|mkv|avi|flv|webm)$/i;

export function thumbUrl(
  path: string,
  { scope = "download", second = 0, w = 480 }: { scope?: string; second?: number; w?: number } = {},
) {
  // Video frames come in one size, and each distinct URL would cost another
  // ffmpeg run on the server, so all sizes of a clip share one cached URL.
  return `/ui/api/feed/thumb?${query({
    path,
    scope: scope === "download" ? undefined : scope,
    second: second || undefined,
    w: VIDEO_PATH.test(path) ? undefined : w,
  })}`;
}

export function avatarUrl(avatar: AvatarSource | null | undefined, w = 160) {
  return avatar
    ? thumbUrl(avatar.path, { scope: avatar.scope, second: avatar.second, w })
    : "";
}
