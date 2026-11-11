from flask import jsonify


def api_response(data=None, message="Success", status_code=200, success=True, meta=None):
    """Uniform JSON response wrapper."""
    payload = {
        "success": success,
        "message": message,
        "data": data,
    }
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status_code


def error_response(message="An error occurred", status_code=400, errors=None):
    """Uniform error response wrapper."""
    payload = {
        "success": False,
        "message": message,
        "data": None,
    }
    if errors is not None:
        payload["errors"] = errors
    return jsonify(payload), status_code

