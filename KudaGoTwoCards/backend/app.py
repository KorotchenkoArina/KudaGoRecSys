import requests
import json
import os
import uuid
import random
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from UCB_recommendation_system import LinearUCBRecommendationSystem

app = Flask(__name__)
CORS(app)

# Конфигурация
KUDAGO_API = 'https://kudago.com/public-api/v1.4/events/'
CACHE_FILE = 'events_cache.json'
EVENTS_PER_PAGE = 100  # Максимум на страницу (API поддерживает до 100)
MAX_EVENTS = 400      # Общее количество событий для загрузки

# Кэш для событий
events_cache = []
last_cache_update = None

# Инициализируем рекомендательную систему
recommendation_system = LinearUCBRecommendationSystem(alpha=1.0, lambda_reg=1.0)

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def safe_get(obj, *keys, default=None):
    """Безопасное получение значения из вложенных словарей"""
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            return default
    return obj

def get_or_create_user_session():
    """Получает или создаёт ID пользователя"""
    # В реальном приложении используйте cookies или JWT
    # Для тестирования используем простой ID
    import hashlib
    import time
    
    # Простой способ: используем IP + user-agent
    user_agent = request.headers.get('User-Agent', 'unknown')
    ip = request.remote_addr or 'localhost'
    
    # Создаём уникальный ID на основе IP и User-Agent
    session_key = f"{ip}_{user_agent}"
    session_id = hashlib.md5(session_key.encode()).hexdigest()[:16]
    
    return session_id

def extract_categories(categories):
    """Извлекает названия категорий из ответа API"""
    category_names = []
    if isinstance(categories, list):
        for cat in categories:
            if isinstance(cat, dict):
                cat_name = cat.get('name', '')
                if cat_name:
                    category_names.append(cat_name)
            elif isinstance(cat, str):
                category_names.append(cat)
    return category_names

def format_event_dates(dates):
    """Форматирует даты события для отображения"""
    if not dates:
        return 'Дата не указана'
    
    if isinstance(dates, list) and len(dates) > 0:
        first_date = dates[0]
        
        if isinstance(first_date, dict):
            start_ts = first_date.get('start')
            if start_ts:
                try:
                    start_date = datetime.fromtimestamp(start_ts)
                    end_ts = first_date.get('end')
                    if end_ts and end_ts != start_ts:
                        end_date = datetime.fromtimestamp(end_ts)
                        if start_date.date() == end_date.date():
                            return start_date.strftime('%d %B %Y, %H:%M')
                        else:
                            return f"{start_date.strftime('%d %B')} - {end_date.strftime('%d %B %Y')}"
                    return start_date.strftime('%d %B %Y, %H:%M')
                except (TypeError, ValueError, OSError):
                    return 'Дата не указана'
        
        elif isinstance(first_date, (int, float)):
            try:
                start_date = datetime.fromtimestamp(first_date)
                return start_date.strftime('%d %B %Y, %H:%M')
            except (TypeError, ValueError, OSError):
                return 'Дата не указана'
    
    return 'Дата не указана'

