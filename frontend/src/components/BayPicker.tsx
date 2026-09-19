/**
 * Pick your bay, the way you pick a seat.
 *
 * Draws the space's layout for the chosen window: free bays are selectable,
 * taken ones are not, and the one you picked is obvious. Choosing is optional —
 * leaving it alone lets the server assign a bay, which is what happened before
 * this existed.
 *
 * The taken/free state here is an optimistic read. The authority is the
 * database's exclusion constraint, so a bay shown free can still be lost to
 * someone a half-second quicker; the booking call reports that honestly rather
 * than moving the renter somewhere else.
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { BayLayout } from "../lib/types";

interface Props {
  spaceId: string;
  /** ISO window. Without both, the picker can't say what is free. */
  startAt: string | null;
  endAt: string | null;
  value: number | null;
  onChange: (slotIndex: number | null) => void;
}

export default function BayPicker({ spaceId, startAt, endAt, value, onChange }: Props) {
  const [layout, setLayout] = useState<BayLayout | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const params: Record<string, string> = {};
        if (startAt && endAt) {
          params.start_at = new Date(startAt).toISOString();
          params.end_at = new Date(endAt).toISOString();
        }
        const result = await api.get<BayLayout>(`/parking/${spaceId}/bays`, params);
        if (active) setLayout(result);
      } catch {
        if (active) setLayout(null);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [spaceId, startAt, endAt]);

  // A single-bay space has nothing to choose between.
  if (!layout || layout.total_slots <= 1) return null;

  const known = startAt && endAt;
  const rows = new Map<number, typeof layout.bays>();
  for (const bay of layout.bays) {
    rows.set(bay.row_index, [...(rows.get(bay.row_index) ?? []), bay]);
  }
  const freeCount = layout.bays.filter((b) => b.is_active && !b.taken).length;

  return (
    <div className="bays">
      <div className="bays__head">
        <span className="field__label" style={{ margin: 0 }}>
          Pick your bay
        </span>
        <span className="small muted">
          {known ? `${freeCount} of ${layout.total_slots} free` : "Choose your times to see what's free"}
        </span>
      </div>

      <div className="bays__entrance">Entrance</div>

      <div className="bays__grid">
        {[...rows.entries()]
          .sort((a, b) => a[0] - b[0])
          .map(([rowIndex, bays]) => (
            <div className="bays__row" key={rowIndex}>
              {bays
                .slice()
                .sort((a, b) => a.col_index - b.col_index)
                .map((bay) => {
                  const unavailable = !bay.is_active || Boolean(bay.taken);
                  const selected = value === bay.slot_index;
                  return (
                    <button
                      type="button"
                      key={bay.slot_index}
                      className={`bay${selected ? " bay--on" : ""}${
                        unavailable ? " bay--off" : ""
                      }`}
                      disabled={unavailable}
                      aria-pressed={selected}
                      aria-label={
                        unavailable
                          ? `Bay ${bay.label}, not available`
                          : `Bay ${bay.label}${selected ? ", selected" : ""}`
                      }
                      onClick={() => onChange(selected ? null : bay.slot_index)}
                    >
                      {bay.label}
                    </button>
                  );
                })}
            </div>
          ))}
      </div>

      <div className="bays__legend">
        <span>
          <i className="bay-key" /> free
        </span>
        <span>
          <i className="bay-key bay-key--on" /> yours
        </span>
        <span>
          <i className="bay-key bay-key--off" /> taken
        </span>
        {value !== null ? (
          <button type="button" className="linklike small" onClick={() => onChange(null)}>
            Clear — any bay is fine
          </button>
        ) : null}
      </div>
    </div>
  );
}
