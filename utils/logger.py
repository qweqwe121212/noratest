# -*- coding: utf-8 -*-

"""
تكوين التسجيل المركزي للتطبيق.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
import sys
from typing import Optional

def setup_logging(log_level: int = logging.INFO, 
                 log_file: Optional[str] = "logs/app.log", 
                 max_file_size: int = 5 * 1024 * 1024,  # 5 ميجابايت
                 max_backup_count: int = 3) -> None:
    """
    إعداد التسجيل المركزي للتطبيق.
    
    Args:
        log_level: مستوى التسجيل
        log_file: مسار ملف التسجيل
        max_file_size: الحجم الأقصى لملف التسجيل بالبايت
        max_backup_count: عدد ملفات النسخ الاحتياطية
    """
    # إنشاء مجلد السجلات إذا لم يكن موجوداً
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    # تهيئة المسجل الجذر
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # إزالة أي معالجات موجودة
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # تنسيق السجلات
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, date_format)
    
    # إضافة معالج لعرض السجلات في الطرفية
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # إضافة معالج لكتابة السجلات في ملف (إذا تم تحديد ملف)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_file_size,
            backupCount=max_backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # تعيين مستويات تسجيل مخصصة للمكتبات الخارجية
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("flask").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    # رسالة بدء التسجيل
    logging.info("تم إعداد التسجيل بنجاح")
