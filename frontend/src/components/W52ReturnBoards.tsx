import { W52_DISPLAY_NAME } from "../utils/strategyIdentity";
import { StrategyReturnBoards } from "./StrategyReturnBoards";

export function W52ReturnBoards({ payload }: { payload: Record<string, any> | null }) {
  return (
    <StrategyReturnBoards
      payload={payload}
      displayName={W52_DISPLAY_NAME}
      testId="w52-return-boards"
      averageTestId="w52-average-return"
      footnoteStrategy="52-Week High Breakout"
    />
  );
}
