from flask import Blueprint, render_template
from flask_login import login_required

bid_bom_bp = Blueprint("bid_bom", __name__, url_prefix="/bid-bom")


@bid_bom_bp.route("/")
@login_required
def index():
    return render_template("bid_bom_placeholder.html")
