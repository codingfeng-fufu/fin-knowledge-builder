"""
API路由模块
"""

from flask import Blueprint

discovery_bp = Blueprint('discovery', __name__)

from . import discovery  # noqa: E402, F401
