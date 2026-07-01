from flask import Blueprint, request
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash

from drawbridge.db import get_session
from drawbridge.models import utcnow_iso, UnprovisionedDevice
from drawbridge.queries import list_devices
from drawbridge.utils import error_response, success_response

def create_blueprint():
    bp = Blueprint('devices', __name__)

    @bp.route('/', methods=['GET', 'POST'])
    @login_required
    def devices():
        match (request.method):
            case 'GET':
                session = get_session()
                devices = list_devices(session)
                return success_response('All devices', payload=devices)
            case 'POST':
                data = request.get_json(silent=True) or {}
                # TODO: Get data from request and create a new device row
                ...
            case _:
                return error_response('Method not allowed', 'method_not_allowed', code=405, silent=True)
        return success_response('')
    