/**
 * Which portal an account belongs to, and where it lands.
 *
 * One account can hold more than one capability — the API lets a renter upgrade
 * to a provider without making a second login — so "role" alone is not enough to
 * decide what to show. This resolves the account to exactly one portal, and
 * every navigation decision in the app reads from here rather than
 * re-implementing the precedence.
 */
import { useAuth } from "./auth";
import type { Provider, User } from "./types";

export type Portal = "guest" | "renter" | "provider" | "admin";

/** Precedence: admin beats provider, provider beats renter. */
export function portalFor(user: User | null, provider: Provider | null): Portal {
  if (!user) return "guest";
  if (user.role === "ADMIN") return "admin";
  if (provider || user.role === "PROVIDER") return "provider";
  return "renter";
}

/** Where this portal's signed-in user belongs after login, or on "/". */
export function homeFor(portal: Portal): string {
  switch (portal) {
    case "admin":
      return "/admin";
    case "provider":
      return "/provider";
    case "renter":
      return "/search";
    default:
      return "/";
  }
}

export function usePortal(): Portal {
  const { user, provider } = useAuth();
  return portalFor(user, provider);
}
