import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/providers", label: "Providers" },
  { to: "/admin/listings", label: "Listings" },
  { to: "/admin/bookings", label: "Bookings" },
  { to: "/admin/payouts", label: "Payouts" },
  { to: "/admin/reports", label: "Reports" },
  { to: "/admin/settings", label: "Settings" },
];

export default function AdminNav() {
  return (
    <div className="tabs" style={{ marginBottom: "1rem" }}>
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          className={({ isActive }) => `tab${isActive ? " tab--on" : ""}`}
          style={{ textDecoration: "none" }}
        >
          {link.label}
        </NavLink>
      ))}
    </div>
  );
}
