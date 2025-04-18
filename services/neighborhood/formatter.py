# -*- coding: utf-8 -*-

"""
خدمة تنسيق الردود الخاصة بالأحياء والعقارات.
تقوم هذه الخدمة بتنسيق المعلومات من مصادر مختلفة لإنشاء ردود مفيدة وشاملة.
"""

import re
import logging
import pandas as pd
from typing import Dict, List, Optional, Any, Union
import random

from services.data.data_loader import DataLoader
from core.exceptions import ResponseFormattingError

logger = logging.getLogger(__name__)

class ResponseFormatter:
    """
    خدمة لتنسيق الردود المتعلقة بالأحياء والعقارات.
    تتضمن طرق متنوعة لتنسيق معلومات الأحياء، والمرافق، والأسعار، والمميزات.
    """
    def __init__(self, data_loader: DataLoader):
        """
        تهيئة خدمة التنسيق.
        
        Args:
            data_loader: محمل البيانات للوصول إلى المعلومات
        """
        self.data_loader = data_loader
        
        # قوالب الردود المتنوعة
        self.response_templates = {
            'neighborhood': [
                "بناءً على تجربة الباحثين عن العقارات السابقين، أقترح عليك البحث في {neighborhood_name}.",
                "وفقاً لتجارب السكان السابقين، يُعتبر {neighborhood_name} خياراً مناسباً لاحتياجاتك.",
                "{neighborhood_name} من الأحياء المميزة التي تناسب متطلباتك حسب تجارب السكان."
            ],
            'price_comparison': [
                "أسعار العقارات في {neighborhood_name} {comparison} مقارنة بالأحياء المجاورة.",
                "يتميز {neighborhood_name} بأسعار {comparison} بالنسبة للمناطق المحيطة.",
                "تعتبر الأسعار في {neighborhood_name} {comparison} بالمقارنة مع متوسط أسعار المنطقة."
            ],
            'no_info': [
                "للأسف، لا تتوفر معلومات كافية عن {item_name} في قاعدة البيانات.",
                "عذراً، لم نتمكن من العثور على معلومات مفصلة عن {item_name}.",
                "لم يتم العثور على بيانات محددة عن {item_name} في سجلاتنا."
            ]
        }
        
        logger.info("تم تهيئة خدمة تنسيق الردود")
    
    def format_neighborhood_response(self, neighborhood_name: str, personalized: bool = False) -> str:
        """
        تنسيق رد شامل حول حي معين.
        """
        try:
            # الحصول على معلومات الحي
            neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
            
            # الحصول على مميزات الحي
            benefits = self.data_loader.get_neighborhood_benefits(neighborhood_name)
            
            # تسجيل البيانات للتصحيح
            logger.info(f"معلومات الحي {neighborhood_name}: {bool(neighborhood_info)}")
            logger.info(f"مميزات الحي {neighborhood_name}: {len(benefits) if benefits else 0} مميزة")
            
            # تنظيف اسم الحي وإضافة كلمة "حي" إذا لم تكن موجودة
            clean_name = neighborhood_name.replace("حي ", "").strip()
            formatted_name = f"حي {clean_name}" if not neighborhood_name.startswith("حي") else neighborhood_name
            
            # إنشاء الرد الأساسي
            template = random.choice(self.response_templates['neighborhood'])
            response = template.format(neighborhood_name=formatted_name)
            
            # إضافة الوصف إذا كان متاحًا
            description = self._get_description(neighborhood_info)
            if description:
                response += f" {description}"
            
            # إضافة المرافق المتاحة
            facilities = self._get_facilities(neighborhood_info)
            if facilities:
                response += f" يتوفر في الحي العديد من المرافق والخدمات."
            
            # إضافة معلومات الأسعار إذا كانت متاحة
            price_info = self._get_price_info(neighborhood_info)
            if price_info:
                # عرض جميع معلومات الأسعار المتاحة
                prices_text = ". ".join(price_info)
                response += f" {prices_text}."
                    
                # إضافة مقارنة الأسعار مع المناطق المجاورة إذا كانت متاحة
                price_comparison = self._get_price_comparison(neighborhood_info)
                if price_comparison:
                    comparison_template = random.choice(self.response_templates['price_comparison'])
                    response += f" {comparison_template.format(neighborhood_name=formatted_name, comparison=price_comparison)}"
            
            # إضافة مميزات الحي من تجارب السكان - التغيير المهم هنا
            if benefits:
                # حذفنا استدعاء self._format_benefits وجعلناه يظهر مباشرة
                all_benefits = []
                for benefit_text in benefits:
                    if not benefit_text or not isinstance(benefit_text, str):
                        continue
                        
                    individual_benefits = re.split(r'[,،\.؛;]', benefit_text)
                    for b in individual_benefits:
                        b = b.strip()
                        if b and len(b.split()) >= 2 and b not in all_benefits:
                            b = re.sub(r'^[-_*•]+', '', b).strip()
                            all_benefits.append(b)
                
                # إزالة المميزات السلبية
                negative_words = ["سيء", "رديء", "مشكلة", "ازعاج", "ضوضاء", "غير", "لا ", "ليس", "ضعيف", "سلبي"]
                filtered_benefits = [b for b in all_benefits if not any(neg in b for neg in negative_words)]
                
                # تنظيم المميزات
                contradictory_groups = [
                    ["هادئ", "هدوء", "سكون", "هادئة"],
                    ["نشط", "مزدحم", "حركة", "نشاط", "حيوية", "صاخب"]
                ]
                
                # استبعاد التناقضات
                final_benefits = []
                used_groups = set()
                
                for benefit in filtered_benefits:
                    group_match = -1
                    for i, group in enumerate(contradictory_groups):
                        if any(word in benefit.lower() for word in group):
                            group_match = i
                            break
                            
                    if group_match == -1 or group_match not in used_groups:
                        final_benefits.append(benefit)
                        if group_match != -1:
                            used_groups.add(group_match)
                
                # اختيار 3-4 مميزات للعرض
                top_benefits = final_benefits[:4]
                if top_benefits:
                    benefits_text = "، ".join(top_benefits)
                    response += f" ويتميز الحي بـ: {benefits_text}."
            
            # باقي الكود كما هو...
            location_info = self._get_location_info(neighborhood_info)
            if location_info:
                response += f" {location_info}"
            
            if personalized:
                custom_info = self._get_personalized_info(neighborhood_info, benefits)
                if custom_info:
                    response += f" {custom_info}"
            
            response += self._get_closing_statement(formatted_name)
            
            return response
                    
        except Exception as e:
            logger.error(f"خطأ في تنسيق رد الحي: {str(e)}")
            error_template = random.choice(self.response_templates['no_info'])
            return error_template.format(item_name=neighborhood_name)
        
    def format_facility_response(self, facility_name: str, facility_type: str, facility_info: Dict) -> str:
        """
        تنسيق رد حول مرفق محدد.
        
        Args:
            facility_name: اسم المرفق
            facility_type: نوع المرفق (مدرسة، مستشفى، الخ)
            facility_info: معلومات المرفق
            
        Returns:
            str: رد منسق يحتوي على معلومات المرفق
        """
        try:
            response = f"معلومات عن {facility_type} {facility_name}:\n"
            
            # إضافة العنوان إذا كان متاحاً
            if 'العنوان' in facility_info and pd.notna(facility_info['العنوان']):
                response += f"• العنوان: {facility_info['العنوان']}\n"
            
            # إضافة معلومات التصنيف إذا كانت متاحة
            if 'التصنيف' in facility_info and pd.notna(facility_info['التصنيف']):
                response += f"• التصنيف: {facility_info['التصنيف']}\n"
            
            # إضافة معلومات إضافية حسب نوع المرفق
            if facility_type == 'مدرسة':
                if 'المرحلة_الدراسية' in facility_info and pd.notna(facility_info['المرحلة_الدراسية']):
                    response += f"• المرحلة الدراسية: {facility_info['المرحلة_الدراسية']}\n"
                if 'نوع_المدرسة' in facility_info and pd.notna(facility_info['نوع_المدرسة']):
                    response += f"• نوع المدرسة: {facility_info['نوع_المدرسة']}\n"
            
            elif facility_type == 'مستشفى':
                if 'التخصص' in facility_info and pd.notna(facility_info['التخصص']):
                    response += f"• التخصص: {facility_info['التخصص']}\n"
            
            elif facility_type == 'حديقة':
                if 'المساحة' in facility_info and pd.notna(facility_info['المساحة']):
                    response += f"• المساحة: {facility_info['المساحة']}\n"
                if 'المرافق' in facility_info and pd.notna(facility_info['المرافق']):
                    response += f"• المرافق: {facility_info['المرافق']}\n"
            
            elif facility_type == 'مول':
                if 'عدد_المتاجر' in facility_info and pd.notna(facility_info['عدد_المتاجر']):
                    response += f"• عدد المتاجر: {facility_info['عدد_المتاجر']}\n"
                if 'المطاعم' in facility_info and pd.notna(facility_info['المطاعم']):
                    response += f"• المطاعم: {facility_info['المطاعم']}\n"
                if 'الترفيه' in facility_info and pd.notna(facility_info['الترفيه']):
                    response += f"• خيارات الترفيه: {facility_info['الترفيه']}\n"
            
            elif facility_type == 'سوبرماركت':
                if 'ساعات_العمل' in facility_info and pd.notna(facility_info['ساعات_العمل']):
                    response += f"• ساعات العمل: {facility_info['ساعات_العمل']}\n"
            
            return response
        
        except Exception as e:
            logger.error(f"خطأ في تنسيق رد المرفق: {str(e)}")
            error_template = random.choice(self.response_templates['no_info'])
            return error_template.format(item_name=f"{facility_type} {facility_name}")
    
    def format_comparison_response(self, neighborhoods: List[str], criteria: Optional[str] = None) -> str:
        """
        تنسيق رد مقارنة بين عدة أحياء.
        
        Args:
            neighborhoods: قائمة بأسماء الأحياء للمقارنة
            criteria: معيار المقارنة (اختياري)
            
        Returns:
            str: رد منسق يحتوي على مقارنة بين الأحياء
        """
        try:
            if not neighborhoods or len(neighborhoods) < 2:
                return "يجب تحديد حيين على الأقل للمقارنة."
            
            response = f"مقارنة بين الأحياء: {', '.join(neighborhoods)}\n\n"
            
            # مقارنة للمرافق
            response += "المرافق المتوفرة:\n"
            for neighborhood in neighborhoods:
                neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood)
                facilities = self._get_facilities(neighborhood_info)
                
                facilities_text = "لا تتوفر معلومات" if not facilities else ", ".join(facilities)
                response += f"• {neighborhood}: {facilities_text}\n"
            
            response += "\n"
            
            # مقارنة للأسعار
            response += "مقارنة الأسعار:\n"
            for neighborhood in neighborhoods:
                neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood)
                price_info = self._get_price_info(neighborhood_info)
                
                price_text = "لا تتوفر معلومات" if not price_info else " | ".join(price_info)
                response += f"• {neighborhood}: {price_text}\n"
            
            # إضافة توصية بناءً على المعيار إذا كان محدداً
            if criteria:
                recommended = self._recommend_based_on_criteria(neighborhoods, criteria)
                if recommended:
                    response += f"\nبناءً على معيار {criteria}، نوصي بالحي: {recommended}"
            
            return response
            
        except Exception as e:
            logger.error(f"خطأ في تنسيق رد المقارنة: {str(e)}")
            return "عذراً، لم نتمكن من إجراء المقارنة بسبب نقص في البيانات."
    
    def _get_description(self, neighborhood_info: Dict) -> str:
        """
        استخراج وصف الحي من البيانات.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            
        Returns:
            str: وصف الحي
        """
        if not neighborhood_info:
            return ""
        
        # البحث في أعمدة مختلفة محتملة للوصف
        description_columns = ["Description", "الوصف", "description", "about", "عن_الحي"]
        
        for col in description_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                return str(neighborhood_info[col])
        
        return ""
    
    def _get_facilities(self, neighborhood_info: Dict) -> List[str]:
        """
        استخراج معلومات المرافق من بيانات الحي.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            
        Returns:
            List[str]: قائمة بنصوص توضح المرافق المتاحة في الحي
        """
        facilities = []
        
        if not neighborhood_info:
            return facilities
        
        # تعريف المرافق المختلفة وتعدد الصيغ المحتملة لها في البيانات
        facility_mappings = {
            "Schools": {
                "names": ["Schools", "المدارس", "school_count", "عدد_المدارس"],
                "singular": "مدرسة",
                "plural2": "مدرستان", # للعدد 2
                "plural": "مدارس"      # للعدد 3 فأكثر
            },
            "Hospitals": {
                "names": ["Hospitals", "المستشفيات", "hospital_count", "عدد_المستشفيات"],
                "singular": "مستشفى",
                "plural2": "مستشفيان",
                "plural": "مستشفيات"
            },
            "Parks": {
                "names": ["Parks", "الحدائق", "park_count", "عدد_الحدائق"],
                "singular": "حديقة",
                "plural2": "حديقتان",
                "plural": "حدائق"
            },
            "Supermarket": {
                "names": ["Supermarket", "السوبرماركت", "supermarket_count", "عدد_السوبرماركت"],
                "singular": "سوبرماركت",
                "plural2": "سوبرماركت",
                "plural": "سوبرماركت"
            },
            "Malls": {
                "names": ["Malls", "المولات", "mall_count", "عدد_المولات"],
                "singular": "مركز تسوق",
                "plural2": "مركزي تسوق",
                "plural": "مراكز تسوق"
            }
        }
        
        # استخراج المرافق مع مراعاة صيغة الجمع الصحيحة
        for facility_key, mapping in facility_mappings.items():
            # البحث عن أي اسم من أسماء العمود المحتملة
            found_value = None
            for name in mapping["names"]:
                if name in neighborhood_info and pd.notna(neighborhood_info[name]):
                    found_value = neighborhood_info[name]
                    break
            
            if found_value is not None:
                try:
                    # محاولة تحويل القيمة إلى عدد
                    count = int(float(found_value))
                    if count > 0:
                        # تحديد صيغة العدد المناسبة (مفرد، مثنى، جمع)
                        if count == 1:
                            name = mapping["singular"]
                            facilities.append(f"{count} {name}")
                        elif count == 2:
                            name = mapping["plural2"]
                            facilities.append(f"{count} {name}")
                        else:
                            name = mapping["plural"]
                            facilities.append(f"{count} {name}")
                except (ValueError, TypeError):
                    # إذا لم تكن القيمة رقماً، فقد تكون نصاً يصف المرافق
                    if isinstance(found_value, str) and found_value.strip():
                        facilities.append(found_value)
        
        return facilities
    
    def _get_price_info(self, neighborhood_info: Dict) -> List[str]:
        """
        استخراج معلومات الأسعار من بيانات الحي.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            
        Returns:
            List[str]: قائمة بنصوص توضح معلومات الأسعار في الحي
        """
        price_info = []
        
        if not neighborhood_info:
            return price_info
        
        # تعريف أنواع العقارات وتعدد أسماء الأعمدة المحتملة لها
        property_types = {
            "Villas": {
                "names": ["price_of_meter_Villas", "سعر_المتر_للفلل", "villa_price", "سعر_الفلل"],
                "label": "سعر المتر للفلل"
            },
            "Apartment": {
                "names": ["price_of_meter_Apartment", "سعر_المتر_للشقق", "apartment_price", "سعر_الشقق"],
                "label": "سعر المتر للشقق"
            },
            "Land": {
                "names": ["price_of_meter_Land", "سعر_المتر_للأراضي", "land_price", "سعر_الأراضي"],
                "label": "سعر المتر للأراضي"
            },
            "Commercial": {
                "names": ["price_of_meter_Commercial", "سعر_المتر_التجاري", "commercial_price", "سعر_التجاري"],
                "label": "سعر المتر للمحلات التجارية"
            },
            "Rent": {
                "names": ["average_rent", "متوسط_الإيجار", "rent_price", "سعر_الإيجار"],
                "label": "متوسط سعر الإيجار"
            }
        }
        
        # استخراج معلومات الأسعار لكل نوع عقاري
        for prop_type, config in property_types.items():
            # البحث عن أي اسم من أسماء العمود المحتملة
            found_value = None
            found_column = None
            
            for name in config["names"]:
                if name in neighborhood_info and pd.notna(neighborhood_info[name]):
                    found_value = neighborhood_info[name]
                    found_column = name
                    break
            
            if found_value is not None:
                try:
                    # محاولة معالجة القيمة كرقم
                    if isinstance(found_value, (int, float)):
                        price = int(found_value)
                        # تنسيق السعر بفواصل الآلاف
                        formatted_price = "{:,}".format(price)
                        
                        # تحديد الوحدة بناءً على نوع العمود
                        if 'rent' in found_column.lower() or 'إيجار' in found_column:
                            price_info.append(f"{config['label']} {formatted_price} ريال شهرياً")
                        else:
                            price_info.append(f"{config['label']} {formatted_price} ريال")
                    elif isinstance(found_value, str) and found_value.strip():
                        # إذا كانت القيمة نصية، استخدمها مباشرة
                        price_info.append(f"{config['label']} {found_value}")
                except (ValueError, TypeError):
                    # إذا حدث خطأ في تحويل القيمة، استخدم النص كما هو
                    if isinstance(found_value, str) and found_value.strip():
                        price_info.append(f"{config['label']} {found_value}")
        
        return price_info
    
    def _get_price_comparison(self, neighborhood_info: Dict) -> Optional[str]:
        """
        استخراج مقارنة الأسعار مع المناطق المجاورة.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            
        Returns:
            Optional[str]: وصف للمقارنة (مرتفعة، متوسطة، منخفضة) أو None
        """
        if not neighborhood_info:
            return None
        
        # البحث في أعمدة مختلفة محتملة لمقارنة الأسعار
        comparison_columns = [
            "price_comparison", "مقارنة_الأسعار", "price_level", "مستوى_السعر"
        ]
        
        for col in comparison_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                value = str(neighborhood_info[col]).lower()
                
                # ترجمة القيم المختلفة إلى التصنيفات الثلاثة الرئيسية
                if any(term in value for term in ["high", "مرتفع", "عالي", "عالية", "أعلى"]):
                    return "مرتفعة"
                elif any(term in value for term in ["low", "منخفض", "منخفضة", "أقل"]):
                    return "منخفضة"
                elif any(term in value for term in ["medium", "متوسط", "متوسطة", "average", "mid"]):
                    return "متوسطة"
                else:
                    return value  # إرجاع القيمة كما هي إذا لم تطابق أي تصنيف
        
        return None
    
    def _format_benefits(self, benefits: List[str]) -> str:
        """
        تنسيق مميزات الحي من تجارب السكان.
        """
        if not benefits:
            return ""
        
        # استخراج كل المميزات المذكورة
        all_benefits = []
        for benefit_text in benefits:
            if not benefit_text or not isinstance(benefit_text, str):
                continue
                
            # تقسيم النص حسب الفواصل والنقاط
            individual_benefits = re.split(r'[,،\.؛;]', benefit_text)
            
            for b in individual_benefits:
                b = b.strip()
                # التحقق من أن المميزة تحتوي على نص معقول (أكثر من كلمتين)
                if b and len(b.split()) >= 2 and b not in all_benefits:
                    # تنظيف النص من علامات الترقيم الزائدة
                    b = re.sub(r'^[-_*•]+', '', b).strip()
                    all_benefits.append(b)
        
        # تحديد الكلمات المتناقضة للتحقق منها
        contradictions = [
            ["هادئ", "هدوء", "سكون"],
            ["نشط", "مزدحم", "حركة", "صاخب", "ضوضاء"]
        ]
        
        # تحديد أي مجموعة متناقضة ظهرت أولاً
        first_group_found = None
        
        selected_benefits = []
        for benefit in all_benefits:
            # تحقق من أي مجموعة تنتمي إليها هذه الميزة
            current_group = None
            for i, group in enumerate(contradictions):
                if any(word in benefit.lower() for word in group):
                    current_group = i
                    break
            
            # إذا لم تنتمي لأي مجموعة، أضفها
            if current_group is None:
                selected_benefits.append(benefit)
            # إذا تنتمي للمجموعة التي ظهرت أولاً، أضفها
            elif first_group_found is None:
                first_group_found = current_group
                selected_benefits.append(benefit)
            # إذا تنتمي للمجموعة التي ظهرت أولاً، أضفها
            elif current_group == first_group_found:
                selected_benefits.append(benefit)
        
        # حد عدد المميزات المعروضة إلى 4
        if len(selected_benefits) > 4:
            selected_benefits = selected_benefits[:4]
        
        # إرجاع النتيجة
        if selected_benefits:
            return "، ".join(selected_benefits)
        else:
            return ""
                                
    def _get_location_info(self, neighborhood_info: Dict) -> str:
        """
        استخراج معلومات الموقع من بيانات الحي.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            
        Returns:
            str: نص يصف موقع الحي والمناطق المجاورة
        """
        location_text = ""
        
        if not neighborhood_info:
            return location_text
        
        # استخراج الموقع من المدينة
        city_location_columns = ["city_location", "الموقع_في_المدينة", "الموقع", "location"]
        for col in city_location_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                location_text += f"يقع الحي في {neighborhood_info[col]}. "
                break
        
        # استخراج الأحياء المجاورة
        nearby_columns = ["nearby_neighborhoods", "الأحياء_المجاورة", "المجاور", "الأحياء_المحيطة"]
        for col in nearby_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                location_text += f"يحده {neighborhood_info[col]}. "
                break
        
        # استخراج معلومات القرب من الخدمات الرئيسية
        key_locations = {
            "distance_to_airport": "المطار",
            "distance_to_city_center": "وسط المدينة",
            "distance_to_highway": "الطريق السريع",
            "المسافة_للمطار": "المطار",
            "المسافة_لوسط_المدينة": "وسط المدينة",
            "المسافة_للطريق_السريع": "الطريق السريع",
            "distance_to_mosque": "المسجد الرئيسي",
            "المسافة_للمسجد": "المسجد الرئيسي"
        }
        
        distance_info = []
        for col, label in key_locations.items():
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                value = neighborhood_info[col]
                if isinstance(value, (int, float)):
                    distance_info.append(f"يبعد {value} كم عن {label}")
                elif isinstance(value, str) and value.strip():
                    # محاولة استخراج الرقم من النص إذا كان ذلك ممكناً
                    match = re.search(r'(\d+(?:\.\d+)?)', value)
                    if match:
                        num = match.group(1)
                        distance_info.append(f"يبعد {num} كم عن {label}")
                    else:
                        distance_info.append(f"يقع {value} من {label}")
        
        if distance_info:
            location_text += " " + "، ".join(distance_info) + "."
        
        return location_text
    
    def _get_personalized_info(self, neighborhood_info: Dict, benefits: List[str]) -> str:
        """
        استخراج معلومات مخصصة إضافية عن الحي.
        
        Args:
            neighborhood_info: قاموس يحتوي على معلومات الحي
            benefits: قائمة بمميزات الحي
            
        Returns:
            str: نص يحتوي على معلومات مخصصة
        """
        if not neighborhood_info:
            return ""
        
        custom_info = []
        
        # استخراج معلومات عن الأمان
        safety_columns = ["safety_level", "مستوى_الأمان", "الأمان"]
        for col in safety_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                custom_info.append(f"مستوى الأمان في الحي {neighborhood_info[col]}")
                break
        
        # استخراج معلومات عن نمط الحياة
        lifestyle_columns = ["lifestyle", "نمط_الحياة", "الحياة_الاجتماعية"]
        for col in lifestyle_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                custom_info.append(f"نمط الحياة في الحي {neighborhood_info[col]}")
                break
        
        # استخراج معلومات عن جودة المرافق
        quality_columns = ["facilities_quality", "جودة_المرافق", "جودة_الخدمات"]
        for col in quality_columns:
            if col in neighborhood_info and pd.notna(neighborhood_info[col]):
                custom_info.append(f"جودة المرافق والخدمات {neighborhood_info[col]}")
                break
        
        # استخراج معلومات مميزة من تجارب السكان
        if benefits:
            # البحث عن كلمات مفتاحية محددة في تجارب السكان
            keywords = {
                "هدوء": "يتميز الحي بالهدوء",
                "نظافة": "يعتبر الحي نظيفاً",
                "راق": "يعتبر الحي راقياً",
                "عائلات": "مناسب للعائلات",
                "قريب": "قريب من الخدمات الأساسية",
                "مسجد": "قريب من المساجد",
                "مدارس": "قريب من المدارس"
            }
            
            for keyword, statement in keywords.items():
                if any(keyword in benefit.lower() for benefit in benefits if isinstance(benefit, str)):
                    if statement not in custom_info:
                        custom_info.append(statement)
        
        if custom_info:
            return " و".join(custom_info) + "."
        else:
            return ""
    
    def _get_closing_statement(self, neighborhood_name: str) -> str:
        """
        إنشاء جملة ختامية للرد.
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            str: جملة ختامية
        """
        closing_statements = [
            f" للمزيد من المعلومات عن {neighborhood_name}، يمكنك الاستفسار عن أي جانب محدد ترغب في معرفته.",
            f" هل ترغب في معرفة المزيد عن المرافق والخدمات المتاحة في {neighborhood_name}؟",
            f" هل تود معرفة تفاصيل أكثر عن الأسعار أو المرافق المتاحة في {neighborhood_name}؟"
        ]
        
        return random.choice(closing_statements)
    
    def _recommend_based_on_criteria(self, neighborhoods: List[str], criteria: str) -> Optional[str]:
        """
        تحديد الحي الموصى به بناءً على معيار محدد.
        
        Args:
            neighborhoods: قائمة بأسماء الأحياء
            criteria: معيار التوصية
            
        Returns:
            Optional[str]: اسم الحي الموصى به أو None
        """
        criteria_lower = criteria.lower()
        
        if any(word in criteria_lower for word in ["سعر", "أسعار", "تكلفة", "رخيص"]):
            # التوصية بناءً على الأسعار
            cheapest_hood = None
            lowest_price = float('inf')
            
            for hood in neighborhoods:
                hood_info = self.data_loader.find_neighborhood_info(hood)
                if not hood_info:
                    continue
                
                # البحث عن معلومات الأسعار
                for key, value in hood_info.items():
                    if ("price" in key.lower() or "سعر" in key) and pd.notna(value):
                        try:
                            # محاولة استخراج رقم من القيمة
                            if isinstance(value, (int, float)):
                                price = float(value)
                            else:
                                # استخراج الرقم من النص
                                match = re.search(r'(\d+(?:\.\d+)?)', str(value))
                                if match:
                                    price = float(match.group(1))
                                else:
                                    continue
                                
                            # تحديث الحي الأرخص
                            if price > 0 and price < lowest_price:
                                lowest_price = price
                                cheapest_hood = hood
                                
                        except (ValueError, TypeError):
                            continue
            
            return cheapest_hood
            
        elif any(word in criteria_lower for word in ["مرفق", "مرافق", "خدمات", "مدارس", "مستشفيات"]):
            # التوصية بناءً على المرافق
            best_hood = None
            max_facilities = -1
            
            for hood in neighborhoods:
                hood_info = self.data_loader.find_neighborhood_info(hood)
                if not hood_info:
                    continue
                
                facilities = self._get_facilities(hood_info)
                if len(facilities) > max_facilities:
                    max_facilities = len(facilities)
                    best_hood = hood
            
            return best_hood
            
        elif any(word in criteria_lower for word in ["موقع", "قرب", "مركز", "وسط"]):
            # التوصية بناءً على الموقع
            best_hood = None
            min_distance = float('inf')
            
            for hood in neighborhoods:
                hood_info = self.data_loader.find_neighborhood_info(hood)
                if not hood_info:
                    continue
                
                # البحث عن أقرب حي للمركز
                distance_column = "distance_to_city_center"
                if distance_column in hood_info and pd.notna(hood_info[distance_column]):
                    try:
                        distance = float(hood_info[distance_column])
                        if distance < min_distance:
                            min_distance = distance
                            best_hood = hood
                    except (ValueError, TypeError):
                        continue
            
            return best_hood
        
        # إذا لم يتم العثور على معيار مناسب، إرجاع الحي الأول في القائمة
        return neighborhoods[0] if neighborhoods else None
