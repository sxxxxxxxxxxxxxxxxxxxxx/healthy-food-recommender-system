from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
import requests
import os
from dotenv import load_dotenv
from collections import deque
import hashlib
from sqlalchemy import text
import html

# 加载环境变量
load_dotenv()

# 检查API密钥是否加载成功
api_key = os.getenv('OPENWEATHER_API_KEY')
unsplash_access_key = os.getenv('UNSPLASH_ACCESS_KEY')

if not api_key:
    print("API 密钥未配置或加载失败！")
else:
    print("API 密钥加载成功！")

app = Flask(__name__)

_is_serverless = bool(os.getenv('VERCEL') or os.getenv('AWS_LAMBDA_FUNCTION_NAME'))
_sqlite_path = '/tmp/foods.db' if _is_serverless else 'foods.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{_sqlite_path}'  # 使用SQLite数据库
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

recent_recommendation_history = {}

# 食物模型类
class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    sugar_content = db.Column(db.Float, nullable=False)
    food_type = db.Column(db.String(50), nullable=False)
    recommend_time = db.Column(db.String(50), nullable=False)
    weather_conditions = db.Column(db.String(100), nullable=False)
    allergens = db.Column(db.String(100), nullable=True)  # 过敏源信息（例如：花生, 牛奶）
    image_url = db.Column(db.String(255), nullable=True)

# 用户模型类
class User(db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    health_condition = db.Column(db.String(100), nullable=True)  # 健康状况
    allergic_foods = db.Column(db.String(100), nullable=True)  # 过敏食物，多个以逗号分隔

# 天气映射表，处理中英文天气名称和同义词
weather_mapping = {
    'Clear': ['晴天', '晴'],
    'Clouds': ['阴天', '多云', '阴'],
    'Rain': ['雨天', '雨', '阵雨'],
    'Drizzle': ['小雨', '毛毛雨'],
    'Thunderstorm': ['雷雨', '雷暴'],
    'Snow': ['雪', '雪天', '寒冷'],
    'Mist': ['雾', '雾天'],
    'Fog': ['雾', '雾天'],
    'Haze': ['雾霾', '霾'],
    '风': ['风', '大风']
}

# 预设的高质量 Unsplash 图片映射 (热门食物)
# 这些是直接指向 Unsplash 图片的链接 (无版权问题，可用于 Demo)
PRESET_FOOD_IMAGES = {
    '无糖燕麦粥': 'https://images.unsplash.com/photo-1517673132405-a56a62b18caf?auto=format&fit=crop&w=800&q=80',
    '全麦吐司': 'https://images.unsplash.com/photo-1598373182133-52452f7691f3?auto=format&fit=crop&w=800&q=80',
    '水煮鸡蛋': 'https://images.unsplash.com/photo-1482049016688-2d3e1b311543?auto=format&fit=crop&w=800&q=80',
    '清炒西兰花': 'https://images.unsplash.com/photo-1583061686733-4f100140c944?auto=format&fit=crop&w=800&q=80',
    '香煎鸡胸肉': 'https://images.unsplash.com/photo-1632778149955-e80f8ceca2e8?auto=format&fit=crop&w=800&q=80',
    '清蒸鱼': 'https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?auto=format&fit=crop&w=800&q=80',
    '凉拌黄瓜': 'https://images.unsplash.com/photo-1606850246029-dd00d3ade945?auto=format&fit=crop&w=800&q=80',
    '番茄炒蛋（少油）': 'https://images.unsplash.com/photo-1613769049987-b31b641325b1?auto=format&fit=crop&w=800&q=80',
    '玉米': 'https://images.unsplash.com/photo-1551754655-cd27e38d2076?auto=format&fit=crop&w=800&q=80',
    '杂粮饭': 'https://images.unsplash.com/photo-1596560548464-f010549b8416?auto=format&fit=crop&w=800&q=80',
    '虾仁豆腐': 'https://images.unsplash.com/photo-1559314809-0d155014e29e?auto=format&fit=crop&w=800&q=80',
    '紫菜蛋花汤': 'https://images.unsplash.com/photo-1547592166-23acbe54099c?auto=format&fit=crop&w=800&q=80',
}

# 获取当前天气的函数
def get_weather(city='Beijing'):
    global api_key  # 使用全局API密钥变量
    if not api_key:
        print("API密钥未配置")
        return None
    
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=zh_cn'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # 抛出HTTP错误
        data = response.json()

        if response.status_code == 200:
            weather = data['weather'][0]['main']  # 获取天气主信息，例如：晴、阴、雨等
            return weather
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"获取天气信息失败: {e}")
        return None

