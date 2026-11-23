import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { api, fileUrl } from "./api";
import { MediaShareAction } from "./MediaShareAction";
import { ImageCopyAction } from "./ImageCopyAction";
import { ScreenshotShareAction } from "./ScreenshotShareAction";
import { formatCount, formatRelativeTime, initialOf, splitCaption } from "./format";
import {
  CloseIcon,
  DownloadIcon,
  ExternalIcon,
  EyeOffIcon,
  HeartIcon,
  LinkIcon,
  PinIcon,
} from "./icons";
import { carouselPositions, type ShareTarget } from "./Pager";
import { preferences, toast, useObservable } from "./store";
import type { FeedComment, Post } from "./types";

function Sheet({
  title,
  onClose,
  children,
  docked = false,
  anchor,
}: {
  title: ReactNode;
  onClose(): void;
  children: ReactNode;
  docked?: boolean;
  anchor?: ShareTarget["anchor"];
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const drag = useRef({ y: 0, dy: 0, active: false });

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
    return () => {
      if (anchor?.element.isConnected) anchor.element.focus({ preventScroll: true });
    };
  }, [anchor]);

  useLayoutEffect(() => {
    const root = rootRef.current;
    const panel = panelRef.current;
    if (!anchor || !root || !panel) return;
    const wide = window.matchMedia("(min-width: 700px)");
    const viewport = window.visualViewport;
    // A feed slide can unmount during a scroll snap, after the tap has opened the sheet.
    let target = anchor.rect;
    const position = () => {
      if (!wide.matches) return;
      const bounds = root.getBoundingClientRect();
      const gap = 12;
      const viewportLeft = viewport?.offsetLeft ?? 0;
      const viewportTop = viewport?.offsetTop ?? 0;
      const leftEdge = Math.max(bounds.left, viewportLeft) + gap;
      const topEdge = Math.max(bounds.top, viewportTop) + gap;
      const rightEdge = Math.min(bounds.right, viewportLeft + (viewport?.width ?? window.innerWidth)) - gap;
      const bottomEdge = Math.min(bounds.bottom, viewportTop + (viewport?.height ?? window.innerHeight)) - gap;
      if (rightEdge <= leftEdge || bottomEdge <= topEdge) return;

      const live = anchor.element.isConnected ? anchor.element.getBoundingClientRect() : undefined;
      if (live?.width && live.height && live.right > leftEdge - gap && live.left < rightEdge + gap &&
          live.bottom > topEdge - gap && live.top < bottomEdge + gap) {
        target = live;
      }
      if (!target.width || !target.height) return;
      panel.style.setProperty("--fa-share-max-width", `${rightEdge - leftEdge}px`);
      panel.style.setProperty("--fa-share-max-height", `${bottomEdge - topEdge}px`);
      const { width, height } = panel.getBoundingClientRect();
      const leftOfButton = target.left - gap - width;
      const rightOfButton = target.right + gap;
      const aboveButton = target.top - gap - height;
      const belowButton = target.bottom + gap;
      let left = target.left + (target.width - width) / 2;
      let top = aboveButton >= topEdge ? aboveButton : belowButton;
      if (leftOfButton >= leftEdge || rightOfButton + width <= rightEdge) {
        left = leftOfButton >= leftEdge ? leftOfButton : rightOfButton;
        top = target.top + (target.height - height) / 2;
      }
      left = Math.max(leftEdge, Math.min(left, rightEdge - width));
      top = Math.max(topEdge, Math.min(top, bottomEdge - height));
      panel.style.setProperty("--fa-share-left", `${left - bounds.left}px`);
      panel.style.setProperty("--fa-share-top", `${top - bounds.top}px`);
      panel.dataset.sharePositioned = "";
    };
    position();
    const observer = new ResizeObserver(position);
    observer.observe(root);
    observer.observe(panel);
    observer.observe(anchor.element);
    wide.addEventListener("change", position);
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    viewport?.addEventListener("resize", position);
    viewport?.addEventListener("scroll", position);
    return () => {
      observer.disconnect();
      wide.removeEventListener("change", position);
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
      viewport?.removeEventListener("resize", position);
      viewport?.removeEventListener("scroll", position);
    };
  }, [anchor]);

  return (
    <div ref={rootRef} className={`fa-sheet-root${docked ? " is-docked" : ""}${anchor ? " is-anchored" : ""}`}>
      <button type="button" className="fa-sheet-scrim" aria-label="关闭" onClick={onClose} />
      <div className="fa-sheet" ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (!anchor) return;
          if (event.key === "Escape") {
            event.stopPropagation();
            onClose();
          } else if (event.key === "Tab") {
            const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
              'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]',
            )).filter((element) => element.getClientRects().length);
            const first = controls[0];
            const last = controls[controls.length - 1];
            if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
              event.preventDefault();
              last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }
        }}>
        <div
          className="fa-sheet-grip"
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            drag.current = { y: event.clientY, dy: 0, active: true };
          }}
          onPointerMove={(event) => {
            if (!drag.current.active || !panelRef.current) {
              return;
            }
            drag.current.dy = Math.max(0, event.clientY - drag.current.y);
            panelRef.current.style.transform = `translateY(${drag.current.dy}px)`;
          }}
          onPointerUp={() => {
            drag.current.active = false;
            if (drag.current.dy > 96) {
              onClose();
            } else if (panelRef.current) {
              panelRef.current.style.transform = "";
            }
          }}
          onPointerCancel={() => {
            drag.current.active = false;
            if (panelRef.current) {
              panelRef.current.style.transform = "";
            }
          }}
        >
          <span />
        </div>
        <header className="fa-sheet-head">
          <div className="fa-sheet-title" id={titleId}>{title}</div>
          <button type="button" className="fa-icon-btn" aria-label="关闭" onClick={onClose}>
            <CloseIcon size={20} />
          </button>
        </header>
        <div className="fa-sheet-body">{children}</div>
      </div>
    </div>
  );
}

