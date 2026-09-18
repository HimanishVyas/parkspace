import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="page page--narrow">
      <div className="card center">
        <h1>Page not found</h1>
        <p className="muted">That page does not exist, or it has moved.</p>
        <Link to="/" className="btn">
          Back to home
        </Link>
      </div>
    </main>
  );
}
