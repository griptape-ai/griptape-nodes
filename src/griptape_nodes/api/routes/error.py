from flask import Blueprint, Response, jsonify
from werkzeug.exceptions import NotFound

error_bp = Blueprint("errors", __name__)


@error_bp.app_errorhandler(Exception)
def handle_generic_exception(err) -> Response:
    return jsonify({"message": f"Unknown error: {err}"}, 500)


@error_bp.app_errorhandler(NotFound)
def handle_not_found(_) -> Response:
    return jsonify({"message": "This resource doesn't exist"}, 404)
