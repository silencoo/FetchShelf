import { useEffect, useRef, useState } from "react";

import { headerOptions } from "../legacy/runtime.js";
import { fileUrl } from "./api";
import { CopyIcon } from "./icons";
import { toast } from "./store";
import type { MediaItem } from "./types";

type Props = { onCopied(): void } & (
  { item: MediaItem; screenshot?: never } | { item?: never; screenshot: File }
);

/** PNG is the interoperable clipboard format, including for JPEG/WebP photos. */
async function photoPng(item: MediaItem, signal: AbortSignal): Promise<Blob> {
  const response = await fetch(fileUrl(item.path), { headers: headerOptions(false), signal });
  if (!response.ok) throw new Error("图片读取失败，请重试或下载图片。");
  const blob = await response.blob();
  if (!blob.size) throw new Error("图片文件为空，无法复制。");
  const url = URL.createObjectURL(blob);
  const canvas = document.createElement("canvas");
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    signal.throwIfAborted();
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("此浏览器无法转换图片，请下载后使用。");
    context.drawImage(image, 0, 0);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((png) => png?.size ? resolve(png) : reject(new Error("图片转换失败，请下载后使用。")), "image/png");
    });
  } finally {
    URL.revokeObjectURL(url);
    canvas.width = canvas.height = 0;
  }
}

export function ImageCopyAction({ item, screenshot, onCopied }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => operation.current?.abort(), []);

  const copy = async () => {
    if (operation.current) return;
    if (!window.isSecureContext) {
      setMessage("复制图片需要 HTTPS，请使用 HTTPS 地址打开；也可以先下载保存。");
      return;
    }
    if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
      setMessage("此浏览器暂不支持复制图片，请下载保存或使用系统分享。");
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setMessage("");
    try {
      const png = screenshot ? Promise.resolve(screenshot) : photoPng(item!, controller.signal);
      // Handle conversion rejection even if clipboard permission is denied first.
      void png.catch(() => {});
      // Call write on the click itself; Safari loses activation after awaiting fetch.
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      if (!controller.signal.aborted) {
        toast(screenshot ? "截图已复制，可粘贴到其他应用" : "图片已复制，可粘贴到其他应用");
        onCopied();
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      controller.abort();
      setMessage(error instanceof Error && error.name === "NotAllowedError"
        ? "未获得剪贴板权限，请允许此网站复制图片后重试，或下载保存。"
        : "无法复制图片，请重试，或下载保存后使用。");
    } finally {
      if (operation.current === controller) operation.current = null;
      setBusy(false);
    }
  };

  return <>
    <button type="button" className="fa-action" onClick={() => void copy()} disabled={busy} aria-busy={busy}>
      <span><CopyIcon size={22} /></span>
      {busy ? "正在复制…" : screenshot ? "复制截图" : "复制图片"}
    </button>
    {message ? <p className="fa-share-status" role="status">{message}</p> : null}
  </>;
}
