import datetime

RATE_FIELDS = ["container_freight"]

def store_rate(conn, country, effective_date, fields):
    values = {name: fields.get(name) or 0 for name in RATE_FIELDS}
    conn.execute(
        "INSERT INTO logistics_rates (country, effective_date, " + ", ".join(RATE_FIELDS) + ", created_at) "
        "VALUES (?, ?, " + ", ".join(["?"] * len(RATE_FIELDS)) + ", ?) "
        "ON CONFLICT(country, effective_date) DO UPDATE SET " +
        ", ".join(f"{name}=excluded.{name}" for name in RATE_FIELDS),
        [country, effective_date] + [values[name] for name in RATE_FIELDS] + [datetime.datetime.now().isoformat(timespec="seconds")],
    )
    conn.commit()

def delete_rate(conn, country, effective_date):
    conn.execute("DELETE FROM logistics_rates WHERE country = ? AND effective_date = ?", (country, effective_date))
    conn.commit()

def get_latest_rate(conn, country):
    row = conn.execute(
        "SELECT * FROM logistics_rates WHERE country = ? ORDER BY effective_date DESC LIMIT 1",
        (country,),
    ).fetchone()
    return dict(row) if row else None

def list_rate_history(conn, country):
    rows = conn.execute(
        "SELECT * FROM logistics_rates WHERE country = ? ORDER BY effective_date DESC",
        (country,),
    ).fetchall()
    return [dict(row) for row in rows]

def list_latest_rates(conn):
    rows = conn.execute("""
        SELECT r.* FROM logistics_rates r
        INNER JOIN (SELECT country, MAX(effective_date) AS effective_date FROM logistics_rates GROUP BY country) latest
            ON latest.country = r.country AND latest.effective_date = r.effective_date
        ORDER BY r.country
    """).fetchall()
    return [dict(row) for row in rows]
