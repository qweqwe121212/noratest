"""
معالجات الأخطاء لواجهة برمجة التطبيقات.
"""

import logging
import traceback
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from core.exceptions import BaseChatbotError

logger = logging.getLogger(__name__)

def register_error_handlers(app: Flask) -> None:
    """
    تسجيل معالجات الأخطاء في تطبيق Flask.
    
    Args:
        app: تطبيق Flask
    """
    @app.errorhandler(404)
    def not_found(error):
        """معالج الخطأ 404 - المسار غير موجود"""
        logger.info(f"خطأ 404: {error}")
        return jsonify({
            'message': 'المسار غير موجود',
            'status': 'error'
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        """معالج الخطأ 405 - طريقة الطلب غير مسموح بها"""
        logger.info(f"خطأ 405: {error}")
        return jsonify({
            'message': 'طريقة الطلب غير مسموح بها',
            'status': 'error'
        }), 405
    
    @app.errorhandler(400)
    def bad_request(error):
        """معالج الخطأ 400 - طلب غير صالح"""
        logger.warning(f"خطأ 400: {error}")
        return jsonify({
            'message': 'طلب غير صالح',
            'error': str(error),
            'status': 'error'
        }), 400
    
    @app.errorhandler(500)
    def server_error(error):
        """معالج الخطأ 500 - خطأ في الخادم"""
        error_traceback = traceback.format_exc()
        logger.error(f"خطأ 500: {error}\n{error_traceback}")
        return jsonify({
            'message': 'خطأ في الخادم',
            'status': 'error'
        }), 500
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """معالج لجميع استثناءات HTTP الأخرى"""
        logger.warning(f"استثناء HTTP: {error}")
        return jsonify({
            'message': error.description,
            'status': 'error'
        }), error.code
    
    @app.errorhandler(BaseChatbotError)
    def handle_chatbot_error(error):
        """معالج لاستثناءات الشاتبوت المخصصة"""
        logger.error(f"خطأ في الشاتبوت: {error}")
        return jsonify({
            'message': str(error),
            'status': 'error',
            'error_type': error.__class__.__name__
        }), 500
    
    @app.errorhandler(Exception)
    def handle_generic_exception(error):
        """معالج للاستثناءات العامة"""
        error_traceback = traceback.format_exc()
        logger.error(f"استثناء عام: {error}\n{error_traceback}")
        return jsonify({
            'message': 'حدث خطأ غير متوقع',
            'error': str(error),
            'status': 'error'
        }), 500