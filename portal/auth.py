from flask_login import UserMixin
import db

class PortalUser(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.role = row["role"]

def load_user_by_id(conn, user_id):
    row = db.get_user_by_id(conn, int(user_id))
    return PortalUser(row) if row else None
