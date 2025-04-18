"""
مسارات واجهة برمجة التطبيقات (API).
"""

import logging
import uuid
from flask import Flask, request, jsonify, current_app
from typing import Dict, Any
from bson.regex import Regex
import re
import hashlib



logger = logging.getLogger(__name__)

def register_routes(app: Flask) -> None:
    """
    تسجيل مسارات واجهة برمجة التطبيقات.
    
    Args:
        app: تطبيق Flask
    """
    @app.route('/chat', methods=['POST'])
    def chat() -> Dict[str, Any]:
        """
        معالجة رسائل الدردشة والاستجابة لها.
        """
        # التحقق من البيانات المستلمة
        data = request.json
        if not data:
            logger.warning("لم يتم استلام بيانات JSON")
            return jsonify({
                'response': 'لم يتم استلام بيانات صالحة. يرجى إرسال رسالتك.',
                'status': 'error'
            }), 400
        
        
        # الحصول على الشاتبوت
        chatbot = current_app.config['CHATBOT']

        # استخراج البيانات من الطلب
        user_message = data.get('message', '')
        user_id = data.get('user_id', str(uuid.uuid4()))  # إنشاء معرف جديد إذا لم يتم تقديمه
        user_latitude = data.get('latitude')
        user_longitude = data.get('longitude')

        # التحقق من وجود معلمات إضافية
        neighborhood_name = data.get('neighborhood')
        query_type = data.get('type')
        
        # الاستجابة بناءً على نوع الاستعلام
        if query_type == 'specific' and neighborhood_name:
            # معالجة طلب مخصص (مثل البحث عن مرافق في حي محدد)
            response = chatbot.handle_specific_requests(user_id, user_message, neighborhood_name, user_latitude, user_longitude)
        else:
            # معالجة رسالة عادية
            response = chatbot.process_message(user_id, user_message, user_latitude, user_longitude)
        
        # ترجيع الرد
        return jsonify({
            'response': response,
            'status': 'success',
            'user_id': user_id  # إرجاع معرف المستخدم للتخزين في الجانب العميل
        })


    @app.route('/neighborhoods', methods=['GET'])
    def get_neighborhoods() -> Dict[str, Any]:
        """
        الحصول على قائمة الأحياء المتاحة.
        """
        chatbot = current_app.config['CHATBOT']
        neighborhoods = chatbot.get_available_neighborhoods()
        
        return jsonify({
            'neighborhoods': neighborhoods,
            'status': 'success'
        })  


    
    @app.route('/neighborhood/<name>', methods=['GET'])
    def get_neighborhood_info(name: str) -> Dict[str, Any]:
        """
        الحصول على معلومات حي محدد.
        """
        if not name:
            return jsonify({
                'message': 'يرجى تحديد اسم الحي',
                'status': 'error'
            }), 400
        
        chatbot = current_app.config['CHATBOT']
        
        neighborhood_info = chatbot.get_neighborhood_info(name)
        benefits = chatbot.get_neighborhood_benefits(name)
        formatted_response = chatbot.format_neighborhood_response(name)
        
        if not neighborhood_info:
            return jsonify({
                'message': f'لم يتم العثور على معلومات للحي: {name}',
                'status': 'error'
            }), 404
        
        return jsonify({
            'name': name,
            'info': neighborhood_info,
            'benefits': benefits,
            'formatted_response': formatted_response,
            'status': 'success'
        })
    
    @app.route('/search', methods=['GET'])
    def search() -> Dict[str, Any]:
        """
        البحث في ملفات CSV.
        """
        # استخراج معلمات البحث
        csv_file = request.args.get('file')
        query = request.args.get('query')
        
        if not csv_file and not query:
            return jsonify({
                'message': 'يرجى تحديد ملف CSV وعبارة البحث',
                'status': 'error'
            }), 400
        
        # الحصول على الشاتبوت
        chatbot = current_app.config['CHATBOT']
        
        # البحث في جميع المرافق إذا لم يتم تحديد ملف معين
        if not csv_file and query:
            result = chatbot.search_all_facilities(query)
            return jsonify({
                'result': result,
                'status': 'success'
            })
        
        # التحقق من صحة ملف CSV
        valid_files = ['المدارس.csv', 'حدائق.csv', 'سوبرماركت.csv', 'مستشفى.csv', 'مول.csv', 'Neighborhoods.csv']
        if csv_file not in valid_files:
            return jsonify({
                'message': f'ملف CSV غير صالح. الملفات المتاحة: {", ".join(valid_files)}',
                'status': 'error'
            }), 400
        
        # البحث في الملف
        result = chatbot.search_facility(csv_file, query)
        
        return jsonify({
            'result': result,
            'status': 'success'
        })
    
    @app.route('/facilities', methods=['GET'])
    def get_facilities() -> Dict[str, Any]:
        """
        الحصول على مرافق في حي محدد.
        """
        neighborhood = request.args.get('neighborhood')
        facility_type = request.args.get('type')  # اختياري
        
        if not neighborhood:
            return jsonify({
                'message': 'يرجى تحديد اسم الحي',
                'status': 'error'
            }), 400
        
        # التحقق من صحة نوع المرفق إذا تم تحديده
        if facility_type and facility_type not in ['مدرسة', 'مستشفى', 'حديقة', 'سوبرماركت', 'مول']:
            return jsonify({
                'message': 'نوع المرفق غير صالح. الأنواع المتاحة: مدرسة، مستشفى، حديقة، سوبرماركت، مول',
                'status': 'error'
            }), 400
        
        # البحث عن المرافق
        chatbot = current_app.config['CHATBOT']
        result = chatbot.find_facilities_in_neighborhood(neighborhood, facility_type)
        
        return jsonify({
            'neighborhood': neighborhood,
            'facility_type': facility_type,
            'result': result,
            'status': 'success'
        })
    
    @app.route('/facilities/search', methods=['GET'])
    def search_all_facilities() -> Dict[str, Any]:
        """
        البحث في جميع المرافق.
        """
        query = request.args.get('query')
        
        if not query:
            return jsonify({
                'message': 'يرجى تحديد عبارة البحث',
                'status': 'error'
            }), 400
        
        chatbot = current_app.config['CHATBOT']
        result = chatbot.search_all_facilities(query)
        
        return jsonify({
            'query': query,
            'result': result,
            'status': 'success'
        })
    
    @app.route('/health', methods=['GET'])
    def health_check() -> Dict[str, Any]:
        """
        التحقق من صحة الخدمة.
        """
        chatbot = current_app.config['CHATBOT']
        
        # التحقق من تهيئة المكونات الرئيسية
        components_status = chatbot.check_components_status()
        all_ok = all(components_status.values())
        
        return jsonify({
            'status': 'healthy' if all_ok else 'degraded',
            'components': components_status,
            'version': '1.0.0'
        }), 200 if all_ok else 207
    

    @app.route('/distances/neighborhood', methods=['GET'])
    def get_distance_to_neighborhood() -> Dict[str, Any]:
        """
        حساب المسافة بين عنوان المستخدم وحي معين.
        """
        user_address = request.args.get('address')
        neighborhood = request.args.get('neighborhood')
        
        if not user_address or not neighborhood:
            return jsonify({
                'message': 'يرجى تحديد عنوان المستخدم واسم الحي',
                'status': 'error'
            }), 400
        
        chatbot = current_app.config['CHATBOT']
        result = chatbot.get_distance_to_neighborhood(user_address, neighborhood)
        
        return jsonify({
            'user_address': user_address,
            'neighborhood': neighborhood,
            'result': result,
            'status': 'success'
        })
    
    @app.route('/neighborhoods/closest', methods=['GET'])
    def find_closest_neighborhoods() -> Dict[str, Any]:
        """
        العثور على أقرب الأحياء إلى عنوان المستخدم.
        """
        user_address = request.args.get('address')
        count = request.args.get('count', default=5, type=int)
        
        if not user_address:
            return jsonify({
                'message': 'يرجى تحديد عنوان المستخدم',
                'status': 'error'
            }), 400
        
        chatbot = current_app.config['CHATBOT']
        closest_neighborhoods = chatbot.find_closest_neighborhoods(user_address, count)
        
        return jsonify({
            'user_address': user_address,
            'count': count,
            'closest_neighborhoods': closest_neighborhoods,
            'status': 'success'
        })
    
    @app.route('/neighborhood/with-distance/<name>', methods=['GET'])
    def get_neighborhood_with_distance(name: str) -> Dict[str, Any]:
        """
        الحصول على معلومات حي مع المسافة من موقع المستخدم.
        """
        if not name:
            return jsonify({
                'message': 'يرجى تحديد اسم الحي',
                'status': 'error'
            }), 400
        
        user_address = request.args.get('address')
        if not user_address:
            return jsonify({
                'message': 'يرجى تحديد عنوان المستخدم',
                'status': 'error'
            }), 400
        
        chatbot = current_app.config['CHATBOT']
        
        result = chatbot.get_neighborhood_with_distance(user_address, name)
        
        if 'error' in result:
            return jsonify({
                'message': result['error'],
                'status': 'error'
            }), 500
        
        return jsonify({
            'name': name,
            'user_address': user_address,
            'result': result,
            'status': 'success'
        })

            # ✅ مسار جديد لجلب أسعار حي معين
    @app.route('/get_neighborhood/<string:name>', methods=['GET'])
    def get_neighborhood_prices(name):
        """
        يرجع سعر المتر للشقق والفلل في حي محدد.
        """
        chatbot = current_app.config['CHATBOT']
        info = chatbot.get_neighborhood_info(name)

        if not info:
            return jsonify({'error': 'not found'}), 404

        return jsonify({
            'apartment': info.get('price_of_meter_Apartment'),
            'villa': info.get('price_of_meter_Villas')
        })







    @app.route('/filter', methods=['POST'])
    def filter_neighborhood():
        print("🚨 تم الوصول إلى راوت /filter")

        data = request.get_json()
        print("✅ تم استقبال البيانات من التطبيق:", data)

        budget = data.get('budget')
        neighborhood_type = data.get('type')
        space = data.get('space')
        modernity = data.get('modernity')

        print("🔍 القيم المستلمة:")
        print("budget:", budget)
        print("type:", neighborhood_type)
        print("space:", space)
        print("modernity:", modernity)

        if not all([budget, neighborhood_type, space, modernity]):
            print("❌ بيانات ناقصة:", data)
            return jsonify({"error": "بيانات ناقصة"}), 400

        db = current_app.config['MONGO_DB']

        matched_doc = db.Knowledge_base.find_one({
            "كم كان الحد الأقصى للميزانية؟": {
                "$regex": re.escape(budget), "$options": "i"
            },
            "هل كنت تفضل العيش في منطقة هادئة أم نشطة؟ ": {
                "$regex": re.escape(neighborhood_type), "$options": "i"
            },
            " كم كانت المساحة المطلوبة (بالمتر المربع)؟": {
                "$regex": re.escape(space), "$options": "i"
            },
            "ماكان مدى أهمية اختيار منطقة حديثة؟": {
                "$regex": re.escape(modernity), "$options": "i"
            },
        })

        if not matched_doc:
            print("⚠️ لم يتم العثور على حي يطابق هذه القيم.")
            return jsonify({"error": "لا يوجد حي مناسب"}), 404

        neighborhood_name = matched_doc.get("ماهو الحي الذي اشتريت/ استأجرت به؟")
        print("🎯 الحي المطابق:", neighborhood_name)

        matched_neighborhood = db.Neighborhoods.find_one({
            "Name_of_neighborhood": neighborhood_name
        })

        if not matched_neighborhood:
            return jsonify({"error": "الحي غير موجود في جدول الأحياء"}), 404

        return jsonify({
            "neighborhood": neighborhood_name,
            "description": matched_neighborhood.get("Description", ""),
            "price_apartment": matched_neighborhood.get("price_of_meter_Apartment"),
            "price_villa": matched_neighborhood.get("price_of_meter_Villas")
        })




    @app.route('/helpus', methods=['POST'])
    def save_helpus_data():
        data = request.get_json()
        if not data:
            return jsonify({'message': 'لم يتم إرسال بيانات', 'status': 'error'}), 400

        try:
            chatbot = current_app.config['CHATBOT']
            chatbot.save_helpus_data(data)  # 👈 هذه السطر يستخدم الدالة الموجودة في chatbot.py
            return jsonify({'message': 'تم حفظ البيانات بنجاح', 'status': 'success'})
        except Exception as e:
            logger.error(f"خطأ أثناء حفظ البيانات: {str(e)}")
            return jsonify({'message': 'حدث خطأ أثناء الحفظ', 'status': 'error'}), 500    
 
    

    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()



    
    @app.route('/change-password', methods=['POST'])
    def change_password():
        data = request.get_json()
        if not data:
            return jsonify({'message': 'لم يتم إرسال بيانات'}), 400

        email = data.get('email')
        old_password = data.get('old_password')
        new_password = data.get('new_password')

        if not all([email, old_password, new_password]):
            return jsonify({'message': 'يرجى تعبئة جميع الحقول'}), 400

        db = current_app.config['MONGO_DB']
        user = db.users.find_one({'email': email})

        if not user:
            return jsonify({'message': 'المستخدم غير موجود'}), 404

        hashed_old_pw = hash_password(old_password)
        if user['password'] != hashed_old_pw:
            return jsonify({'message': 'كلمة المرور القديمة غير صحيحة'}), 401

        hashed_new_pw = hash_password(new_password)
        db.users.update_one({'email': email}, {'$set': {'password': hashed_new_pw}})

        return jsonify({'message': 'تم تغيير كلمة المرور بنجاح'}), 200    


    @app.route('/register', methods=['POST'])
    def register_user():
        data = request.get_json()
        print("✅ تم استقبال طلب تسجيل جديد")

        if not data:
            return jsonify({'message': 'لم يتم إرسال بيانات'}), 400

        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')

        if not all([email, password, full_name]):
            return jsonify({'message': 'يرجى تعبئة جميع الحقول'}), 400

        db = current_app.config['MONGO_DB']
        existing_user = db.users.find_one({'email': email})
        if existing_user:
            return jsonify({'message': 'البريد الإلكتروني مستخدم مسبقًا'}), 409

        hashed_pw = hash_password(password)

        db.users.insert_one({
            'full_name': full_name,
            'email': email,
            'password': hashed_pw
        })

        return jsonify({'message': 'تم التسجيل بنجاح'}), 201


    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        if not data:
            return jsonify({'message': 'لم يتم إرسال بيانات'}), 400

        email = data.get('email')
        password = data.get('password')

        if not all([email, password]):
            return jsonify({'message': 'يرجى تعبئة البريد وكلمة المرور'}), 400

        db = current_app.config['MONGO_DB']
        hashed_pw = hash_password(password)

        user = db.users.find_one({'email': email, 'password': hashed_pw})

        if user:
            return jsonify({
                'message': 'تم تسجيل الدخول بنجاح',
                'full_name': user['full_name']
            }), 200
        else:
            return jsonify({'message': 'بيانات الدخول غير صحيحة'}), 401







    @app.route('/delete_account', methods=['POST'])
    def delete_account():
        data = request.get_json()
        email = data.get('email')

        if not email:
            return jsonify({'message': 'البريد الإلكتروني مطلوب'}), 400

        db = current_app.config['MONGO_DB']
        result = db.users.delete_one({'email': email})

        if result.deleted_count > 0:
            return jsonify({'message': 'تم حذف الحساب بنجاح'}), 200
        else:
            return jsonify({'message': 'لم يتم العثور على المستخدم'}), 404
            
