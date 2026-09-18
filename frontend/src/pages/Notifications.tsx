import { Empty, ErrorMessage, Loading, Panel } from "../components/ui";
import { api } from "../lib/api";
import { relativeTime } from "../lib/format";
import { useAsync, useSubmit } from "../lib/hooks";
import type { Notification, Paginated } from "../lib/types";

export default function Notifications() {
  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<Notification> & { unread: number }>("/notifications", { limit: 50 }, signal),
    [],
  );

  const markAllRead = useSubmit(async () => {
    await api.post("/notifications/read-all");
    reload();
  });

  const markRead = useSubmit(async (id: string) => {
    await api.post(`/notifications/${id}/read`);
    reload();
  });

  return (
    <main className="page page--narrow">
      <div className="stack">
        <div className="row row--between">
          <h1>Notifications</h1>
          {data && data.unread > 0 ? (
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => void markAllRead.run()}
              disabled={markAllRead.pending}
            >
              Mark all read
            </button>
          ) : null}
        </div>

        <ErrorMessage error={error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No notifications yet">
            Booking confirmations, reminders and updates will appear here.
          </Empty>
        ) : (
          <div className="stack">
            {data.items.map((notification) => (
              <Panel key={notification.id}>
                <div className="row row--between" style={{ alignItems: "flex-start" }}>
                  <div className="stack stack--sm" style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: "0.5rem" }}>
                      {!notification.read_at ? (
                        <span
                          aria-label="Unread"
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            background: "var(--primary)",
                            flexShrink: 0,
                          }}
                        />
                      ) : null}
                      <span className="bold">{notification.title}</span>
                    </div>
                    <p className="small muted" style={{ margin: 0 }}>
                      {notification.body}
                    </p>
                    <span className="tiny muted">{relativeTime(notification.created_at)}</span>
                  </div>
                  {!notification.read_at ? (
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => void markRead.run(notification.id)}
                    >
                      Mark read
                    </button>
                  ) : null}
                </div>
              </Panel>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
