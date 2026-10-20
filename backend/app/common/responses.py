from flask import jsonify


def error_response(message: str, status: int):
    return jsonify({"error": message}), status
