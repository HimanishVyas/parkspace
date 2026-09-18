import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Paginated, Notification } from "../lib/types";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "active" : "";
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, provider, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  // Close the mobile menu whenever the route changes.
  useEffect(() => setMenuOpen(false), [location.pathname]);

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

  const isProvider = Boolean(provider);
  const isSociety = provider?.provider_type === "SOCIETY";
  const isAdmin = user?.role === "ADMIN";

  const links = (
    <>
      <NavLink to="/search" className={navClass}>
        Find parking
      </NavLink>
      {user ? (
        <>
          <NavLink to="/bookings" className={navClass}>
            My bookings
          </NavLink>
          {isProvider ? (
            <NavLink to="/provider" className={navClass}>
              {isSociety ? "Society" : "Provider"}
            </NavLink>
          ) : (
            <NavLink to="/list-your-space" className={navClass}>
              List your space
            </NavLink>
          )}
          {isAdmin ? (
            <NavLink to="/admin" className={navClass}>
              Admin
            </NavLink>
          ) : null}
          <NavLink to="/notifications" className={navClass}>
            Alerts{unread > 0 ? ` (${unread})` : ""}
          </NavLink>
          <NavLink to="/profile" className={navClass}>
            Profile
          </NavLink>
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
        </>
      ) : (
        <>
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
      )}
    </>
  );

  return (
    <div className="app">
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

      {children}

      <footer className="footer">
        <div className="footer__inner">
          <span>© {new Date().getFullYear()} ParkSpace</span>
          <span className="spacer" />
          <Link to="/search">Find parking</Link>
          <Link to="/list-your-space">List your space</Link>
          <span className="tiny">
            Liability for damage is governed by our terms and the agreement between the parties.
          </span>
        </div>
      </footer>
    </div>
  );
}
