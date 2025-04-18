"""
نقطة بدء تطبيق شاتبوت الأحياء والعقارات.
"""

from app import create_app
from utils.logger import setup_logging

# إعداد التسجيل
setup_logging()

# إنشاء التطبيق
app = create_app()

if __name__ == '__main__':
    # تشغيل التطبيق
    app.run(debug=app.config['DEBUG'], host=app.config['HOST'], port=app.config['PORT'])
