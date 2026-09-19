import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Notification, Paginated } from "../../lib/types";

/**
 * Unread notification count, refreshed on navigation and once a minute.
 *
 * All three shells show the same badge, so the polling lives here rather than
 * being duplicated — and a signed-out viewer never polls at all.
 */
export function useUnread(): number {
  const { user } = useAuth();
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) {
      setUnread(0);
      return;
    }
    let active = true;
    const poll = async () => {
      try {
        const result = await api.get<Paginated<Notification> & { unread: number }>("/notifications", {
          limit: 1,
        });
        if (active) setUnread(result.unread);
      } catch {
        /* a failed poll is not worth surfacing */
      }
    };
    void poll();
    const timer = setInterval(poll, 60000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [user, location.pathname]);

  return unread;
}

/** Initials for the rail avatar. "Riya Mehta" -> "RM". */
export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
