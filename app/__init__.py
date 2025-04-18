"""
حزمة التطبيق الرئيسية.
"""

from flask import Flask
from flask_cors import CORS
import logging
from pymongo import MongoClient 

from app.config.settings import load_config
from app.api.routes import register_routes
from app.api.error_handlers import register_error_handlers
from core.chatbot import NeighborhoodChatbot

logger = logging.getLogger(__name__)

def create_app():
    """
    إنشاء وتكوين تطبيق Flask.
    """
    # إنشاء تطبيق Flask
    app = Flask(__name__)
    
    # تمكين CORS
    CORS(app)
    
    # تحميل الإعدادات
    config = load_config()
    
    # تكوين التطبيق
    app.config.from_object(config)


    try:
        client = MongoClient("mongodb://localhost:27017/")
        mongo_db = client["riyadh_assistant"]  # ← اسم القاعدة
        app.config['MONGO_DB'] = mongo_db
        logger.info("✅ تم الاتصال بقاعدة بيانات MongoDB")
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بـ MongoDB: {str(e)}")
        raise


    

    # تهيئة الشاتبوت
    try:
        chatbot = NeighborhoodChatbot(config, mongo_db)  # ✅ نمرر القاعدة
        app.config['CHATBOT'] = chatbot
        logger.info("تم تهيئة الشاتبوت بنجاح")
    except Exception as e:
        logger.error(f"خطأ في تهيئة الشاتبوت: {str(e)}")
        raise
    
    # تسجيل المسارات ومعالجات الأخطاء
    register_routes(app)
    register_error_handlers(app)
    
    return app