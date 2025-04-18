# -*- coding: utf-8 -*-

"""
خدمة حساب المسافات بين المستخدم والأحياء.
تستخدم مكتبة geocoder للتفاعل مع خرائط Google والحصول على الإحداثيات وحساب المسافات.
"""

import geocoder
import logging
import math
from typing import Dict, Tuple, Optional, List, Any
import pandas as pd

from services.data.data_loader import DataLoader
from core.exceptions import DistanceCalculationError

logger = logging.getLogger(__name__)

class DistanceCalculator:
    """
    خدمة لحساب المسافات بين المواقع.
    تسمح بحساب المسافة بين موقع المستخدم والأحياء المقترحة.
    """
    def __init__(self, data_loader: DataLoader, api_key: str):
        """
        تهيئة خدمة حساب المسافات.
        
        Args:
            data_loader: محمل البيانات للوصول إلى معلومات الأحياء
            api_key: مفتاح API لخرائط Google
        """
        self.data_loader = data_loader
        self.api_key = api_key
        # تحليل بيانات الأحياء وتخزين إحداثياتها
        self.neighborhoods_coords = self._load_neighborhoods_coords()
        logger.info("تم تهيئة خدمة حساب المسافات")
    
    def _load_neighborhoods_coords(self) -> Dict[str, Tuple[float, float]]:
        """
        تحميل إحداثيات الأحياء من بيانات الأحياء.
        
        Returns:
            Dict[str, Tuple[float, float]]: قاموس يحتوي على إحداثيات كل حي (خط العرض، خط الطول)
        """
        coords = {}
        try:
            neighborhoods_df = self.data_loader.get_neighborhoods_data()
            if neighborhoods_df.empty:
                logger.warning("لم يتم العثور على بيانات الأحياء")
                return coords
            
            # التحقق من وجود الأعمدة المطلوبة
            lat_columns = ["LAT", "خط_العرض", "latitude", "lat"]
            lon_columns = ["LON", "خط_الطول", "longitude", "lon"]
            
            lat_col = next((col for col in lat_columns if col in neighborhoods_df.columns), None)
            lon_col = next((col for col in lon_columns if col in neighborhoods_df.columns), None)
            
            if not lat_col or not lon_col:
                logger.warning("لم يتم العثور على أعمدة الإحداثيات")
                return coords
            
            # استخراج اسم الحي وإحداثياته
            name_col = next((col for col in ["Name_of_neighborhood", "اسم_الحي", "neighborhood_name"] 
                           if col in neighborhoods_df.columns), None)
            
            if not name_col:
                logger.warning("لم يتم العثور على عمود اسم الحي")
                return coords
            
            # تحميل الإحداثيات لكل حي
            for _, row in neighborhoods_df.iterrows():
                name = row[name_col]
                lat = row[lat_col]
                lon = row[lon_col]
                
                if pd.notna(name) and pd.notna(lat) and pd.notna(lon):
                    coords[name] = (float(lat), float(lon))
            
            logger.info(f"تم تحميل إحداثيات {len(coords)} حي")
            return coords
            
        except Exception as e:
            logger.error(f"خطأ في تحميل إحداثيات الأحياء: {str(e)}")
            return coords
    
    def get_coordinates(self, address: str) -> Optional[Tuple[float, float]]:
        """
        الحصول على إحداثيات لعنوان معين.
        
        Args:
            address: العنوان المراد الحصول على إحداثياته
            
        Returns:
            Optional[Tuple[float, float]]: إحداثيات العنوان (خط العرض، خط الطول)، أو None في حالة الفشل
        """
        try:
            # تحسين العنوان للحصول على نتائج أفضل في السعودية
            if not address.endswith("المملكة العربية السعودية"):
                search_address = f"{address}، المملكة العربية السعودية"
            else:
                search_address = address
            
            # استخدام geocoder للحصول على الإحداثيات
            g = geocoder.google(search_address, key=self.api_key)
            
            if g.ok:
                logger.info(f"تم العثور على إحداثيات العنوان: {address}")
                return g.lat, g.lng
            else:
                logger.warning(f"لم يتم العثور على إحداثيات للعنوان: {address}")
                return None
                
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحداثيات للعنوان: {str(e)}")
            return None
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        حساب المسافة بين إحداثيين باستخدام صيغة هافرساين.
        
        Args:
            lat1: خط عرض النقطة الأولى
            lon1: خط طول النقطة الأولى
            lat2: خط عرض النقطة الثانية
            lon2: خط طول النقطة الثانية
            
        Returns:
            float: المسافة بالكيلومتر
        """
        # تحويل الإحداثيات من درجات إلى راديان
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # صيغة هافرساين لحساب المسافة على سطح كروي
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        # نصف قطر الأرض بالكيلومتر
        radius = 6371
        
        # حساب المسافة
        distance = radius * c
        
        return round(distance, 2)
    
    def get_distance_to_neighborhood(self, user_address: str, neighborhood_name: str) -> Dict[str, Any]:
        """
        حساب المسافة بين عنوان المستخدم وحي معين.
        
        Args:
            user_address: عنوان المستخدم
            neighborhood_name: اسم الحي
            
        Returns:
            Dict[str, Any]: معلومات المسافة والموقع
        """
        try:
            distance = self.distance_calculator.get_distance_to_neighborhood(user_address, neighborhood_name)
            
            neighborhood_location = self.distance_calculator.get_neighborhood_location(neighborhood_name)
            
            result = {
                'neighborhood': neighborhood_name,
                'user_address': user_address,
                'distance_km': distance,
                'neighborhood_location': neighborhood_location
            }
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في حساب المسافة إلى الحي: {str(e)}")
            return {
                'neighborhood': neighborhood_name,
                'user_address': user_address,
                'error': str(e)
            }
    
    def find_closest_neighborhoods(self, user_address: str, count: int = 5) -> List[Dict[str, Any]]:
        """
        العثور على أقرب عدد محدد من الأحياء إلى عنوان المستخدم.
        
        Args:
            user_address: عنوان المستخدم
            count: عدد الأحياء المراد إرجاعها
            
        Returns:
            List[Dict[str, Any]]: قائمة بالأحياء الأقرب مع المسافة
        """
        try:
            closest_neighborhoods = self.distance_calculator.find_closest_neighborhoods(user_address, count)
            
            # إضافة معلومات إضافية حول كل حي
            enriched_results = []
            for neighborhood in closest_neighborhoods:
                neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood['name'])
                
                enriched_results.append({
                    'name': neighborhood['name'],
                    'distance_km': neighborhood['distance'],
                    'location': {
                        'lat': neighborhood['lat'],
                        'lon': neighborhood['lon']
                    },
                    'info': neighborhood_info
                })
            
            return enriched_results
            
        except Exception as e:
            logger.error(f"خطأ في البحث عن الأحياء القريبة: {str(e)}")
            return []
    
    def get_neighborhood_with_distance(self, user_address: str, neighborhood_name: str) -> Dict[str, Any]:
        """
        الحصول على معلومات حي مع المسافة من موقع المستخدم.
        
        Args:
            user_address: عنوان المستخدم
            neighborhood_name: اسم الحي
            
        Returns:
            Dict[str, Any]: معلومات الحي مع المسافة
        """
        try:
            # الحصول على معلومات الحي
            neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
            benefits = self.data_loader.get_neighborhood_benefits(neighborhood_name)
            
            # حساب المسافة
            distance = self.distance_calculator.get_distance_to_neighborhood(user_address, neighborhood_name)
            
            # الحصول على موقع الحي
            location = self.distance_calculator.get_neighborhood_location(neighborhood_name)
            
            # تنسيق الرد
            formatted_response = self.formatter.format_neighborhood_response(neighborhood_name)
            
            # إضافة معلومات المسافة إلى الرد
            if distance:
                distance_text = f"\n\nالمسافة من موقعك إلى {neighborhood_name} هي {distance} كيلومتر."
                formatted_response += distance_text
            
            return {
                'name': neighborhood_name,
                'info': neighborhood_info,
                'benefits': benefits,
                'distance_km': distance,
                'location': location,
                'formatted_response': formatted_response
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الحي مع المسافة: {str(e)}")
            return {
                'name': neighborhood_name,
                'error': str(e)
            }
            
    def get_neighborhood_location(self, neighborhood_name: str) -> Optional[Dict[str, float]]:
        """
        الحصول على موقع حي معين.
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            Optional[Dict[str, float]]: قاموس يحتوي على خط العرض وخط الطول للحي
        """
        try:
            # تنظيف اسم الحي
            clean_name = neighborhood_name.replace("حي ", "").strip()
            
            # البحث عن الحي في البيانات المخزنة
            for name, coords in self.neighborhoods_coords.items():
                if clean_name in name or name in clean_name:
                    return {
                        'lat': coords[0],
                        'lon': coords[1]
                    }
            
            # إذا لم يتم العثور على الحي في البيانات المخزنة، استخدم geocoder
            coords = self.get_coordinates(f"حي {clean_name}")
            if coords:
                return {
                    'lat': coords[0],
                    'lon': coords[1]
                }
                
            logger.warning(f"لم يتم العثور على إحداثيات للحي: {neighborhood_name}")
            return None
                
        except Exception as e:
            logger.error(f"خطأ في الحصول على موقع الحي: {str(e)}")
            return None
        
    def calculate_distance_between_coordinates(self, user_lat: float, user_lon: float, neighborhood_name: str) -> Optional[float]:
        """
        حساب المسافة بين إحداثيات المستخدم المحددة وحي معين.
        
        Args:
            user_lat: خط عرض المستخدم
            user_lon: خط طول المستخدم
            neighborhood_name: اسم الحي
            
        Returns:
            Optional[float]: المسافة بالكيلومترات أو None إذا لم يمكن حسابها
        """
        try:
            # الحصول على إحداثيات الحي
            neighborhood_info = self.data_loader.find_neighborhood_info(neighborhood_name)
            if not neighborhood_info:
                logger.warning(f"لم يتم العثور على معلومات للحي: {neighborhood_name}")
                return None
            
            # التحقق مما إذا كانت لدينا إحداثيات الحي
            lat_key = next((key for key in neighborhood_info.keys() if key.lower() in ['lat', 'latitude', 'خط_العرض']), None)
            lon_key = next((key for key in neighborhood_info.keys() if key.lower() in ['lon', 'longitude', 'خط_الطول']), None)
            
            if not lat_key or not lon_key or lat_key not in neighborhood_info or lon_key not in neighborhood_info:
                logger.warning(f"لم يتم العثور على إحداثيات للحي: {neighborhood_name}")
                return None
            
            # حساب المسافة
            neighborhood_lat = float(neighborhood_info[lat_key])
            neighborhood_lon = float(neighborhood_info[lon_key])
            
            distance = self.calculate_distance(
                user_lat, user_lon, neighborhood_lat, neighborhood_lon
            )
            
            logger.info(f"المسافة من الإحداثيات المرسلة إلى الحي {neighborhood_name}: {distance} كم")
            return distance
            
        except Exception as e:
            logger.error(f"خطأ في حساب المسافة من الإحداثيات المرسلة إلى الحي {neighborhood_name}: {str(e)}")
            return None
