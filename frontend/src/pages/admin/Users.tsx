import { useState } from "react";
import AdminNav from "../../components/AdminNav";
import { Badge, ConfirmButton, Empty, ErrorMessage, Loading, Pagination } from "../../components/ui";
import { api } from "../../lib/api";
import { dateOnly } from "../../lib/format";
import { useAsync, useDebounced, useSubmit } from "../../lib/hooks";
import type { AdminUser, Paginated } from "../../lib/types";

const LIMIT = 20;

export default function Users() {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [offset, setOffset] = useState(0);
  const search = useDebounced(query);

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<AdminUser>>(
        "/admin/users",
        { q: search || undefined, role: role || undefined, limit: LIMIT, offset },
        signal,
      ),
    [search, role, offset],
  );

  const setStatus = useSubmit(async (id: string, status: "ACTIVE" | "SUSPENDED", reason?: string) => {
    await api.post(`/admin/users/${id}/status`, { status, reason });
    reload();
  });

  return (
    <main className="page page--wide">
      <h1>Admin</h1>
      <AdminNav />

      <div className="stack">
        <div className="row">
          <input
            type="search"
            placeholder="Search name, email or phone"
            value={query}
            style={{ flex: "1 1 240px" }}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          <select
            value={role}
            style={{ flex: "0 1 180px" }}
            onChange={(event) => {
              setRole(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All roles</option>
            <option value="RENTER">Renters</option>
            <option value="PROVIDER">Providers</option>
            <option value="ADMIN">Admins</option>
          </select>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={setStatus.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No users matched" />
        ) : (
          <>
            <div className="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Contact</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((user) => (
                    <tr key={user.id}>
                      <td className="bold">{user.full_name}</td>
                      <td>
                        <div className="small">{user.email}</div>
                        {user.phone ? <div className="tiny muted numeric">{user.phone}</div> : null}
                      </td>
                      <td>
                        <Badge tone={user.role === "ADMIN" ? "blue" : user.role === "PROVIDER" ? "teal" : ""}>
                          {user.role}
                        </Badge>
                      </td>
                      <td>
                        <Badge tone={user.status === "ACTIVE" ? "green" : "red"}>{user.status}</Badge>
                      </td>
                      <td className="small muted">{dateOnly(user.created_at)}</td>
                      <td>
                        {user.status === "ACTIVE" ? (
                          <ConfirmButton
                            label="Suspend"
                            confirmLabel={`Suspend ${user.full_name}? They are signed out immediately.`}
                            onConfirm={() => void setStatus.run(user.id, "SUSPENDED", "Suspended by admin")}
                          />
                        ) : (
                          <button
                            type="button"
                            className="btn btn--secondary btn--sm"
                            onClick={() => void setStatus.run(user.id, "ACTIVE")}
                          >
                            Reactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </main>
  );
}
