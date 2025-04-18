"""
نواة الشاتبوت - المكون المركزي الذي يربط كل الخدمات.
"""

import logging
import datetime
from typing import Dict, List, Optional, Any
import re

from utils.location_integration import LocationIntegration
from services.data.data_loader import DataLoader
from services.llm.gemini_service import GeminiService
from services.neighborhood.recommendation import NeighborhoodRecommendationService
from services.neighborhood.search import FacilitySearchService
from services.neighborhood.formatter import ResponseFormatter
from services.geo.distance_calculator import DistanceCalculator
from core.exceptions import ServiceInitializationError
from utils.query_processor import QueryProcessor



logger = logging.getLogger(__name__)

class NeighborhoodChatbot:
    """
    الشاتبوت الرئيسي للتوصية بالأحياء والمرافق.
    يعمل كواجهة موحدة للتواصل مع جميع الخدمات.
    """
    def __init__(self, config, db):
        self.config = config
        self.db = db  # ✅ نخزن db في الكائن

        """
        تهيئة الشاتبوت مع جميع الخدمات المطلوبة.
        
        Args:
            config: كائن الإعدادات
        """
        
        try:
            # تهيئة محمل البيانات
            self.data_loader = DataLoader(
                mongo_uri=config.MONGO_URI,
                mongo_db=config.MONGO_DB,
                default_neighborhoods=config.DEFAULT_NEIGHBORHOODS
            )
            
            # تهيئة خدمة النموذج اللغوي
            self.llm_service = GeminiService(
                api_key=config.GOOGLE_API_KEY,
                model_name=config.LLM_MODEL,
                safety_settings=config.SAFETY_SETTINGS,
                temperature=config.LLM_TEMPERATURE,
                top_p=config.LLM_TOP_P,
                top_k=config.LLM_TOP_K,
                max_output_tokens=config.LLM_MAX_OUTPUT_TOKENS
            )
            
            # تهيئة خدمة توصيات الأحياء
            self.recommendation_service = NeighborhoodRecommendationService(
                data_loader=self.data_loader,
                llm_service=self.llm_service
            )
            
            # تهيئة خدمة البحث عن المرافق
            self.search_service = FacilitySearchService(
                data_loader=self.data_loader
            )
            
            # تهيئة خدمة تنسيق الردود
            self.formatter = ResponseFormatter(
                data_loader=self.data_loader
            )
            
            # تهيئة خدمة حساب المسافات
            self.distance_calculator = DistanceCalculator(
                data_loader=self.data_loader,
                api_key=config.GOOGLE_API_KEY
            )
            
            # تهيئة معالج الاستعلامات
            self.query_processor = QueryProcessor(
                available_neighborhoods=self.data_loader.get_available_neighborhoods()
            )
            
            self.location_integration = LocationIntegration(
            distance_calculator=self.distance_calculator,
            data_loader=self.data_loader
            )
            
            # إضافة قائمة لتخزين تاريخ المحادثة
            self.user_chat_histories = {}
            
            logger.info("تمت تهيئة شاتبوت الأحياء بنجاح")
            logger.info("تم تهيئة ذاكرة المحادثة")


            
        except Exception as e:
            logger.error(f"خطأ في تهيئة الشاتبوت: {str(e)}")
            raise ServiceInitializationError(f"فشل تهيئة الشاتبوت: {str(e)}")

    def add_to_history(self, user_id: str, user_message: str, bot_response: str) -> None:
        """
        إضافة رسالة المستخدم ورد الشاتبوت إلى تاريخ المحادثة الخاص بهذا المستخدم.
        
        Args:
            user_id: معرف المستخدم
            user_message: رسالة المستخدم
            bot_response: رد الشاتبوت
        """
        # إنشاء قائمة محادثات للمستخدم إذا لم تكن موجودة
        if user_id not in self.user_chat_histories:
            self.user_chat_histories[user_id] = []
        
        # إضافة المحادثة إلى تاريخ هذا المستخدم
        self.user_chat_histories[user_id].append({
            'user': user_message,
            'bot': bot_response,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
        # الاحتفاظ بآخر 50 رسالة فقط لتجنب استهلاك الذاكرة
        if len(self.user_chat_histories[user_id]) > 50:
            self.user_chat_histories[user_id] = self.user_chat_histories[user_id][-50:]
        
        logger.debug(f"تم إضافة محادثة جديدة للمستخدم {user_id}. عدد المحادثات: {len(self.user_chat_histories[user_id])}")
        
    def get_chat_history(self, user_id: str) -> List[Dict]:
        """
        الحصول على كامل تاريخ المحادثة لمستخدم معين.
        
        Args:
            user_id: معرف المستخدم
            
        Returns:
            List[Dict]: قائمة بالمحادثات السابقة
        """
        return self.user_chat_histories.get(user_id, [])

    def get_last_n_messages(self, user_id: str, n: int = 5) -> List[Dict]:
        """
        الحصول على آخر n رسائل من تاريخ المحادثة لمستخدم معين.
        
        Args:
            user_id: معرف المستخدم
            n: عدد الرسائل التي يجب استرجاعها
            
        Returns:
            List[Dict]: قائمة بآخر n رسائل
        """
        history = self.user_chat_histories.get(user_id, [])
        return history[-n:] if len(history) >= n else history

    def _handle_best_worst_neighborhood_query(self, message: str) -> Optional[str]:
        """
        معالجة استفسارات "أفضل حي" أو "أسوأ حي" بطريقة محايدة
        
        Args:
            message: رسالة المستخدم
            
        Returns:
            Optional[str]: رد محايد إذا كان الاستعلام عن أفضل/أسوأ حي، أو None إذا لم يكن كذلك
        """
        # تنظيف الرسالة
        cleaned_message = message.strip()
        
        # قائمة التعبيرات النمطية الدقيقة لاستفسارات أفضل/أسوأ حي
        best_worst_patterns = [
            # أنماط سؤال عن أفضل حي
            r'^(?:ما|ايش|وش|وين) (?:هو |)(افضل|أفضل) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # ما هو أفضل حي؟
            r'^(?:ما|ايش|وش|وين) (?:هي |)(افضل|أفضل) (?:احياء|أحياء|المناطق|مناطق)(?:\?|؟|$|\s)',  # ما هي أفضل الأحياء؟
            r'^(?:افضل|أفضل) (?:حي|منطقة)(?:\?|؟|$|\s)',  # أفضل حي؟
            r'^(?:احسن|أحسن) (?:حي|منطقة)(?:\?|؟|$|\s)',  # أحسن حي؟
            
            # أنماط سؤال عن أسوأ حي
            r'^(?:ما|ايش|وش|وين) (?:هو |)(اسوء|أسوأ|اسوا|أسوا) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # ما هو أسوأ حي؟
            r'^(?:ما|ايش|وش|وين) (?:هي |)(اسوء|أسوأ|اسوا|أسوا) (?:احياء|أحياء|المناطق|مناطق)(?:\?|؟|$|\s)',  # ما هي أسوأ الأحياء؟
            r'^(?:اسوء|أسوأ|اسوا|أسوا) (?:حي|منطقة)(?:\?|؟|$|\s)',  # أسوأ حي؟
            r'^(?:اردء|أردأ) (?:حي|منطقة)(?:\?|؟|$|\s)',  # أردأ حي؟
            
            # أنماط طلب توصية عامة بأفضل/أسوأ حي
            r'^اقترح (?:لي|علي|) (?:افضل|أفضل) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # اقترح لي أفضل حي؟
            r'^أقترح (?:لي|علي|) (?:افضل|أفضل) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # أقترح لي أفضل حي؟
            r'^اخبرني عن (?:افضل|أفضل) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # اخبرني عن أفضل حي؟
            r'^أخبرني عن (?:افضل|أفضل) (?:حي|منطقة|الاحياء|الأحياء)(?:\?|؟|$|\s)',  # أخبرني عن أفضل حي؟
            
            # أنماط طلب مباشر
            r'^وش افضل حي(?:\?|؟|$|\s)',  # وش افضل حي؟
            r'^وش أفضل حي(?:\?|؟|$|\s)',  # وش أفضل حي؟
            r'^ابغى افضل حي(?:\?|؟|$|\s)',  # ابغى افضل حي؟ 
            r'^أبغى أفضل حي(?:\?|؟|$|\s)',  # أبغى أفضل حي؟
            r'^ابي افضل حي(?:\?|؟|$|\s)',  # ابي افضل حي؟
            r'^أبي أفضل حي(?:\?|؟|$|\s)',  # أبي أفضل حي؟
            
        ]
        
        # التحقق من وجود أنماط تشير إلى طلب شخصي أو خاص للمستخدم
        # هذه الأنماط لا تتطلب الرد المحايد لأنها تطلب توصية شخصية
        contextual_patterns = [
            r'اقترح لي حي بناء على',  # اقترح لي حي بناء على...
            r'أقترح لي حي بناء على',  # أقترح لي حي بناء على...
            r'اقترح لي افضل حي لي',  # اقترح لي افضل حي لي
            r'أقترح لي أفضل حي لي',  # أقترح لي أفضل حي لي
            r'افضل حي لي',  # افضل حي لي
            r'أفضل حي لي',  # أفضل حي لي
            r'افضل حي يناسبني',  # افضل حي يناسبني
            r'أفضل حي يناسبني',  # أفضل حي يناسبني
            r'ماهو افضل حي لي',  # ماهو افضل حي لي
            r'ما هو أفضل حي لي',  # ما هو أفضل حي لي
            r'انا عمري \d+ سنة',  # انا عمري .. سنة واريد افضل حي
            r'عائلة لديها',  # عائلة لديها ... افضل حي
            r'ابحث عن افضل حي',  # ابحث عن افضل حي
            r'أبحث عن أفضل حي',  # أبحث عن أفضل حي
        ]
        
        # الأنماط التي تشير إلى معايير محددة للحي الأفضل
        # هذه الأنماط لا تتطلب الرد المحايد لأنها تسأل عن "أفضل حي" لغرض محدد
        criteria_patterns = [
            # أفضل حي للعائلات / للسكن / للاستثمار... إلخ
            r'(?:افضل|أفضل) حي لل(\w+)',  # أفضل حي للعائلات
            r'(?:افضل|أفضل) منطقة لل(\w+)',  # أفضل منطقة للسكن
            r'(?:افضل|أفضل) حي من ناحية ال(\w+)',  # أفضل حي من ناحية الخدمات
            r'(?:افضل|أفضل) حي من حيث ال(\w+)',  # أفضل حي من حيث الأسعار
            r'(?:افضل|أفضل) الاحياء (من|في|ب|ل)(\w+)',  # أفضل الأحياء من حيث السكن
            r'(?:افضل|أفضل) حي (قريب|بالقرب) من',  # أفضل حي قريب من...
            r'(?:افضل|أفضل) حي (فيه|يوجد فيه|به|يوجد به)',  # أفضل حي فيه مدارس
            r'(?:افضل|أفضل) حي (بسعر|بمتوسط سعر)',  # أفضل حي بسعر معقول
        ]
        
        # التحقق مما إذا كان للسؤال سياق شخصي أو متطلبات محددة
        if any(re.search(pattern, cleaned_message, re.IGNORECASE) for pattern in contextual_patterns):
            logger.info("تم اكتشاف استفسار شخصي عن الحي - المتابعة إلى المعالجة العادية")
            return None
            
        # التحقق مما إذا كان السؤال يحتوي على معايير محددة
        if any(re.search(pattern, cleaned_message, re.IGNORECASE) for pattern in criteria_patterns):
            logger.info("تم اكتشاف استفسار عن أفضل حي مع معايير محددة - المتابعة إلى المعالجة العادية")
            return None
        
        # التحقق من وجود نمط من أنماط أفضل/أسوأ حي العامة
        if any(re.search(pattern, cleaned_message, re.IGNORECASE) for pattern in best_worst_patterns):
            logger.info("تم التعرف على استفسار عن أفضل/أسوأ حي بشكل عام")
            
            # الرد المحايد
            neutral_response = "لا يوجد حي يمكن تصنيفه على أنه الأفضل أو الأسوأ بشكل عام، فاختيار الحي يعتمد بشكل كبير على تفضيلاتك واحتياجاتك الشخصية. كل حي يتمتع بمميزاته الخاصة التي قد تتناسب مع البعض ولا تتناسب مع الآخرين. قد تجد أن بعض الأحياء تتميز بالقرب من المدارس أو المرافق العامة، بينما قد تكون أحياء أخرى مثالية للعائلات التي تبحث عن بيئة هادئة. من المهم أن تأخذ في اعتبارك ما الذي تبحث عنه في الحي مثل الموقع، الخدمات، الأسعار، والأجواء العامة قبل اتخاذ قرارك."
            
            return neutral_response
            
        return None

    def process_message(self, user_id: str, user_message: str, user_latitude: float = None, user_longitude: float = None) -> str:
        """
        معالجة رسالة المستخدم والرد عليها.
        
        Args:
            user_id: معرف المستخدم
            user_message: رسالة المستخدم
            user_latitude: إحداثي خط العرض للمستخدم (اختياري)
            user_longitude: إحداثي خط الطول للمستخدم (اختياري)
            
        Returns:
            str: رد الشاتبوت
        """
        if not user_message:
            return "يرجى إدخال رسالة."
        
        # الاحتفاظ بالرسالة الأصلية
        original_message = user_message
        
        try:
            # تنظيف الرسالة
            cleaned_message = user_message.strip()
            
            # التحقق من الأسئلة الموجهة التي تتطلب ردودًا سريعة
            short_response = self._handle_short_response(user_id, cleaned_message)
            if short_response:
                self.add_to_history(user_id, original_message, short_response)
                return short_response
                
            # التحقق من استفسارات "أفضل حي" أو "أسوأ حي"
            best_worst_response = self._handle_best_worst_neighborhood_query(cleaned_message)
            if best_worst_response:
                self.add_to_history(user_id, original_message, best_worst_response)
                return best_worst_response
            
            # معالجة استفسارات الميزانية مثل "ابحث عن حي مناسب لميزانيتي حيث ان راتبي ١٥٠٠٠"
            budget_response = self._handle_budget_query(cleaned_message)
            if budget_response:
                self.add_to_history(user_id, original_message, budget_response)
                return budget_response
            
            # معالجة أنماط الطلبات مثل "دلني على حي قريب من منطقة الشمال وفيه مدارس"
            neighborhood_direction_patterns = [
                r'دلني على حي ([\u0600-\u06FF\s]+?) وفيه ([\u0600-\u06FF\s]+)',
                r'دلني على حي ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                r'دلني على حي قريب من ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                r'ارشدني إلى حي ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                r'أرشدني إلى حي ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                r'اقترح لي حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
                r'أقترح لي حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            ]
            
            for pattern in neighborhood_direction_patterns:
                match = re.search(pattern, cleaned_message)
                if match:
                    logger.info(f"تم العثور على طلب توصية بحي بناءً على معايير: {match.group(1)}")
                    # تحليل معايير الحي المطلوب (مثل "قريب من منطقة الشمال وفيه مدارس")
                    query_analysis = self.query_processor.analyze_query(cleaned_message)
                    query_analysis['query_type'] = 'neighborhood_recommendation'
                    query_analysis['intents'].add('neighborhood_recommendation')
                    
                    # تحليل معايير المعلومات المكانية أو المرافق المطلوبة
                    if 'قريب من' in cleaned_message or 'بالقرب من' in cleaned_message:
                        query_analysis['entities']['location_preference'] = True
                    
                    # استخراج نوع المرفق المطلوب
                    facility_type = None
                    for facility_key, keywords in self.search_service.facility_keywords.items():
                        if any(keyword in cleaned_message for keyword in keywords):
                            facility_type = facility_key
                            break
                    
                    if facility_type:
                        # إذا كان هناك مرفق محدد، أضفه للمعايير
                        query_analysis['entities']['facility_type'] = facility_type
                    
                    # الحصول على توصية بحي بناءً على المعايير المحللة
                    recommended_neighborhood = self.recommendation_service.get_recommended_neighborhood(cleaned_message)
                    
                    if recommended_neighborhood:
                        # بناء رد مفصل حول الحي الموصى به باستخدام طريقة الرد التفصيلي
                        response = self._build_detailed_neighborhood_response(recommended_neighborhood)
                        
                        # إضافة معلومات حول المرافق المطلوبة إذا كانت محددة
                        if facility_type:
                            facility_info = self.search_service.find_facilities_in_neighborhood(recommended_neighborhood, facility_type)
                            summarized_facilities = self._summarize_facilities(facility_info, recommended_neighborhood, facility_type)
                            
                            # إضافة فاصل بين المعلومات العامة ومعلومات المرافق
                            if "لم نتمكن من العثور" not in summarized_facilities:
                                response += f"\n\n{summarized_facilities}"
                        
                        self.add_to_history(user_id, original_message, response)
                        return response
            
            # تحليل الاستعلام باستخدام معالج الاستعلامات
            query_analysis = self.query_processor.analyze_query(cleaned_message)
            logger.info(f"نتيجة تحليل الاستعلام: {query_analysis}")
            
            # التعامل مع طلبات توصية الأحياء
            if query_analysis['query_type'] == 'neighborhood_recommendation':
                # الحصول على توصية بحي
                recommended_neighborhood = self.recommendation_service.get_recommended_neighborhood(cleaned_message)
                
                # تكوين رد تفصيلي حول الحي الموصى به باستخدام طريقة الرد المفصلة
                response = self._build_detailed_neighborhood_response(recommended_neighborhood)
                
                # إضافة معلومات المرافق إذا كان هناك نوع مرفق محدد في الاستعلام
                if 'facility_type' in query_analysis['entities']:
                    facility_type = query_analysis['entities']['facility_type']
                    facility_info = self.search_service.find_facilities_in_neighborhood(recommended_neighborhood, facility_type)
                    summarized_facilities = self._summarize_facilities(facility_info, recommended_neighborhood, facility_type)
                    
                    # إضافة معلومات المرافق إذا وجدت
                    if "لم نتمكن من العثور" not in summarized_facilities:
                        response += f"\n\n{summarized_facilities}"
                    
                # إضافة معلومات المسافة إذا كانت متوفرة
                if user_latitude and user_longitude:
                    distance = self._calculate_distance_to_neighborhood(recommended_neighborhood, user_latitude, user_longitude)
                    if distance is not None:
                        response += f"\n\nالمسافة من موقعك الحالي إلى حي {recommended_neighborhood} هي {distance:.2f} كيلومتر."
                
                self.add_to_history(user_id, original_message, response)
                return response
            
            # التعامل مع طلبات معلومات الأحياء
            elif query_analysis['query_type'] == 'neighborhood_info' and 'neighborhood' in query_analysis['entities']:
                neighborhood_name = query_analysis['entities']['neighborhood']
                
                # بناء رد مفصل حول الحي
                response = self._build_detailed_neighborhood_response(neighborhood_name)
                
                # إضافة معلومات المسافة إذا كانت متوفرة
                if user_latitude and user_longitude:
                    distance = self._calculate_distance_to_neighborhood(neighborhood_name, user_latitude, user_longitude)
                    if distance is not None:
                        response += f"\n\nالمسافة من موقعك الحالي إلى حي {neighborhood_name} هي {distance:.2f} كيلومتر."
                
                self.add_to_history(user_id, original_message, response)
                return response
            
            # التعامل مع طلبات البحث عن السكن
            elif query_analysis['query_type'] == 'housing_search':
                logger.info("معالجة طلب البحث عن سكن")
                
                # تحليل الرد المناسب
                response = self._handle_housing_with_facilities(query_analysis, cleaned_message, user_latitude, user_longitude)
                
                self.add_to_history(user_id, original_message, response)
                return response
            
            # التعامل مع طلبات البحث عن موقع مرفق معين
            elif query_analysis['query_type'] == 'facility_location' and 'facility_name' in query_analysis['entities']:
                facility_name = query_analysis['entities']['facility_name']
                facility_type = query_analysis['entities'].get('facility_type')
                
                # تحديد ملف CSV الذي يجب البحث فيه
                csv_file = None
                if facility_type == 'مدرسة':
                    csv_file = "المدارس.csv"
                elif facility_type == 'مستشفى':
                    csv_file = "مستشفى.csv"
                elif facility_type == 'حديقة':
                    csv_file = "حدائق.csv"
                elif facility_type == 'سوبرماركت':
                    csv_file = "سوبرماركت.csv"
                elif facility_type == 'مول':
                    csv_file = "مول.csv"
                
                # البحث عن المرفق
                if csv_file:
                    search_result = self.search_service.search_entity(csv_file, facility_name)
                    self.add_to_history(user_id, original_message, search_result)
                    return search_result
                else:
                    # البحث في جميع المرافق إذا لم يتم تحديد نوع
                    search_result = self.search_service.search_all_facilities(facility_name)
                    self.add_to_history(user_id, original_message, search_result)
                    return search_result
            
            # التعامل مع طلبات البحث عن مرفق
            elif query_analysis['query_type'] == 'facility_search' and 'facility_name' in query_analysis['entities']:
                facility_name = query_analysis['entities']['facility_name']
                facility_type = query_analysis['entities'].get('facility_type')
                
                # تحديد ملف CSV الذي يجب البحث فيه
                csv_file = None
                if facility_type == 'مدرسة':
                    csv_file = "المدارس.csv"
                elif facility_type == 'مستشفى':
                    csv_file = "مستشفى.csv"
                elif facility_type == 'حديقة':
                    csv_file = "حدائق.csv"
                elif facility_type == 'سوبرماركت':
                    csv_file = "سوبرماركت.csv"
                elif facility_type == 'مول':
                    csv_file = "مول.csv"
                
                # البحث عن المرفق
                if csv_file:
                    search_result = self.search_service.search_entity(csv_file, facility_name)
                    self.add_to_history(user_id, original_message, search_result)
                    return search_result
                else:
                    # البحث في جميع المرافق إذا لم يتم تحديد نوع
                    search_result = self.search_service.search_all_facilities(facility_name)
                    self.add_to_history(user_id, original_message, search_result)
                    return search_result
            
            # استخدام المعالجة الاحتياطية إذا لم يتم تحديد نوع الاستعلام
            fallback_response = self._fallback_processing(cleaned_message)
            self.add_to_history(user_id, original_message, fallback_response)
            return fallback_response
            
        except Exception as e:
            # تسجيل الخطأ
            logger.error(f"خطأ في معالجة الرسالة: {str(e)}")
            
            # محاولة توليد رد عام
            try:
                fallback = self._generate_response(user_message)
                self.add_to_history(user_id, original_message, fallback)
                return fallback
            except:
                # رسالة خطأ عامة في حالة فشل كل شيء
                error_message = "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."
                self.add_to_history(user_id, original_message, error_message)
                return error_message

    def _handle_short_response(self, user_id: str, cleaned_message: str) -> Optional[str]:
        """
        معالجة الردود القصيرة بناءً على سياق المحادثة السابقة
        
        Args:
            user_id: معرف المستخدم
            cleaned_message: الرسالة المنظفة
                
        Returns:
            Optional[str]: الرد المناسب أو None إذا لم تكن رسالة قصيرة
        """
        short_response_keywords = ["نعم", "المزيد", "اريد", "أريد", "أكمل", "تابع", "اكمل", "استمر", "موافق", "تمام", "اوكي", "اوك", "ok"]
        
        if len(cleaned_message.split()) <= 2 and any(keyword in cleaned_message.lower() for keyword in short_response_keywords):
            # استخراج المحادثة السابقة - زيادة عدد الرسائل المسترجعة
            previous_messages = self.get_last_n_messages(user_id, 3)  # استرجاع آخر 3 رسائل بدلاً من 2
            
            if len(previous_messages) >= 1:
                last_bot_message = previous_messages[-1].get('bot', '')
                
                # تخزين الحي المذكور في سياق المحادثة
                context_neighborhood = None
                
                # البحث عن حي محدد في الرسالة السابقة للبوت
                for neighborhood in self.data_loader.get_available_neighborhoods():
                    if neighborhood in last_bot_message:
                        context_neighborhood = neighborhood
                        logger.info(f"تم العثور على حي '{context_neighborhood}' في المحادثة السابقة")
                        break
                
                # إذا لم يتم العثور على حي في رسالة البوت الأخيرة، ابحث في رسالة البوت قبل الأخيرة (إذا وجدت)
                if context_neighborhood is None and len(previous_messages) >= 2:
                    second_last_bot_message = previous_messages[-2].get('bot', '')
                    for neighborhood in self.data_loader.get_available_neighborhoods():
                        if neighborhood in second_last_bot_message:
                            context_neighborhood = neighborhood
                            logger.info(f"تم العثور على حي '{context_neighborhood}' في الرسالة قبل الأخيرة")
                            break
                
                # الآن لدينا سياق الحي، استخدمه لمعالجة الطلبات المتعلقة "بهذا الحي"
                if context_neighborhood:
                    # تحديد أنواع المرافق المطلوبة
                    facility_types = ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]
                    requested_facility = None
                    
                    # البحث عن الكلمات المتعلقة بالمرافق في رسالة المستخدم
                    for facility in facility_types:
                        if facility in cleaned_message or facility + "س" in cleaned_message or "مرافق" in cleaned_message or "مدارس" in cleaned_message:
                            requested_facility = facility
                            break
                    
                    # اذا كانت الكلمة "المدارس" موجودة صراحة في رسالة المستخدم
                    if "المدارس" in cleaned_message:
                        requested_facility = "مدرسة"
                    
                    if "المرافق" in cleaned_message or "كل المرافق" in cleaned_message:
                        # عرض معلومات عامة عن المرافق في الحي المحفوظ في السياق
                        response = f"إليك أبرز المرافق في {context_neighborhood}:\n\n"
                        
                        # إضافة 1-2 مرفق من كل نوع
                        for facility_type in facility_types:
                            facility_info = self.search_service.find_facilities_in_neighborhood(context_neighborhood, facility_type)
                            if "لم يتم العثور" not in facility_info:
                                # استخراج 1-2 مرفق فقط
                                summarized = self._extract_sample_facilities(facility_info, 2)
                                if summarized:
                                    response += f"• {summarized}\n\n"
                        
                        response += f"لعرض قائمة كاملة بالمرافق، يمكنك أن تسأل عن نوع محدد مثل 'أين توجد المدارس في {context_neighborhood}؟'"
                        return response
                    
                    elif requested_facility:
                        # عرض معلومات مختصرة عن أهم المرافق من النوع المطلوب في الحي المحفوظ في السياق
                        facility_info = self.search_service.find_facilities_in_neighborhood(context_neighborhood, requested_facility)
                        summarized_facilities = self._summarize_facilities(facility_info, context_neighborhood, requested_facility)
                        return summarized_facilities
                    
                    else:
                        # طلب غير محدد - عرض معلومات عامة عن الحي
                        return self.formatter.format_neighborhood_response(context_neighborhood)
                
                # البحث عن مرافق محددة في الرسالة السابقة
                facility_types = ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]
                facility_mentioned = None
                for facility in facility_types:
                    if facility in last_bot_message:
                        facility_mentioned = facility
                        break
                
                if facility_mentioned:
                    logger.info(f"تم العثور على مرفق '{facility_mentioned}' في المحادثة السابقة")
                    # تقديم معلومات إضافية عن نوع المرفق
                    response = f"للبحث عن {facility_mentioned} محددة، أرجو كتابة اسم {facility_mentioned} أو الحي الذي تريد البحث فيه."
                    
                    # إضافة المحادثة إلى التاريخ
                    self.add_to_history(user_id, cleaned_message, response)
                    return response
                
                # البحث عن طلب توصية
                if "اقترح" in last_bot_message or "أقترح" in last_bot_message or "أفضل حي" in last_bot_message:
                    # تقديم توصية بحي بناءً على المحادثة السابقة
                    suggested_neighborhood = self.recommendation_service.get_recommended_neighborhood(last_bot_message)
                    response = self.formatter.format_neighborhood_response(suggested_neighborhood)
                    
                    # إضافة المحادثة إلى التاريخ
                    self.add_to_history(user_id, cleaned_message, response)
                    return response
            
            # لم يتم التعرف على هذه الرسالة كرد قصير
            return None
        
    def _summarize_facilities(self, facility_info: str, neighborhood_name: str, facility_type: str) -> str:
        """
        تلخيص معلومات المرافق لإدراجها في رد الشاتبوت.
        
        Args:
            facility_info: نص معلومات المرفق الكامل
            neighborhood_name: اسم الحي
            facility_type: نوع المرفق
            
        Returns:
            str: ملخص منسق
        """
        try:
            # تنظيف اسم الحي
            clean_name = neighborhood_name.replace("حي ", "").strip()
            formatted_name = f"حي {clean_name}" if not neighborhood_name.startswith("حي") else neighborhood_name
            
            # إذا لم يتم العثور على المرافق
            if "لم يتم العثور" in facility_info:
                facility_type_display = {
                    "مدرسة": "مدارس",
                    "مستشفى": "مستشفيات أو مراكز طبية",
                    "حديقة": "حدائق أو متنزهات",
                    "سوبرماركت": "محلات سوبرماركت",
                    "مول": "مولات أو مراكز تسوق"
                }.get(facility_type, facility_type)
                
                return f"لم نتمكن من العثور على {facility_type_display} في {formatted_name} في قاعدة بياناتنا."
            
            # استخراج عدد المرافق
            count_match = re.search(r'\((\d+)\)', facility_info)
            count = int(count_match.group(1)) if count_match else 0
            
            # استخراج أسماء المرافق
            facility_names = re.findall(r'• ([\u0600-\u06FF\s\d]+)', facility_info)
            
            # تحديد صيغة العرض حسب نوع المرفق
            if facility_type == "مدرسة":
                facility_type_display = "المدارس"
                if count == 1:
                    result = f"يوجد في {formatted_name} مدرسة واحدة"
                elif count == 2:
                    result = f"يوجد في {formatted_name} مدرستان"
                elif count <= 10:
                    result = f"يوجد في {formatted_name} {count} مدارس"
                else:
                    result = f"يوجد في {formatted_name} العديد من المدارس، حيث يصل عددها إلى {count} مدرسة"
            
            elif facility_type == "مستشفى":
                facility_type_display = "المستشفيات والمراكز الطبية"
                if count == 1:
                    result = f"يوجد في {formatted_name} مستشفى واحد"
                elif count == 2:
                    result = f"يوجد في {formatted_name} مستشفيان"
                elif count <= 10:
                    result = f"يوجد في {formatted_name} {count} مستشفيات ومراكز طبية"
                else:
                    result = f"يوجد في {formatted_name} العديد من المستشفيات والمراكز الطبية، حيث يصل عددها إلى {count} منشأة طبية"
            
            elif facility_type == "حديقة":
                facility_type_display = "الحدائق والمتنزهات"
                if count == 1:
                    result = f"يوجد في {formatted_name} حديقة واحدة"
                elif count == 2:
                    result = f"يوجد في {formatted_name} حديقتان"
                elif count <= 10:
                    result = f"يوجد في {formatted_name} {count} حدائق ومتنزهات"
                else:
                    result = f"يوجد في {formatted_name} العديد من الحدائق والمتنزهات، حيث يصل عددها إلى {count} حديقة"
            
            elif facility_type == "سوبرماركت":
                facility_type_display = "محلات السوبرماركت"
                if count == 1:
                    result = f"يوجد في {formatted_name} سوبرماركت واحد"
                elif count == 2:
                    result = f"يوجد في {formatted_name} سوبرماركت اثنان"
                elif count <= 10:
                    result = f"يوجد في {formatted_name} {count} محلات سوبرماركت"
                else:
                    result = f"يوجد في {formatted_name} العديد من محلات السوبرماركت، حيث يصل عددها إلى {count} متجر"
            
            elif facility_type == "مول":
                facility_type_display = "المولات ومراكز التسوق"
                if count == 1:
                    result = f"يوجد في {formatted_name} مول واحد"
                elif count == 2:
                    result = f"يوجد في {formatted_name} مولان"
                elif count <= 10:
                    result = f"يوجد في {formatted_name} {count} مولات ومراكز تسوق"
                else:
                    result = f"يوجد في {formatted_name} العديد من المولات ومراكز التسوق، حيث يصل عددها إلى {count} مركز"
            
            else:
                facility_type_display = "المرافق"
                result = f"يوجد في {formatted_name} {count} من {facility_type}"
            
            # إضافة أمثلة إذا توفرت
            if facility_names:
                if len(facility_names) == 1:
                    result += f"، مثل {facility_names[0]}"
                elif len(facility_names) > 1:
                    names_str = " و".join([", ".join(facility_names[:-1]), facility_names[-1]])
                    result += f"، مثل {names_str}"
            
            result += "."
            
            # إضافة دعوة للإجراء
            result += f" يمكنك السؤال عن المزيد من المعلومات حول {facility_type_display} في {formatted_name} إذا كنت مهتمًا."
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في تلخيص معلومات المرافق: {str(e)}")
            return f"يوجد عدد من {facility_type} في {neighborhood_name}."

    def _extract_sample_facilities(self, facility_info: str, count: int = 1) -> str:
        """
        استخراج عدد محدد من المرافق من النص الكامل
        
        Args:
            facility_info: النص الكامل لمعلومات المرافق
            count: عدد المرافق المراد استخراجها
            
        Returns:
            str: نص يحتوي على عينة من المرافق
        """
        # تقسيم النص إلى سطور
        lines = facility_info.split('\n')
        
        # البحث عن السطور التي تبدأ بـ "•" (العلامة النقطية)
        bullet_lines = [line for line in lines if line.strip().startswith('•')]
        
        # اختيار عدد محدد من السطور
        selected_lines = bullet_lines[:1] if bullet_lines else []
        
        # استخراج اسم المرفق فقط (بدون العنوان أو أي تفاصيل أخرى)
        result_lines = []
        for line in selected_lines:
            line = line.strip()
            # حذف العنوان (بعد علامة '|' أو ':')
            if '|' in line:
                facility_name = line.split('|')[0]
            elif ':' in line:
                facility_name = line.split(':')[0]
            else:
                facility_name = line
                
            # تنظيف الاسم وإزالة العلامة النقطية في البداية
            facility_name = facility_name.replace('•', '').strip()
            result_lines.append(facility_name)
        
        # دمج النتائج
        return '\n'.join(result_lines)

    def _handle_show_all_facilities(self, user_message: str, neighborhood_name: str) -> Optional[str]:
        """
        معالجة طلبات عرض جميع المرافق في حي معين
        
        Args:
            user_message: رسالة المستخدم
            neighborhood_name: اسم الحي
            
        Returns:
            Optional[str]: الرد المناسب أو None إذا لم يكن طلب عرض جميع المرافق
        """
        # قائمة بأنواع المرافق وأسمائها الجماعية
        facility_types = {
            "مدرسة": "المدارس",
            "مستشفى": "المستشفيات والمراكز الطبية",
            "حديقة": "الحدائق والمتنزهات",
            "سوبرماركت": "محلات السوبرماركت",
            "مول": "المولات ومراكز التسوق"
        }
        
        # البحث عن أنماط مثل "اعرض جميع المدارس في حي الياسمين"
        for facility_type, facility_plural in facility_types.items():
            # أنماط مختلفة للطلب
            patterns = [
                f"اعرض (?:جميع|كل) {facility_plural} في (?:حي)? {neighborhood_name}",
                f"ما هي (?:جميع|كل) {facility_plural} في (?:حي)? {neighborhood_name}",
                f"أرني (?:جميع|كل) {facility_plural} في (?:حي)? {neighborhood_name}",
                f"أريد (?:جميع|كل) {facility_plural} في (?:حي)? {neighborhood_name}",
                f"اريد (?:جميع|كل) {facility_plural} في (?:حي)? {neighborhood_name}"
            ]
            
            for pattern in patterns:
                if re.search(pattern, user_message, re.IGNORECASE):
                    logger.info(f"تم تحديد طلب عرض جميع {facility_plural} في {neighborhood_name}")
                    # البحث عن المرافق من هذا النوع في الحي
                    facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                    return facility_info
        
        # البحث عن طلب عام لجميع المرافق مثل "اعرض جميع المرافق في حي الياسمين"
        general_patterns = [
            f"اعرض (?:جميع|كل) (?:المرافق|الخدمات) في (?:حي)? {neighborhood_name}",
            f"ما هي (?:جميع|كل) (?:المرافق|الخدمات) في (?:حي)? {neighborhood_name}",
            f"أرني (?:جميع|كل) (?:المرافق|الخدمات) في (?:حي)? {neighborhood_name}",
            f"أريد (?:جميع|كل) (?:المرافق|الخدمات) في (?:حي)? {neighborhood_name}",
            f"اريد (?:جميع|كل) (?:المرافق|الخدمات) في (?:حي)? {neighborhood_name}"
        ]
        
        for pattern in general_patterns:
            if re.search(pattern, user_message, re.IGNORECASE):
                logger.info(f"تم تحديد طلب عرض جميع المرافق في {neighborhood_name}")
                # جمع معلومات عن جميع أنواع المرافق
                all_facilities = []
                for facility_type in facility_types.keys():
                    facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                    if "لم يتم العثور" not in facility_info:
                        all_facilities.append(facility_info)
                
                # دمج المعلومات
                if all_facilities:
                    response = f"جميع المرافق المتوفرة في {neighborhood_name}:\n\n"
                    response += "\n\n".join(all_facilities)
                    return response
                else:
                    return f"عذراً، لم يتم العثور على معلومات عن المرافق في {neighborhood_name}."
        
        # لم يتم تحديد طلب عرض جميع المرافق
        return None

    def _build_detailed_neighborhood_response(self, neighborhood_name: str) -> str:
        """
        بناء رد مفصل وشامل حول حي معين يشمل جميع المعلومات المهمة.
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            str: رد مفصل عن الحي
        """
        try:
            # الحصول على معلومات الحي
            neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
            if not neighborhood_info:
                return f"عذراً، لم أتمكن من العثور على معلومات مفصلة عن {neighborhood_name}."
            
            # تنظيف اسم الحي
            clean_name = neighborhood_name.replace("حي ", "").strip()
            formatted_name = f"حي {clean_name}" if not neighborhood_name.startswith("حي") else neighborhood_name
            
            # بداية الرد بالتوصية
            response = f"أقترح عليك {formatted_name}. "
            
            # إضافة معلومات عن تجارب الباحثين السابقين إذا توفرت
            if "based_on_experience" in neighborhood_info and neighborhood_info["based_on_experience"]:
                response += "بناءً على تجربة الباحثين عن العقارات السابقين، أقترح عليك البحث في "
                response += f"{formatted_name}. "
            
            # معلومات عن موقع الحي والخصائص العامة
            if "الموقع" in neighborhood_info and neighborhood_info["الموقع"]:
                response += f"يعتبر {formatted_name} من الأحياء "
                if "قديم" in neighborhood_info["الموقع"].lower():
                    response += "القديمة والشهيرة "
                elif "جديد" in neighborhood_info["الموقع"].lower():
                    response += "الحديثة والمتطورة "
                else:
                    response += "المعروفة "
                
                if "شمال" in neighborhood_info["الموقع"].lower():
                    response += f"في شمال مدينة الرياض"
                elif "جنوب" in neighborhood_info["الموقع"].lower():
                    response += f"في جنوب مدينة الرياض"
                elif "شرق" in neighborhood_info["الموقع"].lower():
                    response += f"في شرق مدينة الرياض"
                elif "غرب" in neighborhood_info["الموقع"].lower():
                    response += f"في غرب مدينة الرياض"
                elif "وسط" in neighborhood_info["الموقع"].lower() or "المركز" in neighborhood_info["الموقع"].lower():
                    response += f"في وسط مدينة الرياض"
                else:
                    # استخدام النص كما هو
                    response += f"في {neighborhood_info['الموقع']}"
                
                # إضافة معلومات عن البلدية
                if "البلدية" in neighborhood_info and neighborhood_info["البلدية"]:
                    response += f"، وهو من الأحياء التابعة لبلدية {neighborhood_info['البلدية']}"
                
                response += ".\n"
            
            # إضافة معلومات عن المميزات الطبيعية والإنشائية
            natural_features = []
            if "المعالم_البارزة" in neighborhood_info and neighborhood_info["المعالم_البارزة"]:
                natural_features.append(neighborhood_info["المعالم_البارزة"])
            
            if "المميزات_الطبيعية" in neighborhood_info and neighborhood_info["المميزات_الطبيعية"]:
                natural_features.append(neighborhood_info["المميزات_الطبيعية"])
            
            if natural_features:
                response += f"حيث يعد من الأحياء التي شهدت تطوراً وازدهاراً في السنوات الأخيرة"
                
                # إضافة المميزات الطبيعية
                for feature in natural_features:
                    if "وادي" in feature.lower():
                        response += f"، واشتهر {formatted_name} بوجود {feature} الذي يتمتع بمناظر رائعة وخلابة، والذي يتهافت عليه الزوار بشكل يومي لممارسة مختلف الرياضات فيه كرياضة المشي ورياضة ركوب الدراجات وأيضاً للجلوس والاستمتاع بمنظر البحيرة"
                    else:
                        response += f"، ويتميز بوجود {feature}"
                
                response += ".\n"
            
            # إضافة معلومات عن طرق الوصول وسهولة التنقل
            if "الطرق_الرئيسية" in neighborhood_info and neighborhood_info["الطرق_الرئيسية"]:
                response += f"ويمتاز {formatted_name} بسهولة مخارجه ومداخله من الدائري "
                
                if "شمال" in neighborhood_info["الطرق_الرئيسية"].lower():
                    response += "الشمالي "
                elif "جنوب" in neighborhood_info["الطرق_الرئيسية"].lower():
                    response += "الجنوبي "
                elif "شرق" in neighborhood_info["الطرق_الرئيسية"].lower():
                    response += "الشرقي "
                elif "غرب" in neighborhood_info["الطرق_الرئيسية"].lower():
                    response += "الغربي "
                else:
                    response += ""
                
                roads = neighborhood_info["الطرق_الرئيسية"].split(',')
                if len(roads) > 1:
                    formatted_roads = " و".join([", ".join(roads[:-1]), roads[-1].strip()])
                    response += f"ومن طريق {formatted_roads} "
                else:
                    response += f"ومن طريق {neighborhood_info['الطرق_الرئيسية']} "
                
                response += "ويتوفر فيه جميع الخدمات.\n"
            
            # إضافة معلومات عن المرافق والخدمات
            response += f"يتوفر في {formatted_name} العديد من المرافق والخدمات"
            
            # الاستعلام عن أهم المرافق
            facility_types = ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]
            has_facility_details = False
            
            for facility_type in facility_types:
                facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                if "لم يتم العثور" not in facility_info:
                    has_facility_details = True
                    break
            
            if not has_facility_details:
                response += "."
            else:
                response += " مثل المدارس، المستشفيات، الحدائق، والمراكز التجارية."
            
            # إضافة معلومات الأسعار
            if "متوسط_سعر_المتر" in neighborhood_info and neighborhood_info["متوسط_سعر_المتر"]:
                response += "\n"
                
                # تحويل النص إلى رقم إذا أمكن
                try:
                    meter_price = float(neighborhood_info["متوسط_سعر_المتر"])
                    # تنسيق السعر بفواصل الآلاف
                    formatted_price = "{:,.0f}".format(meter_price)
                    response += f"سعر المتر للفلل {formatted_price} ريال"
                except:
                    response += f"سعر المتر للفلل {neighborhood_info['متوسط_سعر_المتر']} ريال"
            
            if "متوسط_سعر_المتر_شقق" in neighborhood_info and neighborhood_info["متوسط_سعر_المتر_شقق"]:
                if "متوسط_سعر_المتر" in neighborhood_info and neighborhood_info["متوسط_سعر_المتر"]:
                    response += "، "
                else:
                    response += "\n"
                
                # تحويل النص إلى رقم إذا أمكن
                try:
                    meter_price_apt = float(neighborhood_info["متوسط_سعر_المتر_شقق"])
                    # تنسيق السعر بفواصل الآلاف
                    formatted_price_apt = "{:,.0f}".format(meter_price_apt)
                    response += f"سعر المتر للشقق {formatted_price_apt} ريال"
                except:
                    response += f"سعر المتر للشقق {neighborhood_info['متوسط_سعر_المتر_شقق']} ريال"
            
            if ("متوسط_سعر_المتر" in neighborhood_info and neighborhood_info["متوسط_سعر_المتر"]) or \
               ("متوسط_سعر_المتر_شقق" in neighborhood_info and neighborhood_info["متوسط_سعر_المتر_شقق"]):
                response += "."
            
            # إضافة مميزات الحي
            response += "\nويتميز الحي بـ: "
            
            benefits = []
            if "نوع_الحي" in neighborhood_info and neighborhood_info["نوع_الحي"]:
                if "سكني" in neighborhood_info["نوع_الحي"].lower():
                    benefits.append("حي سكني هادئ")
                elif "تجاري" in neighborhood_info["نوع_الحي"].lower():
                    benefits.append("منطقة تجارية نشطة")
                elif "مختلط" in neighborhood_info["نوع_الحي"].lower():
                    benefits.append("منطقة مختلطة (سكنية وتجارية)")
            
            if "المساحة" in neighborhood_info and neighborhood_info["المساحة"]:
                benefits.append("المساحة مناسبة")
            
            if "مستوى_الخدمات" in neighborhood_info and neighborhood_info["مستوى_الخدمات"]:
                quality = neighborhood_info["مستوى_الخدمات"]
                if isinstance(quality, str):
                    if any(word in quality.lower() for word in ["ممتاز", "عالي", "جيد", "متميز"]):
                        benefits.append("وجود خدمات جيدة")
                    elif "متوسط" in quality.lower():
                        benefits.append("وجود خدمات متوسطة")
                
            if "مستوى_الأمان" in neighborhood_info and neighborhood_info["مستوى_الأمان"]:
                if "عالي" in neighborhood_info["مستوى_الأمان"].lower() or "جيد" in neighborhood_info["مستوى_الأمان"].lower():
                    benefits.append("مستوى أمان جيد")
            
            # إضافة معلومات عن حداثة الحي
            if "سنة_التأسيس" in neighborhood_info and neighborhood_info["سنة_التأسيس"]:
                try:
                    year = int(neighborhood_info["سنة_التأسيس"])
                    current_year = datetime.datetime.now().year
                    if current_year - year < 10:
                        benefits.append("الحي حديث")
                except:
                    # إذا كان هناك مشكلة في تحويل السنة إلى رقم، نتحقق من نص الحقل
                    if "جديد" in neighborhood_info["سنة_التأسيس"].lower() or "حديث" in neighborhood_info["سنة_التأسيس"].lower():
                        benefits.append("الحي حديث")
            
            if "مميزات" in neighborhood_info and neighborhood_info["مميزات"]:
                if isinstance(neighborhood_info["مميزات"], list):
                    for benefit in neighborhood_info["مميزات"]:
                        benefits.append(benefit)
                elif isinstance(neighborhood_info["مميزات"], str):
                    benefits_list = neighborhood_info["مميزات"].split("،")
                    for benefit in benefits_list:
                        benefits.append(benefit.strip())
            
            # إضافة معلومات عن مناسبة السعر
            if "مستوى_الأسعار" in neighborhood_info and neighborhood_info["مستوى_الأسعار"]:
                price_level = neighborhood_info["مستوى_الأسعار"]
                if "منخفض" in price_level.lower() or "متوسط" in price_level.lower() or "معقول" in price_level.lower():
                    benefits.append("السعر مناسب")
                elif "مرتفع" in price_level.lower():
                    benefits.append("منطقة راقية")
            
            # إضافة المميزات المتوفرة
            if benefits:
                if len(benefits) == 1:
                    response += benefits[0]
                else:
                    formatted_benefits = "، ".join(benefits)
                    response += formatted_benefits
            else:
                response += "موقع جيد، سهولة الوصول، وتوفر الخدمات"
            
            response += "."
            
            # إضافة جملة ختامية للمزيد من المعلومات
            response += f" للمزيد من المعلومات عن {formatted_name}، يمكنك الاستفسار عن أي جانب محدد ترغب في معرفته."
            
            return response
            
        except Exception as e:
            logger.error(f"خطأ في بناء رد مفصل عن الحي: {str(e)}")
            return f"أقترح عليك حي {neighborhood_name}. للحصول على مزيد من المعلومات التفصيلية، يمكنك سؤالي عن جانب محدد من جوانب هذا الحي."

    def _handle_housing_with_facilities(self, query_analysis: Dict, user_message: str, user_latitude: float = None, user_longitude: float = None) -> str:
        """
        معالجة طلب البحث عن سكن بالقرب من مرافق معينة
        
        Args:
            query_analysis: نتيجة تحليل الاستعلام
            user_message: رسالة المستخدم
            user_latitude: خط العرض للمستخدم (اختياري)
            user_longitude: خط الطول للمستخدم (اختياري)
            
        Returns:
            str: الرد المناسب
        """
        # استخراج المعلومات من التحليل
        budget = query_analysis['entities'].get('budget')
        property_type = query_analysis['entities'].get('property_type')
        transaction_type = query_analysis['entities'].get('transaction_type', 'إيجار')  # افتراضياً إيجار
        proximity_facilities = query_analysis['entities'].get('proximity_facilities', [])
        
        # تحديد أولويات المرافق
        schools_needed = any(facility['type'] == 'مدرسة' for facility in proximity_facilities)
        hospitals_needed = any(facility['type'] == 'مستشفى' for facility in proximity_facilities)
        parks_needed = any(facility['type'] == 'حديقة' for facility in proximity_facilities)
        malls_needed = any(facility['type'] == 'مول' for facility in proximity_facilities)
        
        # اختيار حي مناسب بناءً على المتطلبات
        suggested_neighborhood = self.recommendation_service.get_recommended_neighborhood(user_message)
        
        # بناء الاستجابة
        property_type_display = {
            'شقة': 'شقة', 
            'فيلا': 'فيلا', 
            'أرض': 'أرض', 
            'تجاري': 'عقار تجاري'
        }.get(property_type, 'سكن')
        
        transaction_display = 'استئجار' if transaction_type == 'إيجار' else 'شراء'
        
        response = f"بناءً على متطلباتك للبحث عن {property_type_display} لل{transaction_display}"
        
        # إضافة الميزانية إذا كانت متاحة
        if budget:
            formatted_budget = "{:,}".format(budget)
            response += f" بميزانية {formatted_budget} ريال"
        
        # إضافة المرافق المطلوبة
        if proximity_facilities:
            facility_names = [f['type'] for f in proximity_facilities]
            unique_facility_names = list(set(facility_names))
            
            if len(unique_facility_names) == 1:
                response += f" بالقرب من {unique_facility_names[0]}"
            elif len(unique_facility_names) == 2:
                response += f" بالقرب من {unique_facility_names[0]} و{unique_facility_names[1]}"
            else:
                formatted_facilities = ", ".join(unique_facility_names[:-1]) + f" و{unique_facility_names[-1]}"
                response += f" بالقرب من {formatted_facilities}"
        
        # إضافة توصية الحي
        response += f"، أقترح عليك النظر في {suggested_neighborhood}.\n\n"
        
        # إضافة معلومات الحي مع ضمان ظهور كافة المعلومات السعرية
        neighborhood_info = self.formatter.format_neighborhood_response(suggested_neighborhood)
        response += neighborhood_info + "\n\n"
        
        # إضافة معلومات سعرية إضافية للحي إذا لم تظهر أعلاه
        detailed_info = self.data_loader.find_neighborhood_info(suggested_neighborhood)
        if detailed_info:
            # التحقق من وجود سعر المتر للشقق
            show_extra_prices = False
            if "price_of_meter_Apartment" in detailed_info and detailed_info["price_of_meter_Apartment"] and "سعر المتر للشقق" not in neighborhood_info:
                show_extra_prices = True
            elif "price_of_meter_Villas" in detailed_info and detailed_info["price_of_meter_Villas"] and "سعر المتر للفلل" not in neighborhood_info:
                show_extra_prices = True
                
            if show_extra_prices:
                price_info = []
                # إضافة الأسعار ذات الصلة بنوع العقار المطلوب
                if property_type == "شقة" and "price_of_meter_Apartment" in detailed_info and detailed_info["price_of_meter_Apartment"]:
                    price = int(detailed_info["price_of_meter_Apartment"])
                    formatted_price = "{:,}".format(price)
                    price_info.append(f"سعر المتر للشقق: {formatted_price} ريال")
                    
                elif property_type == "فيلا" and "price_of_meter_Villas" in detailed_info and detailed_info["price_of_meter_Villas"]:
                    price = int(detailed_info["price_of_meter_Villas"])
                    formatted_price = "{:,}".format(price)
                    price_info.append(f"سعر المتر للفلل: {formatted_price} ريال")
                
                if price_info:
                    response += "معلومات الأسعار:\n"
                    for info in price_info:
                        response += f"• {info}\n\n"
        
        # إضافة معلومات المرافق المطلوبة
        facilities_header = "المرافق المتوفرة في الحي والتي تناسب متطلباتك:\n"
        facilities_info = ""
        
        if schools_needed:
            school_info = self.search_service.find_facilities_in_neighborhood(suggested_neighborhood, "مدرسة")
            if "لم يتم العثور" not in school_info:
                facilities_info += f"\n{school_info}\n"
        
        if hospitals_needed:
            hospital_info = self.search_service.find_facilities_in_neighborhood(suggested_neighborhood, "مستشفى")
            if "لم يتم العثور" not in hospital_info:
                facilities_info += f"\n{hospital_info}\n"
        
        if parks_needed:
            park_info = self.search_service.find_facilities_in_neighborhood(suggested_neighborhood, "حديقة")
            if "لم يتم العثور" not in park_info:
                facilities_info += f"\n{park_info}\n"
        
        if malls_needed:
            mall_info = self.search_service.find_facilities_in_neighborhood(suggested_neighborhood, "مول")
            if "لم يتم العثور" not in mall_info:
                facilities_info += f"\n{mall_info}\n"
        
        if facilities_info:
            response += facilities_header + facilities_info
            
        # إضافة معلومات المسافة إذا كانت متاحة
        if user_latitude is not None and user_longitude is not None:
            distance = self._calculate_distance_to_neighborhood(
                suggested_neighborhood, user_latitude, user_longitude
            )
            if distance is not None:
                distance_message = self.location_integration.format_distance_message(suggested_neighborhood, distance)
                response += f"\n{distance_message}"
        
        return response

    def _calculate_distance_to_neighborhood(self, neighborhood_name: str, user_latitude: float, user_longitude: float) -> Optional[float]:
        """
        حساب المسافة بين موقع المستخدم والحي
        
        Args:
            neighborhood_name: اسم الحي
            user_latitude: خط العرض للمستخدم
            user_longitude: خط الطول للمستخدم
            
        Returns:
            Optional[float]: المسافة بالكيلومترات أو None إذا تعذر الحساب
        """
        try:
            logger.info(f"حساب المسافة إلى {neighborhood_name} من الإحداثيات: {user_latitude}, {user_longitude}")
            
            # الحصول على معلومات الحي
            neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
            if not neighborhood_info:
                logger.warning(f"لم يتم العثور على معلومات الحي: {neighborhood_name}")
                return None
            
            # البحث عن أعمدة الإحداثيات
            lat_keys = ["lat", "latitude", "خط_العرض", "LAT"]
            lon_keys = ["lon", "longitude", "خط_الطول", "LON"]
            
            # العثور على مفتاح خط العرض
            lat_key = None
            for key in lat_keys:
                if key in neighborhood_info:
                    lat_key = key
                    break
            
            # العثور على مفتاح خط الطول
            lon_key = None
            for key in lon_keys:
                if key in neighborhood_info:
                    lon_key = key
                    break
            
            if not lat_key or not lon_key:
                logger.warning(f"لم يتم العثور على إحداثيات الحي: {neighborhood_name}")
                return None
            
            # تحويل الإحداثيات إلى أرقام
            try:
                neighborhood_lat = float(neighborhood_info[lat_key])
                neighborhood_lon = float(neighborhood_info[lon_key])
            except (ValueError, TypeError):
                logger.warning(f"إحداثيات الحي غير صالحة: {neighborhood_name}")
                return None
            
            # حساب المسافة
            distance = self.distance_calculator.calculate_distance(
                user_latitude, user_longitude, neighborhood_lat, neighborhood_lon
            )
            
            logger.info(f"تم حساب المسافة إلى {neighborhood_name}: {distance} كم")
            return distance
            
        except Exception as e:
            logger.error(f"خطأ في حساب المسافة إلى {neighborhood_name}: {str(e)}")
            return None

    def _fallback_processing(self, user_message: str) -> str:
        """
        المعالجة الاحتياطية للرسائل التي لم يتم التعرف عليها بواسطة معالج الاستعلامات.
        
        Args:
            user_message: رسالة المستخدم
            
        Returns:
            str: الرد المناسب
        """
        # التحقق مما إذا كانت الرسالة متعلقة بالعقارات أو المرافق
        is_real_estate = self.llm_service.is_real_estate_query(user_message)
        
        if is_real_estate:
            # إذا كانت الرسالة متعلقة بالعقارات أو المرافق
            return self._generate_response(user_message)
        else:
            # إذا كانت الرسالة غير متعلقة بالعقارات أو المرافق
            return self.llm_service.generate_off_topic_response(user_message)
    
    def _generate_response(self, user_message: str) -> str:
        """
        توليد الرد المناسب على رسالة المستخدم.
        طريقة احتياطية للمعالجة إذا فشل معالج الاستعلامات.
        
        Args:
            user_message: رسالة المستخدم
            
        Returns:
            str: الرد المولد
        """
        try:
            # تحقق أولاً مما إذا كان هناك طلب صريح لحي
            explicitly_requested = self.recommendation_service.extract_explicitly_requested_neighborhood(user_message)
            if explicitly_requested:
                return self.formatter.format_neighborhood_response(explicitly_requested)
            
            # تصنيف نوع الاستعلام وتحديد ملف CSV المناسب
            query_type, csv_file, search_query = self.llm_service.classify_query(user_message)
            logger.info(f"نوع الاستعلام (قديم): {query_type}, ملف CSV: {csv_file}, عبارة البحث: {search_query}")
            
            # التعامل مع أنواع الاستعلامات المختلفة
            if query_type == "ترحيب":
                return "أهلاً بك! كيف يمكنني مساعدتك اليوم في البحث عن عقار أو حي مناسب أو المرافق القريبة؟"
                
            elif query_type == "استفسار_عادي":
                return "كيف يمكنني مساعدتك؟ أنا هنا لمساعدتك في العثور على الحي أو العقار المثالي لاحتياجاتك، ويمكنني أيضًا مساعدتك في البحث عن المرافق المتوفرة مثل المدارس والمستشفيات والحدائق والمولات."
                
            elif query_type == "اقتراح_حي":
                # الحصول على الحي المقترح من خدمة التوصيات
                suggested_neighborhood = self.recommendation_service.get_recommended_neighborhood(user_message)
                
                # تنسيق الرد حول الحي المقترح
                return self.formatter.format_neighborhood_response(suggested_neighborhood)
            
            elif query_type == "مرافق_عامة":
                # معالجة الاستعلامات المتعلقة بالمرافق بشكل عام
                neighborhood_name = self.recommendation_service.extract_neighborhood_from_message(user_message)
                
                if neighborhood_name:
                    return self.search_service.find_facilities_in_neighborhood(neighborhood_name, None)
                else:
                    return "في أي حي تود البحث عن المرافق؟"
                
            else:
                # استعلامات المرافق المحددة مثل المدارس والمستشفيات وغيرها
                if csv_file and search_query:
                    # البحث في ملف CSV المحدد
                    return self.search_service.search_entity(csv_file, search_query)
                elif csv_file:
                    # استخراج اسم المرفق من الرسالة بشكل أفضل
                    facility_type = None
                    if "المدارس.csv" in csv_file:
                        facility_type = "مدرسة"
                    elif "مستشفى.csv" in csv_file:
                        facility_type = "مستشفى"
                    elif "حدائق.csv" in csv_file:
                        facility_type = "حديقة"
                    elif "سوبرماركت.csv" in csv_file:
                        facility_type = "سوبرماركت"
                    elif "مول.csv" in csv_file:
                        facility_type = "مول"
                    
                    # محاولة استخراج اسم المرفق باستخدام المعالج الجديد
                    query_analysis = self.query_processor.analyze_query(user_message)
                    
                    if query_analysis['query_type'] in ['facility_location', 'facility_search'] and 'facility_name' in query_analysis['entities']:
                        facility_name = query_analysis['entities']['facility_name']
                        return self.search_service.search_entity(csv_file, facility_name)
                    
                    # إذا فشل ذلك، استخدم الطريقة القديمة
                    return f"من فضلك قم بتحديد اسم {query_type} الذي تريد البحث عنه."
                else:
                    # إذا لم يكن هناك ملف CSV محدد
                    return "كيف يمكنني مساعدتك؟ هل تبحث عن حي معين أو مرفق محدد مثل المدارس أو المستشفيات أو الحدائق أو المولات؟"
        
        except Exception as e:
            logger.error(f"خطأ في توليد الرد: {str(e)}")
            return "عذراً، حدث خطأ ما. هل يمكنك إعادة صياغة طلبك من فضلك؟"
    
    def handle_specific_requests(self, user_id: str, user_message: str, neighborhood_name: Optional[str] = None, user_latitude: float = None, user_longitude: float = None) -> str:
        """
        معالجة الطلبات الخاصة مثل الاستعلام عن مرافق في حي معين.
        
        Args:
            user_id: معرف المستخدم
            user_message: رسالة المستخدم
            neighborhood_name: اسم الحي الاختياري
            user_latitude: خط العرض للمستخدم (اختياري)
            user_longitude: خط الطول للمستخدم (اختياري)
            
        Returns:
            str: الرد المخصص
        """
        try:
            # تحليل الاستعلام
            query_analysis = self.query_processor.analyze_query(user_message)
            
            # إذا كان النص يحتوي على "هذا الحي" أو "الحي" دون تحديد، ابحث عن آخر حي في سياق المحادثة
            if ("هذا الحي" in user_message or "الحي" in user_message) and not neighborhood_name:
                # استخراج آخر حي مذكور في المحادثة
                previous_messages = self.get_last_n_messages(user_id, 3)
                for msg in previous_messages:
                    bot_message = msg.get('bot', '')
                    for hood in self.data_loader.get_available_neighborhoods():
                        if hood in bot_message:
                            neighborhood_name = hood
                            logger.info(f"تم استخراج الحي '{neighborhood_name}' من سياق المحادثة")
                            break
                    if neighborhood_name:
                        break
            
            # إذا كان هناك حي محدد في المعلمات، استخدمه
            if neighborhood_name:
                # البحث عن نوع المرفق
                if query_analysis['query_type'] in ['facility_location', 'facility_search'] and 'facility_type' in query_analysis['entities']:
                    facility_type = query_analysis['entities']['facility_type']
                else:
                    facility_type = self.search_service.extract_facility_type_from_message(user_message)
                
                # البحث عن المرافق في الحي
                response = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                
                # تخزين الحي المستخدم في المحادثة الحالية لاستخدامه لاحقًا في السياق
                self.add_to_history(user_id, user_message, f"معلومات عن {facility_type if facility_type else 'المرافق'} في {neighborhood_name}:\n{response}")
                
                # إضافة معلومات المسافة إذا تم توفير الإحداثيات
                if user_latitude is not None and user_longitude is not None:
                    distance = self.location_integration.calculate_distance_to_neighborhood(
                        neighborhood_name, user_latitude, user_longitude
                    )
                    if distance is not None:
                        distance_message = self.location_integration.format_distance_message(neighborhood_name, distance)
                        response += f"\n\n{distance_message}"
                
                return response
            
            # إذا لم يكن هناك حي محدد في المعلمات، استخرجه من الرسالة
            if 'neighborhood' in query_analysis['entities']:
                neighborhood_name = query_analysis['entities']['neighborhood']
            else:
                neighborhood_name = self.recommendation_service.extract_neighborhood_from_message(user_message)
            
            # إذا لم يتم العثور على اسم الحي، أعد رسالة عامة
            if not neighborhood_name:
                return "من فضلك حدد اسم الحي الذي ترغب في معرفة المزيد عنه."
            
            # تحديد نوع المرفق المطلوب
            if query_analysis['query_type'] in ['facility_location', 'facility_search'] and 'facility_type' in query_analysis['entities']:
                facility_type = query_analysis['entities']['facility_type']
            else:
                facility_type = self.search_service.extract_facility_type_from_message(user_message)
            
            # البحث عن المرافق في الحي
            response = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
            
            # إضافة معلومات المسافة إذا تم توفير الإحداثيات
            if user_latitude is not None and user_longitude is not None:
                distance = self.location_integration.calculate_distance_to_neighborhood(
                    neighborhood_name, user_latitude, user_longitude
                )
                if distance is not None:
                    distance_message = self.location_integration.format_distance_message(neighborhood_name, distance)
                    response += f"\n\n{distance_message}"
            
            return response
                
        except Exception as e:
            logger.error(f"خطأ في معالجة الطلب الخاص: {str(e)}")
            return f"عذراً، حدث خطأ أثناء البحث عن معلومات في {neighborhood_name if neighborhood_name else 'هذا الحي'}."
            
    def get_available_neighborhoods(self) -> List[str]:
        """
        إرجاع قائمة الأحياء المتاحة.
        """
        return self.data_loader.get_available_neighborhoods()
    
    def get_neighborhood_info(self, name: str) -> Dict:
        """
        إرجاع معلومات حي محدد.
        """
        return self.data_loader.find_neighborhood_info(name)
    
    def get_neighborhood_benefits(self, name: str) -> List[str]:
        """
        إرجاع مميزات حي محدد.
        """
        return self.data_loader.get_neighborhood_benefits(name)
    
    def format_neighborhood_response(self, name: str) -> str:
        """
        تنسيق رد حول حي محدد.
        """
        return self.formatter.format_neighborhood_response(name)
    
    def search_facility(self, csv_file: str, query: str) -> str:
        """
        البحث عن مرفق محدد.
        """
        return self.search_service.search_entity(csv_file, query)
    
    def search_all_facilities(self, query: str) -> str:
        """
        البحث في جميع أنواع المرافق.
        """
        return self.search_service.search_all_facilities(query)
        
    def check_components_status(self) -> Dict[str, bool]:
        """
        التحقق من حالة المكونات الرئيسية.
        """
        return {
            'data_loader': self.data_loader is not None,
            'llm_service': self.llm_service is not None,
            'recommendation_service': self.recommendation_service is not None,
            'search_service': self.search_service is not None,
            'formatter': self.formatter is not None,
            'query_processor': self.query_processor is not None
        }

    def process_special_request(self, user_id: str, neighborhood_name: str, request_type: str, 
                                user_latitude: Optional[float] = None, 
                                user_longitude: Optional[float] = None) -> str:
        """
        معالجة الطلبات الخاصة مثل "المزيد" أو "قائمة المرافق" للحي المحدد.
        
        Args:
            user_id: معرف المستخدم
            neighborhood_name: اسم الحي
            request_type: نوع الطلب ("المزيد"، "قائمة المرافق"، إلخ)
            user_latitude: خط العرض للمستخدم (اختياري)
            user_longitude: خط الطول للمستخدم (اختياري)
            
        Returns:
            str: رد منسق يحتوي على المعلومات المطلوبة
        """
        try:
            # تنظيف اسم الحي
            if neighborhood_name and isinstance(neighborhood_name, str):
                neighborhood_name = neighborhood_name.strip()
            
            if not neighborhood_name:
                return "عذراً، لم يتم تحديد الحي. يرجى ذكر اسم الحي الذي ترغب في معرفة المزيد عنه."
            
            if request_type.strip() in ["المزيد", "مزيد", "اكثر", "أكثر"]:
                response = f"أبرز المرافق في {neighborhood_name}:\n\n"
                
                # الحصول على المدارس للحي مع تحديد عدد النتائج بمرفق واحد فقط
                schools = self.search_service.search_facilities(neighborhood_name, "مدارس", limit=1)
                if schools is not None and not schools.empty:
                    response += "• مدارس:\n"
                    for _, school in schools.iterrows():
                        if 'الاسم' in school:
                            facility_name = school['الاسم']
                            # إزالة العنوان إذا كان موجودًا
                            if '|' in facility_name:
                                facility_name = facility_name.split('|')[0]
                            elif ':' in facility_name:
                                facility_name = facility_name.split(':')[0]
                            response += f"  - {facility_name.strip()}\n"
                    response += "\n"
                
                # الحصول على المستشفيات للحي
                hospitals = self.search_service.search_facilities(neighborhood_name, "مستشفيات", limit=1)
                if hospitals is not None and not hospitals.empty:
                    response += "• مستشفيات:\n"
                    for _, hospital in hospitals.iterrows():
                        if 'الاسم' in hospital:
                            facility_name = hospital['الاسم']
                            if '|' in facility_name:
                                facility_name = facility_name.split('|')[0]
                            elif ':' in facility_name:
                                facility_name = facility_name.split(':')[0]
                            response += f"  - {facility_name.strip()}\n"
                    response += "\n"
                
                # الحدائق
                parks = self.search_service.search_facilities(neighborhood_name, "حدائق", limit=1)
                if parks is not None and not parks.empty:
                    response += "• حدائق:\n"
                    for _, park in parks.iterrows():
                        if 'الاسم' in park:
                            facility_name = park['الاسم']
                            if '|' in facility_name:
                                facility_name = facility_name.split('|')[0]
                            elif ':' in facility_name:
                                facility_name = facility_name.split(':')[0]
                            response += f"  - {facility_name.strip()}\n"
                    response += "\n"
                
                # المولات
                malls = self.search_service.search_facilities(neighborhood_name, "مولات", limit=1)
                if malls is not None and not malls.empty:
                    response += "• مراكز تسوق:\n"
                    for _, mall in malls.iterrows():
                        if 'الاسم' in mall:
                            facility_name = mall['الاسم']
                            if '|' in facility_name:
                                facility_name = facility_name.split('|')[0]
                            elif ':' in facility_name:
                                facility_name = facility_name.split(':')[0]
                            response += f"  - {facility_name.strip()}\n"
                    response += "\n"
                
                # السوبرماركت
                supermarkets = self.search_service.search_facilities(neighborhood_name, "سوبرماركت", limit=1)
                if supermarkets is not None and not supermarkets.empty:
                    response += "• سوبرماركت:\n"
                    for _, supermarket in supermarkets.iterrows():
                        if 'الاسم' in supermarket:
                            facility_name = supermarket['الاسم']
                            if '|' in facility_name:
                                facility_name = facility_name.split('|')[0]
                            elif ':' in facility_name:
                                facility_name = facility_name.split(':')[0]
                            response += f"  - {facility_name.strip()}\n"
                    response += "\n"
                
                # إضافة معلومات المسافة إذا تم توفير الإحداثيات
                if user_latitude is not None and user_longitude is not None:
                    distance = self.location_integration.calculate_distance_to_neighborhood(
                        neighborhood_name, user_latitude, user_longitude
                    )
                    if distance is not None:
                        distance_message = self.location_integration.format_distance_message(neighborhood_name, distance)
                        response += f"\n\n{distance_message}"
                
                return response
                
            # إذا لم يتم التعرف على نوع الطلب، استخدم الطريقة القديمة
            user_message = f"معلومات عن {neighborhood_name}"  # رسالة افتراضية
            response = self.process_message(user_id, user_message, user_latitude, user_longitude)
            return response
                
        except Exception as e:
            logger.error(f"خطأ في معالجة الطلب الخاص: {str(e)}")
            return f"عذراً، حدث خطأ أثناء البحث عن معلومات في {neighborhood_name if neighborhood_name else 'هذا الحي'}."
                

    def save_helpus_data(self, data: dict) -> None:
      """
      حفظ بيانات استبيان "Help Us" في قاعدة البيانات.
      """
      self.db['Knowledge_base'].insert_one(data)

    def _handle_budget_query(self, message: str) -> Optional[str]:
        """
        معالجة الاستفسارات المتعلقة بالميزانية واقتراح حي مناسب.
        
        Args:
            message: رسالة المستخدم
            
        Returns:
            Optional[str]: رد منسق أو None إذا لم تكن الرسالة متعلقة بالميزانية
        """
        # أنماط لاستخراج الميزانية أو الراتب
        budget_patterns = [
            r'ابحث عن حي مناسب لميزانيتي حيث ان راتبي (\d+[,\d]*)',
            r'حي مناسب لراتب (\d+[,\d]*)',
            r'حي يناسب ميزانية (\d+[,\d]*)',
            r'ابحث عن حي يناسب راتب (\d+[,\d]*)',
            r'اقترح حي لراتب (\d+[,\d]*)',
            r'راتبي (\d+[,\d]*)',
            r'دخلي (\d+[,\d]*) ريال',
            r'ميزانيتي (\d+[,\d]*)'
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message)
            if match:
                # استخراج قيمة الميزانية/الراتب
                budget_str = match.group(1).replace(',', '')
                try:
                    budget = int(budget_str)
                    logger.info(f"تم العثور على استفسار ميزانية بقيمة: {budget}")
                    
                    # تحديد فئة الدخل
                    income_category = None
                    if budget < 5000:
                        income_category = "منخفض"
                    elif budget < 10000:
                        income_category = "منخفض إلى متوسط"
                    elif budget < 15000:
                        income_category = "متوسط"
                    elif budget < 25000:
                        income_category = "متوسط إلى مرتفع"
                    else:
                        income_category = "مرتفع"
                    
                    # تحديد الحي المناسب بناءً على فئة الدخل
                    recommended_neighborhoods = []
                    all_neighborhoods = self.data_loader.get_available_neighborhoods()
                    
                    for neighborhood in all_neighborhoods:
                        neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood)
                        if not neighborhood_info:
                            continue
                            
                        # البحث عن معلومات مستوى الأسعار
                        if "مستوى_الأسعار" in neighborhood_info:
                            price_level = neighborhood_info["مستوى_الأسعار"]
                            
                            if income_category == "منخفض" and "منخفض" in str(price_level).lower():
                                recommended_neighborhoods.append(neighborhood)
                            elif income_category == "منخفض إلى متوسط" and ("منخفض" in str(price_level).lower() or "متوسط" in str(price_level).lower()):
                                recommended_neighborhoods.append(neighborhood)
                            elif income_category == "متوسط" and "متوسط" in str(price_level).lower():
                                recommended_neighborhoods.append(neighborhood)
                            elif income_category == "متوسط إلى مرتفع" and ("متوسط" in str(price_level).lower() or "مرتفع" in str(price_level).lower()):
                                recommended_neighborhoods.append(neighborhood)
                            elif income_category == "مرتفع" and "مرتفع" in str(price_level).lower():
                                recommended_neighborhoods.append(neighborhood)
                    
                    # إذا لم يتم العثور على أحياء مناسبة، اقترح بعض الأحياء العامة
                    if not recommended_neighborhoods and all_neighborhoods:
                        # اختيار بعض الأحياء العشوائية كتوصيات
                        import random
                        sample_size = min(3, len(all_neighborhoods))
                        recommended_neighborhoods = random.sample(all_neighborhoods, sample_size)
                    
                    if recommended_neighborhoods:
                        # اختيار حي واحد كتوصية رئيسية
                        main_recommendation = recommended_neighborhoods[0]
                        
                        # بناء رد مفصل
                        response = self._build_detailed_neighborhood_response(main_recommendation)
                        
                        # إضافة تفاصيل عن التكلفة المقدرة للسكن
                        monthly_rent = 0
                        if budget < 10000:
                            monthly_rent = budget * 0.3  # 30% من الدخل للسكن للدخل المنخفض
                        else:
                            monthly_rent = budget * 0.25  # 25% من الدخل للسكن للدخل المتوسط والمرتفع
                        
                        formatted_rent = "{:,.0f}".format(monthly_rent)
                        response += f"\n\nبناءً على راتبك البالغ {'{:,.0f}'.format(budget)} ريال، يمكنك تخصيص حوالي {formatted_rent} ريال شهرياً للسكن، وهو ما يتناسب مع أسعار العقارات في {main_recommendation}."
                        
                        # إضافة توصيات بديلة إذا وجدت
                        if len(recommended_neighborhoods) > 1:
                            alternative_recommendations = recommended_neighborhoods[1:3]  # أقصى 2 أحياء بديلة
                            formatted_alternatives = "، ".join(alternative_recommendations)
                            response += f" يمكنك أيضاً النظر في أحياء بديلة مثل {formatted_alternatives} التي تتناسب مع ميزانيتك."
                        
                        return response
                    else:
                        return "عذراً، لم أتمكن من العثور على أحياء محددة تتناسب مع ميزانيتك. يرجى تزويدي بمزيد من المعلومات عن احتياجاتك السكنية، مثل المنطقة المفضلة أو المرافق المطلوبة، لمساعدتك بشكل أفضل."
                    
                except ValueError:
                    # إذا كان هناك خطأ في تحويل النص إلى رقم
                    logger.warning(f"خطأ في استخراج الميزانية: {budget_str}")
        
        return None


    
            

