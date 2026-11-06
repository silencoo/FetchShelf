import { createRoot, type Root } from "react-dom/client";

import { FeedApp } from "./FeedApp";
import { mediaPool } from "./player";
import "./feed.css";

const IMMERSIVE_VIEWPORT =
  "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover";

let root: Root | null = null;
let savedViewport: string | null = null;
let savedThemeColor: string | null = null;

// iOS Safari ignores `user-scalable=no`, so pinch has to be declined by hand.
function blockPinch(event: Event) {
  event.preventDefault();
}

function setChrome(immersive: boolean) {
  const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (immersive) {
    savedViewport ??= viewport?.content ?? null;
    savedThemeColor ??= themeColor?.content ?? null;
    viewport?.setAttribute("content", IMMERSIVE_VIEWPORT);
    themeColor?.setAttribute("content", "#000000");
    document.addEventListener("gesturestart", blockPinch);
  } else {
    if (savedViewport !== null) {
      viewport?.setAttribute("content", savedViewport);
    }
    if (savedThemeColor !== null) {
      themeColor?.setAttribute("content", savedThemeColor);
    }
    savedViewport = null;
    savedThemeColor = null;
    document.removeEventListener("gesturestart", blockPinch);
  }
}

export function activateFeed(container: HTMLElement, onExit: () => void) {
  setChrome(true);
  root ??= createRoot(container);
  root.render(<FeedApp active onExit={onExit} />);
}

export function deactivateFeed(onExit: () => void) {
  setChrome(false);
  root?.render(<FeedApp active={false} onExit={onExit} />);
  mediaPool.release();
}
