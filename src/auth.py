from functools import wraps
from flask import request, Response
from src.config import ADMIN_USERNAME, ADMIN_PASSWORD


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return Response(
                'Please login with valid credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Admin Access"'})
        return f(*args, **kwargs)
    return decorated
