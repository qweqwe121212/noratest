# -*- coding: utf-8 -*-

"""
وحدة تكامل الموقع - للحصول على موقع المستخدم وحساب المسافات.
"""

import logging
import math
from typing import Optional, Dict, Any, Tuple
import json
import requests
from flask import request
from core.exceptions import DistanceCalculationError

logger = logging.getLogger(__name__)

class LocationIntegration:
    """
    فئة لدمج وظائف تحديد الموقع الجغرافي وحساب المسافات.
    """
    
    def __init__(self, distance_calculator, data_loader):
        """
        تهيئة تكامل الموقع.
        
        Args:
            distance_calculator: حاسبة المسافات الموجودة
            data_loader: محمّل البيانات للوصول إلى معلومات الأحياء
        """
        self.distance_calculator = distance_calculator
        self.data_loader = data_loader
        self.ip_geolocation_api = "http://ip-api.com/json/"
        
        self.default_latitude = 24.7136
        self.default_longitude = 46.6753
        
        logger.info("تم تهيئة خدمة تكامل الموقع")
    
    def get_user_location(self) -> Optional[Tuple[float, float]]:
        """
        الحصول على الموقع الحالي للمستخدم باستخدام عنوان IP.
        
        Returns:
            Optional[Tuple[float, float]]: إحداثيات المستخدم (خط العرض، خط الطول) أو None إذا لم يمكن تحديدها
        """
        try:
            # الحصول على IP العميل
            client_ip = self._get_client_ip()
            if not client_ip or client_ip.startswith('127.') or client_ip.startswith('192.168.') or client_ip.startswith('10.'):
                logger.warning(f"تعذر استخدام عنوان IP محلي: {client_ip}. استخدام الإحداثيات الافتراضية للرياض")
                return (self.default_latitude, self.default_longitude)  # إحداثيات افتراضية للرياض
            
            # الاستعلام عن خدمة تحديد الموقع الجغرافي بواسطة IP
            location_data = self._get_location_from_ip(client_ip)
            if location_data and 'lat' in location_data and 'lon' in location_data:
                logger.info(f"تم تحديد موقع المستخدم بواسطة IP: {location_data['lat']}, {location_data['lon']}")
                return (location_data['lat'], location_data['lon'])
            
            # استخدام الإحداثيات الافتراضية إذا فشل الاستعلام
            logger.info("استخدام الإحداثيات الافتراضية للرياض بسبب فشل التحديد بواسطة IP")
            return (self.default_latitude, self.default_longitude)
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على موقع المستخدم: {str(e)}")
            logger.info("استخدام الإحداثيات الافتراضية للرياض بسبب الخطأ")
            return (self.default_latitude, self.default_longitude)
    
    def _get_client_ip(self) -> Optional[str]:
        """
        الحصول على عنوان IP للعميل من الطلب الحالي.
        
        Returns:
            Optional[str]: عنوان IP للعميل أو None إذا تعذر تحديده
        """
        try:
            # محاولة الحصول على IP من رؤوس مختلفة
            headers_to_check = [
                'X-Forwarded-For',
                'X-Real-IP',
                'HTTP_X_FORWARDED_FOR',
                'HTTP_X_REAL_IP',
                'HTTP_CLIENT_IP'
            ]
            
            for header in headers_to_check:
                if header in request.headers:
                    ip = request.headers.get(header).split(',')[0].strip()
                    if ip:
                        return ip
            
            # إذا لم تكن هناك رؤوس وكيل، استخدم عنوان IP البعيد مباشرة
            return request.remote_addr
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على IP العميل: {str(e)}")
            return None
    
    def _get_location_from_ip(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """
        الحصول على معلومات الموقع من عنوان IP.
        
        Args:
            ip_address: عنوان IP للعميل
            
        Returns:
            Optional[Dict[str, Any]]: بيانات الموقع أو None إذا كان هناك خطأ
        """
        try:
            response = requests.get(f"{self.ip_geolocation_api}{ip_address}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        'lat': data.get('lat'),
                        'lon': data.get('lon'),
                        'city': data.get('city'),
                        'country': data.get('country')
                    }
            
            logger.warning(f"تعذر الحصول على الموقع للعنوان IP {ip_address}")
            return None
            
        except Exception as e:
            logger.error(f"خطأ في استعلام تحديد الموقع الجغرافي بواسطة IP: {str(e)}")
            return None
    
    def calculate_distance_to_neighborhood(self, neighborhood_name: str, user_lat: float = None, user_lon: float = None) -> Optional[float]:
        """
        حساب المسافة بين الموقع الحالي للمستخدم وحي معين.
        
        Args:
            neighborhood_name: اسم الحي
            user_lat: خط العرض للمستخدم (اختياري)
            user_lon: خط الطول للمستخدم (اختياري)
            
        Returns:
            Optional[float]: المسافة بالكيلومترات أو None إذا تعذر حسابها
        """
        try:
            # استخدام الإحداثيات المحددة إذا تم توفيرها
            if user_lat is not None and user_lon is not None:
                user_location = (user_lat, user_lon)
                logger.info(f"استخدام الإحداثيات المحددة للمستخدم: {user_lat}, {user_lon}")
            else:
                # الحصول على موقع المستخدم
                user_location = self.get_user_location()
                if not user_location:
                    logger.warning("تعذر تحديد موقع المستخدم لحساب المسافة، استخدام الإحداثيات الافتراضية")
                    user_location = (self.default_latitude, self.default_longitude)
            
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
            user_lat, user_lon = user_location
            neighborhood_lat = float(neighborhood_info[lat_key])
            neighborhood_lon = float(neighborhood_info[lon_key])
            
            distance = self.distance_calculator.calculate_distance(
                user_lat, user_lon, neighborhood_lat, neighborhood_lon
            )
            
            logger.info(f"المسافة إلى الحي {neighborhood_name}: {distance} كم")
            return distance
            
        except Exception as e:
            logger.error(f"خطأ في حساب المسافة إلى الحي {neighborhood_name}: {str(e)}")
            return None
    
    def format_distance_message(self, neighborhood_name: str, distance: Optional[float]) -> str:
        """
        تنسيق رسالة حول المسافة إلى الحي.
        
        Args:
            neighborhood_name: اسم الحي
            distance: المسافة بالكيلومترات
            
        Returns:
            str: رسالة منسقة
        """
        if distance is None:
            return ""
        
        # تنظيف اسم الحي (إزالة "حي " إذا كانت موجودة)
        clean_name = neighborhood_name.replace("حي ", "").strip()
        formatted_name = f"حي {clean_name}" if not neighborhood_name.startswith("حي") else neighborhood_name
        
        # تنسيق المسافة بخانتين عشريتين
        formatted_distance = f"{distance:.2f}"
        
        # إنشاء الرسالة
        message = f"المسافة من موقعك الحالي إلى {formatted_name} هي {formatted_distance} كيلومتر."
        
        return message