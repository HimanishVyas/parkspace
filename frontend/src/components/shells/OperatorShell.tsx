/**
 * The shared chassis behind the provider and admin portals.
 *
 * Both are operator surfaces: a known, small set of destinations that someone
 * moves between all day. A persistent left rail keeps every section one click
 * away; below 1024px the same links become a horizontally scrollable pill bar,
 * which beats a hamburger when there are only six to eight of them.
 *
 * The renter portal deliberately does NOT use this — see RenterShell.
 */
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import ThemeToggle from "../ThemeToggle";
import { initials, useUnread } from "./useUnread";

export interface RailLink {
  to: string;
  label: string;
  end?: boolean;
}

interface OperatorShellProps {
  /** Drives the accent group in CSS; see [data-portal] in styles.css. */
  portal: "provider" | "admin";
  /** Short badge beside the wordmark, e.g. "Provider" or "Admin". */
  role: string;
  /** Where the wordmark links to. */
  home: string;
  links: RailLink[];
}

export default function OperatorShell({ portal, role, home, links }: OperatorShellProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const unread = useUnread();

  return (
    <div className="shell" data-portal={portal}>
      <aside className="rail" aria-label={`${role} navigation`}>
        <div className="rail__top">
          <Link to={home} className="rail__brand">
            <span className="rail__mark" aria-hidden="true">
              P
            </span>
            ParkSpace
            <span className="rail__role">{role}</span>
          </Link>
          <span className="rail__spacer" />
          <ThemeToggle />
          <Link to="/notifications" className="btn btn--ghost btn--sm rail__top-alerts" aria-label="Alerts">
            Alerts {unread > 0 ? <span className="dot">{unread}</span> : null}
          </Link>
        </div>

        <p className="rail__label">Sections</p>
        <nav className="rail__nav">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => `rail__link${isActive ? " active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="rail__foot">
          <NavLink to="/notifications" className={({ isActive }) => `rail__link${isActive ? " active" : ""}`}>
            Alerts
            {unread > 0 ? <span className="dot">{unread}</span> : null}
          </NavLink>
          <NavLink to="/profile" className={({ isActive }) => `rail__link${isActive ? " active" : ""}`}>
            Profile
          </NavLink>
          <div className="rail__user">
            <span className="rail__avatar" aria-hidden="true">
              {user ? initials(user.full_name) : "?"}
            </span>
            <span className="truncate small">
              <span className="bold truncate" style={{ display: "block" }}>
                {user?.full_name}
              </span>
              <button
                type="button"
                className="linklike small muted"
                style={{ background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit" }}
                onClick={() => {
                  logout();
                  navigate("/");
                }}
              >
                Sign out
              </button>
            </span>
          </div>
        </div>
      </aside>

      <div className="shell__main">
        <Outlet />
      </div>
    </div>
  );
}
