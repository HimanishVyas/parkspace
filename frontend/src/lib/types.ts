export type UserRole = "RENTER" | "PROVIDER" | "ADMIN";
export type UserStatus = "ACTIVE" | "SUSPENDED";
export type ParkingType = "OPEN" | "COVERED" | "BASEMENT" | "GARAGE";
export type VehicleType = "BIKE" | "CAR" | "SUV";
export type PricingUnit = "HOURLY" | "DAILY" | "MONTHLY";
export type ListingStatus =
  | "DRAFT"
  | "PENDING_APPROVAL"
  | "PUBLISHED"
  | "PAUSED"
  | "REJECTED"
  | "SUSPENDED";
export type BookingStatus =
  | "PENDING_PAYMENT"
  | "PENDING_APPROVAL"
  | "CONFIRMED"
  | "ACTIVE"
  | "COMPLETED"
  | "CANCELLED"
  | "EXPIRED"
  | "DISPUTED"
  | "REJECTED";
export type VerificationStatus =
  | "UNVERIFIED"
  | "PENDING_VERIFICATION"
  | "VERIFIED"
  | "REJECTED";
export type ReportStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED" | "DISMISSED";
export type IssueType =
  | "SPACE_UNAVAILABLE"
  | "SPACE_OCCUPIED"
  | "ACCESS_PROBLEM"
  | "PROPERTY_DAMAGE"
  | "PAYMENT_PROBLEM"
  | "OTHER";

