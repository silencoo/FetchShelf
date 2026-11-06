import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 24, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export const HeartIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M12 21.2 10.6 20C5.6 15.5 2.3 12.5 2.3 8.8 2.3 5.8 4.7 3.4 7.7 3.4c1.7 0 3.3.8 4.3 2.1 1-1.3 2.6-2.1 4.3-2.1 3 0 5.4 2.4 5.4 5.4 0 3.7-3.3 6.7-8.3 11.2L12 21.2Z" />
  </svg>
);
export const BookmarkIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M6.2 2.6h11.6c1 0 1.8.8 1.8 1.8v16.4c0 .8-.9 1.2-1.5.8L12 17.3l-6.1 4.3c-.6.4-1.5 0-1.5-.8V4.4c0-1 .8-1.8 1.8-1.8Z" />
  </svg>
);
export const CommentIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M12 2.8c5.5 0 10 3.8 10 8.6s-4.5 8.6-10 8.6c-.9 0-1.8-.1-2.6-.3l-4.5 2.4c-.6.3-1.3-.2-1.2-.9l.5-3.8C2.9 15.5 2 13.5 2 11.4c0-4.8 4.5-8.6 10-8.6Zm-4.4 7.2a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Zm4.4 0a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Zm4.4 0a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Z" />
  </svg>
);
export const ShareIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M13.3 3.4c-.6-.5-1.5-.1-1.5.7v3.7C5.4 8.3 2 13.3 2 19.5c0 .7.9 1 1.3.4 2-2.9 4.8-4.4 8.5-4.5v3.8c0 .8.9 1.2 1.5.7l8.4-7.3c.5-.4.5-1.1 0-1.5l-8.4-7.7Z" />
  </svg>
);
export const PlayIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M7.5 3.9c-.8-.5-1.9.1-1.9 1v14.2c0 .9 1 1.5 1.9 1l11.6-7.1c.8-.5.8-1.6 0-2L7.5 3.9Z" />
  </svg>
);
export const PauseIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <rect x="6" y="4" width="4.2" height="16" rx="1.2" />
    <rect x="13.8" y="4" width="4.2" height="16" rx="1.2" />
  </svg>
);
export const PlusIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={3}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={3}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);
export const MusicIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M19.6 2.6 9.2 5c-.6.1-1 .7-1 1.3v9.7a3.7 3.3 0 1 0 1.8 2.9V10l8.6-2v6.1a3.7 3.3 0 1 0 1.8 2.9V3.5c0-.6-.5-1-1-.9Z" />
  </svg>
);
export const VolumeIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M11 5 6.5 9H3v6h3.5L11 19V5Z" fill="currentColor" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9.2 9.2 0 0 1 0 13" />
  </svg>
);
export const MutedIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M11 5 6.5 9H3v6h3.5L11 19V5Z" fill="currentColor" />
    <path d="m16 9.5 5 5M21 9.5l-5 5" />
  </svg>
);
export const SearchIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20.5 20.5-4.3-4.3" />
  </svg>
);
export const HomeIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M12.7 2.9a1 1 0 0 0-1.4 0L2.8 10.8c-.6.6-.2 1.7.7 1.7h1.3v7.3c0 .9.7 1.6 1.6 1.6h3.3v-5.9c0-.6.4-1 1-1h2.6c.6 0 1 .4 1 1v5.9h3.3c.9 0 1.6-.7 1.6-1.6v-7.3h1.3c.9 0 1.3-1.1.7-1.7l-8.5-7.9Z" />
  </svg>
);
export const CompassIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <circle cx="12" cy="12" r="9.2" />
    <path d="m15.8 8.2-2.3 5.3-5.3 2.3 2.3-5.3 5.3-2.3Z" fill="currentColor" />
  </svg>
);
export const UserIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <circle cx="12" cy="7.6" r="4.6" />
    <path d="M3.6 20.4c0-4 3.8-6.7 8.4-6.7s8.4 2.7 8.4 6.7c0 .6-.5 1-1 1H4.6c-.5 0-1-.4-1-1Z" />
  </svg>
);
export const BackIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={2.4}>
    <path d="m15 5-7 7 7 7" />
  </svg>
);
export const ChevronUpIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={2.4}>
    <path d="m6 15 6-6 6 6" />
  </svg>
);
export const ChevronDownIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={2.4}>
    <path d="m6 9 6 6 6-6" />
  </svg>
);
export const ChevronLeftIcon = BackIcon;
export const ChevronRightIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={2.4}>
    <path d="m9 5 7 7-7 7" />
  </svg>
);
export const CloseIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={2.4}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
export const LinkIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2" />
    <path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3A4.5 4.5 0 0 0 11 19.4l1.2-1.2" />
  </svg>
);
export const ExternalIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M14 4h6v6M20 4l-9 9" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </svg>
);
export const DownloadIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
  </svg>
);
export const PinIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M14.8 2.7c-.5-.5-1.4-.3-1.6.4l-.7 2.5-4.3 3.3-2.7-.2c-.8-.1-1.3.9-.7 1.5l3.5 3.5-4.8 6c-.2.3.1.6.4.4l6-4.8 3.5 3.5c.6.6 1.6.1 1.5-.7l-.2-2.7 3.3-4.3 2.5-.7c.7-.2.9-1.1.4-1.6l-5.6-6.1Z" />
  </svg>
);
export const EyeOffIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M3 3l18 18M10.6 5.2A9.8 9.8 0 0 1 12 5c6 0 9.5 7 9.5 7a16 16 0 0 1-3 3.8M6.5 6.7A15.5 15.5 0 0 0 2.5 12S6 19 12 19c1.8 0 3.3-.6 4.6-1.4" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
  </svg>
);
export const ImagesIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor">
    <path d="M7.6 3h11.6C20.8 3 22 4.2 22 5.8v9.8c0 1.6-1.2 2.8-2.8 2.8H7.6c-1.6 0-2.8-1.2-2.8-2.8V5.8C4.8 4.2 6 3 7.6 3Zm2.1 3.4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 0 0 0-3.8ZM20 13l-3.4-3.4c-.4-.4-1-.4-1.4 0l-5.3 5.3-1.4-1.3c-.4-.4-1-.4-1.3 0l-.9.8v1.2c0 .5.3.8.8.8h11.6c.5 0 .8-.3.8-.8V13ZM2 7.6v10.6C2 20.3 3.7 22 5.8 22h10.6c-.2-.6-.9-1-1.5-1H5.8C4.3 21 3 19.7 3 18.2V8.9c0-.6-.4-1.1-1-1.3Z" />
  </svg>
);
export const LiveIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke} strokeWidth={1.8}>
    <circle cx="12" cy="12" r="3" fill="currentColor" />
    <circle cx="12" cy="12" r="6.2" />
    <circle cx="12" cy="12" r="9.5" strokeDasharray="1.2 2.8" />
  </svg>
);
export const ExitIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9" />
  </svg>
);
export const RefreshIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M20 11a8 8 0 1 0-1.6 5.8M20 5v6h-6" />
  </svg>
);
export const FullscreenIcon = (p: IconProps) => (
  <svg {...base(p)} {...stroke}>
    <path d="M8 3H4v4M16 3h4v4M8 21H4v-4M16 21h4v-4" />
  </svg>
);