def fetch_events_from_kudago(location='msk'):
    """Загружает события из KudaGo API с пагинацией (до MAX_EVENTS)"""
    all_events = []
    current_time = int(datetime.now().timestamp())
    three_months_later = int((datetime.now() + timedelta(days=90)).timestamp())
    
    print(f"🚀 Начинаем загрузку событий для {location}...")
    
    # Шаг 1: Получаем общее количество страниц
    try:
        params = {
            'location': location,
            'page_size': 1,
            'actual_since': current_time,
            'actual_until': three_months_later
        }
        response = requests.get(KUDAGO_API, params=params, timeout=10)
        total_count = response.json().get('count', 0)
        total_pages = min((total_count // EVENTS_PER_PAGE) + 1, 20)  # Максимум 20 страниц
        print(f"📊 {location}: всего событий: {total_count}, страниц: {total_pages}")
    except Exception as e:
        print(f"⚠️ Ошибка получения количества страниц: {e}")
        total_pages = 10
    
    # Шаг 2: Выбираем случайные страницы (но не больше, чем нужно для MAX_EVENTS)
    pages_needed = (MAX_EVENTS // EVENTS_PER_PAGE) + 1
    pages_to_load = min(pages_needed, total_pages)
    random_pages = random.sample(range(1, total_pages + 1), min(pages_to_load, total_pages))
    print(f"📖 Загружаем страницы: {random_pages}")
    
    # Шаг 3: Загружаем выбранные страницы
    for idx, page in enumerate(random_pages):
        print(f"🔄 Загрузка страницы {idx + 1}/{len(random_pages)} (page={page})...")
        
        params = {
            'location': location,
            'page_size': EVENTS_PER_PAGE,
            'page': page,
            'actual_since': current_time,
            'actual_until': three_months_later,
            'fields': 'id,title,place,price,dates,description,images,categories,site_url',
            'text_format': 'text'
        }
        
        try:
            response = requests.get(KUDAGO_API, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            for event in data.get('results', []):
                if not isinstance(event, dict):
                    continue
                
                # Получаем изображение
                image_url = None
                images = event.get('images', [])
                
                if images and len(images) > 0:
                    first_image = images[0]
                    if isinstance(first_image, dict):
                        image_url = first_image.get('image') or first_image.get('thumb')
                
                if not image_url:
                    cover = event.get('cover')
                    if cover and isinstance(cover, dict):
                        image_url = cover.get('image') or cover.get('thumb')
                
                if not image_url:
                    image_url = 'https://via.placeholder.com/400x280?text=No+Image'
                
                # Получаем информацию о месте
                place_title = safe_get(event, 'place', 'title', default='Место не указано')
                place_address = safe_get(event, 'place', 'address', default='')
                
                # Форматируем дату
                dates = safe_get(event, 'dates', default=[])
                formatted_date = format_event_dates(dates)
                
                # Извлекаем категории
                categories = safe_get(event, 'categories', default=[])
                category_names = extract_categories(categories)
                
                # Форматируем описание
                description = safe_get(event, 'description', default='')
                if isinstance(description, str):
                    description = description[:300] + '...' if len(description) > 300 else description
                else:
                    description = 'Описание отсутствует'
                
                # Получаем цену
                price = safe_get(event, 'price', default='Бесплатно')
                if not price:
                    price = 'Бесплатно'
                
                formatted_event = {
                    'id': event.get('id'),
                    'title': safe_get(event, 'title', default='Без названия'),
                    'place': place_title,
                    'address': place_address,
                    'price': price,
                    'date': formatted_date,
                    'description': description,
                    'image': image_url,
                    'categories': category_names,
                    'url': safe_get(event, 'site_url', default=f'https://kudago.com/{location}/event/{event.get("id")}/')
                }
                all_events.append(formatted_event)
                
                # Останавливаемся, если набрали нужное количество
                if len(all_events) >= MAX_EVENTS:
                    break
            
            print(f"   ✅ Загружено {len(all_events)} событий так...")
            
            if len(all_events) >= MAX_EVENTS:
                print(f"🎯 Достигнут лимит в {MAX_EVENTS} событий, останавливаем загрузку")
                break
                
        except Exception as e:
            print(f"❌ Ошибка загрузки страницы {page}: {e}")
            continue
    
    # Шаг 4: Удаляем дубликаты (на случай, если событие попало в несколько страниц)
    seen_ids = set()
    unique_events = []
    for event in all_events:
        if event['id'] not in seen_ids:
            seen_ids.add(event['id'])
            unique_events.append(event)
    
    print(f"✅ Загрузка завершена! Уникальных событий: {len(unique_events)}")
    return unique_events

def load_or_refresh_cache():
    """Загружает кэш или обновляет его если он устарел"""
    global events_cache, last_cache_update
    
    if events_cache and last_cache_update:
        cache_age = (datetime.now() - last_cache_update).total_seconds()
        if cache_age < 6 * 3600:  # 6 часов
            print(f"📦 Используем кэш (возраст: {cache_age / 3600:.1f} часов, событий: {len(events_cache)})")
            return events_cache
    
    print("🔄 Обновление кэша событий...")
    events_cache = fetch_events_from_kudago('msk')
    last_cache_update = datetime.now()
    
    if events_cache:
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'events': events_cache,
                    'updated_at': last_cache_update.isoformat(),
                    'total_events': len(events_cache)
                }, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(events_cache)} событий в кэш")
        except Exception as e:
            print(f"⚠️ Ошибка сохранения кэша: {e}")
    else:
        print("⚠️ Не удалось загрузить события")
    
    return events_cache

# ============================================
# API МАРШРУТЫ
# ============================================

@app.route('/api/test', methods=['GET'])
def test():
    """Тестовый эндпоинт для проверки работы"""
    return jsonify({'success': True, 'message': 'Бэкенд работает!'})

@app.route('/api/events', methods=['GET'])
def get_events():
    """Возвращает список всех событий"""
    events = load_or_refresh_cache()
    return jsonify({
        'success': True,
        'events': events,
        'count': len(events)
    })

@app.route('/api/events/random', methods=['GET'])
def get_random_events():
    """Возвращает два случайных события для сравнения"""
    events = load_or_refresh_cache()
    
    if len(events) < 2:
        return jsonify({'success': False, 'error': 'Недостаточно событий'})
    
    selected = random.sample(events, min(2, len(events)))
    
    return jsonify({
        'success': True,
        'event_left': selected[0],
        'event_right': selected[1]
    })

@app.route('/api/events/compare', methods=['GET'])
def get_comparison_pair():
    """Возвращает пару событий для сравнения с учётом рекомендаций"""
    user_id = get_or_create_user_session()
    all_events = load_or_refresh_cache()
    
    if len(all_events) < 2:
        return jsonify({'success': False, 'error': 'Недостаточно событий'})
    
    # ЗАГРУЖАЕМ ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
    profile = recommendation_system.get_user_profile(user_id)
    
    # ФИЛЬТРУЕМ ДИЗЛАЙКНУТЫЕ СОБЫТИЯ
    if profile and profile.get('disliked_events'):
        available_events = [
            e for e in all_events 
            if e['id'] not in profile['disliked_events']
        ]
        print(f"DEBUG: Всего событий: {len(all_events)}, Дизлайкнуто: {len(profile['disliked_events'])}, Доступно: {len(available_events)}")
    else:
        available_events = all_events.copy()
    
    # ПРОВЕРЯЕМ, ОСТАЛОСЬ ЛИ ДОСТАТОЧНО СОБЫТИЙ
    if len(available_events) < 2:
        return jsonify({
            'success': False, 
            'error': 'Вы исключили почти все события! Нажмите "Сбросить", чтобы продолжить.',
            'need_reset': True
        })
    
    # Получаем пару с учётом баланса (ТОЛЬКО ИЗ ДОСТУПНЫХ СОБЫТИЙ)
    event_left, event_right = recommendation_system.get_pair_for_comparison(user_id, available_events)
    
    if not event_left or not event_right:
        import random
        selected = random.sample(available_events, 2)
        return jsonify({
            'success': True,
            'event_left': selected[0],
            'event_right': selected[1],
            'recommendation_type': 'random'
        })

    return jsonify({
        'success': True,
        'event_left': event_left,
        'event_right': event_right,
        'recommendation_type': event_left.get('_recommendation_type', 'linear_ucb')
    })

@app.route('/api/compare', methods=['POST'])
def compare_events():
    user_id = get_or_create_user_session()
    data = request.json
    winner_id = data.get('winner_id')
    loser_id = data.get('loser_id')
    both_disliked = data.get('both_disliked', False)
    both_liked = data.get('both_liked', False)
    left_event_id = data.get('left_event_id')
    right_event_id = data.get('right_event_id')
    
    events = load_or_refresh_cache()
    events_dict = {e['id']: e for e in events}
    
    # Если оба события нравятся
    if both_liked:
        if left_event_id and left_event_id in events_dict:
            recommendation_system.update(user_id, events_dict[left_event_id], liked=True)
        if right_event_id and right_event_id in events_dict:
            recommendation_system.update(user_id, events_dict[right_event_id], liked=True)
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'both_liked': True,
            'left_event_id': left_event_id,
            'right_event_id': right_event_id
        }

    # Если оба события дизлайкнуты
    elif both_disliked:
        # ✅ Обрабатываем оба события в одном запросе
        if left_event_id and left_event_id in events_dict:
            recommendation_system.update(user_id, events_dict[left_event_id], liked=False)
        if right_event_id and right_event_id in events_dict:
            recommendation_system.update(user_id, events_dict[right_event_id], liked=False)
        
        # Один лог для пары
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'both_disliked': True,
            'left_event_id': left_event_id,
            'right_event_id': right_event_id
        }
        
    else:
        # Обычное сравнение (один лайк, один дизлайк)
        if winner_id and winner_id in events_dict:
            recommendation_system.update(user_id, events_dict[winner_id], liked=True)
        
        if loser_id and loser_id in events_dict:
            recommendation_system.update(user_id, events_dict[loser_id], liked=False)
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'winner_id': winner_id,
            'loser_id': loser_id,
            'both_disliked': False
        }
    
    # Сохраняем в лог
    try:
        with open('comparisons_log.json', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f"Ошибка сохранения лога: {e}")
    
    return jsonify({'success': True})

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Возвращает топ-рекомендации на основе сделанных сравнений"""
    events = load_or_refresh_cache()
    event_scores = {event['id']: 0 for event in events}
    
    # Загружаем логи сравнений
    comparisons = []
    try:
        with open('comparisons_log.json', 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    comparisons.append(json.loads(line))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Ошибка загрузки логов: {e}")
    
    # Подсчитываем очки (победа = +1)
    for comp in comparisons:
        if comp['winner_id'] in event_scores:
            event_scores[comp['winner_id']] += 1
    
    # Сортируем события по очкам
    sorted_events = sorted(
        events,
        key=lambda e: event_scores.get(e['id'], 0),
        reverse=True
    )
    
    return jsonify({
        'success': True,
        'recommendations': sorted_events[:10],
        'scores': {e['id']: event_scores.get(e['id'], 0) for e in sorted_events[:10]}
    })

@app.route('/api/user/profile', methods=['GET'])
def get_user_profile():
    """Возвращает профиль пользователя"""
    user_id = get_or_create_user_session()
    profile = recommendation_system.get_user_profile(user_id)
    
    if profile:
        return jsonify({
            'success': True,
            'total_choices': profile['total_choices'],
            'liked_count': len(profile['liked_events']),
            'disliked_count': len(profile['disliked_events']),
            'preferences': dict(profile['preferences'])
        })
    
    return jsonify({
        'success': False, 
        'total_choices': 0,
        'liked_count': 0,
        'disliked_count': 0,
        'preferences': {},
        'message': 'Профиль не найден'
    })

@app.route('/api/user/liked-events', methods=['GET'])
def get_liked_events():
    """Возвращает список событий, которые пользователь лайкнул."""
    user_id = get_or_create_user_session()
    profile = recommendation_system.get_user_profile(user_id)
    liked_ids = profile.get('liked_events', [])
    
    # Реверсируем, чтобы новые лайки были вверху
    liked_ids.reverse()
    
    # Загружаем актуальные события
    all_events = load_or_refresh_cache()
    events_dict = {event['id']: event for event in all_events}
    
    # Находим полные данные для лайкнутых событий, сохраняя порядок
    liked_events_details = [events_dict[id] for id in liked_ids if id in events_dict]
    
    return jsonify({'success': True, 'liked_events': liked_events_details})

@app.route('/api/recommendations/cosine', methods=['GET'])
def get_cosine_recommendations():
    """Возвращает топ рекомендации на основе косинусного сходства с профилем"""
    user_id = get_or_create_user_session()
    events = load_or_refresh_cache()
    
    result = recommendation_system.get_cosine_recommendations(user_id, events, n=50, similarity_threshold=0.8)
    
    return jsonify({
        'success': True,
        'recommendations': result['recommendations'],
        'has_enough_likes': result['has_enough_likes'],
        'total_likes': result['total_likes'],
        'similarity_threshold': result['similarity_threshold'],
        'found_count': result['found_count']
    })

@app.route('/api/recommendations/exploitation', methods=['GET'])
def get_exploitation_recommendations():
    """Возвращает топ рекомендации на основе чистой эксплуатации (mean_reward)"""
    user_id = get_or_create_user_session()
    events = load_or_refresh_cache()
    
    try:
        result = recommendation_system.get_exploitation_recommendations(user_id, events, n=50, min_confidence=0.5)
        return jsonify({
            'success': True,
            'recommendations': result['recommendations'],
            'has_enough_data': result['has_enough_data'],
            'total_choices': result['total_choices'],
            'total_likes': result['total_likes'],
            'found_count': result['found_count'],
            'message': result.get('message')
        })
    except Exception as e:
        print(f"Ошибка в get_exploitation_recommendations: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'recommendations': [],
            'has_enough_data': False,
            'found_count': 0,
            'message': 'Произошла ошибка при поиске рекомендаций'
        }), 500

@app.route('/api/debug/console', methods=['POST'])
def debug_console():
    data = request.json
    command = data.get('command', '')
    user_id = get_or_create_user_session()
    
    if command == 'insights':
        insights = recommendation_system.get_model_insights(user_id)
        return jsonify({'success': True, 'insights': insights})
    
    elif command == 'profile':
        profile = recommendation_system.get_user_profile(user_id)
        # ✅ Создаем КОПИЮ для вывода, не изменяя оригинал
        profile_copy = profile.copy()
        if 'embedding' in profile_copy:
            profile_copy['embedding'] = f"vector[{len(profile_copy['embedding'])}]"
        return jsonify({'success': True, 'profile': profile_copy})
    
    elif command == 'reset_debug':
        recommendation_system.reset_user_profile(user_id)
        return jsonify({'success': True, 'message': 'Профиль сброшен'})
    
    return jsonify({'success': False, 'message': 'Unknown command'})
    
@app.route('/api/reset', methods=['POST'])
def reset_comparisons():
    """Сбрасывает историю сравнений"""
    user_id = get_or_create_user_session()
    
    # 1. Полностью сбрасываем профиль пользователя и модель
    recommendation_system.reset_user_profile(user_id)
    
    # 2. Очищаем логи сравнений для этого пользователя
    if os.path.exists('comparisons_log.json'):
        try:
            with open('comparisons_log.json', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            filtered_lines = []
            for line in lines:
                if line.strip():
                    log = json.loads(line)
                    if log.get('user_id') != user_id:
                        filtered_lines.append(line)
            
            with open('comparisons_log.json', 'w', encoding='utf-8') as f:
                f.writelines(filtered_lines)
        except Exception as e:
            print(f"Ошибка при сбросе логов: {e}")
    
    # 3. Перемешиваем или обновляем кэш
    global events_cache, last_cache_update
    cache_age = (datetime.now() - last_cache_update).total_seconds() if last_cache_update else float('inf')
    
    if cache_age > 3600:  # Если кэш старше 1 часа
        print("🔄 Кэш устарел, загружаем новые события...")
        events_cache = []
        last_cache_update = None
        load_or_refresh_cache()
    else:
        # Просто перемешиваем существующие события
        random.shuffle(events_cache)
        print(f"🃏 Кэш перемешан: {len(events_cache)} событий")
    
    return jsonify({'success': True, 'message': 'Данные сброшены! Начинаем заново 🎯'})

# ============================================
# ЗАПУСК
# ============================================

if __name__ == '__main__': 
    print("=" * 50)
    print("🎯 Запуск сервера EventChoice с UCB рекомендациями")
    print("=" * 50)
    print(f"📋 Конфигурация:")
    print(f"   - Страница: {EVENTS_PER_PAGE} событий")
    print(f"   - Максимум: {MAX_EVENTS} событий")
    print(f"   - Город: Москва")
    print("=" * 50)
    
    # Предварительная загрузка кэша
    load_or_refresh_cache()
    
    print("\n✅ Сервер готов к работе!")
    print("📍 Доступные эндпоинты:")
    print("   GET  /api/test                 - Проверка работы")
    print("   GET  /api/events               - Список всех событий")
    print("   GET  /api/events/random        - Два случайных события")
    print("   GET  /api/events/compare       - Пара с учётом рекомендаций")
    print("   POST /api/compare              - Отправить результат сравнения")
    print("   GET  /api/recommendations      - Список рекомендаций")
    print("   GET  /api/user/profile         - Профиль пользователя")
    print("   POST /api/reset                - Сбросить данные")
    print("\n🚀 Запуск на http://localhost:5000")
    print("=" * 50)
    
    app.run(debug=True, port=5000)