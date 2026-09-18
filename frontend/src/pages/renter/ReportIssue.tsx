import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, ErrorMessage, Field, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { ISSUE_LABEL } from "../../lib/format";
import { useSubmit } from "../../lib/hooks";
import type { IssueType, Report } from "../../lib/types";

export default function ReportIssue() {
  const { bookingId = "" } = useParams();
  const [issueType, setIssueType] = useState<IssueType>("SPACE_OCCUPIED");
  const [description, setDescription] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const submit = useSubmit(async () => {
    const created = await api.post<Report>("/reports", {
      booking_id: bookingId,
      issue_type: issueType,
      description: description.trim(),
    });
    setReport(created);
  });

  const addPhoto = useSubmit(async (file: File) => {
    if (!report) return;
    setPhotoError(null);
    try {
      await api.upload(`/reports/${report.id}/photos`, file);
      setReport(await api.get<Report>(`/reports/${report.id}`));
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : "Upload failed");
    }
  });

  if (report) {
    return (
      <main className="page page--narrow">
        <div className="stack">
          <Alert kind="success">
            Your report has been sent to our team. We will follow up on it.
          </Alert>

          <Panel title="Add photo evidence (optional)">
            <p className="small muted">
              Photos help us understand what happened. You can add up to six.
            </p>
            {report.photos.length > 0 ? (
              <div className="photos" style={{ marginBottom: "0.75rem" }}>
                {report.photos.map((photo) => (
                  <div className="photo" key={photo.id}>
                    <img src={photo.url} alt="" />
                  </div>
                ))}
              </div>
            ) : null}
            {photoError ? <Alert kind="error">{photoError}</Alert> : null}
            <label className="btn btn--secondary btn--sm" style={{ cursor: "pointer" }}>
              {addPhoto.pending ? "Uploading…" : "Add a photo"}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void addPhoto.run(file);
                }}
              />
            </label>
          </Panel>

          <Link to={`/bookings/${bookingId}`} className="btn">
            Back to booking
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page page--narrow">
      <div className="stack">
        <Link to={`/bookings/${bookingId}`} className="small">
          ← Back to booking
        </Link>
        <h1>Report an issue</h1>

        <Alert kind="info">
          We review every report. ParkSpace is a marketplace, not an insurer — liability for damage
          is governed by our terms and the agreement between the parties.
        </Alert>

        <Panel>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              void submit.run();
            }}
          >
            <ErrorMessage error={submit.error} />
            <Field label="What went wrong?" required>
              <select value={issueType} onChange={(event) => setIssueType(event.target.value as IssueType)}>
                {Object.entries(ISSUE_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tell us what happened" required hint="At least 10 characters.">
              <textarea
                rows={5}
                required
                minLength={10}
                maxLength={4000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="When you arrived, what you found, and anything you did about it."
              />
            </Field>
            <button
              type="submit"
              className="btn"
              disabled={submit.pending || description.trim().length < 10}
            >
              {submit.pending ? "Sending…" : "Send report"}
            </button>
          </form>
        </Panel>
      </div>
    </main>
  );
}
