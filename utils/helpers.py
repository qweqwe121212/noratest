# -*- coding: utf-8 -*-

"""
دوال مساعدة متنوعة للاستخدام في أجزاء مختلفة من التطبيق.
"""

import os
import re
import json
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Tuple

def clean_text(text: str) -> str:
    """
    تنظيف النص من العلامات الزائدة وتوحيد المسافات.
    
    Args:
        text: النص المراد تنظيفه
        
    Returns:
        str: النص المنظف
    """
    if not text or not isinstance(text, str):
        return ""
    
    # إزالة مسافات وعلامات الترقيم الزائدة
    cleaned = re.sub(r'\s+', ' ', text)
    cleaned = cleaned.strip()
    
    return cleaned

def normalize_arabic_text(text: str) -> str:
    """
    توحيد النص العربي (مثل توحيد الهمزات والألف).
    
    Args:
        text: النص العربي المراد توحيده
        
    Returns:
        str: النص الموحد
    """
    if not text or not isinstance(text, str):
        return ""
    
    # توحيد أشكال الهمزات والألف
    normalized = text
    normalized = re.sub(r'[إأآا]', 'ا', normalized)
    normalized = re.sub(r'[ىی]', 'ي', normalized)
    normalized = re.sub(r'ؤ', 'و', normalized)
    normalized = re.sub(r'ئ', 'ي', normalized)
    normalized = re.sub(r'ة', 'ه', normalized)
    
    return normalized

def format_price(price: Union[int, float, str]) -> str:
    """
    تنسيق السعر بشكل مناسب.
    
    Args:
        price: السعر كرقم أو نص
        
    Returns:
        str: السعر المنسق
    """
    try:
        # محاولة تحويل القيمة إلى رقم
        if isinstance(price, (int, float)):
            numeric_price = price
        else:
            # محاولة استخراج الرقم من النص
            match = re.search(r'(\d+(?:\.\d+)?)', str(price))
            if match:
                numeric_price = float(match.group(1))
            else:
                return str(price)
        
        # تنسيق الرقم
        if numeric_price == int(numeric_price):
            # إذا كان رقماً صحيحاً
            return "{:,}".format(int(numeric_price))
        else:
            # إذا كان رقماً عشرياً
            return "{:,.2f}".format(numeric_price)
            
    except (ValueError, TypeError):
        # إذا فشل التحويل، إرجاع القيمة كما هي
        return str(price)

def extract_numeric_value(value: Any) -> Optional[float]:
    """
    استخراج قيمة رقمية من قيمة متنوعة.
    
    Args:
        value: القيمة المراد استخراج الرقم منها
        
    Returns:
        Optional[float]: القيمة الرقمية أو None إذا فشل الاستخراج
    """
    if value is None:
        return None
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        # محاولة استخراج رقم من النص
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                return None
    
    return None

def find_similar_items(query: str, items: List[str], 
                     min_similarity: float = 0.7) -> List[Tuple[str, float]]:
    """
    البحث عن العناصر المشابهة للاستعلام.
    
    Args:
        query: نص الاستعلام
        items: قائمة العناصر للبحث فيها
        min_similarity: الحد الأدنى للتشابه (0.0 إلى 1.0)
        
    Returns:
        List[Tuple[str, float]]: قائمة بالعناصر المشابهة ودرجة التشابه
    """
    from difflib import SequenceMatcher
    
    if not query or not items:
        return []
    
    # تنظيف وتوحيد الاستعلام
    clean_query = normalize_arabic_text(clean_text(query.lower()))
    
    # البحث عن التشابه
    similar_items = []
    for item in items:
        if not item or not isinstance(item, str):
            continue
            
        # تنظيف وتوحيد العنصر
        clean_item = normalize_arabic_text(clean_text(item.lower()))
        
        # حساب درجة التشابه
        similarity = SequenceMatcher(None, clean_query, clean_item).ratio()
        
        # إضافة العناصر التي تتجاوز الحد الأدنى للتشابه
        if similarity >= min_similarity:
            similar_items.append((item, similarity))
    
    # ترتيب العناصر حسب درجة التشابه (من الأعلى إلى الأقل)
    return sorted(similar_items, key=lambda x: x[1], reverse=True)

def load_json_safe(file_path: str) -> Dict:
    """
    تحميل ملف JSON بأمان مع معالجة الأخطاء.
    
    Args:
        file_path: مسار ملف JSON
        
    Returns:
        Dict: البيانات المحملة أو قاموس فارغ في حالة الخطأ
    """
    try:
        if not os.path.exists(file_path):
            return {}
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except json.JSONDecodeError:
        # محاولة إصلاح ملف JSON غير صالح
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # إزالة التعليقات وإصلاح المشكلات الشائعة
                content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
                content = content.replace("'", "\"")
                return json.loads(content)
        except Exception:
            return {}
            
    except Exception:
        return {}

def save_json_safe(data: Dict, file_path: str) -> bool:
    """
    حفظ البيانات في ملف JSON بأمان.
    
    Args:
        data: البيانات المراد حفظها
        file_path: مسار ملف JSON
        
    Returns:
        bool: True إذا تم الحفظ بنجاح، وإلا False
    """
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return True
        
    except Exception:
        return False

def df_to_records(df: pd.DataFrame) -> List[Dict]:
    """
    تحويل DataFrame إلى قائمة من القواميس للاستخدام في API.
    
    Args:
        df: DataFrame المراد تحويله
        
    Returns:
        List[Dict]: قائمة من القواميس
    """
    if df is None or df.empty:
        return []
        
    return df.replace({pd.NA: None}).to_dict(orient='records')
