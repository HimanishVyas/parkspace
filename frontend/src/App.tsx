import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import RenterShell from "./components/shells/RenterShell";
import ProviderShell from "./components/shells/ProviderShell";
import AdminShell from "./components/shells/AdminShell";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { homeFor, usePortal } from "./lib/portal";

import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Search from "./pages/Search";
import ListingDetail from "./pages/ListingDetail";
import BecomeProvider from "./pages/BecomeProvider";
import NotFound from "./pages/NotFound";
import Notifications from "./pages/Notifications";
import Profile from "./pages/renter/Profile";
import Vehicles from "./pages/renter/Vehicles";
import Bookings from "./pages/renter/Bookings";
import BookingDetail from "./pages/renter/BookingDetail";
import Checkout from "./pages/renter/Checkout";
import ReportIssue from "./pages/renter/ReportIssue";
import ProviderDashboard from "./pages/provider/Dashboard";
import ProviderListings from "./pages/provider/Listings";
import ListingForm from "./pages/provider/ListingForm";
import ListingAvailability from "./pages/provider/Availability";
import ProviderBookings from "./pages/provider/Bookings";
import ProviderEarnings from "./pages/provider/Earnings";
import SocietyProfile from "./pages/provider/SocietyProfile";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminUsers from "./pages/admin/Users";
import AdminProviders from "./pages/admin/Providers";
import AdminListings from "./pages/admin/Listings";
import AdminBookings from "./pages/admin/Bookings";
import AdminReports from "./pages/admin/Reports";
import AdminSettings from "./pages/admin/Settings";
import AdminPayouts from "./pages/admin/Payouts";

/**
 * "/" is the marketing page, which only means anything to a signed-out visitor.
 * A signed-in account is sent to its own portal instead of a page selling it
 * things it already has.
 */
function Home() {
  const { loading } = useAuth();
  const portal = usePortal();
  if (loading) return <Loading />;
  if (portal === "guest") return <Landing />;
  return <Navigate to={homeFor(portal)} replace />;
}

/**
 * Route guard, used as a layout route so a whole portal is protected once
 * rather than every route repeating the wrapper.
 */
function RequireAuth({ role }: { role?: "PROVIDER" | "ADMIN" }) {
  const { user, provider, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  if (role === "ADMIN" && user.role !== "ADMIN") return <Navigate to="/" replace />;
  if (role === "PROVIDER" && !provider) return <Navigate to="/list-your-space" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      {/* ---------- Renter portal: public pages and the renter's own area ---- */}
      <Route element={<RenterShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/search" element={<Search />} />
        <Route path="/parking/:spaceId" element={<ListingDetail />} />
        <Route path="/list-your-space" element={<BecomeProvider />} />

        <Route element={<RequireAuth />}>
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/vehicles" element={<Vehicles />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/bookings/:bookingId" element={<BookingDetail />} />
          <Route path="/bookings/:bookingId/pay" element={<Checkout />} />
          <Route path="/bookings/:bookingId/report" element={<ReportIssue />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Route>

      {/* ---------- Provider portal ------------------------------------------ */}
      <Route element={<RequireAuth role="PROVIDER" />}>
        <Route path="/provider" element={<ProviderShell />}>
          <Route index element={<ProviderDashboard />} />
          <Route path="listings" element={<ProviderListings />} />
          <Route path="listings/new" element={<ListingForm />} />
          <Route path="listings/:spaceId/edit" element={<ListingForm />} />
          <Route path="listings/:spaceId/availability" element={<ListingAvailability />} />
          <Route path="bookings" element={<ProviderBookings />} />
          <Route path="earnings" element={<ProviderEarnings />} />
          <Route path="society" element={<SocietyProfile />} />
        </Route>
      </Route>

      {/* ---------- Admin portal --------------------------------------------- */}
      <Route element={<RequireAuth role="ADMIN" />}>
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<AdminDashboard />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="providers" element={<AdminProviders />} />
          <Route path="listings" element={<AdminListings />} />
          <Route path="bookings" element={<AdminBookings />} />
          <Route path="reports" element={<AdminReports />} />
          <Route path="payouts" element={<AdminPayouts />} />
          <Route path="settings" element={<AdminSettings />} />
        </Route>
      </Route>
    </Routes>
  );
}