function CommentRow({ comment, postKey }: { comment: FeedComment; postKey: string }) {
  const [replies, setReplies] = useState<FeedComment[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);

  const loadReplies = async () => {
    setLoading(true);
    setFailed(false);
    try {
      const page = await api.comments(postKey, 0, comment.id);
      setReplies(page.items);
      setFailed(Boolean(page.unavailable));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <li className="fa-comment">
      <span className="fa-comment-avatar">
        {comment.avatar && !avatarFailed ? (
          <img
            src={comment.avatar}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setAvatarFailed(true)}
          />
        ) : (
          initialOf(comment.author)
        )}
      </span>
      <div className="fa-comment-body">
        <div className="fa-comment-author">{comment.author || "匿名用户"}</div>
        {comment.text ? <p>{comment.text}</p> : null}
        {comment.image || comment.sticker ? (
          <img
            className="fa-comment-image"
            src={comment.image || comment.sticker}
            alt="评论图片"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        ) : null}
        <div className="fa-comment-meta">
          <span>{formatRelativeTime(comment.created_ts)}</span>
          {comment.ip ? <span>{comment.ip}</span> : null}
        </div>
        {comment.replies > 0 && replies === null ? (
          <button
            type="button"
            className="fa-comment-more"
            disabled={loading}
            onClick={() => void loadReplies()}
          >
            {loading ? "加载中…" : failed ? "加载失败，点击重试" : `展开 ${comment.replies} 条回复`}
          </button>
        ) : null}
        {replies?.length ? (
          <ul className="fa-comment-replies">
            {replies.map((reply) => (
              <CommentRow key={reply.id} comment={{ ...reply, replies: 0 }} postKey={postKey} />
            ))}
          </ul>
        ) : null}
      </div>
      <span className="fa-comment-like">
        <HeartIcon size={15} />
        {formatCount(comment.likes) || ""}
      </span>
    </li>
  );
}

