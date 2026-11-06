import { useEffect, useState } from "react";

import { MediaShareAction } from "./MediaShareAction";
import { DownloadIcon, ShareIcon } from "./icons";
import type { VideoSnapshot } from "./videoSnapshot";

export function ScreenshotShareAction({ snapshot, onShared }: { snapshot: VideoSnapshot; onShared(): void }) {
  const [ready, setReady] = useState<{ file: File; url: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    let url = "";
    setReady(null);
    setError("");
    void snapshot.then((result) => {
      if (disposed) return;
      if (result.file) {
        url = URL.createObjectURL(result.file);
        setReady({ file: result.file, url });
      } else {
        setError(result.error);
      }
    });
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [snapshot]);

  if (!ready) return <>
    <button type="button" className="fa-action" disabled aria-busy={!error}>
      <span><ShareIcon size={22} /></span>
      {error ? "截图不可用" : "正在截图…"}
    </button>
    {error ? <p className="fa-share-status" role="status">{error}</p> : null}
  </>;

  return <>
    <MediaShareAction screenshot={ready.file} onShared={onShared} />
    <a className="fa-action" href={ready.url} download={ready.file.name}>
      <span><DownloadIcon size={22} /></span>
      保存截图
    </a>
  </>;
}
