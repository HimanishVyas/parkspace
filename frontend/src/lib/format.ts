/** Formatting helpers. The pilot is a single Indian city, so currency and
 *  dates are formatted for that locale throughout. */
import type { BookingStatus, ListingStatus, PricingUnit } from "./types";

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});
const CURRENCY_WHOLE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function money(value: string | number | null | undefined, whole = false): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return "—";
  const formatter = whole && Number.isInteger(amount) ? CURRENCY_WHOLE : CURRENCY;
  return formatter.format(amount);
}

export function dateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function dateOnly(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function timeOnly(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

/** "18 Sep, 10:00 am – 1:00 pm", collapsing the date when both ends share one. */
export function bookingWindow(start: string, end: string): string {
  const from = new Date(start);
  const to = new Date(end);
  if (from.toDateString() === to.toDateString()) {
    return `${dateOnly(from)}, ${timeOnly(from)} – ${timeOnly(to)}`;
  }
  return `${dateTime(from)} – ${dateTime(to)}`;
}

export function minutesToTime(minutes: number): string {
  const hours = Math.floor(minutes / 60) % 24;
  const mins = minutes % 60;
  const isMidnightEnd = minutes === 1440;
  const display = isMidnightEnd ? 24 : hours;
  const suffix = display >= 12 && display < 24 ? "pm" : "am";
  const hour12 = display % 12 === 0 ? 12 : display % 12;
  return `${hour12}:${String(mins).padStart(2, "0")} ${suffix}`;
}

export function relativeTime(value: string): string {
  const diff = new Date(value).getTime() - Date.now();
  const minutes = Math.round(diff / 60000);
  const absolute = Math.abs(minutes);
  if (absolute < 1) return "just now";
  if (absolute < 60) return minutes > 0 ? `in ${absolute} min` : `${absolute} min ago`;
  const hours = Math.round(absolute / 60);
  if (hours < 24) return minutes > 0 ? `in ${hours} h` : `${hours} h ago`;
  const days = Math.round(hours / 24);
  return minutes > 0 ? `in ${days} d` : `${days} d ago`;
}

export const UNIT_LABEL: Record<PricingUnit, string> = {
  HOURLY: "hour",
  DAILY: "day",
  MONTHLY: "month",
};

/** Adjective form for tabs and chips — "Daily", not "day" + "ly". */
export const UNIT_ADJECTIVE: Record<PricingUnit, string> = {
  HOURLY: "Hourly",
  DAILY: "Daily",
  MONTHLY: "Monthly",
};

export const UNIT_PLURAL: Record<PricingUnit, string> = {
  HOURLY: "hours",
  DAILY: "days",
  MONTHLY: "months",
};

export const PARKING_TYPE_LABEL: Record<string, string> = {
  OPEN: "Open",
  COVERED: "Covered",
  BASEMENT: "Basement",
  GARAGE: "Garage",
};

export const VEHICLE_LABEL: Record<string, string> = {
  BIKE: "Bike",
  CAR: "Car",
  SUV: "SUV",
};

export const ISSUE_LABEL: Record<string, string> = {
  SPACE_UNAVAILABLE: "Parking space unavailable",
  SPACE_OCCUPIED: "Another vehicle occupying the space",
  ACCESS_PROBLEM: "Access problem",
  PROPERTY_DAMAGE: "Property damage",
  PAYMENT_PROBLEM: "Payment problem",
  OTHER: "Other",
};

type BadgeTone = "" | "green" | "amber" | "red" | "blue" | "teal";

export function bookingBadge(status: BookingStatus): { label: string; tone: BadgeTone } {
  switch (status) {
    case "PENDING_PAYMENT":
      return { label: "Awaiting payment", tone: "amber" };
    case "PENDING_APPROVAL":
      return { label: "Awaiting approval", tone: "amber" };
    case "CONFIRMED":
      return { label: "Confirmed", tone: "green" };
    case "ACTIVE":
      return { label: "In progress", tone: "teal" };
    case "OVERSTAYING":
      return { label: "Running over", tone: "amber" };
    case "COMPLETED":
      return { label: "Completed", tone: "blue" };
    case "CANCELLED":
      return { label: "Cancelled", tone: "red" };
    case "REJECTED":
      return { label: "Declined", tone: "red" };
    case "EXPIRED":
      return { label: "Expired", tone: "" };
    case "DISPUTED":
      return { label: "Disputed", tone: "red" };
    default:
      return { label: status, tone: "" };
  }
}

export function listingBadge(status: ListingStatus): { label: string; tone: BadgeTone } {
  switch (status) {
    case "PUBLISHED":
      return { label: "Live", tone: "green" };
    case "DRAFT":
      return { label: "Draft", tone: "" };
    case "PENDING_APPROVAL":
      return { label: "Awaiting approval", tone: "amber" };
    case "PAUSED":
      return { label: "Paused", tone: "blue" };
    case "REJECTED":
      return { label: "Rejected", tone: "red" };
    case "SUSPENDED":
      return { label: "Suspended", tone: "red" };
    default:
      return { label: status, tone: "" };
  }
}

/** A datetime-local input value for a Date, in the browser's own timezone. */
export function toLocalInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function toDateInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}
