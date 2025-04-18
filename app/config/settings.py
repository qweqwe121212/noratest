"""
إعدادات التطبيق المركزية.
"""

import os
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class AppConfig:
    """
    فئة الإعدادات الرئيسية.
    """
    # API المفاتيح
    GOOGLE_API_KEY: str
    GOOGLE_MAPS_API_KEY: str
    
    # إعدادات MongoDB
    MONGO_URI: str
    MONGO_DB: str
    
    # إعدادات النموذج اللغوي
    LLM_MODEL: str
    LLM_TEMPERATURE: float
    LLM_TOP_P: float
    LLM_TOP_K: int
    LLM_MAX_OUTPUT_TOKENS: int
    SAFETY_SETTINGS: List[Dict[str, Any]]
    
    # إعدادات الخادم
    HOST: str
    PORT: int
    DEBUG: bool
    
    # قائمة الأحياء الافتراضية
    DEFAULT_NEIGHBORHOODS: List[str]

def load_config() -> AppConfig:
    """
    تحميل وإرجاع إعدادات التطبيق.
    """
    # قائمة الأحياء الافتراضية
    default_neighborhoods = [
        "النرجس", "الياسمين", "الملقا", "حطين", "الوادي", "الازدهار", 
        "الربيع", "الرائد", "العقيق", "المروج", "النخيل", "الصحافة"
    ]
    
    # إعدادات الأمان
    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE",
        },
    ]
    
    # إنشاء كائن الإعدادات
    config = AppConfig(
        # يمكن استبدال هذا بقراءة من متغيرات البيئة أو ملف .env
        GOOGLE_API_KEY=os.environ.get('GOOGLE_API_KEY', 'AIzaSyBOfTamgcvFq2MPWYUY0u6kp5tlhPU_WJE'),
        GOOGLE_MAPS_API_KEY=os.environ.get('GOOGLE_MAPS_API_KEY', 'AIzaSyBZD1CNPEuMOdC024IUZHmZn1qfsSUqMLE'),
        
        # إعدادات MongoDB
        MONGO_URI=os.environ.get('MONGO_URI', 'mongodb://localhost:27017/'),
        MONGO_DB=os.environ.get('MONGO_DB', 'riyadh_assistant'),
        
        # إعدادات النموذج اللغوي
        LLM_MODEL='gemini-2.0-flash',
        LLM_TEMPERATURE=0.0,
        LLM_TOP_P=1.0,
        LLM_TOP_K=40,
        LLM_MAX_OUTPUT_TOKENS=2048,
        SAFETY_SETTINGS=safety_settings,
        
        # إعدادات الخادم
        HOST=os.environ.get('HOST', '0.0.0.0'),
        PORT=int(os.environ.get('PORT', 5000)),
        DEBUG=os.environ.get('DEBUG', 'True').lower() == 'true',
        
        # قائمة الأحياء الافتراضية
        DEFAULT_NEIGHBORHOODS=default_neighborhoods,
    )
    
    return config