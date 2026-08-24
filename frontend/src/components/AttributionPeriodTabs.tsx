import { ATTRIBUTION_PERIODS, type AttributionPeriod } from "../utils/attributionPeriod";

export function AttributionPeriodTabs({
  value,
  onChange,
  ariaLabel = "Attribution period",
}: {
  value: AttributionPeriod;
  onChange: (period: AttributionPeriod) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="bt-period-tabs" role="tablist" aria-label={ariaLabel}>
      {ATTRIBUTION_PERIODS.map((period) => (
        <button
          key={period}
          type="button"
          role="tab"
          aria-selected={value === period}
          className={`bt-period-tabs__btn ${value === period ? "is-active" : ""}`}
          onClick={() => onChange(period)}
        >
          {period}
        </button>
      ))}
    </div>
  );
}
