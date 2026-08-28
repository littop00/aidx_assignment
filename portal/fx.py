import requests

API_URL = "https://open.er-api.com/v6/latest/KRW"

def store_rate(conn, currency, rate_date, rate):
    conn.execute(
        "INSERT INTO fx_rates (currency, rate_date, rate) VALUES (?, ?, ?) "
        "ON CONFLICT(currency, rate_date) DO UPDATE SET rate=excluded.rate",
        (currency, rate_date, rate),
    )
    conn.commit()

def get_latest_rate(conn, currency):
    if currency == "KRW":
        return 1.0
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE currency = ? ORDER BY rate_date DESC LIMIT 1",
        (currency,),
    ).fetchone()
    return row["rate"] if row else None

def fetch_rates_from_api():
    resp = requests.get(API_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    krw_per_unit = {}
    for currency, rate_from_krw in data["rates"].items():
        if rate_from_krw:
            krw_per_unit[currency] = 1.0 / rate_from_krw
    return krw_per_unit

def refresh_rates(conn, today, fetch_fn=None):
    fetch_fn = fetch_fn or fetch_rates_from_api
    row = conn.execute("SELECT MAX(rate_date) as latest FROM fx_rates").fetchone()
    if row["latest"] == today:
        return {"updated": False, "reason": "already refreshed today"}

    try:
        rates = fetch_fn()
    except Exception as exc:
        return {"updated": False, "reason": str(exc)}

    for currency, rate in rates.items():
        store_rate(conn, currency, today, rate)
    return {"updated": True, "reason": "refreshed from API"}