export interface User {
  id: string;
  email: string;
  phone: string | null;
  full_name: string;
  profile_photo_url: string | null;
  role: UserRole;
  status: UserStatus;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface Vehicle {
  id: string;
  vehicle_type: VehicleType;
  registration_number: string;
  make_model: string | null;
  color: string | null;
  is_default: boolean;
  created_at: string;
}

export interface Price {
  unit: PricingUnit;
  amount: string;
}

export interface Photo {
  id: string;
  url: string;
  caption: string | null;
  sort_order: number;
}

export interface Society {
  id: string;
  name: string;
  registration_number: string | null;
  address: string | null;
  city: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  description: string | null;
}

export interface Provider {
  id: string;
  provider_type: "INDIVIDUAL" | "SOCIETY";
  display_name: string;
  contact_phone: string | null;
  address: string | null;
  verification_status: VerificationStatus;
  status: "ACTIVE" | "SUSPENDED";
  authority_declared_at: string | null;
  society: Society | null;
  created_at: string;
}

export interface ProviderPublic {
  id: string;
  display_name: string;
  provider_type: "INDIVIDUAL" | "SOCIETY";
  verification_status: VerificationStatus;
  member_since: string;
}

export interface ParkingSpace {
  id: string;
  provider_id: string;
  title: string;
  description: string | null;
  parking_type: ParkingType;
  vehicle_types: VehicleType[];
  address_line: string;
  landmark: string | null;
  city: string;
  state: string | null;
  pincode: string | null;
  latitude: number;
  longitude: number;
  access_instructions: string | null;
  total_slots: number;
  requires_approval: boolean;
  status: ListingStatus;
  rejection_reason: string | null;
  authority_confirmed: boolean;
  rating_average: string | null;
  rating_count: number;
  prices: Price[];
  photos: Photo[];
  created_at: string;
  updated_at: string;
}

export interface ParkingSpacePublic {
  id: string;
  title: string;
  description: string | null;
  parking_type: ParkingType;
  vehicle_types: VehicleType[];
  address_line: string;
  landmark: string | null;
  city: string;
  state: string | null;
  pincode: string | null;
  latitude: number;
  longitude: number;
  total_slots: number;
  requires_approval: boolean;
  rating_average: string | null;
  rating_count: number;
  prices: Price[];
  photos: Photo[];
  provider: ProviderPublic;
  created_at: string;
  distance_km: number | null;
}

export interface SearchResult {
  id: string;
  title: string;
  parking_type: ParkingType;
  vehicle_types: VehicleType[];
  city: string;
  latitude: number;
  longitude: number;
  rating_average: string | null;
  rating_count: number;
  prices: Price[];
  photo_url: string | null;
  distance_km: number | null;
  available: boolean;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AvailabilityRule {
  id: string;
  day_of_week: number;
  start_minute: number;
  end_minute: number;
  is_active: boolean;
}

export interface AvailabilityBlock {
  id: string;
  start_at: string;
  end_at: string;
  reason: string | null;
}

export interface CalendarDay {
  day: string;
  windows: [number, number][];
  blocked: boolean;
  booked_slots: number;
  total_slots: number;
  is_open: boolean;
}

export interface Quote {
  parking_space_id: string;
  unit: PricingUnit;
  start_at: string;
  end_at: string;
  quantity: string;
  unit_price: string;
  base_amount: string;
  platform_fee: string;
  tax_amount: string;
  total_amount: string;
  currency: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface BookingSpaceSummary {
  id: string;
  title: string;
  parking_type: ParkingType;
  address_line: string;
  landmark: string | null;
  city: string;
  latitude: number;
  longitude: number;
  photo_url: string | null;
}

export interface Booking {
  id: string;
  reference: string;
  status: BookingStatus;
  parking_space: BookingSpaceSummary;
  provider_name: string;
  unit: PricingUnit;
  start_at: string;
  end_at: string;
  quantity: string;
  unit_price: string;
  base_amount: string;
  platform_fee: string;
  tax_amount: string;
  total_amount: string;
  refund_amount: string;
  currency: string;
  vehicle_number: string;
  vehicle_type: VehicleType;
  renter_notes: string | null;
  hold_expires_at: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  access_instructions: string | null;
  renter: { full_name: string; phone: string | null } | null;
  provider_earning: string | null;
  can_cancel: boolean;
  refund_if_cancelled_now: string | null;
}

export interface BookingConfirmation {
  booking_id: string;
  reference: string;
  status: BookingStatus;
  parking_location: string;
  latitude: number;
  longitude: number;
  provider_name: string;
  renter_name: string;
  vehicle_number: string;
  start_at: string;
  end_at: string;
  total_amount: string;
  currency: string;
  parking_instructions: string | null;
  qr_payload: string;
}

export interface PaymentSession {
  payment_id: string;
  booking_id: string;
  gateway: string;
  order_id: string;
  amount: string;
  currency: string;
  client_payload: Record<string, unknown> & { mock_payment_id?: string };
}

export interface Notification {
  id: string;
  event: string;
  title: string;
  body: string;
  data: Record<string, string> | null;
  read_at: string | null;
  created_at: string;
}

export interface EarningsMonth {
  month: string;
  gross_booking_value: string;
  platform_fee: string;
  provider_earnings: string;
  booking_count: number;
}

export interface Earnings {
  total_earnings: string;
  pending_payout: string;
  completed_payout: string;
  upcoming_earnings: string;
  currency: string;
  months: EarningsMonth[];
}

export interface ProviderDashboard {
  total_earnings: string;
  pending_payout: string;
  completed_payout: string;
  upcoming_earnings: string;
  current_month: {
    gross_booking_value: string;
    platform_fee: string;
    provider_earnings: string;
    booking_count: number;
  };
  total_listings: number;
  active_listings: number;
  upcoming_bookings: number;
  todays_bookings: number;
  total_bookings: number;
}

export interface AdminDashboard {
  total_users: number;
  total_renters: number;
  total_providers: number;
  verified_providers: number;
  total_listings: number;
  active_listings: number;
  pending_listings: number;
  total_bookings: number;
  todays_bookings: number;
  active_bookings: number;
  monthly_booking_value: string;
  monthly_platform_revenue: string;
  lifetime_booking_value: string;
  lifetime_platform_revenue: string;
  open_reports: number;
  currency: string;
}

export interface AdminUser extends User {
  email_verified: boolean;
}

export interface AdminProvider extends Provider {
  user_id: string;
  verification_notes: string | null;
  listing_count: number;
  total_earnings: string;
}

export interface AdminListing {
  id: string;
  provider_id: string;
  provider_name: string | null;
  title: string;
  city: string;
  status: ListingStatus;
  rejection_reason: string | null;
  authority_confirmed: boolean;
  total_slots: number;
  rating_average: string | null;
  rating_count: number;
  created_at: string;
}

export interface AdminBooking {
  id: string;
  reference: string;
  status: BookingStatus;
  renter_name: string | null;
  provider_name: string | null;
  parking_title: string | null;
  vehicle_number: string;
  start_at: string;
  end_at: string;
  total_amount: string;
  commission_amount: string;
  provider_earning: string;
  refund_amount: string;
  currency: string;
  created_at: string;
}

export interface Report {
  id: string;
  booking_id: string;
  booking_reference: string | null;
  reporter_id: string;
  issue_type: IssueType;
  description: string;
  status: ReportStatus;
  admin_notes: string | null;
  resolved_at: string | null;
  photos: { id: string; url: string }[];
  created_at: string;
}

export interface Review {
  id: string;
  booking_id: string;
  subject: "SPACE" | "RENTER";
  rating: number;
  comment: string | null;
  created_at: string;
  author_name: string | null;
}

export interface ReviewSummary {
  average: string | null;
  count: number;
  items: Review[];
}

export interface PlatformConfig {
  renter_fee_percent: number;
  tax_percent: number;
  commission_percent: number;
  cancellation_policy: {
    tiers: { min_hours_before: number; refund_percent: number }[];
    default_refund_percent: number;
    allow_after_start: boolean;
  };
  payment_hold_minutes: number;
  approval_window_hours: number;
  listing_requires_approval: boolean;
  booking_max_advance_days: number;
  booking_min_lead_minutes: number;
  booking_slot_minutes: number;
  reminder_hours_before: number;
}

export interface Payout {
  id: string;
  provider_id: string;
  amount: string;
  currency: string;
  status: "PENDING" | "PROCESSING" | "PAID" | "FAILED";
  period_start: string | null;
  period_end: string | null;
  reference: string | null;
  notes: string | null;
  paid_at: string | null;
  created_at: string;
  booking_count: number;
}
