export type PostKind = "video" | "images" | "live";

export interface AvatarSource {
  scope: "download" | "project";
  path: string;
  second: number;
}

export interface Author {
  key: string;
  platform: string;
  url: string;
  name: string;
  avatar: AvatarSource | null;
  followed: boolean;
}

export interface Stats {
  likes: number | null;
  comments: number | null;
  saves: number | null;
  shares: number | null;
}

export interface Music {
  title: string;
  author: string;
  url: string;
}

export interface MediaItem {
  path: string;
  kind: "video" | "image";
}

export interface Post {
  key: string;
  kind: PostKind;
  published_ts: number;
  caption: string;
  tags: string[];
  duration: number | null;
  width: number | null;
  height: number | null;
  stats: Stats | null;
  music: Music | null;
  work_id: string;
  share_url: string;
  media: MediaItem[];
  cover: string;
  liked: boolean;
  saved: boolean;
  pinned: boolean;
  meta_pending: boolean;
  author: Author;
}

export interface Account {
  key: string;
  platform: string;
  url: string;
  name: string;
  nickname: string;
  handle: string;
  bio: string;
  uid: string;
  avatar: AvatarSource | null;
  cover: string;
  followed: boolean;
  stats: { posts: number; videos: number; images: number; likes: number };
  latest_ts: number;
  liked?: number;
  saved?: number;
  last_checked_at?: string;
}

export interface FeedComment {
  id: string;
  text: string;
  likes: number;
  created_ts: number;
  ip: string;
  replies: number;
  author: string;
  avatar: string;
  image: string;
  sticker: string;
}

export interface CommentPage {
  items: FeedComment[];
  next_cursor: number | null;
  unavailable?: string;
}

export interface IndexStatus {
  phase: "idle" | "listing" | "scanning" | "enriching";
  done: number;
  total: number;
  accounts: number;
  posts: number;
  metadata_available: boolean;
  metadata_done: number;
  metadata_total: number;
  last_finished_at: number;
  error: string;
}

export interface MeSummary {
  likes: number;
  saves: number;
  following: number;
  hidden: number;
  index: IndexStatus;
}

export type AccountSort = "latest" | "oldest" | "popular";
export type KindFilter = "all" | "video" | "images";

export type PostSource =
  | { type: "foryou" | "latest" | "following" | "popular" }
  | { type: "account"; account: string; sort?: AccountSort; kind?: KindFilter }
  | { type: "likes" | "saves"; account?: string }
  | { type: "search" | "tag" | "music"; q: string };

export interface PostPage {
  items: Post[];
  next_cursor: string | null;
}

export interface AccountPage {
  items: Account[];
  total: number;
  next_offset: number | null;
}
