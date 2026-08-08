/** Inline SVG icons for Recommendation Lab (no new icon package dependency). */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
    ...props,
  };
}

export function IconFlask(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9 3h6 M10 3v6.5L4.5 19a2 2 0 0 0 1.7 3h12a2 2 0 0 0 1.7-3L14 9.5V3" />
    </svg>
  );
}

export function IconLayers(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 2 2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5" />
    </svg>
  );
}

export function IconTrending(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 17 9 11l4 4 8-8 M14 7h7v7" />
    </svg>
  );
}

export function IconWallet(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 7a2 2 0 0 1 2-2h14v14H5a2 2 0 0 1-2-2V7z M21 10h-5a2 2 0 0 0 0 4h5" />
    </svg>
  );
}

export function IconTrophy(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M8 21h8 M12 17v4 M7 4h10v5a5 5 0 0 1-10 0V4z M17 5h2a3 3 0 0 1 0 6h-2 M7 5H5a3 3 0 0 0 0 6h2" />
    </svg>
  );
}

export function IconActivity(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}

export function IconTarget(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}

export function IconChart(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19V5 M9 19v-8 M14 19v-5 M19 19V9" />
    </svg>
  );
}

export function IconBrain(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 5a4 4 0 0 0-4 4v1a3 3 0 0 0-2 2.8V15a3 3 0 0 0 3 3h1 M12 5a4 4 0 0 1 4 4v1a3 3 0 0 1 2 2.8V15a3 3 0 0 1-3 3h-1 M9 18v2 M15 18v2 M12 8v12" />
    </svg>
  );
}

export function IconEye(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function IconBar(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19h16 M7 16V9 M12 16V5 M17 16v-4" />
    </svg>
  );
}

export function IconHistory(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 12a9 9 0 1 0 3-6.7 M3 4v5h5 M12 7v5l3 2" />
    </svg>
  );
}

export function IconAlert(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 9v4 M12 17h.01 M10.3 3.3 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.3a2 2 0 0 0-3.4 0z" />
    </svg>
  );
}

export function IconCheck(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function IconScale(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3v18 M5 7h14 M5 7l-3 7a4 4 0 0 0 8 0L7 7 M19 7l-3 7a4 4 0 0 0 8 0l-3-7" />
    </svg>
  );
}
