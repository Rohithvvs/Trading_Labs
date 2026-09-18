import { W52_DISPLAY_NAME } from "../utils/strategyIdentity";
import { StrategyAverageReturn } from "./StrategyAverageReturn";

export function W52AverageReturn({ payload }: { payload: Record<string, any> | null }) {
  return <StrategyAverageReturn payload={payload} displayName={W52_DISPLAY_NAME} testId="w52-average-return" />;
}
