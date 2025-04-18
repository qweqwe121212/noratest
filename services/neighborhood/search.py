# -*- coding: utf-8 -*-

"""
خدمة البحث عن المرافق والمنشآت في الأحياء.
"""

import logging
import re
import pandas as pd
from typing import Dict, List, Optional, Union, Any

from services.data.data_loader import DataLoader
from core.exceptions import FacilitySearchError

logger = logging.getLogger(__name__)

class FacilitySearchService:
    """
    خدمة للبحث عن المرافق والمنشآت في الأحياء المختلفة.
    """
    def __init__(self, data_loader: DataLoader):
        """
        تهيئة خدمة البحث.
        
        Args:
            data_loader: محمل البيانات
        """
        self.data_loader = data_loader
        
        # ربط ملفات CSV بأسمائها للمساعدة في عمليات البحث
        self.csv_mappings = {
            "المدارس.csv": data_loader.get_schools_data(),
            "حدائق.csv": data_loader.get_parks_data(),
            "سوبرماركت.csv": data_loader.get_supermarkets_data(),
            "مستشفى.csv": data_loader.get_hospitals_data(),
            "مول.csv": data_loader.get_malls_data(),
            "Neighborhoods.csv": data_loader.get_neighborhoods_data()
        }
        
        # تحديد أعمدة البحث والعرض لكل نوع من ملفات CSV
        self.search_columns = {
            "المدارس.csv": {
                "search": ["اسم_المدرسة", "name", "school_name", "المدرسة", "الاسم"],
                "display": ["اسم_المدرسة", "العنوان", "التصنيف", "المرحلة_الدراسية", "نوع_المدرسة", "الاسم"],
                "name_field": "الاسم",
                "type_name": "مدرسة"
            },
            "حدائق.csv": {
                "search": ["اسم_الحديقة", "name", "park_name", "الحديقة", "الاسم"],
                "display": ["اسم_الحديقة", "العنوان", "المساحة", "المرافق", "الاسم"],
                "name_field": "الاسم",
                "type_name": "حديقة"
            },
            "سوبرماركت.csv": {
                "search": ["اسم_السوبرماركت", "name", "supermarket_name", "السوبرماركت", "الاسم"],
                "display": ["اسم_السوبرماركت", "العنوان", "ساعات_العمل", "التصنيف", "الاسم"],
                "name_field": "الاسم",
                "type_name": "سوبرماركت"
            },
            "مستشفى.csv": {
                "search": ["اسم_المستشفى", "name", "hospital_name", "المستشفى", "الاسم"],
                "display": ["اسم_المستشفى", "العنوان", "التخصص", "التصنيف", "الاسم"],
                "name_field": "الاسم",
                "type_name": "مستشفى"
            },
            "مول.csv": {
                "search": ["اسم_المول", "name", "mall_name", "المول", "الاسم"],
                "display": ["اسم_المول", "العنوان", "عدد_المتاجر", "المطاعم", "الترفيه", "الاسم"],
                "name_field": "الاسم",
                "type_name": "مول تجاري"
            }
        }
        
        # تحديد قائمة الكلمات المفتاحية للمرافق
        self.facility_keywords = {
            "مدرسة": ["مدرسة", "مدارس", "تعليم", "دراسة", "مؤسسة تعليمية", "روضة", "ابتدائي", "متوسط", "ثانوي"],
            "مستشفى": ["مستشفى", "مستشفيات", "صحة", "طبية", "علاج", "مركز صحي", "عيادة", "مستوصف", "مركز طبي"],
            "حديقة": ["حديقة", "حدائق", "منتزه", "متنزه", "ملعب", "ساحة", "مساحة خضراء"],
            "سوبرماركت": ["سوبرماركت", "محل", "بقالة", "تسوق", "تموينات", "دكان", "متجر", "سوق", "ماركت"],
            "مول": ["مول", "مولات", "مركز تسوق", "تسوق", "مجمع تجاري", "مركز تجاري", "سوق"]
        }
        
        # الكلمات المفتاحية العامة للمرافق
        self.general_facility_keywords = [
            "مرفق", "مرافق", "خدمات", "منشآت", "قريب", "قريبة", "المتوفرة"
        ]
        
        logger.info("تم تهيئة خدمة البحث عن المرافق")
    
    def is_facility_query(self, message: str) -> bool:
        """
        تحديد ما إذا كانت الرسالة تتعلق بالمرافق بشكل عام.
        
        Args:
            message: رسالة المستخدم
            
        Returns:
            bool: True إذا كانت الرسالة تتعلق بالمرافق، وإلا False
        """
        if not message:
            return False
        
        message_lower = message.lower()
        
        # التحقق من الكلمات المفتاحية العامة للمرافق
        if any(keyword in message_lower for keyword in self.general_facility_keywords):
            logger.info(f"تم تحديد الاستعلام كاستعلام عام عن المرافق: {message}")
            return True
        
        # التحقق من الكلمات المفتاحية لكل نوع من المرافق
        for facility_type, keywords in self.facility_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                logger.info(f"تم تحديد الاستعلام كاستعلام عن {facility_type}: {message}")
                return True
        
        return False
    
    def search_entity(self, csv_file: str, search_query: str) -> str:
        """
        البحث عن كيان محدد في ملف CSV.
        
        Args:
            csv_file: اسم ملف CSV للبحث فيه
            search_query: عبارة البحث
            
        Returns:
            str: نتيجة البحث منسقة
        """
        try:
            # التحقق من محتوى البحث إذا كان طلب توصية بحي
            if ("دلني على حي" in search_query or "اقترح لي حي" in search_query or "أقترح لي حي" in search_query) and (
                "فيه مدارس" in search_query or "به مدارس" in search_query or "فيها مدارس" in search_query or 
                "يوجد فيه مدارس" in search_query or "توجد فيه مدارس" in search_query or
                "قريب من" in search_query or "قريبة من" in search_query):
                
                # هذه حالة طلب توصية بحي وليس بحث عن مدارس
                logger.info(f"تم تحديد طلب توصية حي بدلاً من البحث عن المرافق: {search_query}")
                return "طلب_توصية_حي"
            
            # التحقق من وجود ملف CSV
            if csv_file not in self.csv_mappings:
                logger.error(f"ملف CSV غير موجود: {csv_file}")
                return f"عذراً، ملف البيانات '{csv_file}' غير متوفر."
            
            # الحصول على DataFrame
            df = self.csv_mappings[csv_file]
            
            # التحقق من DataFrame
            if df.empty:
                logger.warning(f"ملف CSV فارغ: {csv_file}")
                return f"عذراً، لا توجد بيانات في ملف '{csv_file}'."
            
            # تنظيف وتقصير عبارة البحث
            # إزالة الأسئلة والعبارات المقدمة
            clean_query = self._clean_search_query(search_query)
            logger.info(f"عبارة البحث الأصلية: '{search_query}' - بعد التنظيف: '{clean_query}'")
            
            # الحصول على إعدادات البحث للملف
            if csv_file not in self.search_columns:
                logger.warning(f"إعدادات البحث غير محددة لـ {csv_file}")
                # استخدام جميع الأعمدة في حالة عدم تحديد إعدادات
                search_cols = df.columns.tolist()
                display_cols = df.columns.tolist()
                name_field = df.columns[0] if len(df.columns) > 0 else None
                type_name = "عنصر"
            else:
                # استخدام الإعدادات المحددة
                settings = self.search_columns[csv_file]
                search_cols = settings["search"]
                display_cols = settings["display"]
                name_field = settings["name_field"]
                type_name = settings["type_name"]
            
            # بناء قائمة نتائج للعناصر المطابقة
            results = []
            
            # محاولة البحث باستخدام اسم الملف المرفق كنوع (مثل البحث عن مدرسة في ملف المدارس)
            if len(clean_query) < 3 and csv_file:
                facility_type_keywords = {
                    "المدارس.csv": ["مدرسة", "مدارس"],
                    "مستشفى.csv": ["مستشفى", "مستشفيات", "مركز طبي"],
                    "حدائق.csv": ["حديقة", "حدائق", "منتزه"],
                    "سوبرماركت.csv": ["سوبرماركت", "هايبر", "ماركت", "متجر"],
                    "مول.csv": ["مول", "مولات", "مركز تسوق"]
                }
                
                if csv_file in facility_type_keywords:
                    clean_query = facility_type_keywords[csv_file][0]
            
            # تجربة البحث المباشر في اسم المرفق أولاً
            if name_field in df.columns:
                # البحث باستخدام التطابق الكامل
                exact_matches = df[df[name_field].astype(str).str.contains(clean_query, case=False, na=False)]
                
                if not exact_matches.empty:
                    for _, row in exact_matches.iterrows():
                        result = self._format_search_result(row, display_cols, name_field)
                        if result not in results:
                            results.append(result)
                
                # إضافة بحث إضافي باستخدام النص العربي الموحد
                if len(results) < 3:  # إذا لم يتم العثور على الكثير من النتائج
                    normalized_query = self._normalize_arabic_text(clean_query)
                    normalized_matches = df[
                        df[name_field].apply(
                            lambda x: self._normalize_arabic_text(str(x)).find(normalized_query) >= 0 
                            if pd.notna(x) else False
                        )
                    ]
                    
                    for _, row in normalized_matches.iterrows():
                        result = self._format_search_result(row, display_cols, name_field)
                        if result not in results:
                            results.append(result)
            
            # إذا لم يتم العثور على نتائج باستخدام اسم المرفق، ابحث في جميع الأعمدة المحددة
            if not results:
                for col in search_cols:
                    if col in df.columns:
                        # البحث عن التطابق الجزئي
                        partial_matches = df[df[col].astype(str).str.contains(clean_query, case=False, na=False)]
                        if not partial_matches.empty:
                            for _, row in partial_matches.iterrows():
                                result = self._format_search_result(row, display_cols, name_field)
                                if result not in results:
                                    results.append(result)
                
                # البحث باستخدام النص العربي الموحد
                if not results:
                    normalized_query = self._normalize_arabic_text(clean_query)
                    for col in search_cols:
                        if col in df.columns:
                            normalized_matches = df[
                                df[col].apply(
                                    lambda x: self._normalize_arabic_text(str(x)).find(normalized_query) >= 0 
                                    if pd.notna(x) else False
                                )
                            ]
                            
                            for _, row in normalized_matches.iterrows():
                                result = self._format_search_result(row, display_cols, name_field)
                                if result not in results:
                                    results.append(result)
            
            # تجربة البحث باستخدام كلمات مفتاحية مستخرجة من الاستعلام
            if not results and len(clean_query.split()) > 1:
                keywords = clean_query.split()
                for keyword in keywords:
                    if len(keyword) >= 3:  # تجاهل الكلمات القصيرة جداً
                        for col in search_cols:
                            if col in df.columns:
                                keyword_matches = df[df[col].astype(str).str.contains(keyword, case=False, na=False)]
                                if not keyword_matches.empty:
                                    for _, row in keyword_matches.iterrows():
                                        result = self._format_search_result(row, display_cols, name_field)
                                        if result not in results:
                                            results.append(result)
            
            # البحث عن المرافق في حي محدد إذا كانت عبارة البحث تحتوي على اسم حي
            if not results and "حي" in clean_query:
                for neighborhood in self.available_neighborhoods:
                    clean_neighborhood = neighborhood.replace("حي ", "").strip()
                    if clean_neighborhood in clean_query:
                        neighborhood_matches = df[df["الحي"].astype(str).str.contains(clean_neighborhood, case=False, na=False)]
                        if not neighborhood_matches.empty:
                            for _, row in neighborhood_matches.iterrows():
                                result = self._format_search_result(row, display_cols, name_field)
                                if result not in results:
                                    results.append(result)
            
            # التحقق من النتائج
            if not results:
                # تنميق نوع المرفق لعرض رسالة أفضل
                facility_type_display = {
                    "المدارس.csv": "مدرسة",
                    "مستشفى.csv": "مستشفى",
                    "حدائق.csv": "حديقة",
                    "سوبرماركت.csv": "سوبرماركت أو متجر",
                    "مول.csv": "مول أو مركز تسوق"
                }
                
                display_type = facility_type_display.get(csv_file, type_name)
                
                # تحقق مما إذا كان الاستعلام سؤالاً
                is_question = any(q in search_query for q in ["اين", "أين", "كيف", "ما", "هل"])
                
                if is_question:
                    return f"عذراً، لم أتمكن من العثور على {display_type} باسم '{clean_query}' في قاعدة البيانات."
                else:
                    return f"لم يتم العثور على {display_type} باسم '{clean_query}' في قاعدة البيانات."
            
            # تنسيق النتائج النهائية
            if len(results) == 1:
                # إذا كانت هناك نتيجة واحدة فقط
                if any(q in search_query for q in ["اين", "أين", "كيف", "ما", "هل"]):
                    return f"وجدت {type_name}: {results[0]}"
                else:
                    return f"{results[0]}"
            else:
                # إذا كان هناك عدة نتائج - الحد من عدد النتائج للحفاظ على قابلية القراءة
                max_results = 5
                truncated = len(results) > max_results
                
                if truncated:
                    results = results[:max_results]
                
                result_text = f"وجدت {len(results)} من {type_name} تطابق بحثك"
                if truncated:
                    result_text += f" (عرض أول {max_results} نتائج من أصل {len(results)})"
                result_text += ":\n"
                
                for i, result in enumerate(results, 1):
                    result_text += f"{i}. {result}\n"
                    
                if truncated:
                    result_text += "\nلعرض المزيد من النتائج، يرجى تحديد عبارة بحث أكثر دقة."
                    
                return result_text
                
        except Exception as e:
            logger.error(f"خطأ في البحث في ملف CSV {csv_file}: {str(e)}")
            raise FacilitySearchError(f"فشل البحث في ملف {csv_file}: {str(e)}")

    def _clean_search_query(self, query: str) -> str:
        """
        تنظيف عبارة البحث من الأسئلة والعبارات المقدمة.
        
        Args:
            query: عبارة البحث الأصلية
        
        Returns:
            str: عبارة البحث المنظفة
        """
        # إزالة الأسئلة الشائعة
        question_patterns = [
            r'^اين (?:توجد|يوجد|تقع|يقع|هي|هو) ',
            r'^أين (?:توجد|يوجد|تقع|يقع|هي|هو) ',
            r'^ما (?:هي|هو) ',
            r'^كيف (?:اجد|أجد) ',
            r'^(?:اين|أين) (?:مكان|موقع) ',
            r'^(?:دلني|دلوني|ارشدني|أرشدني) (?:على|عن|الى|إلى) ',
            r'^(?:ابحث|أبحث) عن '
        ]
        
        cleaned_query = query
        for pattern in question_patterns:
            cleaned_query = re.sub(pattern, '', cleaned_query)
        
        # إزالة علامات الاستفهام والنقاط
        cleaned_query = cleaned_query.replace('؟', '').replace('?', '').replace('.', '').strip()
        
        # إزالة أي عبارات إضافية في نهاية الجملة
        end_phrases = [
            r' في (?:الرياض|جدة|مكة|المدينة|الدمام).*$',
            r' بالقرب من.*$',
            r' على طريق.*$',
            r' عند.*$'
        ]
        
        for pattern in end_phrases:
            cleaned_query = re.sub(pattern, '', cleaned_query)
        
        # تحقق من طول النتيجة
        if len(cleaned_query) < 2:
            return query  # إرجاع الاستعلام الأصلي إذا كانت النتيجة قصيرة جداً
        
        return cleaned_query.strip()    

    def search_all_facilities(self, search_query: str) -> str:
        """
        البحث عن مرفق في جميع أنواع المرافق.
        
        Args:
            search_query: عبارة البحث
            
        Returns:
            str: نتائج البحث المنسقة
        """
        try:
            if not search_query:
                return "يرجى تحديد عبارة بحث."
            
            results = []
            
            # البحث في جميع ملفات CSV للمرافق
            for csv_file in ["المدارس.csv", "مستشفى.csv", "حدائق.csv", "سوبرماركت.csv", "مول.csv"]:
                result = self.search_entity(csv_file, search_query)
                
                # إضافة النتيجة فقط إذا كانت تحتوي على نتائج
                if "لم يتم العثور" not in result and "عذراً" not in result:
                    results.append(result)
            
            if results:
                return "\n\n".join(results)
            else:
                return f"لم يتم العثور على '{search_query}' في أي من المرافق."
                
        except Exception as e:
            logger.error(f"خطأ في البحث في جميع المرافق: {str(e)}")
            return f"حدث خطأ أثناء البحث عن '{search_query}'."
    
    def _format_search_result(self, row: pd.Series, display_cols: List[str], name_field: Optional[str]) -> str:
        """
        تنسيق صف بيانات كنتيجة بحث قابلة للقراءة.
        """
        # نفس الكود السابق دون تغيير
        result_parts = []
        
        # إضافة الاسم أولاً إذا كان محدداً
        if name_field and name_field in row and pd.notna(row[name_field]):
            result_parts.append(f"{row[name_field]}")
        
        # إضافة باقي المعلومات
        for col in display_cols:
            # تخطي حقل الاسم إذا تمت إضافته بالفعل
            if col == name_field:
                continue
                
            # إضافة القيم غير الفارغة فقط
            if col in row and pd.notna(row[col]) and row[col]:
                # تحديد اسم العمود المعروض
                display_name = col.replace("_", " ").replace("اسم", "").strip()
                
                # التحقق من نوع القيمة وتنسيقها
                value = row[col]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    # تنسيق الأرقام
                    if isinstance(value, float) and value.is_integer():
                        formatted_value = "{:,}".format(int(value))
                    else:
                        formatted_value = "{:.2f}".format(value) if isinstance(value, float) else "{:,}".format(value)
                    result_parts.append(f"{display_name}: {formatted_value}")
                else:
                    # تنسيق النصوص
                    result_parts.append(f"{display_name}: {value}")
        
        # دمج جميع الأجزاء في نص واحد
        if result_parts:
            return " | ".join(result_parts)
        else:
            return "معلومات غير متوفرة"
    
    def find_facilities_in_neighborhood(self, neighborhood_name: str, facility_type: Optional[str] = None) -> str:
        """
        البحث عن المرافق المتاحة في حي معين.
        
        Args:
            neighborhood_name: اسم الحي
            facility_type: نوع المرفق (اختياري)
            
        Returns:
            str: نص منسق يحتوي على المرافق المتاحة
        """
        try:
            # تنظيف اسم الحي
            clean_name = neighborhood_name.replace("حي ", "").strip()
            
            # تحديد ملف CSV المناسب حسب نوع المرفق
            if facility_type == "مدرسة":
                csv_file = "المدارس.csv"
                location_column = "الحي"
                result_title = f"المدارس في {neighborhood_name}"
            elif facility_type == "مستشفى":
                csv_file = "مستشفى.csv"
                location_column = "الحي"
                result_title = f"المستشفيات والمراكز الطبية في {neighborhood_name}"
            elif facility_type == "حديقة":
                csv_file = "حدائق.csv"
                location_column = "الحي"
                result_title = f"الحدائق والمتنزهات في {neighborhood_name}"
            elif facility_type == "سوبرماركت":
                csv_file = "سوبرماركت.csv"
                location_column = "الحي"
                result_title = f"محلات السوبرماركت في {neighborhood_name}"
            elif facility_type == "مول":
                csv_file = "مول.csv"
                location_column = "الحي"
                result_title = f"المولات ومراكز التسوق في {neighborhood_name}"
            elif facility_type is None:
                # إذا لم يتم تحديد نوع المرفق، قم بتجميع كل المرافق
                all_facilities = []
                for facility in ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]:
                    facility_info = self.find_facilities_in_neighborhood(neighborhood_name, facility)
                    if facility_info and "لم يتم العثور" not in facility_info:
                        all_facilities.append(facility_info)
                
                if all_facilities:
                    return f"المرافق المتاحة في {neighborhood_name}:\n\n" + "\n\n".join(all_facilities)
                else:
                    return f"لم يتم العثور على مرافق متاحة في {neighborhood_name} في قاعدة البيانات."
            else:
                return f"نوع المرفق '{facility_type}' غير معروف."
            
            # التحقق من وجود ملف CSV
            if csv_file not in self.csv_mappings:
                logger.error(f"ملف CSV غير موجود: {csv_file}")
                return f"عذراً، بيانات {facility_type} غير متوفرة."
            
            # الحصول على DataFrame
            df = self.csv_mappings[csv_file]
            
            # التحقق من DataFrame وعمود الموقع
            if df.empty:
                logger.warning(f"ملف CSV فارغ: {csv_file}")
                return f"عذراً، لا توجد بيانات {facility_type}."
            
            # تحديد عمود الموقع الصحيح
            neighborhood_columns = ["الحي", "اسم_الحي", "neighborhood", "المنطقة", "location", "الحيّ"]
            found_column = None
            
            for col in neighborhood_columns:
                if col in df.columns:
                    found_column = col
                    break
            
            if not found_column:
                logger.warning(f"لم يتم العثور على عمود الحي في {csv_file}")
                return f"عذراً، لا يمكن تحديد موقع {facility_type} بالحي."
            
            # البحث عن المرافق في الحي - تحسين البحث بمطابقة جزئية
            neighborhood_facilities = df[
                df[found_column].str.contains(clean_name, case=False, na=False) |
                df[found_column].str.contains(f"حي {clean_name}", case=False, na=False)
            ]
            
            # إذا لم يتم العثور على نتائج، حاول البحث أيضاً باستخدام أحرف مشابهة
            # (مثل الألف مع همزة، التاء المربوطة والهاء)
            if neighborhood_facilities.empty:
                normalized_name = self._normalize_arabic_text(clean_name)
                neighborhood_facilities = df[
                    df[found_column].apply(
                        lambda x: self._normalize_arabic_text(str(x)).find(normalized_name) >= 0 
                        if pd.notna(x) else False
                    )
                ]
            
            # التحقق من النتائج
            if neighborhood_facilities.empty:
                return f"لم يتم العثور على {facility_type} في {neighborhood_name}."
            
            # الحصول على إعدادات العرض للمرفق
            if csv_file in self.search_columns:
                settings = self.search_columns[csv_file]
                display_cols = settings["display"]
                name_field = settings["name_field"]
                type_name = settings["type_name"]
            else:
                # استخدام الإعدادات الافتراضية
                display_cols = df.columns.tolist()
                name_field = df.columns[0] if len(df.columns) > 0 else None
                type_name = facility_type
            
            # تنسيق النتائج
            facilities_count = len(neighborhood_facilities)
            result_text = f"{result_title} ({facilities_count}):\n"
            
            # عرض عدد محدود من المرافق فقط (1-2)
            max_display = 1
            displayed = 0
            
            for index, row in neighborhood_facilities.iterrows():
                if displayed >= max_display:
                    break
                    
                # استخراج الاسم فقط بدون أي تفاصيل أخرى
                facility_name = None
                if name_field and name_field in row and pd.notna(row[name_field]):
                    facility_name = row[name_field]
                else:
                    # البحث عن أي عمود يمكن أن يحتوي على الاسم
                    for col in ["الاسم", "اسم_المدرسة", "اسم_المستشفى", "اسم_الحديقة", "اسم_السوبرماركت", "اسم_المول"]:
                        if col in row and pd.notna(row[col]):
                            facility_name = row[col]
                            break
                
                if facility_name:
                    result_text += f"• {facility_name}\n"
                    displayed += 1
            
            # إضافة إشارة للمزيد من المرافق إذا لم يتم عرضها كلها
            if displayed < facilities_count:
                if facility_type == "مدرسة":
                    result_text += f"\nويوجد {facilities_count-displayed} مدارس أخرى في الحي."
                elif facility_type == "مستشفى":
                    result_text += f"\nويوجد {facilities_count-displayed} مستشفيات أخرى في الحي."
                elif facility_type == "حديقة":
                    result_text += f"\nويوجد {facilities_count-displayed} حدائق أخرى في الحي."
                elif facility_type == "سوبرماركت":
                    result_text += f"\nويوجد {facilities_count-displayed} متاجر أخرى في الحي."
                elif facility_type == "مول":
                    result_text += f"\nويوجد {facilities_count-displayed} مراكز تسوق أخرى في الحي."
                else:
                    result_text += f"\nويوجد {facilities_count-displayed} مرافق أخرى في الحي."
            
            return result_text
                
        except Exception as e:
            logger.error(f"خطأ في البحث عن المرافق في الحي: {str(e)}")
            raise FacilitySearchError(f"فشل البحث عن المرافق في {neighborhood_name}: {str(e)}")
        
    def _normalize_arabic_text(self, text: str) -> str:
        """
        توحيد النص العربي (مثل توحيد الهمزات والألف) لتحسين البحث
        
        Args:
            text: النص المراد توحيده
            
        Returns:
            str: النص بعد التوحيد
        """
        normalized = text
        # توحيد الهمزات
        normalized = re.sub(r'[إأآا]', 'ا', normalized)
        # توحيد الياء
        normalized = re.sub(r'[ىیي]', 'ي', normalized)
        # توحيد التاء المربوطة والهاء
        normalized = re.sub(r'ة', 'ه', normalized)
        # توحيد الألف المقصورة
        normalized = re.sub(r'ى', 'ي', normalized)
        # إزالة التشكيل
        normalized = re.sub(r'[\u064B-\u065F]', '', normalized)
        
        return normalized

    def extract_facility_type_from_message(self, message: str) -> Optional[str]:
        """
        استخراج نوع المرفق من رسالة المستخدم.
        تحسين خوارزمية استخراج نوع المرفق من الرسالة.
        """
        if not message:
            return None
        
        message_lower = message.lower()
        
        # تحقق من وجود كلمات مفتاحية في الرسالة
        max_matches = 0
        best_facility_type = None
        
        for facility_type, keywords in self.facility_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in message_lower)
            if matches > max_matches:
                max_matches = matches
                best_facility_type = facility_type
        
        if max_matches > 0:
            logger.info(f"تم استخراج نوع المرفق '{best_facility_type}' من الرسالة")
            return best_facility_type
        
        return None

    def search_facilities(self, neighborhood_name: str, facility_type: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        البحث عن مرافق معينة في حي محدد.
        
        Args:
            neighborhood_name: اسم الحي
            facility_type: نوع المرفق (مدارس، مستشفيات، إلخ)
            limit: الحد الأقصى لعدد النتائج (اختياري)
            
        Returns:
            pd.DataFrame: إطار بيانات يحتوي على المرافق
        """
        # تحويل أنواع المرافق إلى أسماء ملفات CSV
        csv_file_name = self.map_facility_type_to_csv(facility_type)
        if not csv_file_name or csv_file_name not in self.csv_mappings:
            logger.warning(f"نوع المرفق غير معروف: {facility_type}")
            return pd.DataFrame()
        
        # الحصول على DataFrame
        df = self.csv_mappings[csv_file_name]
        
        # تحديد اسم العمود الذي يحتوي على اسم الحي
        neighborhood_columns = ["الحي", "اسم_الحي", "neighborhood", "المنطقة", "location"]
        neighborhood_column = None
        
        for col in neighborhood_columns:
            if col in df.columns:
                neighborhood_column = col
                break
        
        if not neighborhood_column:
            logger.warning(f"لم يتم العثور على عمود الحي في {csv_file_name}")
            return pd.DataFrame()
        
        # تنظيف اسم الحي
        clean_neighborhood = neighborhood_name.replace("حي ", "").strip()
        
        # البحث عن جميع المرافق في الحي المحدد
        neighborhood_facilities = df[
            df[neighborhood_column].str.contains(clean_neighborhood, case=False, na=False) |
            df[neighborhood_column].str.contains(f"حي {clean_neighborhood}", case=False, na=False)
        ]
        
        # إذا لم يتم العثور على مرافق، حاول البحث باستخدام نص عربي موحد
        if neighborhood_facilities.empty:
            normalized_name = self._normalize_arabic_text(clean_neighborhood)
            neighborhood_facilities = df[
                df[neighborhood_column].apply(
                    lambda x: self._normalize_arabic_text(str(x)).find(normalized_name) >= 0 
                    if pd.notna(x) else False
                )
            ]
        
        # تطبيق حد على عدد النتائج إذا كان محددًا
        if limit and not neighborhood_facilities.empty:
            return neighborhood_facilities.head(limit)
            
        return neighborhood_facilities

    def _extract_facility_from_question(self, message: str) -> Optional[Dict[str, str]]:
        """
        استخراج اسم المرفق من سؤال "أين يوجد" أو "أين تقع".
        
        Args:
            message: رسالة المستخدم
            
        Returns:
            Optional[Dict[str, str]]: قاموس يحتوي على اسم ونوع المرفق، أو None إذا لم يُعثر على مرفق
        """
        if not message:
            return None
            
        # التحقق مما إذا كانت الرسالة طلب توصية حي
        neighborhood_patterns = [
            "دلني على حي", "أريد حي", "اريد حي", "اقترح لي حي", "أقترح لي حي",
            "ابحث عن حي", "حي فيه", "حي قريب من"
        ]
        
        if any(pattern in message for pattern in neighborhood_patterns):
            logger.info(f"تم تحديد طلب توصية حي: {message}")
            return None
            
        # البحث عن أنماط سؤال عن موقع مرفق
        facility_patterns = [
            r'أين (?:يوجد|توجد) ([\u0600-\u06FF\s]+?)(?:\?|$|\s)',
            r'أين (?:يقع|تقع) ([\u0600-\u06FF\s]+?)(?:\?|$|\s)',
            r'(?:موقع|مكان) ([\u0600-\u06FF\s]+?)(?:\?|$|\s)',
            r'كيف (?:أصل|اصل) (?:إلى|الى) ([\u0600-\u06FF\s]+?)(?:\?|$|\s)',
            r'(?:دلني|دلوني) (?:على|عن|الى|إلى) ([\u0600-\u06FF\s]+?)(?:\?|$|\s)'
        ]
        
        for pattern in facility_patterns:
            match = re.search(pattern, message)
            if match:
                facility_name = match.group(1).strip()
                
                # تحديد نوع المرفق من اسمه
                facility_type = self._determine_facility_type(facility_name)
                
                if facility_type:
                    logger.info(f"تم استخراج اسم المرفق: {facility_name} (النوع: {facility_type})")
                    return {
                        'name': facility_name,
                        'type': facility_type
                    }
        
        return None

    def _determine_facility_type(self, facility_name: str) -> Optional[str]:
        """
        تحديد نوع المرفق بناءً على اسمه.
        
        Args:
            facility_name: اسم المرفق
            
        Returns:
            Optional[str]: نوع المرفق إذا تم العثور عليه، إلا None
        """
        for facility_type, keywords in self.facility_keywords.items():
            if any(keyword in facility_name.lower() for keyword in keywords):
                return facility_type
        return None