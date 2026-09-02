import sqlite3
import datetime
import json
import sqlite3
from columns import DESIGN_FIELDS, PURCHASE_FIELDS
from categories import major_of, group_of
import logistics

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _resolve_bom_id(conn, bom_id=None):
    if bom_id is not None:
        return bom_id
    active = get_active_bom_version(conn)
    return active["id"] if active else 1

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_no INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            vehicle TEXT,
            status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'archived')),
            file_name TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT
        )
    """)
    for column, definition in (("is_withdrawn", "INTEGER NOT NULL DEFAULT 0"), ("withdrawn_at", "TEXT"), ("withdrawal_reason", "TEXT"), ("is_confirmed", "INTEGER NOT NULL DEFAULT 0"), ("confirmed_at", "TEXT"), ("due_date", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE bom_versions ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError:
            pass
    design_cols = ", ".join(f"{name} TEXT" for name, _ in DESIGN_FIELDS if name != "part_no")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS parts (
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            level_depth INTEGER,
            level_marker TEXT,
            {design_cols},
            PRIMARY KEY (part_no, row_num)
        )
    """)
    purchase_cols = ", ".join(f"{name} TEXT" for name, _ in PURCHASE_FIELDS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS purchase_data (
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            country TEXT NOT NULL,
            {purchase_cols},
            updated_at TEXT,
            updated_by TEXT,
            PRIMARY KEY (part_no, row_num, country),
            FOREIGN KEY (part_no, row_num) REFERENCES parts(part_no, row_num)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS bom_parts (
            bom_id INTEGER NOT NULL,
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            level_depth INTEGER,
            level_marker TEXT,
            {design_cols},
            PRIMARY KEY (bom_id, part_no, row_num),
            FOREIGN KEY (bom_id) REFERENCES bom_versions(id)
        )
    """)
    try:
        conn.execute("ALTER TABLE bom_parts ADD COLUMN manual_row INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bom_parts ADD COLUMN sub_category TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS bom_purchase_data (
            bom_id INTEGER NOT NULL,
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            country TEXT NOT NULL,
            {purchase_cols},
            updated_at TEXT,
            updated_by TEXT,
            PRIMARY KEY (bom_id, part_no, row_num, country),
            FOREIGN KEY (bom_id, part_no, row_num) REFERENCES bom_parts(bom_id, part_no, row_num)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS bom_user_purchase_data (
            bom_id INTEGER NOT NULL, user_id INTEGER NOT NULL, part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL, country TEXT NOT NULL, {purchase_cols},
            updated_at TEXT, updated_by TEXT,
            PRIMARY KEY (bom_id, user_id, part_no, row_num, country)
        )
    """)
    # These values are user-entered operational data, not part of the BOM
    # template.  Keep them separate so older databases can be migrated safely.
    for table in ("bom_purchase_data", "bom_user_purchase_data"):
        for column, definition in (
            ("sourcing_part_location", "TEXT"),
            ("sourcing_assembly_location", "TEXT"),
            ("special_fx_rate", "TEXT"),
            ("special_fx_reason", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_part_assignments (
            bom_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (bom_id, user_id, part_no, row_num),
            FOREIGN KEY (bom_id, part_no, row_num) REFERENCES bom_parts(bom_id, part_no, row_num),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_category_members (
            bom_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (bom_id, category, user_id),
            FOREIGN KEY (bom_id) REFERENCES bom_versions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_part_groups (
            bom_id INTEGER NOT NULL,
            parent_part_no TEXT NOT NULL,
            parent_row_num INTEGER NOT NULL,
            owner_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (bom_id, parent_part_no, parent_row_num)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_part_group_members (
            bom_id INTEGER NOT NULL,
            parent_part_no TEXT NOT NULL,
            parent_row_num INTEGER NOT NULL,
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            PRIMARY KEY (bom_id, part_no, row_num)
        )
    """)
    for col in ("updated_at", "updated_by"):
        try:
            conn.execute(f"ALTER TABLE purchase_data ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            currency TEXT NOT NULL,
            rate_date TEXT NOT NULL,
            rate REAL NOT NULL,
            PRIMARY KEY (currency, rate_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            country TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_upload_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            file_name TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS country_master (
            country TEXT PRIMARY KEY,
            is_overseas INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bom_version_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft', 'submitted', 'returned', 'approved')) DEFAULT 'draft',
            submitted_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_comment TEXT,
            snapshot_json TEXT,
            UNIQUE (bom_version_id, user_id),
            FOREIGN KEY (bom_version_id) REFERENCES bom_versions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # Existing databases predate the submission snapshot column.
    try:
        conn.execute("ALTER TABLE bom_submissions ADD COLUMN snapshot_json TEXT")
    except Exception:
        pass
    submissions_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bom_submissions'").fetchone()
    if submissions_schema and "auto_submitted" not in submissions_schema["sql"]:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE bom_submissions RENAME TO bom_submissions_old")
        conn.execute("""
            CREATE TABLE bom_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bom_version_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft', 'submitted', 'returned', 'approved', 'auto_submitted')) DEFAULT 'draft',
                submitted_at TEXT,
                reviewed_at TEXT,
                reviewed_by TEXT,
                review_comment TEXT,
                snapshot_json TEXT,
                UNIQUE (bom_version_id, user_id),
                FOREIGN KEY (bom_version_id) REFERENCES bom_versions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            INSERT INTO bom_submissions (id, bom_version_id, user_id, status, submitted_at, reviewed_at, reviewed_by, review_comment, snapshot_json)
            SELECT id, bom_version_id, user_id, status, submitted_at, reviewed_at, reviewed_by, review_comment, snapshot_json FROM bom_submissions_old
        """)
        conn.execute("DROP TABLE bom_submissions_old")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_version_countries (
            bom_version_id INTEGER NOT NULL,
            country TEXT NOT NULL,
            display_order INTEGER NOT NULL,
            PRIMARY KEY (bom_version_id, country),
            FOREIGN KEY (bom_version_id) REFERENCES bom_versions(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'info',
            link TEXT,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            revision_no INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(submission_id, revision_no),
            FOREIGN KEY(submission_id) REFERENCES bom_submissions(id)
        )
    """)
    revisions_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='submission_revisions'").fetchone()
    if revisions_schema and "bom_submissions_old" in revisions_schema["sql"]:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE submission_revisions RENAME TO submission_revisions_old")
        conn.execute("""
            CREATE TABLE submission_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                revision_no INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                UNIQUE(submission_id, revision_no),
                FOREIGN KEY(submission_id) REFERENCES bom_submissions(id)
            )
        """)
        conn.execute("""
            INSERT INTO submission_revisions (id, submission_id, revision_no, snapshot_json, submitted_at)
            SELECT id, submission_id, revision_no, snapshot_json, submitted_at FROM submission_revisions_old
            WHERE submission_id IN (SELECT id FROM bom_submissions)
        """)
        conn.execute("DROP TABLE submission_revisions_old")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    # Older dev DBs may already have the pre-simplification 10-field rate
    # tables; drop them so the CREATE TABLE below picks up the new schema.
    for legacy_table in ("logistics_rates", "bom_logistics_rate_snapshot"):
        cols = conn.execute(f"PRAGMA table_info({legacy_table})").fetchall()
        if cols and not any(col["name"] == "container_freight" for col in cols):
            conn.execute(f"DROP TABLE {legacy_table}")
    conn.execute("DROP TABLE IF EXISTS bom_logistics_volume")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logistics_rates (
            country TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            container_freight REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (country, effective_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_logistics_settings (
            bom_id INTEGER PRIMARY KEY,
            box_width REAL,
            box_depth REAL,
            box_height REAL,
            boxes_per_container REAL,
            container_weight_limit_kg REAL,
            export_packaging_cost REAL,
            FOREIGN KEY (bom_id) REFERENCES bom_versions(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bom_logistics_rate_snapshot (
            bom_id INTEGER NOT NULL,
            country TEXT NOT NULL,
            container_freight REAL NOT NULL DEFAULT 0,
            captured_at TEXT NOT NULL,
            PRIMARY KEY (bom_id, country),
            FOREIGN KEY (bom_id) REFERENCES bom_versions(id)
        )
    """)
    registered_countries = [
        "유럽", "미국", "캐나다", "멕시코", "브라질", "아르헨티나", "칠레", "콜롬비아", "페루",
        "영국", "독일", "프랑스", "이탈리아", "스페인", "포르투갈", "네덜란드", "벨기에", "스위스", "오스트리아",
        "폴란드", "체코", "슬로바키아", "헝가리", "루마니아", "슬로베니아", "크로아티아", "세르비아", "튀르키예", "스웨덴", "노르웨이", "덴마크", "핀란드",
        "중국", "일본", "인도", "베트남", "태국", "인도네시아", "말레이시아", "싱가포르", "필리핀", "대만", "대한민국", "호주", "뉴질랜드",
        "남아프리카공화국", "이집트", "모로코", "사우디아라비아", "아랍에미리트", "이스라엘",
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO country_master (country) VALUES (?)",
        [(country,) for country in registered_countries],
    )
    if not conn.execute("SELECT 1 FROM bom_versions LIMIT 1").fetchone():
        conn.execute(
            "INSERT INTO bom_versions (version_no, name, vehicle, status, created_at, published_at) VALUES (1, ?, ?, 'published', ?, ?)",
            ("NE2_NV1 BOM v1", "NE2_NV1", datetime.datetime.now().isoformat(timespec="seconds"), datetime.datetime.now().isoformat(timespec="seconds")),
        )
    if not conn.execute("SELECT 1 FROM bom_parts LIMIT 1").fetchone():
        part_names = [name for name, _ in DESIGN_FIELDS if name != "part_no"]
        conn.execute("INSERT INTO bom_parts (bom_id, part_no, row_num, level_depth, level_marker, " + ", ".join(part_names) + ") SELECT 1, part_no, row_num, level_depth, level_marker, " + ", ".join(part_names) + " FROM parts")
        purchase_names = [name for name, _ in PURCHASE_FIELDS]
        target_columns = ["bom_id", "part_no", "row_num", "country"] + purchase_names + ["updated_at", "updated_by"]
        conn.execute("INSERT INTO bom_purchase_data (" + ", ".join(target_columns) + ") SELECT 1, part_no, row_num, country, " + ", ".join(purchase_names) + ", updated_at, updated_by FROM purchase_data")
    if not conn.execute("SELECT 1 FROM bom_version_countries WHERE bom_version_id = 1 LIMIT 1").fetchone():
        conn.executemany("INSERT OR IGNORE INTO bom_version_countries (bom_version_id, country, display_order) VALUES (1, ?, ?)", [("한국", 0), ("미국", 1), ("유럽", 2)])
    conn.commit()

def get_active_bom_version(conn):
    row = conn.execute("SELECT * FROM bom_versions WHERE status = 'published' AND COALESCE(is_withdrawn, 0) = 0 ORDER BY version_no DESC LIMIT 1").fetchone()
    return dict(row) if row else None

def list_bom_versions(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM bom_versions ORDER BY version_no DESC").fetchall()]

def get_bom_version(conn, bom_id):
    row = conn.execute("SELECT * FROM bom_versions WHERE id = ?", (bom_id,)).fetchone()
    return dict(row) if row else None

def create_draft_from_active(conn, name, vehicle, created_by, copy_costs=False):
    active = get_active_bom_version(conn)
    next_version = (conn.execute("SELECT COALESCE(MAX(version_no), 0) + 1 AS next_version FROM bom_versions").fetchone()["next_version"])
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        "INSERT INTO bom_versions (version_no, name, vehicle, status, created_by, created_at) VALUES (?, ?, ?, 'draft', ?, ?)",
        (next_version, name, vehicle, created_by, now),
    )
    bom_id = cursor.lastrowid
    if active:
        part_names = [name for name, _ in DESIGN_FIELDS if name != "part_no"]
        conn.execute("INSERT INTO bom_parts (bom_id, part_no, row_num, level_depth, level_marker, " + ", ".join(part_names) + ", manual_row) SELECT ?, part_no, row_num, level_depth, level_marker, " + ", ".join(part_names) + ", manual_row FROM bom_parts WHERE bom_id = ?", (bom_id, active["id"]))
        if copy_costs:
            conn.execute("INSERT INTO bom_purchase_data SELECT ?, part_no, row_num, country, " + ", ".join(name for name, _ in PURCHASE_FIELDS) + ", updated_at, updated_by FROM bom_purchase_data WHERE bom_id = ?", (bom_id, active["id"]))
        conn.execute("INSERT INTO bom_version_countries SELECT ?, country, display_order FROM bom_version_countries WHERE bom_version_id = ?", (bom_id, active["id"]))
    conn.commit()
    return get_bom_version(conn, bom_id)

def replace_bom_draft_data(conn, bom_id):
    conn.execute("DELETE FROM bom_purchase_data WHERE bom_id = ?", (bom_id,))
    conn.execute("DELETE FROM bom_parts WHERE bom_id = ?", (bom_id,))
    conn.commit()

def delete_bom_draft(conn, bom_id):
    conn.execute("DELETE FROM bom_purchase_data WHERE bom_id = ?", (bom_id,))
    conn.execute("DELETE FROM bom_parts WHERE bom_id = ?", (bom_id,))
    conn.execute("DELETE FROM bom_version_countries WHERE bom_version_id = ?", (bom_id,))
    conn.execute("DELETE FROM bom_versions WHERE id = ?", (bom_id,))
    conn.commit()

def migrate_matching_user_work(conn, from_bom_id, to_bom_id):
    """Carry work forward only for structurally unchanged BOM rows.

    Part numbers deliberately do not participate: engineering may renumber a
    part while keeping the same named/detail row.  Equal duplicates are paired
    in their original Excel order.
    """
    fields = [name for name, _ in DESIGN_FIELDS if name not in ("part_no",)]
    def key(row):
        return tuple(row.get(name) or "" for name in fields) + (row.get("level_depth") or 0,)
    old_by_key, new_by_key = {}, {}
    for row in list_parts(conn, from_bom_id): old_by_key.setdefault(key(row), []).append(row)
    for row in list_parts(conn, to_bom_id): new_by_key.setdefault(key(row), []).append(row)
    pairs = []
    for signature, old_rows in old_by_key.items():
        for old, new in zip(old_rows, new_by_key.get(signature, [])):
            pairs.append((old, new))
    for old, new in pairs:
        users = conn.execute("SELECT * FROM bom_user_purchase_data WHERE bom_id=? AND part_no=? AND row_num=?", (from_bom_id, old["part_no"], old["row_num"])).fetchall()
        for row in users:
            data = dict(row); data["part_no"] = new["part_no"]; data["row_num"] = new["row_num"]
            columns = [c for c in data if c not in ("bom_id",)]
            values = [to_bom_id] + [data[c] for c in columns]
            target = ["bom_id"] + columns
            conn.execute(f"INSERT OR REPLACE INTO bom_user_purchase_data ({', '.join(target)}) VALUES ({', '.join(['?']*len(target))})", values)
        assignments = conn.execute("SELECT user_id, assigned_at FROM bom_part_assignments WHERE bom_id=? AND part_no=? AND row_num=?", (from_bom_id, old["part_no"], old["row_num"])).fetchall()
        conn.executemany("INSERT OR IGNORE INTO bom_part_assignments (bom_id,user_id,part_no,row_num,assigned_at) VALUES (?,?,?,?,?)", [(to_bom_id,a["user_id"],new["part_no"],new["row_num"],a["assigned_at"]) for a in assignments])
    conn.commit()
    return len(pairs)

def get_logistics_settings(conn, bom_id):
    row = conn.execute("SELECT * FROM bom_logistics_settings WHERE bom_id=?", (bom_id,)).fetchone()
    return dict(row) if row else None

def set_logistics_settings(conn, bom_id, fields):
    columns = ["box_width", "box_depth", "box_height", "boxes_per_container", "container_weight_limit_kg", "export_packaging_cost"]
    values = [fields.get(name) or None for name in columns]
    conn.execute(
        "INSERT INTO bom_logistics_settings (bom_id, " + ", ".join(columns) + ") VALUES (?, " + ", ".join(["?"] * len(columns)) + ") "
        "ON CONFLICT(bom_id) DO UPDATE SET " + ", ".join(f"{name}=excluded.{name}" for name in columns),
        [bom_id] + values,
    )
    conn.commit()

def get_logistics_snapshot(conn, bom_id, country):
    row = conn.execute("SELECT * FROM bom_logistics_rate_snapshot WHERE bom_id=? AND country=?", (bom_id, country)).fetchone()
    return dict(row) if row else None

def get_container_freight(conn, bom_id, country):
    version = get_bom_version(conn, bom_id)
    if version and version["status"] == "published":
        snapshot = get_logistics_snapshot(conn, bom_id, country)
        if snapshot:
            return snapshot.get("container_freight")
    rate = logistics.get_latest_rate(conn, country)
    return rate.get("container_freight") if rate else None

def capture_logistics_snapshot(conn, bom_id):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    countries = [c for c in list_bom_countries(conn, bom_id) if c != "한국"]
    for country in countries:
        rate = logistics.get_latest_rate(conn, country)
        if not rate:
            continue
        columns = logistics.RATE_FIELDS
        conn.execute(
            "INSERT INTO bom_logistics_rate_snapshot (bom_id, country, " + ", ".join(columns) + ", captured_at) "
            "VALUES (?, ?, " + ", ".join(["?"] * len(columns)) + ", ?) "
            "ON CONFLICT(bom_id, country) DO UPDATE SET " + ", ".join(f"{name}=excluded.{name}" for name in columns) + ", captured_at=excluded.captured_at",
            [bom_id, country] + [rate.get(name) for name in columns] + [now],
        )
    conn.commit()

def publish_bom_version(conn, bom_id):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE bom_versions SET status = 'archived' WHERE status = 'published'")
    conn.execute("UPDATE bom_versions SET status = 'published', published_at = ?, is_withdrawn = 0, withdrawn_at = NULL, withdrawal_reason = NULL WHERE id = ? AND status = 'draft'", (now, bom_id))
    capture_logistics_snapshot(conn, bom_id)
    version = get_bom_version(conn, bom_id)
    users = conn.execute("SELECT id FROM users WHERE role = 'user'").fetchall()
    conn.executemany("INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'release', '/bom/', ?)", [(row['id'], 'New BOM released', f"{version['name']} (Rev.{version['version_no']}) is ready for input.", now) for row in users])
    """
    conn.executemany("INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'release', '/bom/', ?)", [(row['id'], '새 BOM이 배포되었습니다', f\"{version['name']} (Rev.{version['version_no']})을 확인하고 입력해 주세요.\", now) for row in users])
    """
    conn.commit()

def withdraw_bom_version(conn, bom_id, reason, withdrawn_by):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    version = get_bom_version(conn, bom_id)
    if not version or version["status"] != "published":
        return False
    conn.execute("UPDATE bom_versions SET is_withdrawn=1, withdrawn_at=?, withdrawal_reason=? WHERE id=?", (now, reason, bom_id))
    users = conn.execute("SELECT id FROM users WHERE role = 'user'").fetchall()
    conn.executemany("INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'urgent', '/', ?)", [(row['id'], 'BOM release withdrawn', f"{version['name']} was withdrawn. {reason or 'Please contact the administrator.'}", now) for row in users])
    """
    conn.executemany("INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'urgent', '/', ?)", [(row['id'], 'BOM 배포가 취소되었습니다', f\"{version['name']}의 배포가 취소되었습니다. {reason or '관리자 안내를 확인해 주세요.'}\", now) for row in users])
    """
    conn.commit()
    return True

def list_notifications(conn, user_id, limit=8):
    rows = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY is_read, id DESC LIMIT ?", (user_id, limit)).fetchall()
    return [dict(row) for row in rows]

def unread_notification_count(conn, user_id):
    return conn.execute("SELECT COUNT(*) AS count FROM notifications WHERE user_id=? AND is_read=0", (user_id,)).fetchone()["count"]

def mark_notifications_read(conn, user_id):
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
    conn.commit()

def notify_admins(conn, title, message, kind="info", link=None):
    admin_ids = [row["id"] for row in conn.execute("SELECT id FROM users WHERE role='admin'").fetchall()]
    conn.executemany(
        "INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(admin_id, title, message, kind, link, datetime.datetime.now().isoformat(timespec="seconds")) for admin_id in admin_ids],
    )
    conn.commit()

def submission_progress(conn, bom_id, user_id=None):
    countries = list_bom_countries(conn, bom_id)
    parts = list_assigned_parts(conn, bom_id, user_id) if user_id is not None else list_parts(conn, bom_id)
    # A grouped child is displayed for BOM order/context but never requires a
    # separate cost entry; the representative parent owns the cost.
    required_parts = []
    for part in parts:
        group = group_for_part(conn, bom_id, part["part_no"], part["row_num"])
        if not group or (group["parent_part_no"], group["parent_row_num"]) == (part["part_no"], part["row_num"]):
            required_parts.append(part)
    parts = required_parts
    total = len(parts) * len(countries)
    done = 0
    for part in parts:
        for country in countries:
            value = get_user_purchase(conn, part["part_no"], part["row_num"], country, user_id, bom_id) if user_id else get_purchase(conn, part["part_no"], part["row_num"], country, bom_id)
            if value and value.get("unit_price_material") not in (None, ""):
                done += 1
    return {"done": done, "total": total, "percent": round(done * 100 / total) if total else 0}

def list_bom_countries(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute("SELECT country FROM bom_version_countries WHERE bom_version_id = ? ORDER BY display_order", (bom_id,)).fetchall()
    return [row["country"] for row in rows]

def set_bom_countries(conn, bom_id, countries):
    countries = ["한국"] + [country for country in countries if country != "한국"]
    conn.execute("DELETE FROM bom_version_countries WHERE bom_version_id = ?", (bom_id,))
    conn.executemany("INSERT INTO bom_version_countries (bom_version_id, country, display_order) VALUES (?, ?, ?)", [(bom_id, country, index) for index, country in enumerate(dict.fromkeys(countries))])
    conn.commit()

def list_submissions(conn, bom_version_id):
    rows = conn.execute("""
        SELECT s.*, u.username FROM bom_submissions s JOIN users u ON u.id = s.user_id
        WHERE s.bom_version_id = ? ORDER BY s.status, u.username
    """, (bom_version_id,)).fetchall()
    return [dict(row) for row in rows]

def list_user_submissions(conn, user_id):
    rows = conn.execute("""
        SELECT s.*, b.name AS bom_name, b.vehicle, u.username
        FROM bom_submissions s
        JOIN bom_versions b ON b.id = s.bom_version_id
        JOIN users u ON u.id = s.user_id
        WHERE s.user_id = ?
        ORDER BY COALESCE(s.submitted_at, '') DESC, s.id DESC
    """, (user_id,)).fetchall()
    return [dict(row) for row in rows]

def get_submission(conn, submission_id):
    row = conn.execute("""
        SELECT s.*, b.name AS bom_name, b.vehicle, u.username
        FROM bom_submissions s
        JOIN bom_versions b ON b.id = s.bom_version_id
        JOIN users u ON u.id = s.user_id
        WHERE s.id = ?
    """, (submission_id,)).fetchone()
    return dict(row) if row else None

def save_submission_snapshot(conn, bom_version_id, user_id):
    countries = list_bom_countries(conn, bom_version_id)
    parts = list_assigned_parts(conn, bom_version_id, user_id)
    extra_fields = ["sourcing_part_location", "sourcing_assembly_location", "special_fx_rate", "special_fx_reason"]
    rows = []
    for part in parts:
        values = {}
        for country in countries:
            purchase = get_user_purchase(conn, part["part_no"], part["row_num"], country, user_id, bom_version_id) or {}
            values[country] = {name: purchase.get(name) for name, _ in PURCHASE_FIELDS}
            values[country].update({name: purchase.get(name) for name in extra_fields})
        rows.append({
            "vehicle": part.get("vehicle"), "category": part.get("category"),
            "part_no": part.get("part_no"), "level_marker": part.get("level_marker"),
            "part_name": part.get("part_name"), "qty": part.get("qty"), "countries": values,
        })
    payload = {"countries": countries, "rows": rows, "saved_at": datetime.datetime.now().isoformat(timespec="seconds")}
    conn.execute("UPDATE bom_submissions SET snapshot_json=? WHERE bom_version_id=? AND user_id=?", (json.dumps(payload, ensure_ascii=False), bom_version_id, user_id))
    submission = conn.execute("SELECT id FROM bom_submissions WHERE bom_version_id=? AND user_id=?", (bom_version_id, user_id)).fetchone()
    if submission:
        next_no = conn.execute("SELECT COALESCE(MAX(revision_no), 0) + 1 AS n FROM submission_revisions WHERE submission_id=?", (submission["id"],)).fetchone()["n"]
        conn.execute("INSERT INTO submission_revisions (submission_id, revision_no, snapshot_json, submitted_at) VALUES (?, ?, ?, ?)", (submission["id"], next_no, json.dumps(payload, ensure_ascii=False), payload["saved_at"]))
    conn.commit()
    return payload

def submission_snapshot(submission):
    return json.loads(submission.get("snapshot_json") or "{}")

def list_submission_revisions(conn, submission_id):
    return [dict(row) for row in conn.execute("SELECT revision_no, submitted_at FROM submission_revisions WHERE submission_id=? ORDER BY revision_no DESC", (submission_id,)).fetchall()]

def bom_version_difference(conn, base_bom_id, compare_bom_id):
    if not base_bom_id or not compare_bom_id:
        return {"added": 0, "removed": 0, "changed_qty": 0}
    base = {(p["part_no"], p["row_num"]): p for p in list_parts(conn, base_bom_id)}
    compare = {(p["part_no"], p["row_num"]): p for p in list_parts(conn, compare_bom_id)}
    return {"added": len(compare.keys() - base.keys()), "removed": len(base.keys() - compare.keys()), "changed_qty": sum(1 for key in base.keys() & compare.keys() if str(base[key].get("qty") or "") != str(compare[key].get("qty") or ""))}

def list_users(conn):
    return [dict(row) for row in conn.execute("SELECT id, username, role, created_at FROM users ORDER BY username").fetchall()]

def get_or_create_submission(conn, bom_version_id, user_id):
    conn.execute(
        "INSERT OR IGNORE INTO bom_submissions (bom_version_id, user_id) VALUES (?, ?)",
        (bom_version_id, user_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM bom_submissions WHERE bom_version_id=? AND user_id=?", (bom_version_id, user_id)).fetchone()
    return dict(row)

def update_submission_status(conn, bom_version_id, user_id, status, reviewed_by=None, review_comment=None):
    get_or_create_submission(conn, bom_version_id, user_id)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if status == "submitted":
        conn.execute("UPDATE bom_submissions SET status=?, submitted_at=?, review_comment=NULL WHERE bom_version_id=? AND user_id=?", (status, now, bom_version_id, user_id))
    elif status in ("approved", "returned"):
        conn.execute("UPDATE bom_submissions SET status=?, reviewed_at=?, reviewed_by=?, review_comment=? WHERE bom_version_id=? AND user_id=?", (status, now, reviewed_by, review_comment, bom_version_id, user_id))
    else:
        conn.execute("UPDATE bom_submissions SET status=? WHERE bom_version_id=? AND user_id=?", (status, bom_version_id, user_id))
    conn.commit()
    if status == "approved":
        try_confirm_bom_version(conn, bom_version_id)
    elif status == "returned":
        conn.execute("UPDATE bom_versions SET is_confirmed=0, confirmed_at=NULL WHERE id=?", (bom_version_id,))
        conn.commit()

def set_bom_due_date(conn, bom_id, due_date):
    conn.execute("UPDATE bom_versions SET due_date=? WHERE id=?", (due_date or None, bom_id))
    conn.commit()

def enforce_due_dates(conn):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    versions = conn.execute(
        "SELECT * FROM bom_versions WHERE due_date IS NOT NULL AND due_date != '' AND due_date < ? AND status='published' AND COALESCE(is_withdrawn,0)=0",
        (now,),
    ).fetchall()
    for version in versions:
        bom_id = version["id"]
        pending = conn.execute("SELECT user_id FROM bom_submissions WHERE bom_version_id=? AND status IN ('draft', 'returned')", (bom_id,)).fetchall()
        for row in pending:
            user_id = row["user_id"]
            save_submission_snapshot(conn, bom_id, user_id)
            conn.execute(
                "UPDATE bom_submissions SET status='auto_submitted', submitted_at=?, review_comment=NULL WHERE bom_version_id=? AND user_id=?",
                (now, bom_id, user_id),
            )
            conn.execute(
                "INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'warning', '/bom/', ?)",
                (user_id, "BOM 자동 제출", f"{version['name']}의 마감기한이 지나 입력 내용이 자동 제출되었습니다.", now),
            )
        if pending:
            notify_admins(conn, "BOM 자동 제출 발생", f"{version['name']}의 마감기한 경과로 {len(pending)}명의 입력이 자동 제출되었습니다.", kind="warning", link="/admin/reviews")
    conn.commit()

def try_confirm_bom_version(conn, bom_version_id):
    submissions = conn.execute("SELECT status FROM bom_submissions WHERE bom_version_id=?", (bom_version_id,)).fetchall()
    if not submissions or any(row["status"] != "approved" for row in submissions):
        return False
    version = get_bom_version(conn, bom_version_id)
    if not version or version["is_confirmed"]:
        return False
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE bom_versions SET is_confirmed=1, confirmed_at=? WHERE id=?", (now, bom_version_id))
    user_ids = [row["id"] for row in conn.execute("SELECT id FROM users").fetchall()]
    message = f"{version['name']} (Rev.{version['version_no']})의 모든 사용자 제출이 승인되어 확정되었습니다."
    conn.executemany(
        "INSERT INTO notifications (user_id, title, message, kind, link, created_at) VALUES (?, ?, ?, 'info', '/bom/', ?)",
        [(user_id, "BOM 확정", message, now) for user_id in user_ids],
    )
    conn.commit()
    return True

def save_latest_bom_upload(conn, file_name, uploaded_by, inserted_count, updated_count):
    conn.execute(
        "INSERT INTO bom_upload_metadata (id, file_name, uploaded_at, uploaded_by, inserted_count, updated_count) "
        "VALUES (1, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET file_name=excluded.file_name, uploaded_at=excluded.uploaded_at, "
        "uploaded_by=excluded.uploaded_by, inserted_count=excluded.inserted_count, updated_count=excluded.updated_count",
        (file_name, datetime.datetime.now().isoformat(timespec="seconds"), uploaded_by, inserted_count, updated_count),
    )
    conn.commit()

def get_latest_bom_upload(conn):
    row = conn.execute("SELECT * FROM bom_upload_metadata WHERE id = 1").fetchone()
    return dict(row) if row else None

def upsert_part(conn, part_no, row_num, level_depth, level_marker, fields, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    design_names = [n for n, _ in DESIGN_FIELDS if n != "part_no"]
    columns = ["bom_id", "part_no", "row_num", "level_depth", "level_marker"] + design_names
    values = [bom_id, part_no, row_num, level_depth, level_marker] + [fields.get(n) for n in design_names]
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("part_no", "row_num"))
    conn.execute(
        f"INSERT INTO bom_parts ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(bom_id, part_no, row_num) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()

def get_part(conn, part_no, row_num, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    row = conn.execute(
        "SELECT * FROM bom_parts WHERE bom_id = ? AND part_no = ? AND row_num = ?", (bom_id, part_no, row_num)
    ).fetchone()
    return dict(row) if row else None

def list_parts(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute("SELECT * FROM bom_parts WHERE bom_id = ? ORDER BY row_num", (bom_id,)).fetchall()
    return [dict(r) for r in rows]

def add_manual_part(conn, bom_id, anchor_part_no, anchor_row_num, position, fields):
    """Insert an administrator-created row immediately before/after an existing BOM row."""
    anchor = get_part(conn, anchor_part_no, anchor_row_num, bom_id)
    if not anchor:
        raise ValueError("기준 BOM 행을 찾을 수 없습니다.")
    part_name = (fields.get("part_name") or "").strip()
    if not part_name:
        raise ValueError("추가 행의 품명은 필수입니다.")
    insert_at = anchor_row_num + (1 if position == "after" else 0)
    # Avoid composite-key collisions while moving rows down.
    conn.execute("PRAGMA foreign_keys = OFF")
    rows = conn.execute("SELECT part_no, row_num FROM bom_parts WHERE bom_id=? AND row_num>=? ORDER BY row_num DESC", (bom_id, insert_at)).fetchall()
    for row in rows:
        conn.execute("UPDATE bom_parts SET row_num=? WHERE bom_id=? AND part_no=? AND row_num=?", (row["row_num"] + 1, bom_id, row["part_no"], row["row_num"]))
        conn.execute("UPDATE bom_purchase_data SET row_num=? WHERE bom_id=? AND part_no=? AND row_num=?", (row["row_num"] + 1, bom_id, row["part_no"], row["row_num"]))
        conn.execute("UPDATE bom_user_purchase_data SET row_num=? WHERE bom_id=? AND part_no=? AND row_num=?", (row["row_num"] + 1, bom_id, row["part_no"], row["row_num"]))
        conn.execute("UPDATE bom_part_assignments SET row_num=? WHERE bom_id=? AND part_no=? AND row_num=?", (row["row_num"] + 1, bom_id, row["part_no"], row["row_num"]))
    part_no = (fields.get("part_no") or f"MANUAL-{insert_at}").strip()
    # A duplicate part number is valid; row number keeps it unique.
    design_names = [n for n, _ in DESIGN_FIELDS if n != "part_no"]
    columns = ["bom_id", "part_no", "row_num", "level_depth", "level_marker"] + design_names + ["manual_row"]
    values = [bom_id, part_no, insert_at, int(fields.get("level_depth") or anchor.get("level_depth") or 0), "MANUAL"] + [fields.get(n) for n in design_names] + [1]
    conn.execute(f"INSERT INTO bom_parts ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))})", values)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return get_part(conn, part_no, insert_at, bom_id)

def list_assigned_parts(conn, bom_id, user_id):
    rows = conn.execute("""
        SELECT p.* FROM bom_parts p
        WHERE p.bom_id = ? AND (
            EXISTS (SELECT 1 FROM bom_part_assignments a
                    WHERE a.bom_id=p.bom_id AND a.user_id=? AND a.part_no=p.part_no AND a.row_num=p.row_num)
            OR EXISTS (SELECT 1 FROM bom_user_purchase_data u
                       WHERE u.bom_id=p.bom_id AND u.user_id=? AND u.part_no=p.part_no AND u.row_num=p.row_num)
            OR EXISTS (SELECT 1 FROM bom_category_members m
                       WHERE m.bom_id=p.bom_id AND m.user_id=? AND m.category=p.category)
        )
        ORDER BY p.row_num
    """, (bom_id, user_id, user_id, user_id)).fetchall()
    return [dict(r) for r in rows]

def list_current_assignments(conn, bom_id, user_id):
    rows = conn.execute("""
        SELECT p.* FROM bom_parts p
        JOIN bom_part_assignments a ON a.bom_id=p.bom_id AND a.part_no=p.part_no AND a.row_num=p.row_num
        WHERE p.bom_id=? AND a.user_id=?
        ORDER BY p.row_num
    """, (bom_id, user_id)).fetchall()
    return [dict(r) for r in rows]

def assigned_part_keys(conn, bom_id, user_id):
    rows = conn.execute("""
        SELECT part_no, row_num FROM bom_part_assignments WHERE bom_id=? AND user_id=?
        UNION
        SELECT part_no, row_num FROM bom_user_purchase_data WHERE bom_id=? AND user_id=?
        UNION
        SELECT p.part_no, p.row_num FROM bom_parts p
        JOIN bom_category_members m ON m.bom_id=p.bom_id AND m.category=p.category
        WHERE p.bom_id=? AND m.user_id=?
    """, (bom_id, user_id, bom_id, user_id, bom_id, user_id)).fetchall()
    return {(row["part_no"], row["row_num"]) for row in rows}

def set_part_assignment(conn, bom_id, user_id, part_no, row_num, assigned):
    if assigned:
        conn.execute(
            "INSERT OR IGNORE INTO bom_part_assignments (bom_id, user_id, part_no, row_num, assigned_at) VALUES (?, ?, ?, ?, ?)",
            (bom_id, user_id, part_no, row_num, datetime.datetime.now().isoformat(timespec="seconds")),
        )
    else:
        conn.execute(
            "DELETE FROM bom_part_assignments WHERE bom_id=? AND user_id=? AND part_no=? AND row_num=?",
            (bom_id, user_id, part_no, row_num),
        )
    conn.commit()

def list_categories(conn, bom_id):
    rows = conn.execute("SELECT DISTINCT category FROM bom_parts WHERE bom_id=? AND category IS NOT NULL AND category != '' ORDER BY category", (bom_id,)).fetchall()
    return [row["category"] for row in rows]

def list_category_members(conn, bom_id):
    rows = conn.execute("""
        SELECT m.category, u.id AS user_id, u.username FROM bom_category_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.bom_id=? ORDER BY m.category, u.username
    """, (bom_id,)).fetchall()
    members = {}
    for row in rows:
        members.setdefault(row["category"], []).append({"id": row["user_id"], "username": row["username"]})
    return members

def get_user_categories(conn, bom_id, user_id):
    rows = conn.execute("SELECT category FROM bom_category_members WHERE bom_id=? AND user_id=?", (bom_id, user_id)).fetchall()
    return {row["category"] for row in rows}

def set_category_membership(conn, bom_id, user_id, category, member):
    if member:
        conn.execute(
            "INSERT OR IGNORE INTO bom_category_members (bom_id, category, user_id, joined_at) VALUES (?, ?, ?, ?)",
            (bom_id, category, user_id, datetime.datetime.now().isoformat(timespec="seconds")),
        )
    else:
        conn.execute("DELETE FROM bom_category_members WHERE bom_id=? AND category=? AND user_id=?", (bom_id, category, user_id))
    conn.commit()

def set_category_members_admin(conn, bom_id, category, user_ids):
    conn.execute("DELETE FROM bom_category_members WHERE bom_id=? AND category=?", (bom_id, category))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT OR IGNORE INTO bom_category_members (bom_id, category, user_id, joined_at) VALUES (?, ?, ?, ?)",
        [(bom_id, category, user_id, now) for user_id in user_ids],
    )
    conn.commit()

def category_owner(conn, bom_id, category):
    """The user whose live input a manager sees/edits for a category on the admin grid."""
    if not category:
        return None
    row = conn.execute("""
        SELECT u.id, u.username FROM bom_category_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.bom_id=? AND m.category=?
        ORDER BY u.username LIMIT 1
    """, (bom_id, category)).fetchone()
    return dict(row) if row else None

def group_for_part(conn, bom_id, part_no, row_num):
    row = conn.execute("""
        SELECT g.*, u.username AS owner_name FROM bom_part_group_members m
        JOIN bom_part_groups g ON g.bom_id=m.bom_id AND g.parent_part_no=m.parent_part_no AND g.parent_row_num=m.parent_row_num
        JOIN users u ON u.id=g.owner_user_id
        WHERE m.bom_id=? AND m.part_no=? AND m.row_num=?
    """, (bom_id, part_no, row_num)).fetchone()
    return dict(row) if row else None

def group_members(conn, bom_id, parent_part_no, parent_row_num):
    rows = conn.execute("""
        SELECT m.part_no, m.row_num, p.part_name FROM bom_part_group_members m
        JOIN bom_parts p ON p.bom_id=m.bom_id AND p.part_no=m.part_no AND p.row_num=m.row_num
        WHERE m.bom_id=? AND m.parent_part_no=? AND m.parent_row_num=?
        ORDER BY m.row_num
    """, (bom_id, parent_part_no, parent_row_num)).fetchall()
    return [dict(r) for r in rows]

def set_part_group(conn, bom_id, parent_part_no, parent_row_num, owner_user_id, enabled, member_keys=None):
    """Create a group. With member_keys (list of (part_no, row_num)), group exactly
    those rows. Otherwise, group the parent through all following descendant rows."""
    existing = group_for_part(conn, bom_id, parent_part_no, parent_row_num)
    if not enabled:
        if existing:
            conn.execute("DELETE FROM bom_part_group_members WHERE bom_id=? AND parent_part_no=? AND parent_row_num=?", (bom_id, existing["parent_part_no"], existing["parent_row_num"]))
            conn.execute("DELETE FROM bom_part_groups WHERE bom_id=? AND parent_part_no=? AND parent_row_num=?", (bom_id, existing["parent_part_no"], existing["parent_row_num"]))
            conn.commit()
        return
    parent = get_part(conn, parent_part_no, parent_row_num, bom_id)
    if not parent:
        raise ValueError("BOM row not found")
    if member_keys is not None:
        descendants = [get_part(conn, part_no, row_num, bom_id) for part_no, row_num in member_keys]
        if any(part is None for part in descendants):
            raise ValueError("BOM row not found")
    else:
        descendants = [parent]
        for part in list_parts(conn, bom_id):
            if part["row_num"] <= parent_row_num:
                continue
            if (part.get("level_depth") or 0) <= (parent.get("level_depth") or 0):
                break
            descendants.append(part)
    if len(descendants) < 2:
        raise ValueError("하위 품목이 있는 상위 품목만 그룹으로 지정할 수 있습니다.")
    conn.execute("INSERT OR REPLACE INTO bom_part_groups (bom_id,parent_part_no,parent_row_num,owner_user_id,created_at) VALUES (?,?,?,?,?)", (bom_id,parent_part_no,parent_row_num,owner_user_id,datetime.datetime.now().isoformat(timespec="seconds")))
    conn.execute("INSERT OR IGNORE INTO bom_part_assignments (bom_id,user_id,part_no,row_num,assigned_at) VALUES (?,?,?,?,?)", (bom_id,owner_user_id,parent_part_no,parent_row_num,datetime.datetime.now().isoformat(timespec="seconds")))
    conn.execute("DELETE FROM bom_part_group_members WHERE bom_id=? AND parent_part_no=? AND parent_row_num=?", (bom_id,parent_part_no,parent_row_num))
    conn.executemany("INSERT OR REPLACE INTO bom_part_group_members (bom_id,parent_part_no,parent_row_num,part_no,row_num) VALUES (?,?,?,?,?)", [(bom_id,parent_part_no,parent_row_num,p["part_no"],p["row_num"]) for p in descendants])
    conn.commit()

def reset_user_bom_work(conn, bom_id, user_id):
    conn.execute("DELETE FROM bom_part_assignments WHERE bom_id=? AND user_id=?", (bom_id, user_id))
    conn.execute("DELETE FROM bom_user_purchase_data WHERE bom_id=? AND user_id=?", (bom_id, user_id))
    conn.execute("""
        DELETE FROM bom_part_group_members WHERE bom_id=? AND (parent_part_no, parent_row_num) IN (
            SELECT parent_part_no, parent_row_num FROM bom_part_groups WHERE bom_id=? AND owner_user_id=?
        )
    """, (bom_id, bom_id, user_id))
    conn.execute("DELETE FROM bom_part_groups WHERE bom_id=? AND owner_user_id=?", (bom_id, user_id))
    conn.commit()

def list_vehicles(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute(
        "SELECT DISTINCT vehicle FROM bom_parts WHERE bom_id = ? AND vehicle IS NOT NULL AND TRIM(vehicle) <> '' ORDER BY vehicle", (bom_id,)
    ).fetchall()
    return [row["vehicle"] for row in rows]

def upsert_purchase(conn, part_no, row_num, country, fields, updated_by=None, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    previous = get_purchase(conn, part_no, row_num, country, bom_id)
    extra_fields = ["sourcing_part_location", "sourcing_assembly_location", "special_fx_rate", "special_fx_reason"]
    columns = ["bom_id", "part_no", "row_num", "country"] + [n for n, _ in PURCHASE_FIELDS] + extra_fields + ["updated_at", "updated_by"]
    values = ([bom_id, part_no, row_num, country] + [fields.get(n) for n, _ in PURCHASE_FIELDS] + [fields.get(n) for n in extra_fields]
              + [datetime.datetime.now().isoformat(timespec="minutes"), updated_by])
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("part_no", "row_num", "country"))
    conn.execute(
        f"INSERT INTO bom_purchase_data ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(bom_id, part_no, row_num, country) DO UPDATE SET {updates}",
        values,
    )
    if updated_by:
        input_fields = ("currency", "unit_price_material", "unit_price_logistics", "tariff_rate", "mold_cost")
        for field_name in input_fields:
            old_value = (previous or {}).get(field_name)
            new_value = fields.get(field_name)
            if (old_value or "") != (new_value or ""):
                conn.execute(
                    "INSERT INTO purchase_history (part_no, row_num, country, field_name, old_value, new_value, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (part_no, row_num, country, field_name, old_value, new_value, updated_by, datetime.datetime.now().isoformat(timespec="seconds")),
                )
    conn.commit()

def list_purchase_history(conn, part_no, row_num, country, limit=10):
    rows = conn.execute(
        "SELECT * FROM purchase_history WHERE part_no=? AND row_num=? AND country=? ORDER BY id DESC LIMIT ?",
        (part_no, row_num, country, limit),
    ).fetchall()
    return [dict(row) for row in rows]

def get_part_by_row_num(conn, row_num, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    row = conn.execute("SELECT * FROM bom_parts WHERE bom_id=? AND row_num=?", (bom_id, row_num)).fetchone()
    return dict(row) if row else None

def get_purchase(conn, part_no, row_num, country, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    row = conn.execute(
        "SELECT * FROM bom_purchase_data WHERE bom_id = ? AND part_no = ? AND row_num = ? AND country = ?",
        (bom_id, part_no, row_num, country),
    ).fetchone()
    return dict(row) if row else None

def get_user_purchase(conn, part_no, row_num, country, user_id, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    row = conn.execute("SELECT * FROM bom_user_purchase_data WHERE bom_id=? AND user_id=? AND part_no=? AND row_num=? AND country=?", (bom_id, user_id, part_no, row_num, country)).fetchone()
    return dict(row) if row else get_purchase(conn, part_no, row_num, country, bom_id)

def upsert_user_purchase(conn, part_no, row_num, country, user_id, fields, updated_by=None, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    extra_fields = ["sourcing_part_location", "sourcing_assembly_location", "special_fx_rate", "special_fx_reason"]
    columns = ["bom_id", "user_id", "part_no", "row_num", "country"] + [n for n, _ in PURCHASE_FIELDS] + extra_fields + ["updated_at", "updated_by"]
    values = [bom_id, user_id, part_no, row_num, country] + [fields.get(n) for n, _ in PURCHASE_FIELDS] + [fields.get(n) for n in extra_fields] + [datetime.datetime.now().isoformat(timespec="minutes"), updated_by]
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("bom_id", "user_id", "part_no", "row_num", "country"))
    conn.execute(f"INSERT INTO bom_user_purchase_data ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))}) ON CONFLICT(bom_id, user_id, part_no, row_num, country) DO UPDATE SET {updates}", values)
    conn.commit()

def list_purchase_for_part(conn, part_no, row_num, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute(
        "SELECT * FROM bom_purchase_data WHERE bom_id = ? AND part_no = ? AND row_num = ?", (bom_id, part_no, row_num)
    ).fetchall()
    return [dict(r) for r in rows]

def list_overseas_countries(conn):
    rows = conn.execute(
        "SELECT country FROM country_master WHERE is_overseas = 1 AND is_active = 1 ORDER BY country"
    ).fetchall()
    return [row["country"] for row in rows]

def list_purchase_countries(conn, include_korea=False, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    sql = "SELECT DISTINCT country FROM bom_purchase_data WHERE bom_id = ? AND country <> ''"
    params = [bom_id]
    if not include_korea:
        sql += " AND country <> ?"
        params.append("한국")
    sql += " ORDER BY country"
    rows = conn.execute(sql, params).fetchall()
    return [row["country"] for row in rows]

def create_user(conn, username, password_hash, role="admin"):
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, role, datetime.datetime.now().isoformat()),
    )
    conn.commit()

def get_user_by_username(conn, username):
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None

def get_user_by_id(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None

def vehicle_country_summary(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute("""
        SELECT p.vehicle as vehicle, pd.country as country,
               SUM(CAST(pd.material_cost AS REAL)) as material_sum,
               SUM(CAST(pd.total_cost AS REAL)) as total_sum
        FROM bom_parts p JOIN bom_purchase_data pd
          ON p.bom_id = pd.bom_id AND p.part_no = pd.part_no AND p.row_num = pd.row_num
        WHERE p.bom_id = ?
        GROUP BY p.vehicle, pd.country
        ORDER BY p.vehicle, pd.country
    """, (bom_id,)).fetchall()
    return [dict(r) for r in rows]

def dashboard_case_matrix(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    countries = list_bom_countries(conn, bom_id)
    rows = []
    for part in list_parts(conn, bom_id):
        values = {}
        for country in countries:
            purchase = get_purchase(conn, part["part_no"], part["row_num"], country, bom_id) or {}
            values[country] = {
                "material": float(purchase.get("material_cost") or 0),
                "logistics": float(purchase.get("logistics_cost") or 0),
                "tariff": float(purchase.get("tariff_cost") or 0),
                "total": float(purchase.get("total_cost") or 0),
            }
        rows.append({"category": part.get("category") or "-", "vehicle": part.get("vehicle") or "-", "part_name": part.get("part_name") or "-", "values": values})
    return countries, rows

def category_summary(conn, country, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute("""
        SELECT p.category as category,
               SUM(CAST(pd.material_cost AS REAL)) as material_sum,
               SUM(CAST(pd.logistics_cost AS REAL)) as logistics_sum,
               SUM(CAST(pd.tariff_cost AS REAL)) as tariff_sum,
               SUM(CAST(pd.total_cost AS REAL)) as total_sum
        FROM bom_parts p JOIN bom_purchase_data pd
          ON p.bom_id = pd.bom_id AND p.part_no = pd.part_no AND p.row_num = pd.row_num
        WHERE p.bom_id = ? AND pd.country = ?
        GROUP BY p.category
        ORDER BY p.category
    """, (bom_id, country)).fetchall()
    return [dict(r) for r in rows]

def dashboard_report(conn, bom_id=None, vehicle=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    countries = list_bom_countries(conn, bom_id)
    overseas = [c for c in countries if c != "한국"]
    sql = """
        SELECT p.category as category, p.sub_category as sub_category, pd.country as country, pd.sourcing_part as sourcing_part,
               CAST(pd.material_cost AS REAL) as material_cost,
               CAST(pd.logistics_cost AS REAL) as logistics_cost,
               CAST(pd.tariff_cost AS REAL) as tariff_cost,
               CAST(pd.total_cost AS REAL) as total_cost
        FROM bom_parts p JOIN bom_purchase_data pd
          ON p.bom_id=pd.bom_id AND p.part_no=pd.part_no AND p.row_num=pd.row_num
        WHERE p.bom_id=?
    """
    params = [bom_id]
    if vehicle:
        sql += " AND p.vehicle=?"
        params.append(vehicle)
    rows = conn.execute(sql, params).fetchall()

    def blank_domestic():
        return {"material": 0.0, "logistics": 0.0, "tariff": 0.0, "total": 0.0}

    def blank_overseas():
        return {"material_lp": 0.0, "material_kd": 0.0, "material_total": 0.0, "logistics": 0.0, "tariff": 0.0, "total": 0.0}

    categories = {}
    category_order = []
    for r in rows:
        cat = r["category"] or "미분류"
        major = major_of(cat)
        row_key = (r["sub_category"] or "미분류") if major == "TTMM" else cat
        if row_key not in categories:
            categories[row_key] = {"major": major, "domestic": blank_domestic(), "overseas": {c: blank_overseas() for c in overseas}}
            category_order.append(row_key)
        bucket = categories[row_key]
        if r["country"] == "한국":
            d = bucket["domestic"]
            d["material"] += r["material_cost"] or 0
            d["logistics"] += r["logistics_cost"] or 0
            d["tariff"] += r["tariff_cost"] or 0
            d["total"] += r["total_cost"] or 0
        elif r["country"] in overseas:
            o = bucket["overseas"][r["country"]]
            material = r["material_cost"] or 0
            if r["sourcing_part"] == "LP":
                o["material_lp"] += material
            elif r["sourcing_part"] == "KD":
                o["material_kd"] += material
            o["material_total"] += material
            o["logistics"] += r["logistics_cost"] or 0
            o["tariff"] += r["tariff_cost"] or 0
            o["total"] += r["total_cost"] or 0

    majors = {}
    major_order = []
    for cat_name in category_order:
        data = categories[cat_name]
        major = data["major"]
        if major not in majors:
            majors[major] = {"major": major, "categories": [], "domestic": blank_domestic(), "overseas": {c: blank_overseas() for c in overseas}}
            major_order.append(major)
        majors[major]["categories"].append({"category": cat_name, "domestic": data["domestic"], "overseas": data["overseas"]})
        for key in ("material", "logistics", "tariff", "total"):
            majors[major]["domestic"][key] += data["domestic"][key]
        for c in overseas:
            for key in ("material_lp", "material_kd", "material_total", "logistics", "tariff", "total"):
                majors[major]["overseas"][c][key] += data["overseas"][c][key]

    grand_domestic = blank_domestic()
    grand_overseas = {c: blank_overseas() for c in overseas}
    for major in majors.values():
        for key in ("material", "logistics", "tariff", "total"):
            grand_domestic[key] += major["domestic"][key]
        for c in overseas:
            for key in ("material_lp", "material_kd", "material_total", "logistics", "tariff", "total"):
                grand_overseas[c][key] += major["overseas"][c][key]

    return {
        "overseas_countries": overseas,
        "majors": [majors[m] for m in major_order],
        "grand_domestic": grand_domestic,
        "grand_overseas": grand_overseas,
    }

def bom_tree(conn, country, vehicle=None, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    sql = """
        SELECT p.part_no as part_no, p.row_num as row_num, p.category as category, p.vehicle as vehicle,
               p.part_name as part_name, p.level_depth as level_depth,
               CAST(pd.material_cost AS REAL) as material_cost,
               CAST(pd.logistics_cost AS REAL) as logistics_cost,
               CAST(pd.tariff_cost AS REAL) as tariff_cost,
               CAST(pd.total_cost AS REAL) as total_cost
        FROM bom_parts p LEFT JOIN bom_purchase_data pd
          ON p.bom_id = pd.bom_id AND p.part_no = pd.part_no AND p.row_num = pd.row_num AND pd.country = ?
    """
    params = [country, bom_id]
    if vehicle:
        sql += " WHERE p.bom_id = ? AND p.vehicle = ?"
        params.append(vehicle)
    else:
        sql += " WHERE p.bom_id = ?"
    sql += " ORDER BY p.row_num"
    rows = conn.execute(sql, params).fetchall()

    categories = {}
    order = []
    for r in rows:
        cat_name = r["category"] or "미분류"
        if cat_name not in categories:
            categories[cat_name] = {
                "name": cat_name, "children": [], "stack": [],
                "material_sum": 0.0, "logistics_sum": 0.0, "tariff_sum": 0.0, "total_sum": 0.0,
            }
            order.append(cat_name)
        bucket = categories[cat_name]

        material_cost = r["material_cost"] or 0.0
        logistics_cost = r["logistics_cost"] or 0.0
        tariff_cost = r["tariff_cost"] or 0.0
        total_cost = r["total_cost"] or 0.0
        node = {
            "part_no": r["part_no"], "part_name": r["part_name"] or "", "vehicle": r["vehicle"] or "",
            "material_cost": material_cost, "logistics_cost": logistics_cost,
            "tariff_cost": tariff_cost, "total_cost": total_cost, "children": [],
        }

        depth = r["level_depth"] if r["level_depth"] is not None else 0
        stack = bucket["stack"]
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            bucket["children"].append(node)
        stack.append((depth, node))

        bucket["material_sum"] += material_cost
        bucket["logistics_sum"] += logistics_cost
        bucket["tariff_sum"] += tariff_cost
        bucket["total_sum"] += total_cost

    result = []
    for cat_name in order:
        bucket = categories[cat_name]
        del bucket["stack"]
        result.append(bucket)
    return result

def summary_tree(conn, country, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    sql = """
        SELECT p.part_no as part_no, p.row_num as row_num, p.category as category, p.sub_category as sub_category,
               p.vehicle as vehicle, p.part_name as part_name, p.level_depth as level_depth,
               CAST(pd.material_cost AS REAL) as material_cost,
               CAST(pd.logistics_cost AS REAL) as logistics_cost,
               CAST(pd.tariff_cost AS REAL) as tariff_cost,
               CAST(pd.total_cost AS REAL) as total_cost
        FROM bom_parts p LEFT JOIN bom_purchase_data pd
          ON p.bom_id = pd.bom_id AND p.part_no = pd.part_no AND p.row_num = pd.row_num AND pd.country = ?
        WHERE p.bom_id = ?
        ORDER BY p.row_num
    """
    rows = conn.execute(sql, [country, bom_id]).fetchall()

    def blank_sums():
        return {"material_sum": 0.0, "logistics_sum": 0.0, "tariff_sum": 0.0, "total_sum": 0.0}

    def add_sums(target, material, logistics, tariff, total):
        target["material_sum"] += material
        target["logistics_sum"] += logistics
        target["tariff_sum"] += tariff
        target["total_sum"] += total

    categories = {}
    order = []
    ttmm_subs = {}
    ttmm_order = []

    for r in rows:
        cat_name = r["category"] or "미분류"
        material_cost = r["material_cost"] or 0.0
        logistics_cost = r["logistics_cost"] or 0.0
        tariff_cost = r["tariff_cost"] or 0.0
        total_cost = r["total_cost"] or 0.0

        if major_of(cat_name) == "TTMM":
            sub_name = r["sub_category"] or "미분류"
            if sub_name not in ttmm_subs:
                ttmm_subs[sub_name] = {"name": sub_name, "children": [], **blank_sums()}
                ttmm_order.append(sub_name)
            bucket = ttmm_subs[sub_name]
            bucket["children"].append({
                "part_no": r["part_no"], "part_name": r["part_name"] or "", "vehicle": r["vehicle"] or "",
                "material_cost": material_cost, "logistics_cost": logistics_cost,
                "tariff_cost": tariff_cost, "total_cost": total_cost, "children": [],
            })
            add_sums(bucket, material_cost, logistics_cost, tariff_cost, total_cost)
            continue

        if cat_name not in categories:
            categories[cat_name] = {"name": cat_name, "children": [], "stack": [], **blank_sums()}
            order.append(cat_name)
        bucket = categories[cat_name]
        node = {
            "part_no": r["part_no"], "part_name": r["part_name"] or "", "vehicle": r["vehicle"] or "",
            "material_cost": material_cost, "logistics_cost": logistics_cost,
            "tariff_cost": tariff_cost, "total_cost": total_cost, "children": [],
        }
        depth = r["level_depth"] if r["level_depth"] is not None else 0
        stack = bucket["stack"]
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            bucket["children"].append(node)
        stack.append((depth, node))
        add_sums(bucket, material_cost, logistics_cost, tariff_cost, total_cost)

    for cat_name in order:
        del categories[cat_name]["stack"]

    majors = {}
    major_order = ["HVAC", "CRFM", "TTMM", "SENSOR", "E-COMP"]

    def get_major(name):
        if name not in majors:
            majors[name] = {"name": name, "groups": {}, "group_order": [], **blank_sums()}
        return majors[name]

    for cat_name in order:
        bucket = categories[cat_name]
        major = get_major(major_of(cat_name))
        group_name = group_of(cat_name)
        if group_name not in major["groups"]:
            major["groups"][group_name] = {
                "name": group_name, "is_wrapper": group_name != cat_name,
                "categories": [], **blank_sums(),
            }
            major["group_order"].append(group_name)
        group = major["groups"][group_name]
        group["categories"].append(bucket)
        for key in ("material_sum", "logistics_sum", "tariff_sum", "total_sum"):
            group[key] += bucket[key]
            major[key] += bucket[key]

    if ttmm_order:
        major = get_major("TTMM")
        for sub_name in ttmm_order:
            sub_bucket = ttmm_subs[sub_name]
            major["groups"][sub_name] = {
                "name": sub_name, "is_wrapper": False,
                "categories": [sub_bucket],
                "material_sum": sub_bucket["material_sum"], "logistics_sum": sub_bucket["logistics_sum"],
                "tariff_sum": sub_bucket["tariff_sum"], "total_sum": sub_bucket["total_sum"],
            }
            major["group_order"].append(sub_name)
            for key in ("material_sum", "logistics_sum", "tariff_sum", "total_sum"):
                major[key] += sub_bucket[key]

    grand = blank_sums()
    for major in majors.values():
        for key in ("material_sum", "logistics_sum", "tariff_sum", "total_sum"):
            grand[key] += major[key]

    ordered_majors = [majors[m] for m in major_order if m in majors]
    ordered_majors += [majors[m] for m in majors if m not in major_order]
    for major in ordered_majors:
        major["groups"] = [major["groups"][g] for g in major["group_order"]]
        del major["group_order"]

    return {"majors": ordered_majors, "grand": grand}

def search_suggestions(conn, bom_id=None):
    bom_id = _resolve_bom_id(conn, bom_id)
    rows = conn.execute("SELECT DISTINCT part_no, part_name, category FROM bom_parts WHERE bom_id = ?", (bom_id,)).fetchall()
    return [dict(r) for r in rows]
