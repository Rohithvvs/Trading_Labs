import { Badge } from "../design-system";

export type TechMetricState = "pass" | "fail" | "off" | "na" | "neutral";

export type TechMetric = {
  label: string;
  value: string;
  state?: TechMetricState;
  hint?: string;
};

export type TechSection = {
  title: string;
  metrics: TechMetric[];
};

type Props = {
  strategyName: string;
  signal: string;
  hardFiltersPass?: boolean | null;
  sections: TechSection[];
  testId?: string;
};

function badgeTone(signal: string): "buy" | "watch" | "negative" | "neutral" {
  const s = (signal || "").toUpperCase();
  if (s === "BUY") return "buy";
  if (s === "WATCH" || s === "HOLD") return "watch";
  if (s === "REJECT") return "negative";
  return "neutral";
}

function stateLabel(state?: TechMetricState): string | null {
  if (state === "pass") return "PASS";
  if (state === "fail") return "FAIL";
  if (state === "off") return "DISABLED";
  if (state === "na") return "NOT AVAILABLE";
  return null;
}

export function displayMetric(raw: unknown, { percent = false, digits = 2 }: { percent?: boolean; digits?: number } = {}): {
  value: string;
  state: TechMetricState;
} {
  if (raw === undefined || raw === null || raw === "" || raw === "unavailable") {
    return { value: "—", state: "na" };
  }
  if (typeof raw === "boolean") {
    return raw ? { value: "Yes", state: "pass" } : { value: "No", state: "fail" };
  }
  if (typeof raw === "number") {
    if (!Number.isFinite(raw)) return { value: "—", state: "na" };
    if (percent) return { value: `${(Math.abs(raw) <= 1.0001 ? raw * 100 : raw).toFixed(digits)}%`, state: "neutral" };
    return { value: Number.isInteger(raw) ? String(raw) : raw.toFixed(digits), state: "neutral" };
  }
  return { value: String(raw), state: "neutral" };
}

export function TechnicalsDecisionPanel({ strategyName, signal, hardFiltersPass, sections, testId }: Props) {
  return (
    <div className="tech-decision" data-testid={testId}>
      <header className="tech-decision__header">
        <div>
          <p className="section-label">Technical decision</p>
          <h3 className="tech-decision__title">{strategyName}</h3>
        </div>
        <div className="tech-decision__flags">
          <Badge tone={badgeTone(signal)}>{signal || "—"}</Badge>
          <Badge tone={hardFiltersPass ? "positive" : hardFiltersPass === false ? "negative" : "neutral"}>
            Hard filters: {hardFiltersPass ? "YES" : hardFiltersPass === false ? "NO" : "—"}
          </Badge>
        </div>
      </header>
      {sections.map((section) => (
        <section key={section.title} className="tech-decision__section">
          <h4 className="tech-decision__section-title">{section.title}</h4>
          <div className="tech-decision__grid">
            {section.metrics.map((m) => (
              <article key={m.label} className={`tech-metric tech-metric--${m.state || "neutral"}`}>
                <span className="tech-metric__label">{m.label}</span>
                <strong className="tech-metric__value">{m.value}</strong>
                {stateLabel(m.state) ? (
                  <span className={`tech-metric__state tech-metric__state--${m.state}`}>{stateLabel(m.state)}</span>
                ) : null}
                {m.hint ? <span className="tech-metric__hint">{m.hint}</span> : null}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
