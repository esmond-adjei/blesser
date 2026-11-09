import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { RoleGuard } from "./auth";
import type { Role, StaffUser } from "./api";

const staff = (role: Role): StaffUser => ({
  id: "person",
  email: "staff@example.test",
  display_name: null,
  role,
  email_verified: true,
  disabled: false,
  created_at: "2026-11-01T00:00:00Z",
  scans_last_30_days: 0,
});
function guarded(user: StaffUser | null, adminOnly = false, ready = true) {
  return renderToString(
    <MemoryRouter initialEntries={["/people"]}>
      <RoleGuard user={user} adminOnly={adminOnly} ready={ready}>
        <div>Protected staff content</div>
      </RoleGuard>
    </MemoryRouter>,
  );
}
describe("staff route guard", () => {
  it("renders editor tools for verified editors", () =>
    expect(guarded(staff("editor"))).toContain("Protected staff content"));
  it("renders admin tools for admins", () =>
    expect(guarded(staff("admin"), true)).toContain("Protected staff content"));
  it("blocks editors from admin pages even through a direct URL", () => {
    const html = guarded(staff("editor"), true);
    expect(html).toContain("An admin role is required");
    expect(html).not.toContain("Protected staff content");
  });
  it("blocks member accounts", () =>
    expect(guarded(staff("member"))).not.toContain("Protected staff content"));
  it("blocks disabled and unverified staff", () => {
    expect(guarded({ ...staff("admin"), disabled: true }, true)).not.toContain(
      "Protected staff content",
    );
    expect(
      guarded({ ...staff("admin"), email_verified: false }, true),
    ).not.toContain("Protected staff content");
  });
  it("withholds staff content while restoring the session", () => {
    const html = guarded(staff("admin"), true, false);
    expect(html).toContain("Restoring your session");
    expect(html).not.toContain("Protected staff content");
  });
  it("withholds staff content from signed-out visitors", () =>
    expect(guarded(null)).not.toContain("Protected staff content"));
});
