import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function Landing() {
  const { user, provider } = useAuth();

  return (
    <>
      <section className="hero">
        <div className="hero__inner">
          <div className="hero__copy">
            <h1>Find Parking. Rent Your Empty Space.</h1>
            <p>
              ParkSpace connects people who need parking with the houses, societies and
              organisations that have space sitting empty. Book by the hour, the day or the month.
            </p>
            <div className="hero__actions">
              <Link to="/search" className="btn btn--lg">
                Find parking
              </Link>
              <Link
                to={provider ? "/provider/listings/new" : "/list-your-space"}
                className="btn btn--lg btn--secondary"
              >
                List my parking
              </Link>
            </div>
          </div>

          {/* Decorative, and deliberately made of the product's own furniture — a
              price pill and a bay grid — rather than stock illustration. */}
          <div className="hero__art" aria-hidden="true">
            <div className="hero__card hero__card--price">
              <span className="hero__price">
                ₹50<small>/hr</small>
              </span>
              <span className="hero__where">Ashram Road</span>
              <span className="hero__meta">Covered · 2 min walk</span>
            </div>
            <div className="hero__card hero__card--bays">
              <span className="hero__meta">Pick your bay</span>
              <div className="hero__bays">
                <i /><i className="is-off" /><i />
                <i className="is-mine" /><i /><i className="is-off" />
              </div>
            </div>
            <span className="hero__chip">Booked in 40s</span>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section__inner grid grid--2">
          <div className="card">
            <h2>Need parking?</h2>
            <p className="muted">
              Search by area or around where you are, see what is genuinely free for the times you
              need, and book it. You will know the exact price, including fees, before you pay.
            </p>
            <Link to="/search" className="btn">
              Search nearby parking
            </Link>
          </div>
          <div className="card">
            <h2>Have unused parking?</h2>
            <p className="muted">
              Turn an empty parking space into income. Set your own price and hours, block the
              days you need it yourself, and get paid for the rest.
            </p>
            <Link to="/list-your-space" className="btn btn--secondary">
              Start listing
            </Link>
          </div>
        </div>
      </section>

      <section className="section section--alt">
        <div className="section__inner">
          <h2 className="center" style={{ marginBottom: "1.75rem" }}>
            How it works
          </h2>
          <div className="grid grid--3">
            {[
              {
                step: 1,
                title: "Search",
                body: "Enter an area or use your location. Filter by vehicle, parking type and price.",
              },
              {
                step: 2,
                title: "Book and pay",
                body: "Pick your dates and times, choose a vehicle, and pay securely online.",
              },
              {
                step: 3,
                title: "Park",
                body: "Your confirmation carries the address, access instructions and a reference to show on arrival.",
              },
            ].map((item) => (
              <div className="stack stack--sm" key={item.step}>
                <div className="step__num">{item.step}</div>
                <h3 style={{ margin: 0 }}>{item.title}</h3>
                <p className="muted small" style={{ margin: 0 }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section__inner">
          <h2 className="center" style={{ marginBottom: "1.75rem" }}>
            For societies and organisations
          </h2>
          <div className="grid grid--3">
            {[
              {
                title: "Monetise visitor bays",
                body: "Open spare or visitor parking to the public during the hours that suit the society.",
              },
              {
                title: "Stay in control",
                body: "Set hours per day, block dates instantly, and see every booking and vehicle.",
              },
              {
                title: "Clear revenue share",
                body: "Your agreed share is applied to every booking, with earnings you can check any time.",
              },
            ].map((item) => (
              <div className="card" key={item.title}>
                <h3 className="card__title">{item.title}</h3>
                <p className="muted small" style={{ margin: 0 }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
          {!user ? (
            <div className="center" style={{ marginTop: "2rem" }}>
              <Link to="/register?role=provider&type=society" className="btn btn--lg">
                Register your society
              </Link>
            </div>
          ) : null}
        </div>
      </section>
    </>
  );
}
