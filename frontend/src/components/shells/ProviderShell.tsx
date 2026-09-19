import { useAuth } from "../../lib/auth";
import OperatorShell, { type RailLink } from "./OperatorShell";

const LINKS: RailLink[] = [
  { to: "/provider", label: "Overview", end: true },
  { to: "/provider/listings", label: "My spaces" },
  { to: "/provider/bookings", label: "Bookings" },
  { to: "/provider/earnings", label: "Earnings" },
];

const SOCIETY_LINK: RailLink = { to: "/provider/society", label: "Society" };

export default function ProviderShell() {
  const { provider } = useAuth();
  const isSociety = provider?.provider_type === "SOCIETY";
  // A society manages an organisation profile and its agreement; an individual
  // provider has neither, so the link only appears where it leads somewhere.
  const links = isSociety ? [...LINKS, SOCIETY_LINK] : LINKS;

  return (
    <OperatorShell portal="provider" role={isSociety ? "Society" : "Provider"} home="/provider" links={links} />
  );
}
