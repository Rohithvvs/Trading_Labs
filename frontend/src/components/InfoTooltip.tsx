import React, { useState, useRef, useEffect, useLayoutEffect, useCallback, useId } from 'react';
import { createPortal } from 'react-dom';

export interface InfoTooltipProps {
  content: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  maxWidth?: string;
  icon?: React.ReactNode;
  ariaLabel?: string;
}

interface Coords {
  top: number;
  left: number;
  placement: 'top' | 'bottom' | 'left' | 'right';
  arrowLeft?: number;
}

export function InfoTooltip({
  content,
  position = 'top',
  maxWidth = '280px',
  icon,
  ariaLabel = 'More information',
}: InfoTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;

    const triggerRect = trigger.getBoundingClientRect();
    const tooltipEl = tooltipRef.current;
    const tooltipWidth = tooltipEl?.offsetWidth || 260;
    const tooltipHeight = tooltipEl?.offsetHeight || 64;

    const margin = 8;
    const viewportPad = 8;
    const vw = typeof window !== 'undefined' && window.innerWidth > 0 ? window.innerWidth : 1024;
    const vh = typeof window !== 'undefined' && window.innerHeight > 0 ? window.innerHeight : 768;

    let effectivePosition = position;

    // Viewport boundary check & auto-flip
    if (position === 'top') {
      const spaceTop = triggerRect.top;
      const spaceBottom = vh - triggerRect.bottom;
      if (spaceTop < tooltipHeight + margin && spaceBottom > spaceTop) {
        effectivePosition = 'bottom';
      }
    } else if (position === 'bottom') {
      const spaceTop = triggerRect.top;
      const spaceBottom = vh - triggerRect.bottom;
      if (spaceBottom < tooltipHeight + margin && spaceTop > spaceBottom) {
        effectivePosition = 'top';
      }
    } else if (position === 'left') {
      const spaceLeft = triggerRect.left;
      const spaceRight = vw - triggerRect.right;
      if (spaceLeft < tooltipWidth + margin && spaceRight > spaceLeft) {
        effectivePosition = 'right';
      }
    } else if (position === 'right') {
      const spaceLeft = triggerRect.left;
      const spaceRight = vw - triggerRect.right;
      if (spaceRight < tooltipWidth + margin && spaceLeft > spaceRight) {
        effectivePosition = 'left';
      }
    }

    let top = 0;
    let left = 0;

    if (effectivePosition === 'top') {
      top = triggerRect.top - tooltipHeight - margin;
      left = triggerRect.left + (triggerRect.width || 14) / 2 - tooltipWidth / 2;
    } else if (effectivePosition === 'bottom') {
      top = triggerRect.bottom + margin;
      left = triggerRect.left + (triggerRect.width || 14) / 2 - tooltipWidth / 2;
    } else if (effectivePosition === 'left') {
      top = triggerRect.top + (triggerRect.height || 14) / 2 - tooltipHeight / 2;
      left = triggerRect.left - tooltipWidth - margin;
    } else {
      // right
      top = triggerRect.top + (triggerRect.height || 14) / 2 - tooltipHeight / 2;
      left = triggerRect.right + margin;
    }

    // Clamp within viewport
    const clampedLeft = Math.max(viewportPad, Math.min(left, vw - tooltipWidth - viewportPad));
    const clampedTop = Math.max(viewportPad, Math.min(top, vh - tooltipHeight - viewportPad));

    // Align arrow to trigger center
    const triggerCenterX = triggerRect.left + (triggerRect.width || 14) / 2;
    const arrowLeft = Math.max(12, Math.min(tooltipWidth - 12, triggerCenterX - clampedLeft));

    setCoords({
      top: clampedTop,
      left: clampedLeft,
      placement: effectivePosition,
      arrowLeft,
    });
  }, [position]);

  const showTooltip = useCallback(() => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
    setIsVisible(true);
  }, []);

  const hideTooltip = useCallback(() => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
    }
    hideTimeoutRef.current = setTimeout(() => {
      setIsVisible(false);
      setCoords(null);
    }, 120);
  }, []);

  useLayoutEffect(() => {
    if (!isVisible) return;

    updatePosition();
    const frameId = requestAnimationFrame(updatePosition);

    const handleScrollOrResize = () => {
      updatePosition();
    };

    window.addEventListener('scroll', handleScrollOrResize, true);
    window.addEventListener('resize', handleScrollOrResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener('scroll', handleScrollOrResize, true);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [isVisible, updatePosition]);

  useEffect(() => {
    if (!isVisible) return;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || tooltipRef.current?.contains(target)) {
        return;
      }
      setIsVisible(false);
      setCoords(null);
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsVisible(false);
        setCoords(null);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isVisible]);

  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current);
      }
    };
  }, []);

  const tooltipPortal =
    isVisible && typeof document !== 'undefined'
      ? createPortal(
          <div
            ref={tooltipRef}
            id={tooltipId}
            role="tooltip"
            data-testid="info-tooltip-popover"
            className={`tooltip-content tooltip-${coords?.placement ?? position}`}
            onMouseEnter={showTooltip}
            onMouseLeave={hideTooltip}
            style={{
              position: 'fixed',
              top: coords ? `${coords.top}px` : '0px',
              left: coords ? `${coords.left}px` : '0px',
              zIndex: 10000,
              background: 'var(--surface-2, #1e293b)',
              color: 'var(--text, #e2e8f0)',
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '12px',
              lineHeight: '1.5',
              width: 'max-content',
              maxWidth: maxWidth,
              boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
              border: '1px solid var(--border, #334155)',
              whiteSpace: 'pre-line',
              wordWrap: 'break-word',
              pointerEvents: 'auto',
              '--tooltip-arrow-left': coords?.arrowLeft ? `${coords.arrowLeft}px` : '50%',
            } as React.CSSProperties}
          >
            {content}
          </div>,
          document.body
        )
      : null;

  return (
    <span
      className="info-tooltip-container"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: '6px', verticalAlign: 'middle' }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="info-icon-btn"
        aria-label={ariaLabel}
        aria-describedby={isVisible ? tooltipId : undefined}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (isVisible) {
            setIsVisible(false);
            setCoords(null);
          } else {
            showTooltip();
          }
        }}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'help',
          padding: '2px 4px',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '13px',
          color: '#94a3b8',
          transition: 'color 0.2s',
          lineHeight: 1,
        }}
        onMouseOver={(e) => (e.currentTarget.style.color = '#3b82f6')}
        onMouseOut={(e) => (e.currentTarget.style.color = '#94a3b8')}
      >
        {icon ?? (
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        )}
      </button>

      {tooltipPortal}
    </span>
  );
}
