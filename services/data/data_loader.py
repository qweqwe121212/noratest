# -*- coding: utf-8 -*-

"""
محمل البيانات المركزي للتطبيق.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging
from pymongo import MongoClient

from core.exceptions import DataLoadingError

logger = logging.getLogger(__name__)

class DataLoader:
    """
    مسؤول عن تحميل ومعالجة البيانات من MongoDB للشاتبوت.
    """
    def __init__(self, mongo_uri: str, mongo_db: str, 
                 default_neighborhoods: List[str]):
        """
        تهيئة محمل البيانات من MongoDB.
        
        Args:
            mongo_uri: عنوان اتصال MongoDB
            mongo_db: اسم قاعدة البيانات
            default_neighborhoods: قائمة الأحياء الافتراضية
        """
        self.default_neighborhoods = default_neighborhoods
        
        # الاتصال بقاعدة البيانات MongoDB
        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[mongo_db]
            logger.info(f"تم الاتصال بقاعدة البيانات MongoDB: {mongo_db}")
        except Exception as e:
            logger.error(f"فشل الاتصال بقاعدة البيانات MongoDB: {str(e)}")
            raise DataLoadingError(f"فشل الاتصال بقاعدة البيانات: {str(e)}")
        
        # تحميل البيانات من MongoDB
        self.knowledge_base = self._load_dataframe('Knowledge_base')
        self.neighborhoods = self._load_dataframe('Neighborhoods')
        self.schools = self._load_dataframe('Schools')
        self.parks = self._load_dataframe('Gardens')  # اسم المجموعة في MongoDB
        self.supermarkets = self._load_dataframe('Supermarkets')
        self.hospitals = self._load_dataframe('Hospitals')
        self.malls = self._load_dataframe('Malls')
        
        # تحديد أسماء الأعمدة
        self._identify_columns()
        
        # معالجة مميزات الأحياء
        self._process_neighborhood_benefits()
        
        logger.info("تم تهيئة محمل البيانات من MongoDB بنجاح")
    
    def _verify_files_exist(self) -> None:
        """
        التحقق من وجود جميع ملفات البيانات.
        """
        missing_files = []
        for name, path in self.file_paths.items():
            if not os.path.exists(path):
                missing_files.append(f"{name}: {path}")
        
        if missing_files:
            logger.warning(f"الملفات التالية غير موجودة: {', '.join(missing_files)}")
    
    def _load_dataframe(self, collection_name: str) -> pd.DataFrame:
        """
        تحميل بيانات من مجموعة MongoDB إلى DataFrame.
        
        Args:
            collection_name: اسم المجموعة في MongoDB
            
        Returns:
            pd.DataFrame: البيانات المحملة
        """
        try:
            # الحصول على المجموعة من MongoDB
            collection = self.db[collection_name]
            
            # استخراج البيانات
            data = list(collection.find({}))
            
            # تحويل إلى DataFrame
            if data:
                df = pd.DataFrame(data)
                
                # حذف عمود _id الذي تضيفه MongoDB تلقائياً
                if '_id' in df.columns:
                    df = df.drop('_id', axis=1)
                
                logger.info(f"تم تحميل بيانات المجموعة {collection_name} بنجاح ({len(df)} صف)")
                return df
            else:
                logger.warning(f"المجموعة {collection_name} فارغة")
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"خطأ في تحميل بيانات المجموعة {collection_name}: {str(e)}")
            return pd.DataFrame()
    
    def _identify_columns(self) -> None:
        """
        تحديد أسماء الأعمدة في ملفات البيانات المحمّلة.
        """
        # لقاعدة المعرفة
        self.neighborhood_column = "ماهو الحي الذي اشتريت/ استأجرت به؟"
        self._validate_column(self.knowledge_base, self.neighborhood_column, "neighborhood")
        
        self.case_column = "الحالة"
        self._validate_column(self.knowledge_base, self.case_column, "case")
        
        self.satisfaction_column = "ما سبب أنك راضٍ عن عملية الشراء/ الاستئجار في هذا الحي؟  "
        self._validate_column(self.knowledge_base, self.satisfaction_column, "satisfaction")
        
        # لملف الأحياء
        self.neighborhood_name_column = "Name_of_neighborhood"
        self._validate_column(self.neighborhoods, self.neighborhood_name_column, "neighborhood_name")
        
        # تعيين الأحياء المتاحة
        self._set_available_neighborhoods()
    
    def _validate_column(self, df: pd.DataFrame, column_name: str, column_type: str) -> None:
        """
        التحقق من وجود العمود في DataFrame، ومحاولة إيجاد بديل إذا لم يكن موجودًا.
        
        Args:
            df: DataFrame للتحقق
            column_name: اسم العمود
            column_type: نوع العمود (للتسجيل)
        """
        if not df.empty and column_name in df.columns:
            logger.info(f"تم العثور على العمود المطلوب {column_type}: {column_name}")
        else:
            logger.warning(f"العمود '{column_name}' غير موجود!")
            
            # محاولة العثور على أعمدة بديلة
            if column_type == "neighborhood":
                possible_columns = [col for col in df.columns if "الحي" in col]
                self._set_alternative_column(df, column_name, possible_columns, "الحي_المقترح", column_type)
            
            elif column_type == "case":
                possible_columns = [col for col in df.columns if "حالة" in col.lower()]
                self._set_alternative_column(df, column_name, possible_columns, None, column_type)
            
            elif column_type == "satisfaction":
                possible_columns = [col for col in df.columns if "راضٍ" in col or "مميزات" in col]
                self._set_alternative_column(df, column_name, possible_columns, None, column_type)
            
            elif column_type == "neighborhood_name":
                possible_columns = [col for col in df.columns if "name" in col.lower() or "اسم" in col.lower()]
                self._set_alternative_column(df, column_name, possible_columns, None, column_type)
    
    def _set_alternative_column(self, df: pd.DataFrame, column_name: str, 
                               possible_columns: List[str], fallback: Optional[str], 
                               column_type: str) -> None:
        """
        تعيين عمود بديل إذا كان ممكنًا.
        
        Args:
            df: DataFrame للتحقق
            column_name: اسم العمود الأصلي
            possible_columns: قائمة بأسماء الأعمدة البديلة المحتملة
            fallback: اسم العمود الاحتياطي إذا لم يتم العثور على بديل
            column_type: نوع العمود (للتسجيل)
        """
        if possible_columns:
            setattr(self, column_type + "_column", possible_columns[0])
            logger.info(f"استخدام العمود البديل {column_type}: {possible_columns[0]}")
        elif fallback and fallback in df.columns:
            setattr(self, column_type + "_column", fallback)
            logger.info(f"استخدام {fallback} كاحتياطي لـ {column_type}")
        else:
            logger.warning(f"لم يتم العثور على عمود {column_type} مناسب")
            setattr(self, column_type + "_column", None)
    
    def _set_available_neighborhoods(self) -> None:
        """
        تجميع قائمة الأحياء المتاحة من مجموعة الأحياء وقاعدة المعرفة.
        تضمن هذه الخطوة تجميع الأحياء من المصادر المختلفة وإزالة التكرار.
        """
        try:
            self.available_neighborhoods = []
            
            # جمع الأحياء من قاعدة المعرفة
            if not self.knowledge_base.empty and 'category' in self.knowledge_base.columns and 'neighborhood' in self.knowledge_base.columns:
                kb_neighborhoods = self.knowledge_base[self.knowledge_base['category'] == 'الأحياء']['neighborhood'].tolist()
                kb_neighborhoods = [n for n in kb_neighborhoods if isinstance(n, str) and n.strip()]
                self.available_neighborhoods.extend(kb_neighborhoods)
            
            # جمع الأحياء من مجموعة الأحياء
            if not self.neighborhoods.empty and hasattr(self, 'neighborhood_name_column') and self.neighborhood_name_column in self.neighborhoods.columns:
                collection_neighborhoods = self.neighborhoods[self.neighborhood_name_column].tolist()
                collection_neighborhoods = [n for n in collection_neighborhoods if isinstance(n, str) and n.strip()]
                self.available_neighborhoods.extend(collection_neighborhoods)
            
            # إزالة التكرار وتنظيف القائمة
            self.available_neighborhoods = list(set(self.available_neighborhoods))
            self.available_neighborhoods = [n.replace("حي ", "").strip() for n in self.available_neighborhoods]
            self.available_neighborhoods = [n for n in self.available_neighborhoods if n]
            
            logger.info(f"تم تجميع {len(self.available_neighborhoods)} حي من مجموعة الأحياء وقاعدة المعرفة")
            
        except Exception as e:
            logger.error(f"خطأ في تجميع قائمة الأحياء: {str(e)}")
            self.available_neighborhoods = []
    
    def _process_neighborhood_benefits(self) -> None:
        """
        معالجة مميزات الأحياء من قاعدة المعرفة.
        """
        self.neighborhood_benefits = {}
        
        if (hasattr(self, 'neighborhood_column') and self.neighborhood_column and
            hasattr(self, 'satisfaction_column') and self.satisfaction_column and
            not self.knowledge_base.empty):
            
            # تجميع المميزات لكل حي
            for _, row in self.knowledge_base.iterrows():
                neighborhood = row.get(self.neighborhood_column)
                satisfaction = row.get(self.satisfaction_column)
                
                if pd.notna(neighborhood) and pd.notna(satisfaction) and satisfaction:
                    # تنظيف اسم الحي
                    clean_name = str(neighborhood).strip()
                    
                    if clean_name not in self.neighborhood_benefits:
                        self.neighborhood_benefits[clean_name] = []
                    
                    if satisfaction not in self.neighborhood_benefits[clean_name]:
                        self.neighborhood_benefits[clean_name].append(str(satisfaction))
            
            logger.info(f"تم تحميل مميزات لـ {len(self.neighborhood_benefits)} حي")
    
    # الواجهات العامة
    
    def get_available_neighborhoods(self) -> List[str]:
        """
        الحصول على قائمة الأحياء المتاحة.
        
        Returns:
            List[str]: قائمة بأسماء الأحياء المتاحة
        """
        return self.available_neighborhoods
    
    def get_neighborhood_from_case(self, case_id: int) -> Optional[str]:
        """
        الحصول على اسم الحي من معرّف الحالة.
        
        Args:
            case_id: معرف الحالة
            
        Returns:
            Optional[str]: اسم الحي إذا وجد، وإلا None
        """
        try:
            case_index = case_id - 1
            if (case_index < 0 or case_index >= len(self.knowledge_base) or
                not hasattr(self, 'neighborhood_column') or not self.neighborhood_column or
                self.neighborhood_column not in self.knowledge_base.columns):
                return None
            
            neighborhood = self.knowledge_base.iloc[case_index][self.neighborhood_column]
            return neighborhood if pd.notna(neighborhood) and neighborhood else None
        
        except Exception as e:
            logger.error(f"خطأ في الحصول على الحي من الحالة {case_id}: {str(e)}")
            return None
    
    def find_neighborhood_info(self, neighborhood_name: str) -> Dict:
        """
        البحث عن معلومات الحي في مجموعة الأحياء.
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            Dict: قاموس يحتوي على معلومات الحي
        """
        try:
            if (self.neighborhoods.empty or not hasattr(self, 'neighborhood_name_column') or
                not self.neighborhood_name_column or 
                self.neighborhood_name_column not in self.neighborhoods.columns):
                logger.warning("بيانات الأحياء أو العمود غير متاح")
                return {}
            
            # إزالة بادئة "حي" إذا كانت موجودة
            clean_name = neighborhood_name.replace("حي ", "").strip()
            
            # محاولة التطابق المباشر
            exact_match = self.neighborhoods[self.neighborhoods[self.neighborhood_name_column] == clean_name]
            if not exact_match.empty:
                return exact_match.iloc[0].to_dict()
            
            # محاولة التطابق المباشر مع بادئة "حي"
            exact_match = self.neighborhoods[self.neighborhoods[self.neighborhood_name_column] == "حي " + clean_name]
            if not exact_match.empty:
                return exact_match.iloc[0].to_dict()
            
            # محاولة التطابق الجزئي
            for name_to_try in [clean_name, "حي " + clean_name]:
                partial_matches = self.neighborhoods[
                    self.neighborhoods[self.neighborhood_name_column].str.contains(name_to_try, na=False, case=False)
                ]
                if not partial_matches.empty:
                    return partial_matches.iloc[0].to_dict()
            
            logger.warning(f"الحي '{neighborhood_name}' غير موجود في مجموعة الأحياء")
            return {}
            
        except Exception as e:
            logger.error(f"خطأ في العثور على معلومات الحي: {str(e)}")
            return {}
    
    def get_neighborhood_benefits(self, neighborhood_name: str) -> List[str]:
        """
        الحصول على مميزات حي معين.
        
        Args:
            neighborhood_name: اسم الحي
            
        Returns:
            List[str]: قائمة بمميزات الحي
        """
        try:
            clean_name = neighborhood_name.replace("حي ", "").strip()
            
            # محاولة التطابق المباشر
            if clean_name in self.neighborhood_benefits:
                return self.neighborhood_benefits[clean_name]
            
            # محاولة التطابق مع بادئة "حي"
            if f"حي {clean_name}" in self.neighborhood_benefits:
                return self.neighborhood_benefits[f"حي {clean_name}"]
            
            # محاولة التطابق الجزئي
            for neighborhood in self.neighborhood_benefits.keys():
                if clean_name in neighborhood or neighborhood in clean_name:
                    return self.neighborhood_benefits[neighborhood]
            
            logger.warning(f"لم يتم العثور على مميزات للحي '{neighborhood_name}'")
            return []
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مميزات الحي: {str(e)}")
            return []
    
    def get_cases_for_llm(self) -> List[Dict]:
        """
        الحصول على الحالات المنسقة لمعالجة النموذج اللغوي.
        
        Returns:
            List[Dict]: قائمة بالحالات المنسقة
        """
        knowledge_cases = []
        
        try:
            if (self.knowledge_base.empty or not hasattr(self, 'case_column') or 
                not self.case_column or not hasattr(self, 'neighborhood_column') or 
                not self.neighborhood_column):
                logger.warning("قاعدة المعرفة أو الأعمدة المطلوبة غير موجودة")
                return knowledge_cases
            
            for index, row in self.knowledge_base.iterrows():
                if (self.case_column in row and pd.notna(row[self.case_column]) and 
                    self.neighborhood_column in row and pd.notna(row[self.neighborhood_column])):
                    case = {
                        "رقم_الحالة": index + 1,
                        "الحالة": row[self.case_column],
                        "الحي_المقترح": row[self.neighborhood_column]
                    }
                    knowledge_cases.append(case)
            
            logger.info(f"تم تجهيز {len(knowledge_cases)} حالة للنموذج اللغوي")
            return knowledge_cases
            
        except Exception as e:
            logger.error(f"خطأ في تجهيز الحالات للنموذج اللغوي: {str(e)}")
            return []
    
    # واجهات للحصول على البيانات الخام
    
    def get_neighborhoods_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات الأحياء الخام.
        
        Returns:
            pd.DataFrame: بيانات الأحياء
        """
        return self.neighborhoods
    
    def get_schools_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات المدارس الخام.
        
        Returns:
            pd.DataFrame: بيانات المدارس
        """
        return self.schools
    
    def get_parks_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات الحدائق الخام.
        
        Returns:
            pd.DataFrame: بيانات الحدائق
        """
        return self.parks
    
    def get_supermarkets_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات السوبرماركت الخام.
        
        Returns:
            pd.DataFrame: بيانات السوبرماركت
        """
        return self.supermarkets
    
    def get_hospitals_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات المستشفيات الخام.
        
        Returns:
            pd.DataFrame: بيانات المستشفيات
        """
        return self.hospitals
    
    def get_malls_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات المولات الخام.
        
        Returns:
            pd.DataFrame: بيانات المولات
        """
        return self.malls
    
    def get_knowledge_base_data(self) -> pd.DataFrame:
        """
        الحصول على بيانات قاعدة المعرفة الخام.
        
        Returns:
            pd.DataFrame: بيانات قاعدة المعرفة
        """
        return self.knowledge_base
