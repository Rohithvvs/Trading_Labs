import React, { useRef, useMemo, useEffect } from "react";

interface PineCodeEditorProps {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  readOnly?: boolean;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function highlightPineCode(code: string): string {
  const lines = code.split("\n");
  const highlightedLines = lines.map((line) => {
    // Check for comment
    let commentPart = "";
    let codePart = line;

    // Check version comment
    const vMatch = line.match(/^(\s*\/\/\s*@version\s*=\s*\d+)(.*)$/i);
    if (vMatch) {
      return `<span class="pine-tok-version">${escapeHtml(vMatch[1])}</span><span class="pine-tok-comment">${escapeHtml(vMatch[2])}</span>`;
    }

    const commentIdx = line.indexOf("//");
    if (commentIdx !== -1) {
      codePart = line.slice(0, commentIdx);
      commentPart = line.slice(commentIdx);
    }

    let escaped = escapeHtml(codePart);

    // Strings: "..." or '...'
    escaped = escaped.replace(
      /(&quot;.*?&quot;|&#039;.*?&#039;)/g,
      '<span class="pine-tok-string">$1</span>'
    );

    // Strategy calls & keywords
    escaped = escaped.replace(
      /\b(strategy\.(?:entry|close|exit|order|cancel|position_size|position_avg_price|long|short)|strategy)\b/g,
      '<span class="pine-tok-strategy">$1</span>'
    );

    // Technical Analysis & inputs
    escaped = escaped.replace(
      /\b(ta\.(?:sma|ema|wma|rsi|highest|lowest|crossover|crossunder|macd|stoch|atr|roc|rma)|sma|ema|rsi|highest|lowest|crossover|crossunder|input\.(?:int|float|bool|string|symbol|timeframe)|input|request\.security|indicator|plotshape|alertcondition|plot)\b/g,
      '<span class="pine-tok-func">$1</span>'
    );

    // Builtin series
    escaped = escaped.replace(
      /\b(close|open|high|low|volume|hl2|hlc3|ohlc4|bar_index|time)\b/g,
      '<span class="pine-tok-series">$1</span>'
    );

    // Keywords
    escaped = escaped.replace(
      /\b(and|or|not|if|else|true|false|var|varip|for|while|return|break|continue)\b/g,
      '<span class="pine-tok-keyword">$1</span>'
    );

    // Numbers
    escaped = escaped.replace(
      /\b(\d+(?:\.\d+)?)\b/g,
      '<span class="pine-tok-number">$1</span>'
    );

    // Operators
    escaped = escaped.replace(
      /(&gt;=|&lt;=|&gt;|&lt;|==|!=|:=|=|\+|-|\*|\/)/g,
      '<span class="pine-tok-operator">$1</span>'
    );

    if (commentPart) {
      escaped += `<span class="pine-tok-comment">${escapeHtml(commentPart)}</span>`;
    }

    return escaped;
  });

  return highlightedLines.join("\n") + "\n";
}

export const PineCodeEditor: React.FC<PineCodeEditorProps> = ({
  value,
  onChange,
  placeholder = "Enter Pine Script code here...",
  readOnly = false,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const lineNumsRef = useRef<HTMLDivElement>(null);

  const linesCount = useMemo(() => {
    return Math.max(1, value.split("\n").length);
  }, [value]);

  const lineNumbers = useMemo(() => {
    return Array.from({ length: linesCount }, (_, i) => i + 1);
  }, [linesCount]);

  const highlightedHtml = useMemo(() => {
    return highlightPineCode(value);
  }, [value]);

  const handleScroll = () => {
    if (!textareaRef.current) return;
    const top = textareaRef.current.scrollTop;
    const left = textareaRef.current.scrollLeft;
    if (preRef.current) {
      preRef.current.scrollTop = top;
      preRef.current.scrollLeft = left;
    }
    if (lineNumsRef.current) {
      lineNumsRef.current.scrollTop = top;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const target = e.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const spaces = "    ";
      const nextValue = value.substring(0, start) + spaces + value.substring(end);
      onChange(nextValue);

      // Restore cursor position
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + 4;
        }
      }, 0);
    }
  };

  return (
    <div className="pine-editor-container" data-testid="pine-code-editor">
      {/* Line numbers gutter */}
      <div className="pine-line-numbers" ref={lineNumsRef} aria-hidden="true">
        {lineNumbers.map((num) => (
          <div key={num} className="pine-line-num">
            {num}
          </div>
        ))}
      </div>

      {/* Code editing area */}
      <div className="pine-editor-canvas">
        {/* Highlighted syntax overlay */}
        <pre
          ref={preRef}
          className="pine-highlight-overlay"
          aria-hidden="true"
          dangerouslySetInnerHTML={{ __html: highlightedHtml }}
        />

        {/* Real transparent textarea */}
        <textarea
          ref={textareaRef}
          className="pine-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={handleScroll}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          readOnly={readOnly}
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          autoCorrect="off"
          data-testid="pine-textarea"
        />
      </div>
    </div>
  );
};
