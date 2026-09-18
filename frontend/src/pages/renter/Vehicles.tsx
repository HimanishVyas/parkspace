import { useState } from "react";
import { Badge, ConfirmButton, Empty, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { VEHICLE_LABEL } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Vehicle, VehicleType } from "../../lib/types";

export default function Vehicles() {
  const { data, error, loading, reload } = useAsync(
    (signal) => api.get<Vehicle[]>("/vehicles", undefined, signal),
    [],
  );
  const [form, setForm] = useState({
    vehicle_type: "CAR" as VehicleType,
    registration_number: "",
    make_model: "",
    color: "",
  });

  const add = useSubmit(async () => {
    await api.post("/vehicles", {
      vehicle_type: form.vehicle_type,
      registration_number: form.registration_number.trim(),
      make_model: form.make_model.trim() || undefined,
      color: form.color.trim() || undefined,
    });
    setForm({ vehicle_type: "CAR", registration_number: "", make_model: "", color: "" });
    reload();
  });

  const remove = useSubmit(async (id: string) => {
    await api.del(`/vehicles/${id}`);
    reload();
  });

  const makeDefault = useSubmit(async (id: string) => {
    await api.patch(`/vehicles/${id}`, { is_default: true });
    reload();
  });

  return (
    <main className="page page--narrow">
      <div className="stack">
        <div>
          <h1>My vehicles</h1>
          <p className="muted small">
            A vehicle registration number is required to confirm a booking, so providers and
            security know which car is theirs.
          </p>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={remove.error} />

        {loading ? (
          <Loading />
        ) : !data?.length ? (
          <Empty title="No vehicles saved yet">Add one below to start booking.</Empty>
        ) : (
          <div className="stack">
            {data.map((vehicle) => (
              <div className="card" key={vehicle.id}>
                <div className="row row--between">
                  <div>
                    <div className="row" style={{ gap: "0.5rem" }}>
                      <span className="bold numeric">{vehicle.registration_number}</span>
                      {vehicle.is_default ? <Badge tone="teal">Default</Badge> : null}
                    </div>
                    <div className="small muted">
                      {VEHICLE_LABEL[vehicle.vehicle_type]}
                      {vehicle.make_model ? ` · ${vehicle.make_model}` : ""}
                      {vehicle.color ? ` · ${vehicle.color}` : ""}
                    </div>
                  </div>
                  <div className="row">
                    {!vehicle.is_default ? (
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm"
                        onClick={() => void makeDefault.run(vehicle.id)}
                      >
                        Make default
                      </button>
                    ) : null}
                    <ConfirmButton
                      label="Remove"
                      confirmLabel={`Remove ${vehicle.registration_number}?`}
                      onConfirm={() => void remove.run(vehicle.id)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <Panel title="Add a vehicle">
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              void add.run();
            }}
          >
            <ErrorMessage error={add.error} />
            <Field label="Vehicle type" required>
              <select
                value={form.vehicle_type}
                onChange={(event) =>
                  setForm({ ...form, vehicle_type: event.target.value as VehicleType })
                }
              >
                <option value="BIKE">Bike</option>
                <option value="CAR">Car</option>
                <option value="SUV">SUV</option>
              </select>
            </Field>
            <Field label="Registration number" required hint="For example GJ01AB1234">
              <input
                type="text"
                required
                value={form.registration_number}
                onChange={(event) => setForm({ ...form, registration_number: event.target.value })}
                style={{ textTransform: "uppercase" }}
              />
            </Field>
            <div className="row" style={{ gap: "0.75rem" }}>
              <div style={{ flex: 1 }}>
                <Field label="Make and model">
                  <input
                    type="text"
                    value={form.make_model}
                    placeholder="Hyundai i20"
                    onChange={(event) => setForm({ ...form, make_model: event.target.value })}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="Colour">
                  <input
                    type="text"
                    value={form.color}
                    placeholder="White"
                    onChange={(event) => setForm({ ...form, color: event.target.value })}
                  />
                </Field>
              </div>
            </div>
            <button type="submit" className="btn" disabled={add.pending}>
              {add.pending ? "Saving…" : "Add vehicle"}
            </button>
          </form>
        </Panel>
      </div>
    </main>
  );
}
