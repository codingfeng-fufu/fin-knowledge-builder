"""
Muti Agent Exploration Backend - Flask应用工厂
"""

import os
from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应用工厂函数。"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    logger = setup_logger('muti_agent_exploration')

    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("Muti Agent Exploration Backend 启动中...")
        logger.info("=" * 50)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.before_request
    def log_request():
        request_logger = get_logger('muti_agent_exploration.request')
        request_logger.debug("请求: %s %s", request.method, request.path)
        if request.content_type and 'json' in request.content_type:
            request_logger.debug("请求体: %s", request.get_json(silent=True))

    @app.after_request
    def log_response(response):
        response_logger = get_logger('muti_agent_exploration.request')
        response_logger.debug("响应: %s", response.status_code)
        return response

    from .api import discovery_bp

    app.register_blueprint(discovery_bp, url_prefix='/api/discovery')

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'Muti Agent Exploration Backend'}

    if should_log_startup:
        logger.info("Muti Agent Exploration Backend 启动完成")

    return app
