import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { UserProfilePage } from "../profile/UserProfilePage";
import { ToastProvider } from "../../design-system";

const mockUseAuth = vi.fn();
const mockCanAccess = vi.fn();
const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../../hooks/useTheme", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn() }),
}));

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({
    canAccess: mockCanAccess,
    isLoading: false,
    permissions: {},
    error: null,
    refetchPermissions: vi.fn(),
  }),
}));

vi.mock("../../api", () => ({
  authMe: vi.fn().mockResolvedValue({ id: "1", email: "admin@test.com", full_name: "Admin User", role: "admin" }),
  fetchUserProfile: vi.fn().mockResolvedValue({ user_id: "1", display_name: "Admin User" }),
  fetchPaperTradingDashboard: vi.fn().mockResolvedValue({ account: { balance: 100000, equity: 100000 }, positions: [], trades: [] }),
  fetchAnalytics: vi.fn().mockResolvedValue({ total_trades: 0, win_rate_pct: 0 }),
  getTokenStatus: vi.fn().mockResolvedValue({ status: "active" }),
  fetchApiHealth: vi.fn().mockResolvedValue({ status: "ok" }),
  updateUserProfile: vi.fn().mockResolvedValue({}),
}));

function renderProfile() {
  return render(
    <ToastProvider>
      <MemoryRouter>
        <UserProfilePage retailMode={false} />
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("Profile Page 4 Settings (Admin, Central Command, System Logs, Diagnostics)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all 4 admin settings inside Profile for admin user", async () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", email: "admin@test.com", full_name: "Admin User", role: "admin" },
      role: "admin",
      logout: vi.fn(),
      updateUser: vi.fn(),
    });
    mockCanAccess.mockReturnValue(true);

    renderProfile();

    // Verify Administration Settings in Overview section
    expect(screen.getByTestId("profile-admin-settings-section")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-admin")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-central-command")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-system-logs")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-diagnostics")).toBeTruthy();

    // Verify sidebar and section items
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Central Command").length).toBeGreaterThan(0);
    expect(screen.getAllByText("System Logs").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Diagnostics").length).toBeGreaterThan(0);
  });

  it("hides admin settings inside Profile for regular trader user", async () => {
    mockUseAuth.mockReturnValue({
      user: { id: "2", email: "trader@test.com", full_name: "Trader User", role: "trader" },
      role: "trader",
      logout: vi.fn(),
      updateUser: vi.fn(),
    });
    mockCanAccess.mockReturnValue(true);

    renderProfile();

    // Admin section in overview should not be rendered
    expect(screen.queryByTestId("profile-admin-settings-section")).toBeNull();
    expect(screen.queryByTestId("profile-overview-admin")).toBeNull();
    expect(screen.queryByTestId("profile-overview-central-command")).toBeNull();
    expect(screen.queryByTestId("profile-overview-system-logs")).toBeNull();
    expect(screen.queryByTestId("profile-overview-diagnostics")).toBeNull();
  });

  it("navigates to admin routes when clicked from overview cards", async () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", email: "admin@test.com", full_name: "Admin User", role: "admin" },
      role: "admin",
      logout: vi.fn(),
      updateUser: vi.fn(),
    });
    mockCanAccess.mockReturnValue(true);

    renderProfile();

    fireEvent.click(screen.getByText("Open Admin"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin");

    fireEvent.click(screen.getByText("Open Command"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/command");

    fireEvent.click(screen.getByText("View Logs"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/logs");

    fireEvent.click(screen.getByText("Run Diagnostics"));
    expect(mockNavigate).toHaveBeenCalledWith("/diagnostics");
  });

  it("filters admin settings in profile when specific permissions are denied", async () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", email: "admin@test.com", full_name: "Admin User", role: "admin" },
      role: "admin",
      logout: vi.fn(),
      updateUser: vi.fn(),
    });

    mockCanAccess.mockImplementation((key: string) => {
      if (key === "central_command") return false;
      return true;
    });

    renderProfile();

    expect(screen.getByTestId("profile-overview-admin")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-system-logs")).toBeTruthy();
    expect(screen.getByTestId("profile-overview-diagnostics")).toBeTruthy();
    expect(screen.queryByTestId("profile-overview-central-command")).toBeNull();
  });
});
