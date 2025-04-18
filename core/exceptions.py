"""
استثناءات مخصصة للتطبيق.
"""

class BaseChatbotError(Exception):
    """الفئة الأساسية لجميع استثناءات الشاتبوت."""
    pass


class ServiceInitializationError(BaseChatbotError):
    """يُثار عندما يفشل تهيئة خدمة."""
    pass


class DataLoadingError(BaseChatbotError):
    """يُثار عندما تفشل عملية تحميل البيانات."""
    pass


class LLMServiceError(BaseChatbotError):
    """يُثار عندما يحدث خطأ في خدمة النموذج اللغوي."""
    pass


class QueryClassificationError(BaseChatbotError):
    """يُثار عندما يفشل تصنيف الاستعلام."""
    pass


class FacilitySearchError(BaseChatbotError):
    """يُثار عندما يفشل البحث عن المرافق."""
    pass


class NeighborhoodRecommendationError(BaseChatbotError):
    """يُثار عندما تفشل توصية الحي."""
    pass


class ResponseFormattingError(BaseChatbotError):
    """يُثار عندما يفشل تنسيق الرد."""
    pass

class DistanceCalculationError(BaseChatbotError):
    """يُثار عندما يفشل حساب المسافة بين المستخدم والحي."""
    pass