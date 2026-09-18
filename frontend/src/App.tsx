import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";

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

/** Sends signed-out visitors to login, remembering where they were headed. */
function RequireAuth({ children, role }: { children: JSX.Element; role?: "PROVIDER" | "ADMIN" }) {
  const { user, provider, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  if (role === "ADMIN" && user.role !== "ADMIN") return <Navigate to="/" replace />;
  if (role === "PROVIDER" && !provider) return <Navigate to="/list-your-space" replace />;
  return children;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/search" element={<Search />} />
        <Route path="/parking/:spaceId" element={<ListingDetail />} />
        <Route path="/list-your-space" element={<BecomeProvider />} />

        <Route
          path="/notifications"
          element={
            <RequireAuth>
              <Notifications />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <Profile />
            </RequireAuth>
          }
        />
        <Route
          path="/vehicles"
          element={
            <RequireAuth>
              <Vehicles />
            </RequireAuth>
          }
        />
        <Route
          path="/bookings"
          element={
            <RequireAuth>
              <Bookings />
            </RequireAuth>
          }
        />
        <Route
          path="/bookings/:bookingId"
          element={
            <RequireAuth>
              <BookingDetail />
            </RequireAuth>
          }
        />
        <Route
          path="/bookings/:bookingId/pay"
          element={
            <RequireAuth>
              <Checkout />
            </RequireAuth>
          }
        />
        <Route
          path="/bookings/:bookingId/report"
          element={
            <RequireAuth>
              <ReportIssue />
            </RequireAuth>
          }
        />

        <Route
          path="/provider"
          element={
            <RequireAuth role="PROVIDER">
              <ProviderDashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/listings"
          element={
            <RequireAuth role="PROVIDER">
              <ProviderListings />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/listings/new"
          element={
            <RequireAuth role="PROVIDER">
              <ListingForm />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/listings/:spaceId/edit"
          element={
            <RequireAuth role="PROVIDER">
              <ListingForm />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/listings/:spaceId/availability"
          element={
            <RequireAuth role="PROVIDER">
              <ListingAvailability />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/bookings"
          element={
            <RequireAuth role="PROVIDER">
              <ProviderBookings />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/earnings"
          element={
            <RequireAuth role="PROVIDER">
              <ProviderEarnings />
            </RequireAuth>
          }
        />
        <Route
          path="/provider/society"
          element={
            <RequireAuth role="PROVIDER">
              <SocietyProfile />
            </RequireAuth>
          }
        />

        <Route
          path="/admin"
          element={
            <RequireAuth role="ADMIN">
              <AdminDashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/users"
          element={
            <RequireAuth role="ADMIN">
              <AdminUsers />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/providers"
          element={
            <RequireAuth role="ADMIN">
              <AdminProviders />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/listings"
          element={
            <RequireAuth role="ADMIN">
              <AdminListings />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/bookings"
          element={
            <RequireAuth role="ADMIN">
              <AdminBookings />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/reports"
          element={
            <RequireAuth role="ADMIN">
              <AdminReports />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/payouts"
          element={
            <RequireAuth role="ADMIN">
              <AdminPayouts />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/settings"
          element={
            <RequireAuth role="ADMIN">
              <AdminSettings />
            </RequireAuth>
          }
        />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
