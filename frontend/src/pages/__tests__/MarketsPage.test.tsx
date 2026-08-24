import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api", () => ({
  fetchMarketOverview: vi.fn(async () => ({})),
  fetchSavedScans: vi.fn(async () => []),
  fetchWorkstationAlerts: vi.fn(async () => []),
  getLatestScan: vi.fn(async () => null),
  fetchUserProfile: vi.fn(async () => ({ preferences: {} })),
  createWorkstationAlert: vi.fn(),
  deleteScannerPreset: vi.fn(),
  deleteWorkstationAlert: vi.fn(),
}));

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { email: "t@example.com", full_name: "Test" } }),
}));

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({ canAccess: () => true, isLoading: false }),
}));

vi.mock("../../components/FeatureGuard", () => ({
  FeatureGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("../../utils/appCache", () => ({
  CACHE_KEYS: { marketOverview: "m", savedScans: "s", workstationAlerts: "a", latestScan: "l" },
  getCached: () => null,
}));

import { MarketsPage } from "../MarketsPage";

describe("MarketsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render Swing Decision Dashboard or Scanner Statistics", () => {
    render(
      <MemoryRouter>
        <MarketsPage />
      </MemoryRouter>,
    );
    expect(screen.queryByText("Swing Decision Dashboard")).toBeNull();
    expect(screen.queryByText("Scanner statistics")).toBeNull();
    expect(screen.queryByLabelText("Swing Decision Dashboard")).toBeNull();
    expect(screen.queryByLabelText("Scanner statistics")).toBeNull();
    expect(screen.getByText("Market summary")).toBeTruthy();
  });
});
