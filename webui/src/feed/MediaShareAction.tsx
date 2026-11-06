import { useEffect, useRef, useState } from "react";

import { headerOptions } from "../legacy/runtime.js";
import { fileUrl } from "./api";
import { ShareIcon } from "./icons";
import type { MediaItem } from "./types";

const MIME_TYPES: Record<string, string> = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", gif: "image/gif",
  webp: "image/webp", avif: "image/avif", heic: "image/heic",
  mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm",
};

/** Download only on request, then hand the actual file to the OS share sheet. */
export function MediaShareAction({ item, onShared }: { item: MediaItem; onShared(): void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => operation.current?.abort(), []);

  const share = async () => {
    if (operation.current && !operation.current.signal.aborted) return;
    if (!window.isSecureContext) {
      setMessage("系统文件分享需要 HTTPS，请使用 HTTPS 地址打开；也可以先下载媒体。");
      return;
    }
    if (typeof navigator.share !== "function" || typeof navigator.canShare !== "function") {
      setMessage("此浏览器暂不支持文件分享，请先下载媒体，再从照片或文件 App 分享。");
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setMessage("");
    try {
      let ready = file;
      if (!ready) {
        setMessage("正在准备媒体，较大的视频可能需要一些时间…");
        const response = await fetch(fileUrl(item.path), {
          headers: headerOptions(false), signal: controller.signal,
        });
        if (!response.ok) throw new Error("媒体读取失败，请重试或下载媒体。");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (!blob.size) throw new Error("媒体文件为空，无法分享。");
        const name = item.path.split("/").pop() || (item.kind === "video" ? "video.mp4" : "photo.jpg");
        const extension = name.split(".").pop()?.toLowerCase() || "";
        const type = MIME_TYPES[extension] || blob.type;
        ready = new File([blob], name, { type });
        if (!navigator.canShare({ files: [ready] })) {
          throw new Error("此设备无法分享这个文件格式，请先下载媒体。");
        }
        setFile(ready);
        // Safari's tap permission may expire while a large file downloads.
        // A fresh tap on the ready button must invoke share without an await.
        if (!navigator.userActivation?.isActive) {
          setMessage("媒体已准备好，请点“继续分享”选择 App。");
          return;
        }
      }
      setMessage("");
      await navigator.share({ files: [ready] });
      if (!controller.signal.aborted) onShared();
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof Error && error.name === "AbortError") {
        // Closing the native sheet is cancellation, not a failed download.
        setMessage("");
      } else if (error instanceof Error && error.name === "NotAllowedError") {
        setMessage("请再次点“继续分享”；如果仍无法打开，可先下载媒体。");
      } else {
        setMessage(error instanceof Error ? error.message : "暂时无法分享，请重试或下载媒体。");
      }
    } finally {
      if (!controller.signal.aborted) {
        operation.current = null;
        setBusy(false);
      }
    }
  };

  return <>
    <button type="button" className="fa-action" onClick={() => void share()} disabled={busy} aria-busy={busy}>
      <span><ShareIcon size={22} /></span>
      {busy ? "准备分享…" : file ? "继续分享" : item.kind === "video" ? "分享视频" : "分享图片"}
    </button>
    {message ? <p className="fa-share-status" role="status">{message}</p> : null}
  </>;
}
