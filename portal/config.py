import os
import secrets

DB_PATH = "bom.db"
TEMPLATE_PATH = r"D:\재료비 관리 포탈 PJT\BOM 양식.xlsx"

_SECRET_KEY_PATH = os.path.join(os.path.dirname(__file__), ".secret_key")
if os.path.exists(_SECRET_KEY_PATH):
    with open(_SECRET_KEY_PATH, "r") as f:
        SECRET_KEY = f.read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(_SECRET_KEY_PATH, "w") as f:
        f.write(SECRET_KEY)
