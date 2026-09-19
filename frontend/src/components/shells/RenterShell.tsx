/**
 * The consumer portal.
 *
 * Unlike the two operator portals this keeps a top bar and a marketing footer:
 * a renter arrives from a search or a link, does one thing, and leaves.
 *
 * The nav is built per portal rather than by stacking conditionals, so each
 * account type sees only what belongs to it — a renter is never offered
 * provider tools, and a provider passing through is never offered renter ones.
 */
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { usePortal } from "../../lib/portal";
import ThemeToggle from "../ThemeToggle";
import { initials, useUnread } from "./useUnread";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "active" : "";
}

export default function RenterShell() {
  const { user, logout } = useAuth();
  const portal = usePortal();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const unread = useUnread();

  // Close the mobile menu whenever the route changes.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const signOut = (
    <button
      type="button"
      className="linklike"
      onClick={() => {
        logout();
        navigate("/");
      }}
    >
      Sign out
    </button>
  );

  const alerts = (
    <NavLink to="/notifications" className={navClass}>
      Alerts {unread > 0 ? <span className="dot">{unread}</span> : null}
    </NavLink>
  );

  const account = user ? (
    <NavLink to="/profile" className={navClass} aria-label="Profile">
      <span className="rail__avatar" aria-hidden="true">
        {initials(user.full_name)}
      </span>
    </NavLink>
  ) : null;

  let links;
  if (portal === "guest") {
    links = (
      <>
        <NavLink to="/search" className={navClass}>
          Find parking
        </NavLink>
        <NavLink to="/list-your-space" className={navClass}>
          List your space
        </NavLink>
        <NavLink to="/login" className={navClass}>
          Sign in
        </NavLink>
        <Link to="/register" className="btn btn--sm" style={{ marginLeft: "0.35rem" }}>
          Get started
        </Link>
      </>
    );
  } else if (portal === "renter") {
    // Renters get renter tools only — no provider entry points.
    links = (
      <>
        <NavLink to="/search" className={navClass}>
          Find parking
        </NavLink>
        <NavLink to="/bookings" className={navClass}>
          My bookings
        </NavLink>
        <NavLink to="/vehicles" className={navClass}>
          Vehicles
        </NavLink>
        {alerts}
        {account}
        {signOut}
      </>
    );
  } else if (portal === "provider") {
    // A provider is only ever passing through the consumer shell; point them home.
    links = (
      <>
        <NavLink to="/provider" className={navClass}>
          Provider dashboard
        </NavLink>
        {alerts}
        {account}
        {signOut}
      </>
    );
  } else {
    links = (
      <>
        <NavLink to="/admin" className={navClass}>
          Admin console
        </NavLink>
        {alerts}
        {account}
        {signOut}
      </>
    );
  }

  return (
    <div className="app" data-portal="renter">
      <header className="header">
        <div className="header__inner">
          <Link to="/" className="logo">
            <span className="logo__mark" aria-hidden="true">
              P
            </span>
            ParkSpace
          </Link>
          <nav className="nav" aria-label="Main">
            <div className="spacer" />
            {links}
          </nav>
          <ThemeToggle className="theme-toggle--header" />
          <button
            type="button"
            className="menu-toggle"
            aria-expanded={menuOpen}
            aria-label="Toggle menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
        {menuOpen ? (
          <nav className="mobile-nav" aria-label="Mobile">
            {links}
          </nav>
        ) : null}
      </header>

      <Outlet />

      <footer className="footer">
        <div className="footer__inner">
          <span>© {new Date().getFullYear()} ParkSpace</span>
          <span className="spacer" />
          {portal === "guest" || portal === "renter" ? <Link to="/search">Find parking</Link> : null}
          {/* Only offered where it is actually an option for that account. */}
          {portal === "guest" ? <Link to="/list-your-space">List your space</Link> : null}
          <span className="tiny">
            Liability for damage is governed by our terms and the agreement between the parties.
          </span>
        </div>
      </footer>
    </div>
  );
}
