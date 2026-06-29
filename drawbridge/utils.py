import hashlib

from flask import current_app, jsonify


def success_response(msg, payload=None, code=200, silent=False):
    """Standard success envelope: {success, message, payload}."""
    if not silent:
        current_app.logger.info(msg)
    return jsonify({
        'success': True,
        'message': msg,
        'payload': payload
    }), code


def error_response(msg, error, code=400, silent=False):
    """Standard error envelope: {success, message, error}."""
    if not silent:
        current_app.logger.error(msg)
    return jsonify({
        'success': False,
        'message': msg,
        'error': error
    }), code


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    """Check whether filename has one of the allowed extensions."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def hash_file(filepath: str) -> str:
    """Compute the SHA-256 hash of a file on disk, read in chunks.
    """
    algorithm = hashlib.sha256()

    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            algorithm.update(chunk)

    return algorithm.hexdigest()
