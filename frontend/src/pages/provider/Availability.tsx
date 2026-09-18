/**
 * Provider availability management (PRD §9).
 *
 * Two controls, deliberately separate:
 *   - the weekly schedule, which says when the space is normally open;
 *   - blocks, which take specific dates out regardless of the schedule.
 * The calendar below shows the result of both, plus bookings that already
 * occupy the space — the provider sees exactly what a renter would.
 */
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, ConfirmButton, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { dateOnly, minutesToTime, toDateInput } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { AvailabilityBlock, AvailabilityRule, CalendarDay, ParkingSpace } from "../../lib/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface DayForm {
  open: boolean;
  from: string;
  to: string;
}

function minutesFromTime(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function timeFromMinutes(value: number): string {
  if (value >= 1440) return "23:59";
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

export default function Availability() {
  const { spaceId = "" } = useParams();
  const [monthOffset, setMonthOffset] = useState(0);

  const space = useAsync(
    (signal) => api.get<ParkingSpace>(`/parking/mine/${spaceId}`, undefined, signal),
    [spaceId],
  );
  const availability = useAsync(
    (signal) =>
      api.get<{ rules: AvailabilityRule[]; blocks: AvailabilityBlock[] }>(
        `/parking/${spaceId}/availability`,
        undefined,
        signal,
      ),
    [spaceId],
  );

  const { from, to } = useMemo(() => {
    const base = new Date();
    base.setDate(1);
    base.setMonth(base.getMonth() + monthOffset);
    const start = new Date(base.getFullYear(), base.getMonth(), 1);
    const end = new Date(base.getFullYear(), base.getMonth() + 1, 0);
    return { from: start, to: end };
  }, [monthOffset]);

  const calendar = useAsync(
    (signal) =>
      api.get<{ days: CalendarDay[] }>(
        `/parking/${spaceId}/calendar`,
        { from_date: toDateInput(from), to_date: toDateInput(to) },
        signal,
      ),
    [spaceId, from.toISOString()],
  );
  const blocks = useAsync(
    (signal) => api.get<AvailabilityBlock[]>(`/parking/${spaceId}/blocks`, undefined, signal),
    [spaceId],
  );

  // Weekly schedule form, seeded from the saved rules.
  const [schedule, setSchedule] = useState<DayForm[] | null>(null);
  const effectiveSchedule: DayForm[] =
    schedule ??
    DAYS.map((_, day) => {
      const rule = availability.data?.rules.find((item) => item.day_of_week === day && item.is_active);
      return rule
        ? { open: true, from: timeFromMinutes(rule.start_minute), to: timeFromMinutes(rule.end_minute) }
        : { open: false, from: "08:00", to: "20:00" };
    });

  const updateDay = (index: number, patch: Partial<DayForm>) => {
    const next = effectiveSchedule.map((day, i) => (i === index ? { ...day, ...patch } : day));
    setSchedule(next);
  };

  const saveSchedule = useSubmit(async () => {
    const rules = effectiveSchedule
      .map((day, index) =>
        day.open
          ? {
              day_of_week: index,
              start_minute: minutesFromTime(day.from),
              // 23:59 in the picker means "until midnight".
              end_minute: day.to === "23:59" ? 1440 : minutesFromTime(day.to),
              is_active: true,
            }
          : null,
      )
      .filter((rule): rule is NonNullable<typeof rule> => rule !== null);
    await api.put(`/parking/${spaceId}/availability`, { rules });
    availability.reload();
    calendar.reload();
    setSchedule(null);
  });

  const [blockForm, setBlockForm] = useState({ start: "", end: "", reason: "" });
  const addBlock = useSubmit(async () => {
    await api.post(`/parking/${spaceId}/blocks`, {
      // A block covers whole days: from midnight on the first to midnight after the last.
      start_at: new Date(`${blockForm.start}T00:00`).toISOString(),
      end_at: new Date(`${blockForm.end}T00:00`).toISOString(),
      reason: blockForm.reason.trim() || undefined,
    });
    setBlockForm({ start: "", end: "", reason: "" });
    blocks.reload();
    calendar.reload();
  });

  const removeBlock = useSubmit(async (id: string) => {
    await api.del(`/parking/${spaceId}/blocks/${id}`);
    blocks.reload();
    calendar.reload();
  });

  const publish = useSubmit(async () => {
    await api.post(`/parking/${spaceId}/publish`);
    space.reload();
  });

  if (space.loading) return <Loading />;

  const days = calendar.data?.days ?? [];
  // Pad the grid so the 1st lands under the right weekday (Monday-first).
  const leadingBlanks = days.length ? (new Date(days[0].day).getDay() + 6) % 7 : 0;

  return (
    <main className="page">
      <div className="stack">
        <Link to="/provider/listings" className="small">
          ← My parking spaces
        </Link>
        <div className="row row--between">
          <div>
            <h1>Availability</h1>
            <p className="muted small" style={{ margin: 0 }}>
              {space.data?.title}
            </p>
          </div>
          {space.data && ["DRAFT", "PAUSED"].includes(space.data.status) ? (
            <button type="button" className="btn" onClick={() => void publish.run()} disabled={publish.pending}>
              {publish.pending ? "Publishing…" : "Publish listing"}
            </button>
          ) : null}
        </div>

        <ErrorMessage error={publish.error} />

        <div className="search-layout">
          <div className="stack">
            <Panel title="Weekly schedule">
              <div className="stack">
                <p className="small muted" style={{ margin: 0 }}>
                  Set the hours your space is normally free. Renters can only book inside these
                  windows.
                </p>
                <ErrorMessage error={saveSchedule.error} />

                {effectiveSchedule.map((day, index) => (
                  <div className="row" key={DAYS[index]} style={{ gap: "0.6rem" }}>
                    <label className="checkbox" style={{ minWidth: 88 }}>
                      <input
                        type="checkbox"
                        checked={day.open}
                        onChange={(event) => updateDay(index, { open: event.target.checked })}
                      />
                      <span className="bold small">{DAYS[index]}</span>
                    </label>
                    <input
                      type="time"
                      value={day.from}
                      disabled={!day.open}
                      style={{ flex: "0 1 130px" }}
                      onChange={(event) => updateDay(index, { from: event.target.value })}
                    />
                    <span className="muted small">to</span>
                    <input
                      type="time"
                      value={day.to}
                      disabled={!day.open}
                      style={{ flex: "0 1 130px" }}
                      onChange={(event) => updateDay(index, { to: event.target.value })}
                    />
                  </div>
                ))}

                <div className="row">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void saveSchedule.run()}
                    disabled={saveSchedule.pending}
                  >
                    {saveSchedule.pending ? "Saving…" : "Save schedule"}
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() =>
                      setSchedule(DAYS.map(() => ({ open: true, from: "00:00", to: "23:59" })))
                    }
                  >
                    Open 24/7
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() =>
                      setSchedule(
                        DAYS.map((_, index) => ({
                          open: index < 5,
                          from: "08:00",
                          to: "20:00",
                        })),
                      )
                    }
                  >
                    Weekdays 8–8
                  </button>
                </div>
              </div>
            </Panel>

            <Panel title="Block dates">
              <div className="stack">
                <p className="small muted" style={{ margin: 0 }}>
                  Need the space yourself? Block those dates and nobody can book them.
                </p>
                <ErrorMessage error={addBlock.error} />
                <ErrorMessage error={removeBlock.error} />
                <form
                  className="row"
                  style={{ gap: "0.6rem", alignItems: "flex-end" }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    void addBlock.run();
                  }}
                >
                  <div style={{ flex: "1 1 150px" }}>
                    <Field label="From">
                      <input
                        type="date"
                        required
                        value={blockForm.start}
                        min={toDateInput(new Date())}
                        onChange={(event) => setBlockForm({ ...blockForm, start: event.target.value })}
                      />
                    </Field>
                  </div>
                  <div style={{ flex: "1 1 150px" }}>
                    <Field label="Until (exclusive)">
                      <input
                        type="date"
                        required
                        value={blockForm.end}
                        min={blockForm.start || toDateInput(new Date())}
                        onChange={(event) => setBlockForm({ ...blockForm, end: event.target.value })}
                      />
                    </Field>
                  </div>
                  <div style={{ flex: "1 1 160px" }}>
                    <Field label="Reason">
                      <input
                        type="text"
                        value={blockForm.reason}
                        placeholder="Optional"
                        onChange={(event) => setBlockForm({ ...blockForm, reason: event.target.value })}
                      />
                    </Field>
                  </div>
                  <button type="submit" className="btn btn--secondary" disabled={addBlock.pending}>
                    Block
                  </button>
                </form>

                {blocks.data?.length ? (
                  <div className="stack stack--sm">
                    {blocks.data.map((block) => (
                      <div className="row row--between" key={block.id}>
                        <div>
                          <div className="small bold">
                            {dateOnly(block.start_at)} → {dateOnly(block.end_at)}
                          </div>
                          {block.reason ? <div className="tiny muted">{block.reason}</div> : null}
                        </div>
                        <ConfirmButton
                          label="Remove"
                          confirmLabel="Remove this block?"
                          className="btn btn--ghost btn--sm"
                          onConfirm={() => void removeBlock.run(block.id)}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="small muted" style={{ margin: 0 }}>
                    No blocked dates.
                  </p>
                )}
              </div>
            </Panel>
          </div>

          <div className="search-layout__map">
            <Panel
              title={from.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
              actions={
                <div className="row" style={{ gap: "0.25rem" }}>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setMonthOffset((value) => value - 1)}
                    disabled={monthOffset <= 0}
                  >
                    ←
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setMonthOffset((value) => value + 1)}
                  >
                    →
                  </button>
                </div>
              }
            >
              {calendar.loading ? (
                <Loading />
              ) : (
                <>
                  <div className="calendar">
                    {DAYS.map((day) => (
                      <div className="calendar__head" key={day}>
                        {day}
                      </div>
                    ))}
                    {Array.from({ length: leadingBlanks }, (_, index) => (
                      <div key={`blank-${index}`} />
                    ))}
                    {days.map((day) => {
                      const date = new Date(day.day);
                      const state = day.blocked
                        ? "blocked"
                        : day.booked_slots >= day.total_slots && day.windows.length
                          ? "booked"
                          : day.is_open
                            ? "open"
                            : "closed";
                      const title = day.blocked
                        ? "Blocked"
                        : !day.windows.length
                          ? "Closed"
                          : `${day.windows
                              .map(([open, close]) => `${minutesToTime(open)}–${minutesToTime(close)}`)
                              .join(", ")}${day.booked_slots ? ` · ${day.booked_slots}/${day.total_slots} booked` : ""}`;
                      return (
                        <div
                          key={day.day}
                          className={`calendar__day calendar__day--${state}`}
                          title={`${dateOnly(day.day)}: ${title}`}
                        >
                          <span>{date.getDate()}</span>
                          <span className="calendar__mark" aria-hidden="true">
                            {state === "blocked"
                              ? "✕"
                              : state === "booked"
                                ? "●"
                                : state === "open"
                                  ? "✓"
                                  : "–"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="row tiny muted" style={{ marginTop: "0.9rem", gap: "0.9rem" }}>
                    <span>✓ Open</span>
                    <span>● Booked</span>
                    <span>✕ Blocked</span>
                    <span>– Closed</span>
                  </div>
                </>
              )}
            </Panel>

            {space.data?.status === "DRAFT" ? (
              <Alert kind="info">
                Save a schedule, then publish the listing to make it bookable.
              </Alert>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
