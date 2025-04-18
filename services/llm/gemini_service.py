# -*- coding: utf-8 -*-

"""
خدمة التفاعل مع Google Gemini API.
"""

import google.generativeai as genai
import json
import re
import logging
from typing import Dict, List, Tuple, Any, Optional
import pandas as pd

from core.exceptions import LLMServiceError, QueryClassificationError
from services.llm.templates import (
    REAL_ESTATE_QUERY_TEMPLATE,
    OFF_TOPIC_RESPONSE_TEMPLATE,
    QUERY_TYPE_CLASSIFICATION_TEMPLATE,
    SIMILARITY_SEARCH_TEMPLATE,
    ENTITY_EXTRACTION_TEMPLATE
)

logger = logging.getLogger(__name__)

class GeminiService:
    """
    خدمة للتفاعل مع واجهة برمجة تطبيقات Google Gemini.
    """
    def __init__(self, api_key: str, model_name: str, safety_settings: List[Dict],
                temperature: float = 0.0, top_p: float = 1.0, 
                top_k: int = 40, max_output_tokens: int = 2048):
        """
        تهيئة خدمة النموذج اللغوي.
        """
        try:
            genai.configure(api_key=api_key)
            
            self.model = genai.GenerativeModel(
                model_name=model_name,
                safety_settings=safety_settings
            )
            
            self.generation_config = {
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "max_output_tokens": max_output_tokens,
            }
            
            logger.info(f"تم تهيئة خدمة النموذج اللغوي بنموذج: {model_name}")
            
        except Exception as e:
            logger.error(f"خطأ في تهيئة خدمة النموذج اللغوي: {str(e)}")
            raise LLMServiceError(f"فشل تهيئة خدمة النموذج اللغوي: {str(e)}")
    
    def generate_content(self, prompt: str, temperature: Optional[float] = None, 
                         max_output_tokens: Optional[int] = None) -> str:
        """
        توليد محتوى باستخدام النموذج اللغوي.
        
        Args:
            prompt: النص المدخل للنموذج
            temperature: درجة الحرارة (الابتكار) - اختياري
            max_output_tokens: الحد الأقصى لعدد الرموز المخرجة - اختياري
            
        Returns:
            str: النص المولد
        """
        try:
            # تكوين الجيل المخصص إذا تم تقديم المعلمات
            custom_config = self.generation_config.copy()
            if temperature is not None:
                custom_config["temperature"] = temperature
            if max_output_tokens is not None:
                custom_config["max_output_tokens"] = max_output_tokens
            
            response = self.model.generate_content(
                prompt,
                generation_config=custom_config
            )
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"خطأ في توليد المحتوى: {str(e)}")
            # إرجاع رسالة خطأ عامة بدلاً من رفع استثناء
            return "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."
    
    def is_real_estate_query(self, user_message: str) -> bool:
        """
        تحديد ما إذا كانت رسالة المستخدم متعلقة بالعقارات أو المرافق.
        """
        try:
            prompt = REAL_ESTATE_QUERY_TEMPLATE.format(user_message=user_message)
            
            result = self.generate_content(
                prompt,
                temperature=0.0,
                max_output_tokens=10,
            )
            
            response_text = result.lower()
            return "نعم" in response_text or "yes" in response_text
            
        except Exception as e:
            logger.error(f"خطأ في تحديد ما إذا كان الاستعلام يتعلق بالعقارات: {str(e)}")
            # في حالة الخطأ، نفترض أنه متعلق بالعقارات
            return True
    
    def generate_off_topic_response(self, user_message: str) -> str:
        """
        توليد رد للاستعلامات الخارجة عن النطاق.
        """
        try:
            prompt = OFF_TOPIC_RESPONSE_TEMPLATE.format(user_message=user_message)
            
            result = self.generate_content(
                prompt,
                temperature=0.3,  # درجة حرارة أعلى قليلاً للتنوع في الردود
                max_output_tokens=200,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في توليد رد خارج النطاق: {str(e)}")
            return "أستطيع مساعدتك في البحث عن عقار أو سكن مناسب أو المرافق المتوفرة. هل يمكنني مساعدتك في إيجاد حي مناسب لاحتياجاتك؟"
    
    def classify_query(self, user_message: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        تصنيف استعلام المستخدم واختيار ملف CSV المناسب.
        """
        try:
            # استخدام النموذج لتحديد نوع الرسالة
            prompt = QUERY_TYPE_CLASSIFICATION_TEMPLATE.format(user_message=user_message)
            
            query_type_response = self.generate_content(
                prompt,
                temperature=0.0,
                max_output_tokens=20,
            )
            
            query_type = query_type_response.strip().lower()
            logger.info(f"تم تصنيف الاستعلام كـ: {query_type}")
            
            # تحديد ملف CSV المناسب بناءً على نوع الاستعلام
            csv_file = None
            search_query = None
            
            if query_type in ["ترحيب", "استفسار_عادي"]:
                # لا حاجة لملف CSV للاستفسارات العامة
                pass
            elif query_type == "اقتراح_حي":  
                csv_file = "Neighborhoods.csv"
            elif query_type == "مرافق_عامة":
                # لا ملف محدد للمرافق العامة، سيتم تحديد النوع لاحقًا
                pass
            elif query_type == "مدرسة":
                csv_file = "المدارس.csv"
                search_query = self.extract_entity_from_message(user_message, "school")
            elif query_type == "مول":
                csv_file = "مول.csv"  
                search_query = self.extract_entity_from_message(user_message, "mall")
            elif query_type == "مستشفى":
                csv_file = "مستشفى.csv"
                search_query = self.extract_entity_from_message(user_message, "hospital")
            elif query_type == "حديقة":  
                csv_file = "حدائق.csv"
                search_query = self.extract_entity_from_message(user_message, "park")
            elif query_type == "سوبرماركت":
                csv_file = "سوبرماركت.csv"  
                search_query = self.extract_entity_from_message(user_message, "supermarket")
            
            return query_type, csv_file, search_query
        
        except Exception as e:
            logger.error(f"خطأ في تصنيف الاستعلام: {str(e)}")
            raise QueryClassificationError(f"فشل تصنيف الاستعلام: {str(e)}")
    
    def extract_entity_from_message(self, message: str, entity_type: str) -> Optional[str]:
        """
        استخراج كيان محدد من رسالة المستخدم.
        """
        try:
            prompt = ENTITY_EXTRACTION_TEMPLATE.format(
                entity_type=entity_type,
                message=message
            )
            
            entity_response = self.generate_content(
                prompt,
                temperature=0.0,
                max_output_tokens=20,
            )
            
            extracted_entity = entity_response.strip()
            
            if extracted_entity.lower() != "عام":
                logger.info(f"تم استخراج {entity_type}: {extracted_entity}")
                return extracted_entity
            else:
                logger.info(f"لم يتم العثور على {entity_type} محدد في الرسالة")
                return None
        
        except Exception as e:
            logger.error(f"خطأ في استخراج {entity_type} من الرسالة: {str(e)}")
            return None
    
    def find_similar_cases(self, user_message: str, knowledge_cases: List[Dict]) -> Tuple[str, pd.DataFrame]:
        """
        البحث عن حالات مشابهة لرسالة المستخدم باستخدام النموذج اللغوي.
        """
        try:
            if not knowledge_cases:
                logger.warning("لم يتم توفير حالات المعرفة")
                return "[]", pd.DataFrame()
            
            # تحويل الحالات إلى JSON
            knowledge_cases_json = json.dumps(knowledge_cases, ensure_ascii=False)
            
            # إنشاء prompt للنموذج اللغوي
            prompt = SIMILARITY_SEARCH_TEMPLATE.format(
                user_message=user_message,
                knowledge_cases_json=knowledge_cases_json
            )
            
            # استدعاء النموذج
            similarity_response = self.generate_content(prompt)
            
            # تنظيف النتيجة لاستخراج JSON فقط
            similarity_result = re.sub(r'^.*?```json', '', similarity_response, flags=re.DOTALL)
            similarity_result = re.sub(r'```.*?$', '', similarity_result, flags=re.DOTALL)
            similarity_result = similarity_result.strip()
            
            # تحليل JSON
            try:
                similar_cases = json.loads(similarity_result)
                logger.info(f"تم العثور على {len(similar_cases)} حالة مشابهة")
                
                # تحويل إلى DataFrame
                df_similar = pd.DataFrame(similar_cases)
                
                # إذا لم يتم العثور على نتائج، استخدم الحالة الأولى كافتراضية
                if len(similar_cases) == 0 and knowledge_cases:
                    logger.warning("لم يجد النموذج اللغوي حالات مشابهة، استخدام الحالة الأولى")
                    first_case = knowledge_cases[0]
                    similar_cases = [{
                        "رقم_الحالة": first_case['رقم_الحالة'],
                        "نسبة_التشابه": 10.0,
                        "الحي_المقترح": first_case['الحي_المقترح'],
                        "سبب_التشابه": "تم اختيار هذه الحالة كخيار افتراضي لعدم وجود تطابق أفضل"
                    }]
                    similarity_result = json.dumps(similar_cases, ensure_ascii=False)
                    df_similar = pd.DataFrame(similar_cases)
                
                return similarity_result, df_similar
                
            except json.JSONDecodeError as e:
                logger.error(f"تنسيق JSON غير صالح: {e}")
                logger.debug(f"الاستجابة الأولية: {similarity_result}")
                
                if knowledge_cases:
                    first_case = knowledge_cases[0]
                    similar_cases = [{
                        "رقم_الحالة": first_case['رقم_الحالة'],
                        "نسبة_التشابه": 10.0,
                        "الحي_المقترح": first_case['الحي_المقترح'],
                        "سبب_التشابه": "تم اختيار هذه الحالة كخيار افتراضي لعدم تمكن النظام من تحليل التشابه"
                    }]
                    similarity_result = json.dumps(similar_cases, ensure_ascii=False)
                    df_similar = pd.DataFrame(similar_cases)
                else:
                    similarity_result = "[]"
                    df_similar = pd.DataFrame()
                
                return similarity_result, df_similar
            
        except Exception as e:
            logger.error(f"خطأ في البحث عن حالات مشابهة باستخدام النموذج اللغوي: {str(e)}")
            return "[]", pd.DataFrame()