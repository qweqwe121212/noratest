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
        معالجة رسالة المستخدم وإرجاع الرد المناسب.
        
        Args:
            user_id: معرف المستخدم
            user_message: رسالة المستخدم
            user_latitude: خط العرض للمستخدم (اختياري)
            user_longitude: خط الطول للمستخدم (اختياري)
            
        Returns:
            str: الرد المناسب
        """
        try:
            # التحقق من أن الرسالة نصية
            if not user_message or not isinstance(user_message, str):
                response = "كيف يمكنني مساعدتك في البحث عن عقار أو حي مناسب أو المرافق المتوفرة؟"
                self.add_to_history(user_id, "", response)
                return response
            
            # تنظيف الرسالة
            cleaned_message = user_message.strip()
            if not cleaned_message:
                response = "كيف يمكنني مساعدتك في البحث عن عقار أو حي مناسب أو المرافق المتوفرة؟"
                self.add_to_history(user_id, cleaned_message, response)
                return response
                
            # التحقق مما إذا كان استفسار عن أفضل/أسوأ حي
            best_worst_response = self._handle_best_worst_neighborhood_query(cleaned_message)
            if best_worst_response:
                self.add_to_history(user_id, cleaned_message, best_worst_response)
                return best_worst_response
            
            # التحقق من الأحياء المذكورة في الرسالة
            mentioned_neighborhood = None
            for neighborhood in self.data_loader.get_available_neighborhoods():
                if neighborhood in cleaned_message:
                    mentioned_neighborhood = neighborhood
                    break
                    
            # التحقق مما إذا كان طلب عرض جميع المرافق في حي محدد
            if mentioned_neighborhood:
                all_facilities_response = self._handle_show_all_facilities(cleaned_message, mentioned_neighborhood)
                if all_facilities_response:
                    self.add_to_history(user_id, cleaned_message, all_facilities_response)
                    return all_facilities_response
            
            # التحقق مما إذا كانت الرسالة قصيرة (مثل "نعم"، "المزيد"، إلخ)
            # والتعامل معها باستخدام سياق المحادثة السابقة إذا لزم الأمر
            short_response_result = self._handle_short_response(user_id, cleaned_message)
            if short_response_result:
                return short_response_result
            
            # تحليل الاستعلام باستخدام معالج الاستعلامات
            query_analysis = self.query_processor.analyze_query(cleaned_message)
            logger.info(f"تحليل الاستعلام: {query_analysis}")
            
            # متغير لتخزين الحي الموصى به إذا وجد
            recommended_neighborhood = None
            
            # معالجة البحث عن سكن قرب مرافق محددة
            if query_analysis['query_type'] == 'housing_search' and 'proximity_facilities' in query_analysis['entities']:
                response = self._handle_housing_with_facilities(query_analysis, cleaned_message, user_latitude, user_longitude)
            
            # معالجة الاستعلام بناءً على نوعه
            elif query_analysis['query_type'] == 'neighborhood_info':
                # طلب معلومات حول حي محدد
                neighborhood_name = query_analysis['entities'].get('neighborhood')
                if neighborhood_name:
                    recommended_neighborhood = neighborhood_name
                    response = self.formatter.format_neighborhood_response(neighborhood_name)
            
            elif query_analysis['query_type'] == 'neighborhood_recommendation':
                # طلب توصية حي
                if 'neighborhood' in query_analysis['entities']:
                    # إذا تم تحديد حي معين في الطلب
                    recommended_neighborhood = query_analysis['entities']['neighborhood']
                    response = self.formatter.format_neighborhood_response(recommended_neighborhood)
                else:
                    # استخدام محرك التوصيات للحصول على حي مناسب
                    recommended_neighborhood = self.recommendation_service.get_recommended_neighborhood(cleaned_message)
                    response = self.formatter.format_neighborhood_response(recommended_neighborhood)
            
            elif query_analysis['query_type'] == 'neighborhood_facilities':
                # طلب معلومات حول مرافق في حي معين
                neighborhood_name = query_analysis['entities'].get('neighborhood')
                facility_type = query_analysis['entities'].get('facility_type')
                
                if neighborhood_name:
                    recommended_neighborhood = neighborhood_name
                    if facility_type:
                        # إذا تم تحديد نوع المرفق، عرض معلومات مختصرة
                        facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                        response = self._summarize_facilities(facility_info, neighborhood_name, facility_type)
                    else:
                        # عرض نظرة عامة عن المرافق
                        response = f"إليك أبرز المرافق في {neighborhood_name}:\n\n"
                        
                        # إضافة 1-2 مرفق من كل نوع
                        for facility_type in ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]:
                            facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                            if "لم يتم العثور" not in facility_info:
                                # استخراج 1-2 مرفق فقط
                                summarized = self._extract_sample_facilities(facility_info, 2)
                                if summarized:
                                    facility_plural = {
                                        "مدرسة": "المدارس",
                                        "مستشفى": "المستشفيات والمراكز الطبية",
                                        "حديقة": "الحدائق والمتنزهات",
                                        "سوبرماركت": "محلات السوبرماركت",
                                        "مول": "المولات ومراكز التسوق"
                                    }.get(facility_type, facility_type)
                                    response += f"أبرز {facility_plural}:\n{summarized}\n\n"
                        
                        response += "للاطلاع على قائمة كاملة بالمرافق، يمكنك أن تسأل عن نوع محدد مثل 'أين توجد المدارس في هذا الحي؟'"
                else:
                    response = "يرجى تحديد الحي الذي تريد معرفة المرافق فيه."
            
            elif query_analysis['query_type'] == 'facility_location':
                # سؤال عن موقع مرفق محدد
                facility_name = query_analysis['entities'].get('facility_name')
                facility_type = query_analysis['entities'].get('facility_type')
                
                if facility_name and facility_type:
                    # تحديد ملف CSV المناسب
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
                    
                    if csv_file:
                        response = self.search_service.search_entity(csv_file, facility_name)
            
            elif query_analysis['query_type'] == 'facility_search':
                # بحث عن مرفق باسمه
                facility_name = query_analysis['entities'].get('facility_name')
                facility_type = query_analysis['entities'].get('facility_type')
                
                if facility_name and facility_type:
                    # تحديد ملف CSV المناسب
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
                    
                    if csv_file:
                        response = self.search_service.search_entity(csv_file, facility_name)
            else:
                # إذا لم يتم التعرف على نوع الاستعلام بواسطة معالج الاستعلامات، 
                # استخدم آلية المعالجة القديمة
                response = self._fallback_processing(cleaned_message)
                    
                # التحقق مما إذا كان لدينا حي موصى به من المعالجة الاحتياطية
                if "حي" in response:
                    # محاولة استخراج اسم الحي من الرسالة
                    for neighborhood in self.data_loader.get_available_neighborhoods():
                        if neighborhood in response:
                            recommended_neighborhood = neighborhood
                            break
            
            # إذا تم التوصية بحي، قم بحساب وإضافة معلومات المسافة
            if recommended_neighborhood:
                distance = None
                
                # إذا تم توفير الإحداثيات من المستخدم، استخدمها
                if user_latitude is not None and user_longitude is not None:
                    distance = self._calculate_distance_to_neighborhood(
                        recommended_neighborhood, user_latitude, user_longitude
                    )
                else:
                    # محاولة استخدام طريقة تحديد الموقع القائمة على IP كاحتياطي
                    distance = self.location_integration.calculate_distance_to_neighborhood(recommended_neighborhood)
                
                # إضافة معلومات المسافة إلى الرد إذا تم حسابها
                if distance is not None:
                    distance_message = self.location_integration.format_distance_message(recommended_neighborhood, distance)
                    response += f"\n\n{distance_message}"
            
            # إضافة المحادثة إلى التاريخ
            self.add_to_history(user_id, cleaned_message, response)
            
            return response
                
        except Exception as e:
            logger.error(f"خطأ في معالجة الرسالة: {str(e)}")
            response = "عذراً، حدث خطأ ما. هل يمكنك إعادة صياغة طلبك من فضلك؟"
            self.add_to_history(user_id, user_message, response)
            return response


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
        تلخيص معلومات المرافق وعرض عدد قليل منها
        
        Args:
            facility_info: النص الكامل لمعلومات المرافق
            neighborhood_name: اسم الحي
            facility_type: نوع المرفق
            
        Returns:
            str: معلومات ملخصة عن المرافق
        """
        # التحقق من وجود مرافق
        if "لم يتم العثور" in facility_info:
            return f"لم يتم العثور على {facility_type} في {neighborhood_name}."
        
        # تحديد الاسم الجماعي المناسب للمرفق
        facility_plural = {
            "مدرسة": "المدارس",
            "مستشفى": "المستشفيات والمراكز الطبية",
            "حديقة": "الحدائق والمتنزهات",
            "سوبرماركت": "محلات السوبرماركت",
            "مول": "المولات ومراكز التسوق"
        }.get(facility_type, facility_type)
        
        # عنوان الرد
        response = f"إليك أبرز {facility_plural} في حي {neighborhood_name}:\n\n"
        
        # استخراج 2-3 مرافق فقط
        sample_facilities = self._extract_sample_facilities(facility_info, 2)
        if sample_facilities:
            response += sample_facilities + "\n\n"
        
        # استخراج عدد المرافق الكلي من النص
        total_count = 0
        count_match = re.search(r'\((\d+)\)', facility_info)
        if count_match:
            total_count = int(count_match.group(1))
        
        # إضافة معلومات إحصائية
        if total_count > 2:
            response += f"يوجد إجمالي {total_count} من {facility_plural} في الحي.\n"
        
        # إضافة تلميح
        response += f"لعرض القائمة الكاملة، اكتب 'اعرض جميع {facility_plural} في {neighborhood_name}'"
        
        return response

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
        بناء استجابة مفصلة للحي تتضمن المرافق والمزايا
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            str: الاستجابة المفصلة
        """
        # البحث عن المرافق في الحي
        facilities_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, None)
        
        # دمج المعلومات مع بعض التفاصيل الإضافية
        extra_info = f"إليك المزيد من المعلومات عن {neighborhood_name}:\n\n"
        
        # إضافة معلومات المزايا من قاعدة البيانات
        benefits = self.data_loader.get_neighborhood_benefits(neighborhood_name)
        if benefits and len(benefits) > 0:
            extra_info += "تجارب السكان السابقين:\n"
            for i, benefit in enumerate(benefits[:3], 1):  # أخذ أول 3 مزايا فقط
                extra_info += f"{i}. {benefit}\n"
            extra_info += "\n"
        
        # إضافة معلومات المرافق
        if "لم يتم العثور" not in facilities_info:
            extra_info += facilities_info
        else:
            extra_info += "المرافق المتوفرة في الحي:\n"
            
            # البحث عن المرافق المختلفة بشكل منفصل
            for facility_type in ["مدرسة", "مستشفى", "حديقة", "سوبرماركت", "مول"]:
                facility_info = self.search_service.find_facilities_in_neighborhood(neighborhood_name, facility_type)
                if "لم يتم العثور" not in facility_info:
                    extra_info += f"\n{facility_info}\n"
        
        # إضافة معلومات عن الأسعار إذا كانت متاحة
        neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
        if neighborhood_info:
            price_info = []
            
            # البحث عن معلومات الأسعار - تحديث أسماء الحقول لتتوافق مع البيانات الفعلية
            price_fields = [
                {"key": "price_of_meter_Apartment", "label": "سعر المتر للشقق"},
                {"key": "price_of_meter_Villas", "label": "سعر المتر للفلل"},
                {"key": "average_rent", "label": "متوسط الإيجار"},
                {"key": "price_of_meter_Commercial", "label": "سعر المتر التجاري"},
                # أسماء بديلة بالعربية
                {"key": "سعر_المتر_للشقق", "label": "سعر المتر للشقق"},
                {"key": "سعر_المتر_للفلل", "label": "سعر المتر للفلل"},
                {"key": "متوسط_الإيجار", "label": "متوسط الإيجار"},
                {"key": "سعر_المتر_التجاري", "label": "سعر المتر التجاري"}
            ]
            
            for field in price_fields:
                key = field["key"]
                if key in neighborhood_info and neighborhood_info[key]:
                    price_value = neighborhood_info[key]
                    
                    # تنسيق السعر
                    if isinstance(price_value, (int, float)):
                        formatted_price = "{:,}".format(int(price_value))
                        price_info.append(f"{field['label']}: {formatted_price} ريال")
                    else:
                        price_info.append(f"{field['label']}: {price_value}")
            
            if price_info:
                extra_info += "\nمعلومات الأسعار في الحي:\n"
                for info in price_info:
                    extra_info += f"• {info}\n"
        
        extra_info += "\nيمكنك السؤال عن تفاصيل أكثر مثل 'أين توجد مدارس في الحي' أو 'معلومات عن مستشفيات الحي'"
        
        return extra_info

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


    
            

