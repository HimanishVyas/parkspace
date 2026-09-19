import { useState } from "react";
import { Badge, Empty, ErrorMessage, Field, Loading, Pagination } from "../../components/ui";
import { api } from "../../lib/api";
import { ISSUE_LABEL, dateTime } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Paginated, Report, ReportStatus } from "../../lib/types";

const LIMIT = 20;

function statusTone(status: ReportStatus): string {
  return status === "OPEN" ? "red" : status === "UNDER_REVIEW" ? "amber" : status === "RESOLVED" ? "green" : "";
}

export default function Reports() {
  const [status, setStatus] = useState("OPEN");
  const [offset, setOffset] = useState(0);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<Report>>(
        "/admin/reports",
        { report_status: status || undefined, limit: LIMIT, offset },
        signal,
      ),
    [status, offset],
  );

  const update = useSubmit(async (id: string, nextStatus: ReportStatus) => {
    await api.patch(`/admin/reports/${id}`, {
      status: nextStatus,
      admin_notes: notes[id]?.trim() || undefined,
    });
    reload();
  });

  return (
    <main className="page page--wide">
      <h1>Reports</h1>

      <div className="stack">
        <div className="row">
          <select
            value={status}
            style={{ flex: "0 1 220px" }}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All reports</option>
            <option value="OPEN">Open</option>
            <option value="UNDER_REVIEW">Under review</option>
            <option value="RESOLVED">Resolved</option>
            <option value="DISMISSED">Dismissed</option>
          </select>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={update.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No reports here">Nothing needs attention in this view.</Empty>
        ) : (
          <>
            <div className="stack">
              {data.items.map((report) => (
                <div className="panel panel__body" key={report.id}>
                  <div className="stack">
                    <div className="row row--between" style={{ alignItems: "flex-start" }}>
                      <div>
                        <div className="row" style={{ gap: "0.5rem" }}>
                          <span className="bold">{ISSUE_LABEL[report.issue_type]}</span>
                          <Badge tone={statusTone(report.status)}>
                            {report.status.replace(/_/g, " ")}
                          </Badge>
                        </div>
                        <div className="tiny muted">
                          Reported {dateTime(report.created_at)} · booking {report.booking_id.slice(0, 8)}
                        </div>
                      </div>
                    </div>

                    <p className="small" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {report.description}
                    </p>

                    {report.photos.length > 0 ? (
                      <div className="photos">
                        {report.photos.map((photo) => (
                          <a
                            className="photo"
                            key={photo.id}
                            href={photo.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img src={photo.url} alt="Evidence" />
                          </a>
                        ))}
                      </div>
                    ) : null}

                    {report.admin_notes ? (
                      <div className="small muted">Previous note: {report.admin_notes}</div>
                    ) : null}

                    <Field label="Note to the reporter">
                      <input
                        type="text"
                        value={notes[report.id] ?? ""}
                        placeholder="What you found and what happens next"
                        onChange={(event) => setNotes({ ...notes, [report.id]: event.target.value })}
                      />
                    </Field>

                    <div className="row" style={{ gap: "0.4rem" }}>
                      {report.status === "OPEN" ? (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => void update.run(report.id, "UNDER_REVIEW")}
                        >
                          Start review
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => void update.run(report.id, "RESOLVED")}
                      >
                        Mark resolved
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => void update.run(report.id, "DISMISSED")}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </main>
  );
}