function CommentList({ post }: { post: Post }) {
  const [items, setItems] = useState<FeedComment[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback(
    async (from: number) => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      setLoading(true);
      setNotice("");
      try {
        const page = await api.comments(post.key, from, "", controller.signal);
        setItems((current) => (from === 0 ? page.items : current.concat(page.items)));
        setCursor(page.next_cursor);
        if (page.unavailable) {
          setNotice(page.unavailable);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setNotice(error instanceof Error ? error.message : "评论加载失败");
        setCursor(null);
      }
      setLoading(false);
    },
    [post.key],
  );

  useEffect(() => {
    // Comments are live platform requests: only fetch for a post the viewer stays
    // on, and cancel the request when they move on.
    const timer = window.setTimeout(() => void load(0), 450);
    return () => {
      window.clearTimeout(timer);
      inFlight.current?.abort();
    };
  }, [load]);

  return (
    <div className="fa-comments">
      {notice ? (
        <div className="fa-state fa-state-small">
          <p>{notice}</p>
          <button type="button" className="fa-btn" onClick={() => void load(0)}>
            重新拉取
          </button>
        </div>
      ) : null}
      {!items.length && !loading && !notice ? (
        <div className="fa-state fa-state-small">
          <p>还没有评论</p>
        </div>
      ) : null}
      <ul>
        {items.map((comment) => (
          <CommentRow key={comment.id} comment={comment} postKey={post.key} />
        ))}
      </ul>
      {loading ? <span className="fa-spinner fa-spinner-inline" aria-label="正在加载评论" /> : null}
      {!loading && cursor !== null && items.length ? (
        <button type="button" className="fa-btn fa-btn-wide" onClick={() => void load(cursor)}>
          加载更多评论
        </button>
      ) : null}
      <p className="fa-comments-note">评论由采集身份按需从平台拉取，不会保存到媒体库。</p>
    </div>
  );
}

function PostDetails({ post, onTag }: { post: Post; onTag(tag: string): void }) {
  const date = post.published_ts ? new Date(post.published_ts * 1000) : null;
  const rows: Array<[string, string]> = [
    ["发布时间", date ? date.toLocaleString("zh-CN", { hour12: false }) : "未知"],
    ["类型", post.kind === "video" ? "视频" : post.kind === "live" ? "实况图文" : "图文"],
    ["文件数", String(post.media.length)],
  ];
  if (post.duration) {
    rows.push(["时长", `${post.duration} 秒`]);
  }
  if (post.width && post.height) {
    rows.push(["分辨率", `${post.width} × ${post.height}`]);
  }
  if (post.stats) {
    rows.push(
      ["点赞", formatCount(post.stats.likes) || "—"],
      ["评论", formatCount(post.stats.comments) || "—"],
      ["收藏", formatCount(post.stats.saves) || "—"],
      ["分享", formatCount(post.stats.shares) || "—"],
    );
  }
  if (post.music?.title) {
    rows.push(["音乐", post.music.author ? `${post.music.title} · ${post.music.author}` : post.music.title]);
  }
  return (
    <div className="fa-details">
      {post.caption ? (
        <p className="fa-details-caption">
          {splitCaption(post.caption).map((part, index) =>
            part.tag ? (
              <button key={index} type="button" className="fa-tag" onClick={() => onTag(part.tag ?? "")}>
                {part.text}
              </button>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </p>
      ) : null}
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {!post.stats ? <p className="fa-comments-note">这条作品暂时没有采集到互动数据。</p> : null}
    </div>
  );
}

export function PostPanel({
  post,
  tab,
  docked,
  onTab,
  onClose,
  onTag,
}: {
  post: Post;
  tab: "comments" | "details";
  docked: boolean;
  onTab(tab: "comments" | "details"): void;
  onClose(): void;
  onTag(tag: string): void;
}) {
  return (
    <Sheet
      docked={docked}
      onClose={onClose}
      title={
        <div className="fa-segment" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "comments"}
            onClick={() => onTab("comments")}
          >
            评论{post.stats?.comments ? ` ${formatCount(post.stats.comments)}` : ""}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "details"}
            onClick={() => onTab("details")}
          >
            详情
          </button>
        </div>
      }
    >
      {tab === "comments" ? (
        post.work_id ? (
          <CommentList key={post.key} post={post} />
        ) : (
          <div className="fa-state fa-state-small">
            <p>这条作品没有可用的作品 ID，无法拉取评论。</p>
          </div>
        )
      ) : (
        <PostDetails post={post} onTag={onTag} />
      )}
    </Sheet>
  );
}

/** Clipboard APIs require HTTPS, but this service usually runs on plain LAN HTTP. */
async function copyText(text: string) {
  if (window.isSecureContext && navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.focus();
  field.setSelectionRange(0, text.length);
  const copied = document.execCommand("copy");
  field.remove();
  return copied;
}

const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] as const;

export function ShareSheet({
  post,
  snapshot,
  anchor,
  playback,
  onClose,
  onHideAuthor,
}: ShareTarget & {
  onClose(): void;
  onHideAuthor(post: Post): void;
}) {
  useObservable(preferences);
  const rateName = useId();
  const [rate, setRate] = useState(playback?.rate ?? 1);
  const [position] = useState(() => Math.min(carouselPositions.get(post.key) ?? 0, post.media.length - 1));
  const item = post.media[position] ?? post.media[0];
  const shareUrl = post.share_url;

  const copyLink = async () => {
    try {
      if (await copyText(shareUrl)) {
        toast("链接已复制");
      } else {
        toast("无法自动复制，请打开原作品后手动分享");
      }
    } catch {
      toast("无法自动复制，请打开原作品后手动分享");
    }
    onClose();
  };

  const nativeShare = async () => {
    try {
      await navigator.share({ url: shareUrl, title: post.caption || post.author.name });
    } catch {
      // The viewer dismissed the system sheet.
    }
    onClose();
  };

  const pinCover = async () => {
    try {
      await api.pinCover(post.author.platform, post.author.url, post.cover);
      toast("已设为账户封面");
    } catch (error) {
      toast(error instanceof Error ? error.message : "设置失败");
    }
    onClose();
  };

  return (
    <Sheet title="分享与更多" onClose={onClose} anchor={anchor}>
      <div className="fa-actions-grid">
        {item?.kind === "image" ? <ImageCopyAction key={`copy-${item.path}`} item={item} onCopied={onClose} /> : null}
        {item ? <MediaShareAction key={item.path} item={item} onShared={onClose} /> : null}
        {snapshot ? <ScreenshotShareAction snapshot={snapshot} onShared={onClose} /> : null}
        {shareUrl && typeof navigator.share === "function" ? (
          <button type="button" className="fa-action" onClick={() => void nativeShare()}>
            <span>
              <ExternalIcon size={22} />
            </span>
            分享链接
          </button>
        ) : null}
        {shareUrl ? (
          <button type="button" className="fa-action" onClick={() => void copyLink()}>
            <span>
              <LinkIcon size={22} />
            </span>
            复制链接
          </button>
        ) : null}
        {shareUrl ? (
          <a className="fa-action" href={shareUrl} target="_blank" rel="noreferrer noopener" onClick={onClose}>
            <span>
              <ExternalIcon size={22} />
            </span>
            打开原作品
          </a>
        ) : null}
        <a className="fa-action" href={fileUrl(item.path)} download onClick={onClose}>
          <span>
            <DownloadIcon size={22} />
          </span>
          {post.media.length > 1 ? "下载当前" : "下载"}
        </a>
        <button type="button" className="fa-action" onClick={() => void pinCover()}>
          <span>
            <PinIcon size={22} />
          </span>
          设为封面
        </button>
        <button
          type="button"
          className="fa-action"
          onClick={() => {
            onHideAuthor(post);
            onClose();
          }}
        >
          <span>
            <EyeOffIcon size={22} />
          </span>
          不看此账号
        </button>
      </div>
      {playback && (
        <div className="fa-share-playback">
          <p id={rateName}>播放倍速</p>
          <div className="fa-share-playback-rates" role="radiogroup" aria-labelledby={rateName}>
            {PLAYBACK_RATES.map((option) => (
              <label key={option}>
                <input type="radio" name={rateName} value={option} checked={rate === option}
                  onChange={() => {
                    if (playback.setRate(option)) setRate(option);
                    else toast("无法为当前视频设置此倍速");
                  }} />
                <span>{option}×</span>
              </label>
            ))}
          </div>
        </div>
      )}
      <label className="fa-switch-row">
        <span>
          自动连播
          <small>看完后自动切到下一个</small>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={preferences.autoNext}
          onChange={(event) => preferences.setAutoNext(event.target.checked)}
        />
      </label>
    </Sheet>
  );
}
