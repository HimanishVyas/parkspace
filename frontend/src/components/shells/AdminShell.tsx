import OperatorShell, { type RailLink } from "./OperatorShell";

const LINKS: RailLink[] = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/providers", label: "Providers" },
  { to: "/admin/listings", label: "Listings" },
  { to: "/admin/bookings", label: "Bookings" },
  { to: "/admin/payouts", label: "Payouts" },
  { to: "/admin/reports", label: "Reports" },
  { to: "/admin/settings", label: "Settings" },
];

export default function AdminShell() {
  return <OperatorShell portal="admin" role="Admin" home="/admin" links={LINKS} />;
}
