from flask import Blueprint, request
from flask_login import current_user, login_required

from drawbridge.db import get_session
from drawbridge.queries import get_device
from drawbridge.utils import error_response, success_response

def create_blueprint():
    bp = Blueprint('leases', __name__)

    @bp.route('/lease-event', methods=['GET', 'POST'])
    @login_required
    def leases():
        return error_response('Method not implemented', 'method_not_implemented', code=501)