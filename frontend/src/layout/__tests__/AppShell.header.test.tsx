import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "../AppShell";

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { email: "t@example.com", full_name: "Test User" },
    logout: vi.fn(),
    role: "user",
  }),
}));

vi.mock("../../hooks/useTheme", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: vi.fn() }),
}));

vi.mock("../../hooks/useDensity", () => ({
  useDensity: () => ({ density: "comfortable", setDensity: vi.fn() }),
}));

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({
    canAccess: () => true,
    isLoading: false,
    permissions: {},
    error: null,
    refetchPermissions: vi.fn(),
  }),
}));

vi.mock("../../hooks/useInfrastructureHealth", () => ({
  useInfrastructureHealth: () => ({
    services: [
      { label: "Render Server", key: "render", status: "active" },
      { label: "Neon Database", key: "db", status: "active" },
    ],
    lastCheckedAt: null,
    error: null,
  }),
}));

describe("AppShell global header", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("renders Infrastructure once, left of BUY, with SELL and Paper trade", () => {
    render(
      <MemoryRouter initialEntries={["/markets"]}>
        <AppShell>
          <div>Markets body</div>
        </AppShell>
      </MemoryRouter>,
    );
    const infra = screen.getAllByTestId("global-infrastructure");
    expect(infra).toHaveLength(1);
    const buy = screen.getByTestId("global-buy-cta");
    const sell = screen.getByTestId("global-sell-cta");
    const paper = screen.getByTestId("global-paper-cta");
    expect(infra[0].compareDocumentPosition(buy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(buy.compareDocumentPosition(sell) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sell.compareDocumentPosition(paper) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps Infrastructure visible when the page body changes", () => {
    const { rerender } = render(
      <MemoryRouter initialEntries={["/scanner"]}>
        <AppShell>
          <div>Scanner body</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("global-infrastructure")).toBeTruthy();
    rerender(
      <MemoryRouter initialEntries={["/paper"]}>
        <AppShell>
          <div>Paper body</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("global-infrastructure")).toBeTruthy();
  });
});
