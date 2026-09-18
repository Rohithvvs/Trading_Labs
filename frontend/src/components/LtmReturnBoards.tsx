import { LTM_DISPLAY_NAME } from "../utils/strategyIdentity";
import { StrategyReturnBoards } from "./StrategyReturnBoards";

export function LtmReturnBoards({ payload }: { payload: Record<string, any> | null }) {
  return (
    <StrategyReturnBoards
      payload={payload}
      displayName={LTM_DISPLAY_NAME}
      testId="ltm-return-boards"
      averageTestId="ltm-average-return"
      footnoteStrategy="Long-Term Buy & Hold Momentum"
    />
  );
}