def get_unsplash_image_url(food_name):
    """
    使用 Unsplash API 搜索食物图片
    需要配置 UNSPLASH_ACCESS_KEY 环境变量
    """
    global unsplash_access_key
    if not unsplash_access_key:
        return None
        
    try:
        url = f"https://api.unsplash.com/search/photos"
        params = {
            "query": f"{food_name} food",
            "client_id": unsplash_access_key,
            "per_page": 1,
            "lang": "zh"  # 尝试支持中文搜索
        }
        resp = requests.get(url, params=params, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data['results']:
                # 返回 regular 大小的图片 URL
                return data['results'][0]['urls']['regular']
    except Exception as e:
        print(f"Unsplash API 调用失败: {e}")
    
    return None

def _get_user_or_error(user_id: int):
    user = User.query.get(user_id)
    if not user:
        return None, (jsonify({'error': '用户信息未找到'}), 404)
    return user, None

def _get_recent_ids(user_id: int):
    history = recent_recommendation_history.get(user_id)
    if not history:
        return set()
    return set(history)

def _record_recommended_ids(user_id: int, food_ids):
    if user_id not in recent_recommendation_history:
        recent_recommendation_history[user_id] = deque(maxlen=30)
    recent_recommendation_history[user_id].extend([fid for fid in food_ids if fid is not None])

def _food_to_dict(food: 'Food'):
    return {
        'id': food.id,
        'food_name': food.food_name,
        'calories': food.calories,
        'sugar_content': food.sugar_content,
        'food_type': food.food_type,
        'recommend_time': food.recommend_time,
        'weather_conditions': food.weather_conditions,
        'allergens': food.allergens,
        'image_url': getattr(food, 'image_url', None)
    }

def _ensure_food_image_column():
    try:
        cols = db.session.execute(text("PRAGMA table_info(food)")).fetchall()
    except Exception:
        cols = []
    if not cols:
        try:
            cols = db.session.execute(text("PRAGMA table_info(foods)")).fetchall()
        except Exception:
            cols = []

    names = set()
    for row in cols:
        try:
            names.add(row[1])
        except Exception:
            pass

    if 'image_url' in names:
        return

    try:
        db.session.execute(text("ALTER TABLE food ADD COLUMN image_url VARCHAR(255)"))
        db.session.commit()
        return
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE foods ADD COLUMN image_url VARCHAR(255)"))
        db.session.commit()
    except Exception:
        db.session.rollback()

def _svg_thumb(food_name: str, subtitle: str):
    title = (food_name or '食物').strip().replace('\n', ' ')
    title = title[:12]
    sub = (subtitle or '').strip().replace('\n', ' ')
    sub = sub[:10]
    title_xml = html.escape(title, quote=True)
    sub_xml = html.escape(sub, quote=True)
    base = int(hashlib.md5(f"{title}|{sub}".encode('utf-8')).hexdigest()[:8], 16)
    hue1 = base % 360
    hue2 = (hue1 + 46) % 360
    c1 = f"hsl({hue1} 82% 56%)"
    c2 = f"hsl({hue2} 82% 56%)"
    svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"360\" viewBox=\"0 0 640 360\">
  <defs>
    <linearGradient id=\"g\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
      <stop offset=\"0\" stop-color=\"{c1}\"/>
      <stop offset=\"1\" stop-color=\"{c2}\"/>
    </linearGradient>
  </defs>
  <rect width=\"640\" height=\"360\" rx=\"28\" fill=\"url(#g)\"/>
  <rect x=\"24\" y=\"24\" width=\"592\" height=\"312\" rx=\"22\" fill=\"rgba(255,255,255,0.14)\" stroke=\"rgba(255,255,255,0.22)\"/>
  <text x=\"48\" y=\"186\" fill=\"rgba(255,255,255,0.96)\" font-size=\"44\" font-weight=\"800\" font-family=\"Noto Sans SC, system-ui, -apple-system, Segoe UI, Arial\">{title_xml}</text>
  <text x=\"48\" y=\"236\" fill=\"rgba(255,255,255,0.92)\" font-size=\"26\" font-weight=\"700\" font-family=\"Noto Sans SC, system-ui, -apple-system, Segoe UI, Arial\">{sub_xml}</text>
</svg>"""
    return svg

def _populate_missing_image_urls():
    try:
        foods = Food.query.filter((Food.image_url == None) | (Food.image_url == '')).all()  # noqa: E711
    except Exception:
        return
    changed = 0
    for f in foods:
        # 策略 1: 检查是否有预设图片
        if f.food_name in PRESET_FOOD_IMAGES:
            f.image_url = PRESET_FOOD_IMAGES[f.food_name]
            changed += 1
            continue
            
        # 策略 2: 尝试调用 Unsplash API (如果配置了Key)
        # 注意：为了避免启动时大量请求耗尽配额，这里仅演示，实际生产建议异步或按需触发
        # api_url = get_unsplash_image_url(f.food_name)
        # if api_url:
        #     f.image_url = api_url
        #     changed += 1
        #     continue

        # 策略 3: 使用 SVG 兜底
        # 只有当还没有 URL 时才设置 SVG
        if not f.image_url:
            f.image_url = f"/food_image/{f.id}?v=2"
            changed += 1
    if changed:
        db.session.commit()

def _apply_presets():
    """
    强制将热门食物的图片更新为预设的高清图
    """
    try:
        # 避免在表不存在时报错
        foods = Food.query.filter(Food.food_name.in_(PRESET_FOOD_IMAGES.keys())).all()
    except Exception:
        return
        
    changed = 0
    for f in foods:
        preset_url = PRESET_FOOD_IMAGES.get(f.food_name)
        if preset_url and f.image_url != preset_url:
            f.image_url = preset_url
            changed += 1
            
    if changed:
        db.session.commit()
        print(f"已更新 {changed} 个热门食物为高清图片")

def _bump_image_url_version():
    try:
        foods = Food.query.filter(Food.image_url != None).all()  # noqa: E711
    except Exception:
        return
    changed = 0
    for f in foods:
        url = f.image_url or ''
        # 如果是外部链接 (http/https)，不加 v=2 版本号
        if url.startswith('http'):
            continue
        if not url.startswith('/food_image/'):
            continue
        if 'v=2' in url:
            continue
        f.image_url = f"/food_image/{f.id}?v=2"
        changed += 1
    if changed:
        db.session.commit()

def _filter_foods_for_user(user_id: int, user_time: str, user_city: str, user_max_calories: int, condition_override: str = None):
    user, err = _get_user_or_error(user_id)
    if err:
        return None, err, None

    health_condition_raw = condition_override if condition_override else user.health_condition
    if health_condition_raw is not None:
        health_condition_raw = str(health_condition_raw).strip()
        if health_condition_raw in ('无', 'none', 'None'):
            health_condition_raw = ''

    def _parse_conditions(raw: str):
        s = str(raw or '').strip()
        if not s:
            return []
        for sep in [',', '，', '、', ';', '；', '+']:
            s = s.replace(sep, ',')
        parts = []
        for p in s.split(','):
            v = str(p or '').strip()
            if not v:
                continue
            if v not in parts:
                parts.append(v)
        return parts

    conditions = _parse_conditions(health_condition_raw)
    health_condition = ','.join(conditions)
    allergic_foods = [food.strip() for food in user.allergic_foods.split(',')] if user.allergic_foods else []

    weather = get_weather(user_city)
    fallback_weather_used = False
    if not weather:
        weather = "晴天"
        fallback_weather_used = True
        print("无法获取天气信息，使用默认天气: 晴天")

    matching_weathers = weather_mapping.get(weather, [weather])
    print(f"天气: {weather}, 匹配的天气条件: {matching_weathers}")

    from sqlalchemy import or_
    weather_conditions = [Food.weather_conditions.like(f'%{w}%') for w in matching_weathers]
    print(f"天气条件查询: {weather_conditions}")

    food_recommendations = Food.query.filter(
        Food.recommend_time == user_time,
        or_(*weather_conditions),
        Food.calories <= user_max_calories
    ).all()
    print(f"天气条件筛选后: {[food.food_name for food in food_recommendations]}")

    if not food_recommendations:
        print("天气条件筛选结果为空，放宽天气限制")
        food_recommendations = Food.query.filter(
            Food.recommend_time == user_time,
            Food.calories <= user_max_calories
        ).all()
        print(f"放宽天气限制后: {[food.food_name for food in food_recommendations]}")
    print(f"初始食物推荐: {[food.food_name for food in food_recommendations]}")

    condition_notes = []
    print(f"健康状况: {health_condition}")
    if conditions:
        print(f"健康状况筛选前: {[food.food_name for food in food_recommendations]}")
        cond_set = set(conditions)

        if '糖尿病' in cond_set:
            low_sugar = [food for food in food_recommendations if float(food.sugar_content or 0) <= 5]
            if low_sugar:
                food_recommendations = low_sugar
            condition_notes.append('已按糖尿病偏好：优先低糖')

        if '肥胖' in cond_set:
            low_cal = [food for food in food_recommendations if int(food.calories or 0) <= 350]
            if low_cal:
                food_recommendations = low_cal
            condition_notes.append('已按控能量偏好：优先低热量')

        if '高血压' in cond_set:
            if hasattr(Food, 'salt_content'):
                low_salt = [food for food in food_recommendations if float(getattr(food, 'salt_content', 0) or 0) < 1.5]
                if low_salt:
                    food_recommendations = low_salt
                condition_notes.append('已按高血压偏好：优先低盐')
            else:
                condition_notes.append('当前食物库无盐分字段，高血压仅做保守排序：优先低热量/低糖')

        if '高血脂' in cond_set:
            if hasattr(Food, 'fat_content'):
                low_fat = [food for food in food_recommendations if float(getattr(food, 'fat_content', 0) or 0) < 10]
                if low_fat:
                    food_recommendations = low_fat
                condition_notes.append('已按高血脂偏好：优先低脂')
            else:
                condition_notes.append('当前食物库无脂肪字段，高血脂仅做保守排序：优先低热量/低糖')

        if '糖尿病' in cond_set:
            food_recommendations = sorted(food_recommendations, key=lambda f: (float(f.sugar_content or 0), int(f.calories or 0)))
        else:
            food_recommendations = sorted(food_recommendations, key=lambda f: (int(f.calories or 0), float(f.sugar_content or 0)))

    print(f"过敏食物列表: {allergic_foods}")
    filtered_foods = []
    for food in food_recommendations:
        print(f"检查食物: {food.food_name}, 过敏源: {food.allergens}")
        if food.allergens:
            food_allergens = [allergen.strip() for allergen in food.allergens.split(',')]
            if any(allergen in allergic_foods for allergen in food_allergens):
                print(f"食物 {food.food_name} 包含过敏源，被过滤掉")
                continue
        filtered_foods.append(food)
        print(f"食物 {food.food_name} 通过过敏源检查")

    if not conditions:
        filtered_foods.sort(key=lambda x: x.calories, reverse=True)

    meta = {
        'weather': weather,
        'fallback_weather_used': fallback_weather_used,
        'city': user_city,
        'time': user_time,
        'max_calories': user_max_calories,
        'health_condition': health_condition,
        'condition_notes': condition_notes
    }
    return filtered_foods, None, meta

# 根据健康状况、过敏史、天气、时间和热量筛选食物
@app.route('/recommend', methods=['GET'])
def recommend_food():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({'error': '缺少用户ID参数'}), 400

    user_time = request.args.get('time')
    if not user_time:
        return jsonify({'error': '缺少时间参数'}), 400

    user_city = request.args.get('city', 'Beijing')
    user_max_calories = request.args.get('max_calories', 500, type=int)
    condition = request.args.get('condition')

    filtered_foods, err, _meta = _filter_foods_for_user(user_id, user_time, user_city, user_max_calories, condition_override=condition)
    if err:
        return err

    if not filtered_foods:
        return jsonify({'recommendations': [], 'message': '没有找到符合条件的食物'}), 200

    recommended_food = [_food_to_dict(food) for food in filtered_foods]
    return jsonify({'recommendations': recommended_food, 'message': ''})

@app.route('/recommend/meal', methods=['GET'])
def recommend_meal():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({'error': '缺少用户ID参数'}), 400

    user_time = request.args.get('time')
    if not user_time:
        return jsonify({'error': '缺少时间参数'}), 400

    user_city = request.args.get('city', 'Beijing')
    user_max_calories = request.args.get('max_calories', 500, type=int)
    condition = request.args.get('condition')

    foods, err, meta = _filter_foods_for_user(user_id, user_time, user_city, user_max_calories, condition_override=condition)
    if err:
        return err

    if not foods:
        return jsonify({
            'meal': None,
            'alternatives': {'staple': [], 'protein': [], 'vegetable': []},
            'meta': meta,
            'message': '没有找到符合条件的食物'
        }), 200

    allowed_types = {'主食': 'staple', '蛋白': 'protein', '蔬菜': 'vegetable'}
    categorized = {'staple': [], 'protein': [], 'vegetable': [], 'other': []}
    for food in foods:
        key = allowed_types.get(food.food_type)
        if key:
            categorized[key].append(food)
        else:
            categorized['other'].append(food)

    recent_ids = _get_recent_ids(user_id)

    def score(food: 'Food'):
        base = food.calories
        if food.id in recent_ids:
            base -= 10000
        return base

    def pick_one(bucket_key: str, used_ids: set):
        bucket = categorized[bucket_key]
        if not bucket:
            bucket = categorized['other']
        candidates = [f for f in bucket if f.id not in used_ids]
        candidates = sorted(candidates, key=score, reverse=True)
        return candidates[0] if candidates else None

    used_ids = set()
    staple = pick_one('staple', used_ids)
    if staple:
        used_ids.add(staple.id)

    protein = pick_one('protein', used_ids)
    if protein:
        used_ids.add(protein.id)

    vegetable = pick_one('vegetable', used_ids)
    if vegetable:
        used_ids.add(vegetable.id)

    picked = [f for f in [staple, protein, vegetable] if f]
    if not picked:
        return jsonify({
            'meal': None,
            'alternatives': {'staple': [], 'protein': [], 'vegetable': []},
            'meta': meta,
            'message': '没有找到符合条件的食物'
        }), 200

    _record_recommended_ids(user_id, [f.id for f in picked])

    def build_alternatives(bucket_key: str, selected_food: 'Food', excluded_ids: set):
        bucket = categorized[bucket_key] if categorized[bucket_key] else categorized['other']
        candidates = [
            f for f in bucket
            if (
                (not selected_food or f.id != selected_food.id)
                and (f.id not in excluded_ids)
            )
        ]
        candidates = sorted(candidates, key=score, reverse=True)
        seen_ids = set()
        result = []
        for f in candidates:
            if f.id in seen_ids:
                continue
            seen_ids.add(f.id)
            result.append(_food_to_dict(f))
            if len(result) >= 5:
                break
        return result

    excluded_ids = set([f.id for f in picked])
    alternatives = {
        'staple': build_alternatives('staple', staple, excluded_ids),
        'protein': build_alternatives('protein', protein, excluded_ids),
        'vegetable': build_alternatives('vegetable', vegetable, excluded_ids)
    }

    explanations = [
        f"推荐时段：{user_time}",
        f"城市：{user_city}",
        f"最大热量：{user_max_calories}"
    ]
    warnings = []
    if meta and meta.get('health_condition'):
        explanations.append(f"健康状况：{meta.get('health_condition')}")
        notes = meta.get('condition_notes')
        if isinstance(notes, list) and notes:
            warnings.extend([str(x) for x in notes if x])
    if meta and meta.get('fallback_weather_used'):
        warnings.append('天气服务不可用，已使用默认天气策略')
    elif meta and meta.get('weather'):
        explanations.append(f"天气：{meta.get('weather')}")

    meal = {
        'staple': _food_to_dict(staple) if staple else None,
        'protein': _food_to_dict(protein) if protein else None,
        'vegetable': _food_to_dict(vegetable) if vegetable else None,
        'nutrition_total': {
            'calories': sum([f.calories for f in picked]),
            'sugar_content': sum([float(f.sugar_content or 0) for f in picked])
        },
        'explanations': explanations,
        'warnings': warnings
    }

    return jsonify({
        'meal': meal,
        'alternatives': alternatives,
        'meta': meta,
        'message': ''
    }), 200

@app.route('/')
def index():
    # 返回HTML界面
    return app.send_static_file('index.html')

@app.route('/debug/foods')
def debug_foods():
    # 返回所有食物数据用于调试
    foods = Food.query.all()
    return jsonify([{
        'id': food.id,
        'food_name': food.food_name,
        'calories': food.calories,
        'sugar_content': food.sugar_content,
        'food_type': food.food_type,
        'recommend_time': food.recommend_time,
        'weather_conditions': food.weather_conditions,
        'allergens': food.allergens,
        'image_url': getattr(food, 'image_url', None)
    } for food in foods])

@app.route('/food_image/<int:food_id>')
def food_image(food_id: int):
    food = Food.query.get(food_id)
    if not food:
        svg = _svg_thumb('未找到', '')
        return Response(svg, mimetype='image/svg+xml')
    subtitle = f"{food.food_type} · {food.recommend_time}"
    svg = _svg_thumb(food.food_name, subtitle)
    resp = Response(svg, mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
    return resp

@app.route('/debug/weather')
def debug_weather():
    # 测试天气API功能
    city = request.args.get('city', '北京')
    weather = get_weather(city)
    if weather:
        # 获取匹配的天气条件列表
        matching_weathers = weather_mapping.get(weather, [weather])
        return jsonify({
            'city': city,
            'weather': weather,
            'matching_weathers': matching_weathers
        })
    else:
        return jsonify({
            'city': city,
            'weather': '无法获取',
            'message': '使用默认天气: 晴天'
        })

@app.route('/api/verify_weather', methods=['GET'])
def api_verify_weather():
    city = request.args.get('city', 'Beijing')
    key = request.args.get('api_key') or api_key
    if not key:
        return jsonify({
            'ok': False,
            'status_code': 400,
            'city': city,
            'message': 'OPENWEATHER_API_KEY 未配置'
        }), 400

    url = 'https://api.openweathermap.org/data/2.5/weather'
    params = {
        'q': city,
        'appid': key,
        'units': 'metric',
        'lang': 'zh_cn'
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        status = int(resp.status_code)
        payload = {}
        try:
            payload = resp.json() if resp.content else {}
        except Exception:
            payload = {}

        if status == 200:
            weather_main = None
            temp = None
            try:
                weather_main = payload.get('weather', [{}])[0].get('main')
                temp = payload.get('main', {}).get('temp')
            except Exception:
                weather_main = None
                temp = None

            return jsonify({
                'ok': True,
                'status_code': 200,
                'city': city,
                'weather': weather_main,
                'temp_c': temp,
                'message': '验证成功'
            }), 200

        message = None
        if status == 401:
            message = '401 Unauthorized：Key 无效或未生效'
        elif status == 404:
            message = '404 Not Found：城市不存在或拼写错误'
        else:
            message = f'请求失败：状态码 {status}'

        return jsonify({
            'ok': False,
            'status_code': status,
            'city': city,
            'message': message,
            'error': payload
        }), 200
    except requests.exceptions.RequestException as e:
        return jsonify({
            'ok': False,
            'status_code': 500,
            'city': city,
            'message': f'网络请求失败: {e}'
        }), 200

# 初始化食物和用户数据
def initialize_data():
    with app.app_context():
        _ensure_food_image_column()
        _apply_presets()  # 优先应用高清图预设
        # 初始化/补充示例食物数据（幂等：按 food_name 去重）
        seed_foods = [
            # 早餐
            Food(food_name='无糖燕麦粥', calories=180, sugar_content=3, food_type='主食', recommend_time='早餐', weather_conditions='晴天,阴天,雨天', allergens='无'),
            Food(food_name='全麦吐司', calories=160, sugar_content=4, food_type='主食', recommend_time='早餐', weather_conditions='晴天,阴天', allergens='麸质'),
            Food(food_name='水煮鸡蛋', calories=80, sugar_content=0, food_type='蛋白', recommend_time='早餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='鸡蛋'),
            Food(food_name='豆腐脑（少糖）', calories=120, sugar_content=4, food_type='蛋白', recommend_time='早餐', weather_conditions='晴天,阴天', allergens='大豆'),
            Food(food_name='清炒西兰花', calories=60, sugar_content=2, food_type='蔬菜', recommend_time='早餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),
            Food(food_name='凉拌海带丝', calories=50, sugar_content=1, food_type='蔬菜', recommend_time='早餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),
            Food(food_name='清炒生菜', calories=55, sugar_content=1, food_type='蔬菜', recommend_time='早餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),

            # 午餐
            Food(food_name='糙米饭', calories=220, sugar_content=1, food_type='主食', recommend_time='午餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),
            Food(food_name='荞麦面', calories=240, sugar_content=2, food_type='主食', recommend_time='午餐', weather_conditions='阴天,雨天,寒冷', allergens='麸质'),
            Food(food_name='香煎鸡胸肉', calories=210, sugar_content=0, food_type='蛋白', recommend_time='午餐', weather_conditions='晴天,阴天,雨天', allergens='无'),
            Food(food_name='清蒸鱼', calories=190, sugar_content=0, food_type='蛋白', recommend_time='午餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='鱼类'),
            Food(food_name='凉拌黄瓜', calories=40, sugar_content=1, food_type='蔬菜', recommend_time='午餐', weather_conditions='晴天,阴天', allergens='无'),
            Food(food_name='番茄炒蛋（少油）', calories=180, sugar_content=3, food_type='蔬菜', recommend_time='午餐', weather_conditions='晴天,阴天,雨天', allergens='鸡蛋'),

            # 晚餐
            Food(food_name='玉米', calories=170, sugar_content=4, food_type='主食', recommend_time='晚餐', weather_conditions='晴天,阴天', allergens='无'),
            Food(food_name='藜麦饭', calories=210, sugar_content=2, food_type='主食', recommend_time='晚餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),
            Food(food_name='杂粮饭', calories=200, sugar_content=3, food_type='主食', recommend_time='晚餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),
            Food(food_name='虾仁豆腐', calories=200, sugar_content=1, food_type='蛋白', recommend_time='晚餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='虾,大豆'),
            Food(food_name='鸡丝菌菇汤', calories=120, sugar_content=2, food_type='蛋白', recommend_time='晚餐', weather_conditions='雨天,寒冷', allergens='无'),
            Food(food_name='紫菜蛋花汤', calories=90, sugar_content=1, food_type='蔬菜', recommend_time='晚餐', weather_conditions='雨天,寒冷', allergens='鸡蛋'),
            Food(food_name='清炒菠菜', calories=70, sugar_content=2, food_type='蔬菜', recommend_time='晚餐', weather_conditions='晴天,阴天,雨天,寒冷', allergens='无'),

            # 负例（用于验证过滤逻辑）
            Food(food_name='花生糖', calories=300, sugar_content=25, food_type='主食', recommend_time='晚餐', weather_conditions='晴天', allergens='花生'),
        ]

        generated_foods = []
        times = ['早餐', '午餐', '晚餐']
        weather_all = '晴天,阴天,雨天,寒冷'

        staple_bases = {
            '早餐': ['燕麦', '全麦吐司', '玉米', '红薯', '南瓜', '藜麦', '小米', '黑米', '山药', '紫薯', '荞麦面', '糙米'],
            '午餐': ['糙米饭', '藜麦饭', '荞麦面', '全麦意面', '杂粮饭', '玉米', '红薯', '燕麦饭', '小米饭', '黑米饭', '南瓜饭', '莜麦面'],
            '晚餐': ['藜麦饭', '杂粮饭', '玉米', '红薯', '南瓜', '小米粥', '燕麦粥', '山药', '紫薯', '糙米饭', '荞麦面', '全麦馒头'],
        }
        protein_bases = {
            '早餐': ['鸡蛋', '鸡胸肉', '豆腐', '豆浆', '希腊酸奶', '金枪鱼', '虾仁', '低脂牛奶', '牛肉（瘦）', '三文鱼', '毛豆', '鸡腿肉（去皮）'],
            '午餐': ['鸡胸肉', '牛肉（瘦）', '清蒸鱼', '虾仁', '豆腐', '豆干', '牛奶', '鸡蛋', '鸡腿肉（去皮）', '鸭胸肉', '鳕鱼', '毛豆'],
            '晚餐': ['清蒸鱼', '鸡胸肉', '虾仁', '豆腐', '菌菇鸡汤', '鸡蛋', '牛肉（瘦）', '鳕鱼', '三文鱼', '豆干', '毛豆', '鸡丝'],
        }
        vegetable_bases = {
            '早餐': ['西兰花', '菠菜', '生菜', '黄瓜', '番茄', '海带', '紫甘蓝', '芦笋', '香菇', '金针菇', '菜花', '青椒'],
            '午餐': ['西兰花', '黄瓜', '番茄', '菠菜', '芦笋', '香菇', '金针菇', '茄子', '青椒', '菜花', '木耳', '紫甘蓝'],
            '晚餐': ['菠菜', '芦笋', '西兰花', '香菇', '金针菇', '菜花', '青椒', '茄子', '木耳', '紫甘蓝', '海带', '番茄'],
        }

        staple_methods = ['蒸', '煮', '烤', '清炒', '凉拌']
        protein_methods = ['水煮', '清蒸', '香煎', '炖', '凉拌']
        vegetable_methods = ['清炒', '凉拌', '清蒸', '水煮', '炖']

        def infer_allergens(name: str) -> str:
            n = name
            allergens = []
            if '鸡蛋' in n or n.endswith('蛋') or '蛋花' in n:
                allergens.append('鸡蛋')
            if '豆腐' in n or '豆浆' in n or '毛豆' in n or '大豆' in n or '豆干' in n:
                allergens.append('大豆')
            if '牛奶' in n or '酸奶' in n:
                allergens.append('牛奶')
            if '虾' in n:
                allergens.append('虾')
            if '鱼' in n or '三文鱼' in n or '鳕鱼' in n or '金枪鱼' in n:
                allergens.append('鱼类')
            if '全麦' in n or '吐司' in n or '意面' in n or ('面' in n and '荞麦' not in n and '莜麦' not in n):
                allergens.append('麸质')
            if '花生' in n:
                allergens.append('花生')
            return ','.join(dict.fromkeys(allergens)) if allergens else '无'

        def mk_food(name: str, calories: int, sugar: float, food_type: str, time: str) -> Food:
            return Food(
                food_name=name,
                calories=int(calories),
                sugar_content=float(sugar),
                food_type=food_type,
                recommend_time=time,
                weather_conditions=weather_all,
                allergens=infer_allergens(name)
            )

        def bounded(v: int, lo: int, hi: int) -> int:
            return max(lo, min(hi, v))

        idx = 0
        for t in times:
            for base in staple_bases[t]:
                for m in staple_methods:
                    idx += 1
                    name = f"{m}{base}（{t}）"
                    cal = bounded(150 + (idx * 7) % 130, 140, 280)
                    sugar = float((idx * 3) % 7)
                    generated_foods.append(mk_food(name, cal, sugar, '主食', t))

            for base in protein_bases[t]:
                for m in protein_methods:
                    idx += 1
                    name = f"{m}{base}（{t}）"
                    cal = bounded(90 + (idx * 11) % 170, 70, 260)
                    sugar = float((idx * 2) % 6)
                    generated_foods.append(mk_food(name, cal, sugar, '蛋白', t))

            for base in vegetable_bases[t]:
                for m in vegetable_methods:
                    idx += 1
                    name = f"{m}{base}（{t}）"
                    cal = bounded(35 + (idx * 5) % 95, 25, 130)
                    sugar = float((idx * 2) % 5)
                    generated_foods.append(mk_food(name, cal, sugar, '蔬菜', t))

        seed_foods.extend(generated_foods)

        inserted = 0
        existing_names = set([n for (n,) in db.session.query(Food.food_name).all()])
        for food in seed_foods:
            if food.food_name in existing_names:
                continue
            db.session.add(food)
            existing_names.add(food.food_name)
            inserted += 1

        if inserted > 0:
            print(f"食物数据补充完成，新增 {inserted} 条")
        else:
            print("食物数据已存在，跳过补充")

        _populate_missing_image_urls()
        _bump_image_url_version()

        # 检查是否已有用户数据
        existing_users = User.query.count()
        if existing_users == 0:
            # 添加示例用户数据
            user = User(user_id=1, health_condition='糖尿病', allergic_foods='花生,牛奶')
            db.session.add(user)
            print("用户数据初始化完成")
        else:
            print("用户数据已存在，跳过初始化")
        
        db.session.commit()

if __name__ == '__main__':
    import sys
    import os
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        with app.app_context():
            db.create_all()
            _ensure_food_image_column()
        initialize_data()
        print('数据初始化完成')
    else:
        with app.app_context():
            db.create_all()  # 创建数据库表
            _ensure_food_image_column()
        initialize_data()
        port = int(os.getenv('PORT', '5000'))
        app.run(host='127.0.0.1', port=port, debug=True)

@app.route("/api/health")
def health():
    return "ok"