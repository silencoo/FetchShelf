import { useState } from "react";

import { thumbUrl } from "./api";
import type { Account } from "./types";

/** A saved selection may disappear between the API response and image load. */
export function AccountCover({ account, className, width, lazy = false }: {
  account: Account;
  className: string;
  width: number;
  lazy?: boolean;
}) {
  const fallback = account.cover ? thumbUrl(account.cover, { w: width }) : "";
  const preferred = account.avatar?.scope === "download"
    ? thumbUrl(account.avatar.path, { w: width, second: account.avatar.second })
    : fallback;
  // Remount on source changes so a reused tile can recover after a refresh.
  return <CoverImage key={JSON.stringify([preferred, fallback])}
    preferred={preferred} fallback={fallback} className={className} lazy={lazy} />;
}

function CoverImage({ preferred, fallback, className, lazy }: {
  preferred: string;
  fallback: string;
  className: string;
  lazy: boolean;
}) {
  const [failed, setFailed] = useState<string[]>([]);
  const src = [preferred, fallback].find((url) => url && !failed.includes(url));
  // The existing tile/hero background remains when neither preview is usable.
  return src ? <img key={src} className={className} src={src} alt=""
    loading={lazy ? "lazy" : undefined} decoding="async"
    onError={() => setFailed((previous) => [...previous, src])} /> : null;
}
