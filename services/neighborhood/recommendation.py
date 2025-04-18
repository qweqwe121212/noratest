# -*- coding: utf-8 -*-

"""
خدمة توصيات الأحياء.
"""

import logging
import pandas as pd
import re
from typing import List, Optional

from services.data.data_loader import DataLoader
from services.llm.gemini_service import GeminiService
from core.exceptions import NeighborhoodRecommendationError

logger = logging.getLogger(__name__)

class NeighborhoodRecommendationService:
    """
    خدمة للتوصية بالأحياء المناسبة بناءً على رسالة المستخدم.
    """
    def __init__(self, data_loader: DataLoader, llm_service: GeminiService):
        """
        تهيئة خدمة التوصيات.
        
        Args:
            data_loader: مُحمل البيانات
            llm_service: خدمة النموذج اللغوي
        """
        self.data_loader = data_loader
        self.llm_service = llm_service
        logger.info("تم تهيئة خدمة توصيات الأحياء")
    
    def get_recommended_neighborhood(self, user_message: str) -> str:
        """
        الحصول على الحي الموصى به بناءً على رسالة المستخدم.
        
        Args:
            user_message: رسالة المستخدم
            
        Returns:
            str: اسم الحي الموصى به
        """
        try:
            # أولاً، تحقق مما إذا كان المستخدم طلب حياً محدداً بشكل صريح
            explicitly_requested_neighborhood = self.extract_explicitly_requested_neighborhood(user_message)
            if explicitly_requested_neighborhood:
                logger.info(f"تم تحديد طلب صريح للحي: {explicitly_requested_neighborhood}")
                return explicitly_requested_neighborhood
            
            # البحث عن الحالات المشابهة في قاعدة المعرفة
            knowledge_cases = self.data_loader.get_cases_for_llm()
            similar_cases_json, df_similar = self.llm_service.find_similar_cases(user_message, knowledge_cases)
            
            if not df_similar.empty:
                # الحصول على الحي المقترح من أعلى تطابق
                top_case = df_similar.iloc[0]
                suggested_neighborhood = top_case.get('الحي_المقترح')
                similarity_percentage = top_case.get('نسبة_التشابه', 0)
                
                logger.info(f"الحي المقترح: {suggested_neighborhood} بنسبة تطابق {similarity_percentage}%")
                
                if suggested_neighborhood and not pd.isna(suggested_neighborhood):
                    return suggested_neighborhood
                
                # إذا لم يُعثر على حي، استخدم الطريقة البديلة
                suggested_neighborhoods = [row.get('الحي_المقترح') for _, row in df_similar.iterrows() 
                                        if row.get('الحي_المقترح') and not pd.isna(row.get('الحي_المقترح'))]
                
                if suggested_neighborhoods:
                    suggested_neighborhood = self.get_neighborhood_from_list_or_message(
                        user_message, suggested_neighborhoods
                    )
                    return suggested_neighborhood
            
            # إذا لم تكن هناك حالات مشابهة، استخدم الطريقة البديلة
            suggested_neighborhood = self.get_neighborhood_from_list_or_message(user_message)
            return suggested_neighborhood
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الحي الموصى به: {str(e)}")
            raise NeighborhoodRecommendationError(f"فشل في التوصية بحي مناسب: {str(e)}")

    def extract_explicitly_requested_neighborhood(self, user_message: str) -> Optional[str]:
        """
        استخراج اسم الحي المطلوب صراحةً من رسالة المستخدم.
        
        Args:
            user_message: رسالة المستخدم
            
        Returns:
            Optional[str]: اسم الحي المطلوب صراحةً، أو None إذا لم يوجد
        """
        if not user_message:
            return None
        
        # قائمة الكلمات العربية الشائعة التي يجب استبعادها من أسماء الأحياء
        common_words = [
            "فيه", "فيها", "به", "بها", "هذا", "هذه", "ذلك", "تلك",
            "من", "إلى", "على", "في", "عن", "مع", "حول", "قرب", "بجانب"
        ]
        
        # أنماط للعثور على طلبات صريحة للأحياء
        explicit_patterns = [
            r'اقترح (?:لي|علي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'أقترح (?:لي|علي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'اقتراح (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'(?:أبي|أبغى|أريد|ابي|ابغى|اريد) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'معلومات عن (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'(?:ساكن|أسكن|اسكن) في (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'أفضل (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)'
        ]
        
        # تتيح التحليل على سطر واحد
        user_message_oneline = user_message.replace('\n', ' ')
        
        for pattern in explicit_patterns:
            match = re.search(pattern, user_message_oneline)
            if match:
                neighborhood = match.group(1).strip()
                
                # التحقق من أن الاسم المستخرج ليس كلمة شائعة
                if neighborhood in common_words:
                    logger.info(f"تم تجاهل الكلمة الشائعة '{neighborhood}' كاسم حي")
                    continue
                    
                # التحقق من أن الاسم ليس قصيرًا جدًا
                if len(neighborhood) < 3:
                    logger.info(f"تم تجاهل الاسم القصير '{neighborhood}' كاسم حي")
                    continue
                    
                # التحقق من وجود هذا الحي في قائمة الأحياء المتاحة
                available_neighborhoods = self.data_loader.get_available_neighborhoods()
                found_match = False
                
                for available_hood in available_neighborhoods:
                    clean_available = available_hood.replace("حي ", "").strip()
                    clean_matched = neighborhood.replace("حي ", "").strip()
                    
                    if clean_available == clean_matched or clean_available in clean_matched or clean_matched in clean_available:
                        logger.info(f"تم العثور على حي مطابق: {available_hood}")
                        return available_hood
                        
                # إذا وصلنا إلى هنا، فلم يتم العثور على تطابق في قائمة الأحياء المتاحة
                return None
        
        # فحص وجود عبارة صريحة في نهاية الرسالة
        lines = user_message.split('\n')
        last_line = lines[-1].strip() if lines else ""
        
        # البحث عن أنماط محددة في آخر سطر
        last_line_patterns = [
            r'(?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            r'^([\u0600-\u06FF\s]+?)$'  # اسم حي وحيد في السطر الأخير
        ]
        
        for pattern in last_line_patterns:
            match = re.search(pattern, last_line)
            if match:
                neighborhood = match.group(1).strip()
                
                # التحقق من أن الاسم المستخرج ليس كلمة شائعة
                if neighborhood in common_words:
                    logger.info(f"تم تجاهل الكلمة الشائعة '{neighborhood}' في السطر الأخير")
                    continue
                    
                # التحقق مما إذا كان هذا اسم حي معروف
                available_neighborhoods = self.data_loader.get_available_neighborhoods()
                for available_hood in available_neighborhoods:
                    clean_available = available_hood.replace("حي ", "").strip()
                    clean_matched = neighborhood.replace("حي ", "").strip()
                    
                    if clean_available == clean_matched or clean_available in clean_matched or clean_matched in clean_available:
                        logger.info(f"تم العثور على حي مطابق في السطر الأخير: {available_hood}")
                        return available_hood
                
                # إذا كان آخر سطر في الرسالة هو اسم الحي فقط
                if len(last_line.split()) <= 3 and any(word in last_line for word in ['حي', 'الشفا', 'النرجس', 'الياسمين', 'العقيق', 'الملقا']):
                    # تحقق إضافي ضد الكلمات الشائعة
                    if not any(word == neighborhood for word in common_words):
                        return neighborhood
        
        # فحص خاص للعبارات مثل "اقترح لي حي فيه مدارس" أو "أريد حي فيه خدمات"
        special_patterns = [
            r'اقترح (?:لي|علي) حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'أقترح (?:لي|علي) حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'أريد حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'اريد حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'ابحث عن حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)'
        ]
        
        for pattern in special_patterns:
            if re.search(pattern, user_message):
                # في هذه الحالة المستخدم يطلب توصية بحي يحتوي على مرافق معينة
                # ولا يطلب حيًا محددًا بالاسم
                logger.info("تم تحديد طلب توصية بحي يحتوي على مرافق محددة")
                return None
        
        return None
        
    def get_neighborhood_from_list_or_message(self, user_message: str, 
                                        suggested_neighborhoods: Optional[List[str]] = None) -> str:
        """
        استخراج اسم الحي من قائمة مقترحة أو من رسالة المستخدم، أو إرجاع القيمة الافتراضية.
        
        Args:
            user_message: رسالة المستخدم
            suggested_neighborhoods: قائمة اختيارية بالأحياء المقترحة
            
        Returns:
            str: اسم الحي
        """
        # إذا كانت هناك قائمة أحياء مقترحة، استخدم الحي الأول
        if suggested_neighborhoods and len(suggested_neighborhoods) > 0:
            for neighborhood in suggested_neighborhoods:
                if neighborhood and not pd.isna(neighborhood):
                    logger.info(f"اختيار الحي المقترح من القائمة: {neighborhood}")
                    return neighborhood
        
        # تحليل رسالة المستخدم بحثاً عن أسماء أحياء
        neighborhood_from_message = self.extract_neighborhood_from_message(user_message)
        if neighborhood_from_message:
            return neighborhood_from_message
        
        # القيمة الافتراضية: حي الياسمين
        return "الياسمين"
    
    def extract_neighborhood_from_message(self, user_message: str) -> Optional[str]:
        """
        استخراج اسم الحي من رسالة المستخدم.
        
        Args:
            user_message: رسالة المستخدم
            
        Returns:
            Optional[str]: اسم الحي إذا وجد، وإلا None
        """
        if not user_message:
            return None
        
        # قائمة الأحياء المتاحة
        available_neighborhoods = self.data_loader.get_available_neighborhoods()
        
        # أولاً، ابحث عن أنماط الجمل التي تشير إلى الحي المقصود للسكن
        housing_patterns = [
            r'(?:أسكن|اسكن|أعيش|اعيش|مقيم) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
            r'(?:أفضل|افضل|ارغب|أرغب) (?:السكن|العيش) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
            r'(?:أبحث|ابحث) عن عقار في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
            r'(?:حي|منطقة) ([\u0600-\u06FF\s]+?) (?:للسكن|مناسب|مناسبة|جيدة|جيد)(?:\.|\s|$)'
        ]
        
        for pattern in housing_patterns:
            match = re.search(pattern, user_message)
            if match:
                potential_hood = match.group(1).strip()
                for neighborhood in available_neighborhoods:
                    # إزالة بادئة "حي" إذا كانت موجودة
                    clean_name = neighborhood.replace("حي ", "").strip()
                    
                    if clean_name.lower() == potential_hood.lower() or clean_name.lower() in potential_hood.lower():
                        logger.info(f"تم العثور على اسم الحي في سياق السكن: {neighborhood}")
                        return neighborhood
        
        # ثانياً، ابحث عن الكلمات التي تشير إلى مكان العمل (لتجنب اختياره كحي للسكن)
        work_patterns = [
            r'(?:مكان عملي|أعمل|اعمل|وظيفتي) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
            r'(?:مقر العمل|مكتبي|شركتي) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)'
        ]
        
        work_neighborhoods = []
        for pattern in work_patterns:
            match = re.search(pattern, user_message)
            if match:
                work_hood = match.group(1).strip()
                work_neighborhoods.append(work_hood)
        
        # الآن ابحث عن أي حي متاح في الرسالة (باستثناء أحياء العمل)
        for neighborhood in available_neighborhoods:
            # إزالة بادئة "حي" إذا كانت موجودة
            clean_name = neighborhood.replace("حي ", "").strip()
            
            # فحص ما إذا كان اسم الحي موجودًا في رسالة المستخدم وليس في أحياء العمل
            if clean_name in user_message and not any(clean_name in work_hood for work_hood in work_neighborhoods):
                logger.info(f"تم العثور على اسم الحي في رسالة المستخدم: {neighborhood}")
                return neighborhood
        
        return None