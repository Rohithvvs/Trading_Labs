import React, { useState } from 'react';

export interface InfoTooltipProps {
  content: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  maxWidth?: string;
  icon?: React.ReactNode;
  ariaLabel?: string;
}

export function InfoTooltip({
  content,
  position = 'top',
  maxWidth = '280px',
  icon,
  ariaLabel = 'More information',
}: InfoTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <span
      className="info-tooltip-container"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: '6px', verticalAlign: 'middle' }}
    >
      <button
        type="button"
        className="info-icon-btn"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsVisible(!isVisible);
        }}
        aria-label={ariaLabel}
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

      {isVisible && (
        <div
          className={`tooltip-content tooltip-${position}`}
          style={{
            position: 'absolute',
            zIndex: 9999,
            background: 'var(--card-bg, #1e293b)',
            color: 'var(--text-primary, #e2e8f0)',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '12px',
            lineHeight: '1.5',
            width: 'max-content',
            maxWidth: maxWidth,
            boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
            border: '1px solid var(--border-color, #334155)',
            whiteSpace: 'normal',
            wordWrap: 'break-word',
            pointerEvents: 'auto',
            ...(position === 'top' && { bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: '8px' }),
            ...(position === 'bottom' && { top: '100%', left: '50%', transform: 'translateX(-50%)', marginTop: '8px' }),
            ...(position === 'left' && { right: '100%', top: '50%', transform: 'translateY(-50%)', marginRight: '8px' }),
            ...(position === 'right' && { left: '100%', top: '50%', transform: 'translateY(-50%)', marginLeft: '8px' }),
          }}
        >
          {content}
        </div>
      )}
    </span>
  );
}
