from flask import Blueprint, request, current_app

from drawbridge.auth import kea_endpoint
from drawbridge.db import get_session
from drawbridge.kea import reservation_add, reservation_del, KeaError
from drawbridge.queries import get_device, get_provisioning_session, create_provisioning_session, delete_provisioning_session, add_log_entry
from drawbridge.utils import error_response, success_response

def create_blueprint():
    bp = Blueprint('leases', __name__)

    @bp.post('/lease-event')
    @kea_endpoint
    def lease_event():
        data = request.get_json()
        if data is None:
            return error_response('Empty request body', 'empty_request_body', code=422)

        serial = data.get('serial')
        if serial is None:
            return error_response('Request body is missing required parameter serial', 'missing_parameter', code=422)

        mac = data.get('mac')
        ip = data.get('ip')

        session = get_session()
        device = get_device(session, serial)

        if device is None:
            return error_response(f'{serial} not found', 'device_not_found', code=404)

        try:
            reservation_add(
                ctrl_url=current_app.config['KEA_CTRL_URL'],
                subnet_id=current_app.config['KEA_SUBNET_ID'],
                mac=mac,
                ip=ip,
            )
        except KeaError as e:
            current_app.logger.error(f'Kea Control Agent error on reservation-add for {serial}: {e}')
            return error_response('Kea Control Agent unreachable', 'kea_error', code=502)

        create_provisioning_session(session, serial=serial, mac=mac, ip=ip)
        session.commit()

        return success_response(f'{serial} approved', payload=device.as_dict())

    @bp.route('/provision-complete', methods=['PUT', 'POST'])
    def provision_complete():
        # force=True: IOS XE `copy` sends PUT without Content-Type: application/json
        data = request.get_json(force=True, silent=True)
        if data is None:
            return error_response('Empty request body', 'empty_request_body', code=422)

        serial = data.get('serial')
        if serial is None:
            return error_response('Request body is missing required parameter serial', 'missing_parameter', code=422)

        event = data.get('event', 'provision_complete')
        image = data.get('image')
        config_file = data.get('config_file')
        detail = data.get('detail')

        session = get_session()
        active = get_provisioning_session(session, serial)

        if active is None:
            return error_response(f'{serial} is not in active provisioning', 'device_not_active', code=404)

        if active.mac is not None:
            try:
                reservation_del(
                    ctrl_url=current_app.config['KEA_CTRL_URL'],
                    subnet_id=current_app.config['KEA_SUBNET_ID'],
                    mac=active.mac,
                )
            except KeaError as e:
                current_app.logger.error(f'Kea Control Agent error on reservation-del for {serial}: {e}')
                return error_response('Kea Control Agent unreachable', 'kea_error', code=502)
        else:
            current_app.logger.warning(f'No MAC on record for {serial}, skipping reservation-del')

        add_log_entry(
            session,
            serial=serial,
            event=event,
            ip=active.ip,
            image=image,
            config_file=config_file,
            detail=detail,
        )
        delete_provisioning_session(session, serial)
        session.commit()

        return success_response(f'{serial} provisioning recorded')

    return bp
