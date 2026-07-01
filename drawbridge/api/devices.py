from flask import Blueprint, request
from flask_login import current_user, login_required

from drawbridge.db import get_session
from drawbridge.queries import list_devices, add_device, get_device, delete_device
from drawbridge.utils import error_response, success_response


# NOTE: URL prefixes are defined and appended to the following routes when this blueprint is registered in main.py.
#       They should not be defined here

def create_blueprint():
    bp = Blueprint(name='devices', import_name= __name__)

    @bp.route('/', methods=['GET', 'POST'])
    @login_required
    def devices():
        match (request.method):
            case 'GET':
                session = get_session()
                devices = list_devices(session)
                return success_response('All devices', payload=[d.as_dict() for d in devices])
            case 'POST':
                data = request.get_json(silent=True) or {}
                serial = data.get('serial')
                mac = data.get('mac', '')
                description = data.get('description', 'No description')
                if serial is None:
                    return error_response('Request body is missing required parameter serial', 'missing_parameter', code=422)
                session = get_session()
                add_device(session, serial=serial, mac=mac, description=description, added_by=current_user.username)
                session.commit()
                return success_response(f'{serial} added')
            case _:
                return error_response('Method not allowed', 'method_not_allowed', code=405, silent=True)


    @bp.route('/<string:serial>', methods=['GET', 'DELETE'])
    @login_required
    def device_actions(serial: str):
        session = get_session()
        match (request.method):
            case 'GET':
                device = get_device(session, serial)
                if device is None:
                    return error_response(f'{serial} not found', 'device_not_found', code=404)
                return success_response(f'{serial} delivered', payload=device.as_dict())

            case 'DELETE':
                success = delete_device(session, serial)
                if not success:
                    return error_response(f'{serial} not found', 'device_not_found', code=404)
                session.commit()
                return success_response(f'{serial} deleted')

            case _:
                return error_response('Method not allowed', 'method_not_allowed', code=405, silent=True)
            
    return bp