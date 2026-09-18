import type { ReactNode } from "react";
import { ApiError } from "../lib/api";

export function Badge({ tone = "", children }: { tone?: string; children: ReactNode }) {
  return <span className={`badge${tone ? ` badge--${tone}` : ""}`}>{children}</span>;
}

export function Alert({
  kind = "error",
  children,
}: {
  kind?: "error" | "success" | "info" | "warn";
  children: ReactNode;
}) {
  return (
    <div className={`alert alert--${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function ErrorMessage({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <Alert kind="error">{error.message}</Alert>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading">
      <div className="stack stack--sm" style={{ alignItems: "center" }}>
        <div className="spinner" />
        <span className="small muted">{label}</span>
      </div>
    </div>
  );
}

export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      {children ? <div className="small">{children}</div> : null}
      {action ? <div style={{ marginTop: "1rem" }}>{action}</div> : null}
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span className="field__label">
        {label}
        {required ? <span aria-hidden="true" style={{ color: "var(--red-600)" }}> *</span> : null}
      </span>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
      {error ? <span className="field__error">{error}</span> : null}
    </label>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className="stat__value numeric">{value}</div>
      {hint ? <div className="stat__hint">{hint}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  actions,
  children,
  flush,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className="panel">
      {title || actions ? (
        <header className="panel__header">
          {typeof title === "string" ? <h2 style={{ fontSize: "1.05rem", margin: 0 }}>{title}</h2> : title}
          <div className="spacer" />
          {actions}
        </header>
      ) : null}
      <div className={flush ? "" : "panel__body"}>{children}</div>
    </section>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          className={`tab${value === option.value ? " tab--on" : ""}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined ? ` (${option.count})` : ""}
        </button>
      ))}
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <div className="row row--between" style={{ marginTop: "1rem" }}>
      <span className="small muted">
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="row">
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <span className="small muted numeric">
          {page} / {pages}
        </span>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Stars({ rating, count }: { rating: string | number | null; count?: number }) {
  if (rating === null || rating === undefined) {
    return <span className="small muted">No ratings yet</span>;
  }
  const value = typeof rating === "string" ? Number.parseFloat(rating) : rating;
  return (
    <span className="small" title={`${value.toFixed(1)} out of 5`}>
      <span aria-hidden="true" style={{ color: "var(--star)" }}>
        {"★".repeat(Math.round(value))}
        {"☆".repeat(Math.max(0, 5 - Math.round(value)))}
      </span>{" "}
      <span className="numeric">{value.toFixed(1)}</span>
      {count !== undefined ? <span className="muted"> ({count})</span> : null}
    </span>
  );
}

export function ConfirmButton({
  onConfirm,
  label,
  confirmLabel = "Are you sure?",
  className = "btn btn--danger btn--sm",
  disabled,
  pending,
}: {
  onConfirm: () => void;
  label: string;
  confirmLabel?: string;
  className?: string;
  disabled?: boolean;
  pending?: boolean;
}) {
  return (
    <button
      type="button"
      className={className}
      disabled={disabled || pending}
      onClick={() => {
        if (window.confirm(confirmLabel)) onConfirm();
      }}
    >
      {pending ? "Working…" : label}
    </button>
  );
}
