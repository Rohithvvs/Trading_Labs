import { useEffect, useRef, useState } from "react";
import { useInfrastructureHealth, type ServiceBadgeState } from "../hooks/useInfrastructureHealth";

const BADGE_CONFIG: Record<ServiceBadgeState, { text: string; dotClass: string }> = {
  active: { text: "Active", dotClass: "infra-card__dot--active" },
  waking: { text: "Waking Up", dotClass: "infra-card__dot--waking" },
  connecting: { text: "Connecting", dotClass: "infra-card__dot--connecting" },
  offline: { text: "Offline", dotClass: "infra-card__dot--offline" },
  sleeping: { text: "Sleeping", dotClass: "infra-card__dot--sleeping" },
};

type Props = {
  variant?: "panel" | "header";
};

export function InfrastructureStatus({ variant = "panel" }: Props) {
  const { services, lastCheckedAt, error } = useInfrastructureHealth();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent | TouchEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const cards = (
    <div className="infra-cards">
      {services.map((svc) => {
        const badge = BADGE_CONFIG[svc.status] || BADGE_CONFIG.sleeping;
        return (
          <div key={svc.key} className="infra-card" data-status={svc.status}>
            <div className="infra-card__row">
              <span className={`infra-card__dot ${badge.dotClass}`} aria-hidden />
              <span className="infra-card__label">{svc.label}</span>
            </div>
            <span className="infra-card__badge">
              {badge.text}
              {svc.meta && <span className="infra-card__meta">{svc.meta}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );

  if (variant === "header") {
    const offline = services.filter((s) => s.status === "offline" || s.status === "sleeping").length;
    return (
      <div className="infra-header" ref={wrapRef} data-testid="global-infrastructure">
        <button
          type="button"
          className="infra-header__toggle"
          aria-expanded={open}
          aria-haspopup="dialog"
          onClick={() => setOpen((v) => !v)}
        >
          <span className="infra-header__label">Infrastructure</span>
          <span className="infra-header__dots" aria-hidden>
            {services.map((svc) => {
              const badge = BADGE_CONFIG[svc.status] || BADGE_CONFIG.sleeping;
              return (
                <span
                  key={svc.key}
                  className={`infra-card__dot ${badge.dotClass}`}
                  title={`${svc.label}: ${badge.text}`}
                />
              );
            })}
          </span>
          {offline ? <span className="infra-header__warn">{offline}</span> : null}
        </button>
        {open ? (
          <div className="infra-header__popover" role="dialog" aria-label="Infrastructure health">
            <h3 className="infra-panel__header">
              Infrastructure
              {lastCheckedAt ? (
                <span className="infra-panel__time">· {lastCheckedAt.toLocaleTimeString()}</span>
              ) : null}
            </h3>
            {cards}
            {error ? <p className="infra-panel__error">{error}</p> : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="infra-panel" aria-label="Infrastructure health">
      <h3 className="infra-panel__header">
        Infrastructure
        {lastCheckedAt && (
          <span className="infra-panel__time">
            · {lastCheckedAt.toLocaleTimeString()}
          </span>
        )}
      </h3>
      {cards}
      {error && <p className="infra-panel__error">{error}</p>}
    </div>
  );
}
