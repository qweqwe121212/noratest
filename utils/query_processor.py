"""
معالج الاستعلامات الذكي - تحليل استعلامات المستخدم وتصنيفها واستخراج المعلومات منها
"""

import re
import logging
from typing import Dict, Tuple, List, Optional, Any, Set

logger = logging.getLogger(__name__)

class QueryProcessor:
    """
    فئة لمعالجة استعلامات المستخدم وتحليلها وتصنيفها بشكل ذكي
    """
    
    def __init__(self, available_neighborhoods: List[str]):
        """
        إنشاء معالج الاستعلامات
        
        Args:
            available_neighborhoods: قائمة الأحياء المتاحة في النظام
        """
        self.available_neighborhoods = available_neighborhoods
        
        # التعبيرات النمطية للأحياء
        self.neighborhood_patterns = {
            'recommendation': [
                r'اقترح (?:لي|علي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'أقترح (?:لي|علي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'اقتراح (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'(?:أبي|أبغى|أريد|ابي|ابغى|اريد) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'معلومات عن (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'اين (?:يقع|تقع|هو|هي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'أين (?:يقع|تقع|هو|هي) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            ],
            'general_info': [
                r'ما (?:هي|هو) (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
                r'كيف (?:حي|منطقة) ([\u0600-\u06FF\s]+?)(?:\.|$|\s)',
            ],
            'living': [
                r'(?:أسكن|اسكن|أعيش|اعيش|مقيم) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
                r'(?:أفضل|افضل|ارغب|أرغب) (?:السكن|العيش) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
                r'(?:أبحث|ابحث) عن عقار في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
                r'(?:حي|منطقة) ([\u0600-\u06FF\s]+?) (?:للسكن|مناسب|مناسبة|جيدة|جيد)(?:\.|\s|$)'
            ],
            'work': [
                r'(?:مكان عملي|أعمل|اعمل|وظيفتي) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)',
                r'(?:مقر العمل|مكتبي|شركتي) في (?:حي|منطقة)? ([\u0600-\u06FF\s]+?)(?:\.|\s|$)'
            ]
        }
        
        # التعبيرات النمطية للمرافق
        self.facility_patterns = {
            'general': [
                r'اين (?:توجد|يوجد|تقع|يقع) ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
                r'أين (?:توجد|يوجد|تقع|يقع) ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
                r'(?:موقع|مكان|عنوان) ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
                r'ابحث عن ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
                r'أبحث عن ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
                r'(?:دلني|دلوني|ارشدني|أرشدني) (?:على|عن|الى|إلى) ([\u0600-\u06FF\s]+?)(?:\?|$|\s|\.|في)',
            ],
            'search_by_name': [
                r'^([\u0600-\u06FF\s]+)$',  # اسم مرفق وحيد في السطر
            ]
        }
        
        # أنواع المرافق والكلمات المفتاحية المرتبطة بها
        self.facility_keywords = {
            "مدرسة": [
                "مدرسة", "مدارس", "روضة", "روضات", "كلية", "كليات", "معهد", "معاهد", "جامعة", "جامعات",
                "ابتدائية", "متوسطة", "ثانوية", "تعليم", "دراسة", "أكاديمية"
            ],
            "مستشفى": [
                "مستشفى", "مستشفيات", "مركز طبي", "مراكز طبية", "عيادة", "عيادات", "مستوصف", "مستوصفات",
                "مجمع طبي", "مجمعات طبية", "صحة", "طبي", "علاج", "طوارئ", "مختبر", "صيدلية"
            ],
            "حديقة": [
                "حديقة", "حدائق", "منتزه", "منتزهات", "متنزه", "متنزهات", "ملعب", "ملاعب", 
                "ساحة", "ساحات", "مساحة خضراء", "مساحات خضراء", "بارك", "حدائق عامة"
            ],
            "سوبرماركت": [
                "سوبرماركت", "هايبر", "هايبرماركت", "ماركت", "سوق", "أسواق", "بقالة", "محل", "متجر",
                "دكان", "تموينات", "جمعية", "مخبز", "مخابز", "بقالات", "محلات"
            ],
            "مول": [
                "مول", "مولات", "مركز تسوق", "مراكز تسوق", "مجمع تجاري", "مجمعات تجارية", 
                "بلازا", "سوق تجاري", "أسواق تجارية", "سنتر", "مجمع", "معرض", "معارض"
            ]
        }
        
        # الكلمات المفتاحية لأنواع العقارات
        self.property_keywords = {
            "شقة": ["شقة", "شقق", "دور", "دوبلكس", "استديو", "روف", "ملحق", "غرفة"],
            "فيلا": ["فيلا", "فلل", "قصر", "شاليه", "استراحة", "بيت"],
            "أرض": ["أرض", "قطعة", "أراضي", "مخطط"],
            "تجاري": ["محل", "عمارة", "مكتب", "معرض", "مستودع", "تجاري", "مول"]
        }
        
        # الكلمات المفتاحية التي تشير إلى الإيجار أو الشراء
        self.transaction_keywords = {
            "إيجار": ["إيجار", "ايجار", "استئجار", "أجرة", "اجار", "ايجارات", "للايجار", "للإيجار", "مستأجر"],
            "تمليك": ["تمليك", "شراء", "بيع", "تملك", "امتلاك", "ملك", "للبيع", "مالك", "تملك"]
        }
        
        # الكلمات المفتاحية التي تشير إلى طلب توصية حي
        self.neighborhood_recommendation_keywords = [
            "اقترح", "أقترح", "توصية", "أوصي", "رأيك", "رأيكم", "تنصح", "تنصحون", "أفضل حي", "افضل حي",
            "أنسب حي", "انسب حي", "حي مناسب", "أفضل منطقة", "افضل منطقة", "أين أسكن", "اين اسكن",
            "دلني", "خبرني", "اخبرني", "انصحني"
        ]
        
        # كلمات مفتاحية للبحث عن سكن
        self.housing_search_keywords = [
            "أبحث عن", "ابحث عن", "أريد", "اريد", "أبغى", "ابغى", "محتاج", "بحاجة", 
            "أدور على", "ادور على", "عقار", "سكن", "شقة", "فيلا", "بيت", "منزل", "استأجر", "اشتري"
        ]
        
        # كلمات المسافة والقرب
        self.proximity_keywords = [
            "قريب من", "قريبة من", "بالقرب من", "جنب", "بجانب", "جوار", "بجوار", "حول"
        ]
    
    def analyze_query(self, user_message: str) -> Dict[str, Any]:
        """
        تحليل استعلام المستخدم وتحديد نوعه والمعلومات المستخرجة منه
        
        Args:
            user_message: استعلام المستخدم
            
        Returns:
            Dict[str, Any]: نتائج التحليل بما في ذلك نوع الاستعلام والكيانات المستخرجة
        """
        if not user_message:
            return {'query_type': 'unknown'}
        
        result = {
            'query_type': 'unknown',
            'entities': {},
            'intents': set()  # مجموعة من النوايا - يمكن أن يحتوي الاستعلام على عدة نوايا
        }
        
        # تنظيف الرسالة
        clean_message = user_message.strip()
        
        # البحث عن أنماط محددة للطلبات بحي يحتوي على خصائص معينة أو في موقع معين
        neighborhood_direction_patterns = [
            r'دلني على حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            r'دلني على حي قريب من ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            r'دلني على حي ([\u0600-\u06FF\s]+?) وفيه ([\u0600-\u06FF\s]+)',
            r'ارشدني إلى حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            r'أرشدني إلى حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            r'اقترح لي حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
            r'أقترح لي حي ([\u0600-\u06FF\s]+?)(?:\?|؟|$|\s)',
        ]
        
        for pattern in neighborhood_direction_patterns:
            match = re.search(pattern, clean_message)
            if match:
                # هذا طلب توصية بحي مع معايير
                logger.info(f"تم تحديد طلب توصية بحي: {match.group(1)}")
                result['query_type'] = 'neighborhood_recommendation'
                result['intents'].add('neighborhood_recommendation')
                
                # استخراج معايير المكان
                if 'قريب من' in clean_message or 'بالقرب من' in clean_message:
                    result['entities']['location_preference'] = True
                    # محاولة استخراج المنطقة المطلوبة (مثل "الشمال", "الجنوب", إلخ)
                    location_patterns = [
                        r'قريب من (?:منطقة |)([\u0600-\u06FF]+)',
                        r'بالقرب من (?:منطقة |)([\u0600-\u06FF]+)'
                    ]
                    for loc_pattern in location_patterns:
                        loc_match = re.search(loc_pattern, clean_message)
                        if loc_match:
                            location = loc_match.group(1).strip()
                            result['entities']['preferred_location'] = location
                            break
                
                # تحليل معايير المرافق
                if 'وفيه' in clean_message or 'يوجد فيه' in clean_message or 'فيه' in clean_message:
                    facility_patterns = [
                        r'وفيه ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                        r'يوجد فيه ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)',
                        r'فيه ([\u0600-\u06FF\s]+)(?:\?|؟|$|\s)'
                    ]
                    
                    for fac_pattern in facility_patterns:
                        fac_match = re.search(fac_pattern, clean_message)
                        if fac_match:
                            facilities_text = fac_match.group(1).strip()
                            
                            # تحديد نوع المرفق من النص
                            for facility_type, keywords in self.facility_keywords.items():
                                if any(keyword in facilities_text for keyword in keywords):
                                    result['entities']['facility_type'] = facility_type
                                    result['entities']['facilities_text'] = facilities_text
                                    break
                            break
                
                # استخراج معلومات شخصية إذا وجدت
                person_info = self._extract_person_info(clean_message)
                if person_info:
                    result['entities'].update(person_info)
                
                return result
        
        # البحث عن أنماط معينة للطلبات بحي يحتوي على خصائص معينة
        special_recommendation_patterns = [
            r'اقترح (?:لي|علي) حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'أقترح (?:لي|علي) حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'أريد حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'اريد حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)',
            r'ابحث عن حي (?:فيه|فيها|به|بها) ([\u0600-\u06FF\s]+)'
        ]
        
        for pattern in special_recommendation_patterns:
            match = re.search(pattern, clean_message)
            if match:
                # هذا طلب توصية حي مع خصائص معينة
                logger.info(f"تم تحديد طلب توصية حي مع خصائص: {match.group(1)}")
                result['query_type'] = 'neighborhood_recommendation'
                result['intents'].add('neighborhood_recommendation')
                
                # استخراج الخصائص المطلوبة
                facilities_text = match.group(1)
                
                # تحديد نوع المرفق من النص
                proximity_facilities = []
                for facility_type, keywords in self.facility_keywords.items():
                    if any(keyword in facilities_text for keyword in keywords):
                        proximity_facilities.append({
                            'text': facilities_text,
                            'type': facility_type
                        })
                        break
                
                if proximity_facilities:
                    result['entities']['proximity_facilities'] = proximity_facilities
                    
                # استخراج معلومات شخصية
                person_info = self._extract_person_info(clean_message)
                if person_info:
                    result['entities'].update(person_info)
                    
                # استخراج الميزانية
                budget = self._extract_budget(clean_message)
                if budget:
                    result['entities']['budget'] = budget
                    
                return result
        
        # تحديد ما إذا كان الاستعلام عن بحث عن سكن
        if self._is_housing_search_query(clean_message):
            result['query_type'] = 'housing_search'
            result['intents'].add('housing_search')
            
            # استخراج معلومات السكن
            housing_info = self._extract_housing_info(clean_message)
            if housing_info:
                result['entities'].update(housing_info)
            
            # استخراج الميزانية
            budget = self._extract_budget(clean_message)
            if budget:
                result['entities']['budget'] = budget
            
            # استخراج معلومات شخصية
            person_info = self._extract_person_info(clean_message)
            if person_info:
                result['entities'].update(person_info)
                
            # تحديد الأحياء المذكورة
            neighborhood_info = self._extract_neighborhood_info(clean_message)
            if neighborhood_info:
                result['entities']['neighborhood'] = neighborhood_info['name']
                
            # استخراج المرافق المطلوب القرب منها
            proximity_facilities = self._extract_proximity_facilities(clean_message)
            if proximity_facilities:
                result['entities']['proximity_facilities'] = proximity_facilities
                
            return result
        
        # البحث عن استفسارات "أين توجد" أو "أين يقع" للمرافق
        facility_entity = self._extract_facility_from_question(clean_message)
        if facility_entity:
            result['query_type'] = 'facility_location'
            result['intents'].add('facility_search')
            result['entities']['facility_name'] = facility_entity['name']
            result['entities']['facility_type'] = facility_entity['type']
            return result
        
        # التحقق مما إذا كانت الرسالة مجرد اسم مرفق وحيد (سطر واحد)
        if len(clean_message.split()) <= 5 and '\n' not in clean_message:
            facility_type = self._determine_facility_type(clean_message)
            if facility_type:
                result['query_type'] = 'facility_search'
                result['intents'].add('facility_search')
                result['entities']['facility_name'] = clean_message
                result['entities']['facility_type'] = facility_type
                return result
        
        # البحث عن طلب صريح للحصول على معلومات حول حي معين
        neighborhood_info = self._extract_neighborhood_info(clean_message)
        if neighborhood_info and neighborhood_info['type'] == 'recommendation':
            result['query_type'] = 'neighborhood_info'
            result['intents'].add('neighborhood_info')
            result['entities']['neighborhood'] = neighborhood_info['name']
            return result
        
        # البحث عن طلب توصية حي
        if any(keyword in clean_message for keyword in self.neighborhood_recommendation_keywords):
            result['query_type'] = 'neighborhood_recommendation'
            result['intents'].add('neighborhood_recommendation')
            
            # محاولة استخراج حي محدد إذا كان موجوداً
            if neighborhood_info:
                result['entities']['neighborhood'] = neighborhood_info['name']
                
            # استخراج معلومات إضافية للحصول على توصية دقيقة
            person_info = self._extract_person_info(clean_message)
            if person_info:
                result['entities'].update(person_info)
            
            # استخراج المرافق المطلوب القرب منها
            proximity_facilities = self._extract_proximity_facilities(clean_message)
            if proximity_facilities:
                result['entities']['proximity_facilities'] = proximity_facilities
                
            # استخراج الميزانية
            budget = self._extract_budget(clean_message)
            if budget:
                result['entities']['budget'] = budget
                
            return result
        
        # فحص ما إذا كان النص يذكر مرافق حي معين
        facility_keywords = [
            'مدرسة', 'مدارس', 'مستشفى', 'مستشفيات', 'حديقة', 'حدائق', 
            'سوبرماركت', 'مول', 'مولات', 'مرافق', 'خدمات'
        ]
        
        has_facility_keywords = any(keyword in clean_message for keyword in facility_keywords)
        
        if has_facility_keywords and neighborhood_info:
            result['query_type'] = 'neighborhood_facilities'
            result['intents'].add('neighborhood_facilities')
            result['entities']['neighborhood'] = neighborhood_info['name']
            
            # تحديد نوع المرفق إذا كان محدداً
            for facility_type, keywords in self.facility_keywords.items():
                if any(keyword in clean_message for keyword in keywords):
                    result['entities']['facility_type'] = facility_type
                    break
                    
            return result
        
        # إذا لم يتم تصنيف الاستعلام حتى الآن، تحقق مما إذا كان يحتوي على معلومات شخصية
        person_info = self._extract_person_info(clean_message)
        if person_info and len(person_info) >= 2:  # إذا كانت هناك معلومات كافية عن الشخص
            result['query_type'] = 'neighborhood_recommendation'
            result['intents'].add('neighborhood_recommendation')
            result['entities'].update(person_info)
            return result
        
        # إذا وصلنا إلى هنا، فقد نحتاج إلى مزيد من المعلومات
        return result
    
    def _is_housing_search_query(self, message: str) -> bool:
        """
        تحديد ما إذا كان الاستعلام متعلقاً بالبحث عن سكن
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            bool: صح إذا كان الاستعلام متعلقاً بالبحث عن سكن
        """
        # البحث عن كلمات مفتاحية للبحث عن سكن
        if any(keyword in message for keyword in self.housing_search_keywords):
            # التحقق من وجود نوع عقار
            for property_type, keywords in self.property_keywords.items():
                if any(keyword in message for keyword in keywords):
                    return True
            
            # التحقق من وجود كلمات إيجار أو تمليك
            for transaction_type, keywords in self.transaction_keywords.items():
                if any(keyword in message for keyword in keywords):
                    return True
            
            # التحقق من وجود كلمة "سكن" أو "عقار" أو "منزل"
            if any(word in message for word in ["سكن", "عقار", "منزل", "بيت", "شقة", "فيلا"]):
                return True
        
        # أنماط للبحث عن سكن
        housing_patterns = [
            r'(?:أبحث|ابحث) عن (?:سكن|شقة|فيلا|بيت|منزل|عقار)',
            r'(?:أريد|اريد|أبغى|ابغى) (?:سكن|شقة|فيلا|بيت|منزل|عقار)',
            r'(?:أبحث|ابحث) عن مكان للسكن',
            r'(?:أريد|اريد|أبغى|ابغى) مكان للسكن'
        ]
        
        for pattern in housing_patterns:
            if re.search(pattern, message):
                return True
                
        return False
    
    def _extract_housing_info(self, message: str) -> Dict[str, Any]:
        """
        استخراج معلومات السكن المطلوب من الرسالة
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            Dict[str, Any]: معلومات السكن المستخرجة
        """
        info = {}
        
        # تحديد نوع العقار المطلوب
        for property_type, keywords in self.property_keywords.items():
            if any(keyword in message for keyword in keywords):
                info['property_type'] = property_type
                break
        
        # تحديد نوع المعاملة (إيجار أو تمليك)
        for transaction_type, keywords in self.transaction_keywords.items():
            if any(keyword in message for keyword in keywords):
                info['transaction_type'] = transaction_type
                break
        
        # استخراج عدد الغرف المطلوب
        room_match = re.search(r'(\d+) (?:غرف|غرفة|غرف نوم|غرفة نوم)', message)
        if room_match:
            info['rooms'] = int(room_match.group(1))
        
        # استخراج المساحة المطلوبة
        area_match = re.search(r'(?:مساحة|مساحته|مساحتها) (\d+)', message)
        if area_match:
            info['area'] = int(area_match.group(1))
        
        # استخراج الطابق المطلوب
        floor_match = re.search(r'(?:الطابق|دور|الدور) (?:ال)?(\d+|أرضي|ارضي|الأرضي|الارضي)', message)
        if floor_match:
            floor = floor_match.group(1)
            if floor in ['أرضي', 'ارضي', 'الأرضي', 'الارضي']:
                info['floor'] = 0
            else:
                info['floor'] = int(floor)
        
        return info
    
    def _extract_budget(self, message: str) -> Optional[int]:
        """
        استخراج الميزانية من الرسالة
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            Optional[int]: الميزانية المستخرجة أو None إذا لم يتم العثور عليها
        """
        # أنماط الميزانية المختلفة
        budget_patterns = [
            r'(?:ميزانية|الميزانية|ميزانيتي|ميزانيه|بحدود|بميزانية) (?:قدرها|مقدارها|تبلغ|حوالي|تقريبا|تقريباً)? (\d+(?:,\d+)?(?:\.\d+)?) (?:ريال|ألف|الف|مليون|ريال سعودي|ر.س)',
            r'(\d+(?:,\d+)?(?:\.\d+)?) (?:ريال|ألف|الف|مليون|ريال سعودي|ر.س)',
            r'(\d+(?:,\d+)?(?:\.\d+)?) (?:ميزانية|ميزانيتي)',
            r'(?:أقصى|اقصى|الأقصى|الاقصى) (?:سعر|حد|ميزانية) (?:هو|هي)? (\d+(?:,\d+)?(?:\.\d+)?)'
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message)
            if match:
                # معالجة القيمة المستخرجة
                budget_str = match.group(1).replace(',', '')
                
                # تحديد الوحدة المستخدمة (ريال، ألف، مليون)
                if 'ألف' in match.group(0) or 'الف' in match.group(0):
                    multiplier = 1000
                elif 'مليون' in match.group(0):
                    multiplier = 1000000
                else:
                    multiplier = 1
                
                try:
                    return int(float(budget_str) * multiplier)
                except (ValueError, TypeError):
                    return None
        
        return None
    
    def _extract_facility_from_question(self, message: str) -> Optional[Dict[str, str]]:
        """
        استخراج اسم المرفق من سؤال "أين توجد" أو سؤال مشابه
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            Optional[Dict[str, str]]: قاموس يحتوي على اسم المرفق ونوعه، أو None إذا لم يُعثر على مرفق
        """
        for pattern_type, patterns in self.facility_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    facility_name = match.group(1).strip()
                    
                    # تجاهل المطابقات القصيرة جداً أو الطويلة جداً
                    if len(facility_name) < 3 or len(facility_name) > 50:
                        continue
                    
                    # التحقق مما إذا كان الاسم المستخرج يتطابق مع اسم حي (لتجنب الالتباس)
                    is_neighborhood = False
                    for neighborhood in self.available_neighborhoods:
                        if neighborhood.replace("حي ", "") in facility_name:
                            is_neighborhood = True
                            break
                    
                    if not is_neighborhood:
                        facility_type = self._determine_facility_type(facility_name)
                        if facility_type:
                            return {
                                'name': facility_name,
                                'type': facility_type
                            }
        
        return None
    
    def _determine_facility_type(self, facility_name: str) -> Optional[str]:
        """
        تحديد نوع المرفق بناءً على اسمه
        
        Args:
            facility_name: اسم المرفق
            
        Returns:
            Optional[str]: نوع المرفق، أو None إذا لم يتم التعرف عليه
        """
        facility_name_lower = facility_name.lower()
        
        # إنشاء قائمة من الأنواع مع عدد تطابقات الكلمات المفتاحية
        matches = []
        
        for facility_type, keywords in self.facility_keywords.items():
            type_matches = 0
            for keyword in keywords:
                if keyword in facility_name_lower:
                    type_matches += 1
            
            if type_matches > 0:
                matches.append((facility_type, type_matches))
        
        # فرز بترتيب تنازلي حسب عدد التطابقات
        matches.sort(key=lambda x: x[1], reverse=True)
        
        if matches:
            return matches[0][0]  # إرجاع النوع ذو أكبر عدد تطابقات
        
        # فحص بعض التلميحات الشائعة في أسماء المرافق
        if any(hint in facility_name_lower for hint in ['مدرسة', 'مدارس', 'روضة']):
            return 'مدرسة'
        elif any(hint in facility_name_lower for hint in ['مستشفى', 'طبي', 'مركز صحي', 'عيادة']):
            return 'مستشفى'
        elif any(hint in facility_name_lower for hint in ['حديقة', 'منتزه', 'متنزه', 'بارك']):
            return 'حديقة'
        elif any(hint in facility_name_lower for hint in ['سوبرماركت', 'هايبر', 'أسواق', 'ماركت', 'مخابز']):
            return 'سوبرماركت'
        elif any(hint in facility_name_lower for hint in ['مول', 'مركز تسوق', 'بلازا', 'مجمع تجاري']):
            return 'مول'
        
        return None
    
    def _extract_neighborhood_info(self, message: str) -> Optional[Dict[str, str]]:
        """
        استخراج معلومات الحي من الرسالة
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            Optional[Dict[str, str]]: قاموس يحتوي على اسم الحي ونوع المعلومات، أو None إذا لم يُعثر على حي
        """
        for pattern_type, patterns in self.neighborhood_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    neighborhood = match.group(1).strip()
                    
                    # التحقق من وجود الحي في القائمة المتاحة
                    found_neighborhood = self._find_matching_neighborhood(neighborhood)
                    if found_neighborhood:
                        return {
                            'name': found_neighborhood,
                            'type': pattern_type
                        }
        
        # التحقق من وجود أي حي من القائمة في الرسالة
        for neighborhood in self.available_neighborhoods:
            clean_neighborhood = neighborhood.replace("حي ", "").strip()
            if clean_neighborhood in message:
                return {
                    'name': neighborhood,
                    'type': 'mention'
                }
        
        return None
    
    def _find_matching_neighborhood(self, neighborhood_name: str) -> Optional[str]:
        """
        البحث عن تطابق لاسم الحي في قائمة الأحياء المتاحة
        
        Args:
            neighborhood_name: اسم الحي المراد البحث عنه
            
        Returns:
            Optional[str]: اسم الحي المطابق، أو None إذا لم يُعثر على تطابق
        """
        # تنظيف اسم الحي
        clean_name = neighborhood_name.replace("حي ", "").strip()
        
        # أولاً البحث عن تطابق دقيق
        for neighborhood in self.available_neighborhoods:
            if neighborhood.replace("حي ", "").strip() == clean_name:
                return neighborhood
        
        # ثم البحث عن تطابق جزئي
        for neighborhood in self.available_neighborhoods:
            if clean_name in neighborhood.replace("حي ", "").strip():
                return neighborhood
        
        return None
    
    def _extract_person_info(self, message: str) -> Dict[str, Any]:
        """
        استخراج معلومات شخصية من الرسالة مثل العمر والحالة الاجتماعية والميزانية وما إلى ذلك
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            Dict[str, Any]: قاموس يحتوي على المعلومات المستخرجة
        """
        info = {}
        
        # استخراج العمر
        age_matches = [
            re.search(r'عمري (\d+)', message),
            re.search(r'أنا (?:في|ب|بعمر) (\d+)', message),
            re.search(r'عندي (\d+) (?:سنة|عام|سنه)', message),
            re.search(r'انا (\d+) (?:سنة|عام|سنه)', message)
        ]
        
        for match in age_matches:
            if match:
                info['age'] = int(match.group(1))
                break
        
        # استخراج الحالة الاجتماعية
        marital_status_matches = {
            'أعزب': ['اعزب', 'أعزب', 'عازب', 'غير متزوج'],
            'متزوج': ['متزوج', 'مرتبط'],
            'مطلق': ['مطلق', 'منفصل'],
            'أرمل': ['أرمل', 'ارمل']
        }
        
        for status, keywords in marital_status_matches.items():
            if any(keyword in message for keyword in keywords):
                info['marital_status'] = status
                break
        
        # استخراج عدد الأطفال
        children_match = re.search(r'(\d+) (?:أولاد|اطفال|أطفال|ابناء|أبناء|اولاد|طفل|ابن|ولد)', message)
        if children_match:
            info['children'] = int(children_match.group(1))
        
        # استخراج المساحة المطلوبة
        area_match = re.search(r'مساحة (?:عقاري|العقار|المطلوبة|السكن|الشقة|البيت|المنزل)? (\d+)(?:م|م2|متر|متر مربع)?', message)
        if area_match:
            info['area'] = int(area_match.group(1))
        
        # استخراج عدد الغرف
        rooms_match = re.search(r'(\d+) (?:غرف|غرفة)', message)
        if rooms_match:
            info['rooms'] = int(rooms_match.group(1))
        
        # استخراج عدد الحمامات
        bathroom_match = re.search(r'(\d+) (?:حمام|حمامات|دورة مياه|دورات مياه)', message)
        if bathroom_match:
            info['bathrooms'] = int(bathroom_match.group(1))
        
        # استخراج المنطقة المفضلة
        location_preferences = {
            'شمال': ['شمال', 'الشمال', 'الشمالية', 'شمالية'],
            'جنوب': ['جنوب', 'الجنوب', 'الجنوبية', 'جنوبية'],
            'شرق': ['شرق', 'الشرق', 'الشرقية', 'شرقية'],
            'غرب': ['غرب', 'الغرب', 'الغربية', 'غربية'],
            'وسط': ['وسط', 'الوسط', 'المركز', 'المركزية']
        }
        
        for location, keywords in location_preferences.items():
            if any(f"في {keyword}" in message.lower() for keyword in keywords):
                info['preferred_location'] = location
                break
            if any(f"منطقة {keyword}" in message.lower() for keyword in keywords):
                info['preferred_location'] = location
                break
            if any(f"{keyword} المدينة" in message.lower() for keyword in keywords):
                info['preferred_location'] = location
                break
        
        return info
    
    def _extract_proximity_facilities(self, message: str) -> List[Dict[str, str]]:
        """
        استخراج المرافق التي يرغب المستخدم في القرب منها
        
        Args:
            message: استعلام المستخدم
            
        Returns:
            List[Dict[str, str]]: قائمة بالمرافق المطلوب القرب منها
        """
        facilities = []
        
        # البحث عن كل عبارات القرب والمرافق المرتبطة بها
        for proximity_phrase in self.proximity_keywords:
            # بناء نمط للبحث عن "قريب من X" أو "بالقرب من X"
            pattern = f"{proximity_phrase} ([^\\.،,]*)"
            matches = re.finditer(pattern, message)
            
            for match in matches:
                facility_text = match.group(1).strip()
                
                # تحديد نوع المرفق من النص
                facility_type = None
                for type_name, keywords in self.facility_keywords.items():
                    if any(keyword in facility_text for keyword in keywords):
                        facility_type = type_name
                        break
                
                if facility_type:
                    facilities.append({
                        'text': facility_text,
                        'type': facility_type
                    })
        
        # البحث عن أسماء المرافق المباشرة
        for facility_type, keywords in self.facility_keywords.items():
            for keyword in keywords:
                if keyword in message:
                    # تحقق من أن هذا المرفق لم تتم إضافته بالفعل
                    if not any(f['type'] == facility_type for f in facilities):
                        facilities.append({
                            'text': keyword,
                            'type': facility_type
                        })
                    break
        
        return facilities