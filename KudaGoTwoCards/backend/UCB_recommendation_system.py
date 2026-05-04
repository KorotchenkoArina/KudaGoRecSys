import profile
import random
import numpy as np
from scipy.linalg import inv
from collections import defaultdict
from datetime import datetime
import json
import os
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize

class LinearUCB:
    """
    Linear Upper Confidence Bound с поддержкой богатых признаков
    """
    
    def __init__(self, n_features=384, alpha=1.0, lambda_reg=1.0):
        """
        n_features: размерность признакового пространства
        alpha: коэффициент exploration (чем выше, тем больше исследуем)
        lambda_reg: коэффициент регуляризации Ridge
        """
        self.n_features = n_features
        self.alpha = alpha
        self.lambda_reg = lambda_reg
        
        # A = X^T * X + λI (матрица информации)
        self.A = lambda_reg * np.identity(n_features)
        
        # b = X^T * y (накопленные награды)
        self.b = np.zeros(n_features)
        
        # theta = A^{-1} * b (текущие веса)
        self.theta = np.zeros(n_features)
        
        # Кэш для A_inv (оптимизация)
        self.A_inv = inv(self.A)
        
        # Статистика
        self.total_updates = 0
        self.reward_history = []
        self.feature_history = []  # для отладки
    
    def _update_theta(self):
        """Обновляет параметры модели"""
        try:
            self.A_inv = inv(self.A)
            self.theta = np.dot(self.A_inv, self.b)
        except np.linalg.LinAlgError:
            # Если матрица вырождена, добавляем небольшой шум
            self.A += 1e-6 * np.identity(self.n_features)
            self.A_inv = inv(self.A)
            self.theta = np.dot(self.A_inv, self.b)
    
    def get_score(self, features):
        """
        Вычисляет UCB score для события
        Возвращает: score, mean_reward, uncertainty
        """
        features = np.array(features).reshape(-1)
        
        # Expected reward (exploitation) 
        mean_reward = np.dot(self.theta, features)
        
        # Uncertainty (exploration)
        uncertainty = np.sqrt(np.dot(features, np.dot(self.A_inv, features)))
        
        # UCB score
        ucb_score = mean_reward + self.alpha * uncertainty
        
        return ucb_score, mean_reward, uncertainty
    
    def update(self, features, reward):
        """
        Обновляет модель на основе фидбека (ОПТИМИЗИРОВАННАЯ ВЕРСИЯ)
        features: вектор признаков события
        reward: 1 (лайк) или -1 (дизлайк)
        """
        features = np.array(features).reshape(-1, 1)
        
        # Обновляем A = A + x*x^T
        self.A += np.outer(features, features)
        
        # Обновляем b = b + reward * x
        self.b += reward * features.flatten()

        # ОПТИМИЗАЦИЯ: Обновляем A_inv с помощью формулы Шермана-Моррисона
        # Это на порядки быстрее, чем инвертировать матрицу заново.
        # Сложность O(d^2) вместо O(d^3).
        A_inv_dot_x = np.dot(self.A_inv, features)
        numerator = np.dot(A_inv_dot_x, A_inv_dot_x.T)
        denominator = 1 + np.dot(features.T, A_inv_dot_x)
        self.A_inv -= numerator / denominator
        
        # Обновляем theta с новым A_inv
        self.theta = np.dot(self.A_inv, self.b)
        
        self.total_updates += 1
        self.reward_history.append(reward)
        self.feature_history.append(features.flatten())
        
        # Ограничиваем историю для экономии памяти
        if len(self.feature_history) > 1000:
            self.feature_history = self.feature_history[-500:]
    
    def get_confidence(self, features):
        """Возвращает уверенность в предсказании (0-1)"""
        features = np.array(features).reshape(-1)
        variance = np.dot(features, np.dot(self.A_inv, features))
        # Чем меньше variance, тем выше уверенность
        confidence = 1.0 / (1.0 + variance)
        return confidence
    
    def get_model_complexity(self):
        """Возвращает сложность модели (след матрицы A_inv)"""
        return np.trace(self.A_inv)


class EventFeatureExtractor:
    """
    Извлекает богатые признаки из событий KudaGo для линейного UCB
    
    Признаки:
    1. Эмбеддинги (384-dim) - из SentenceTransformer
    2. Цена (нормализованная, логарифмическая)
    3. Категории (one-hot + эмбеддинги категорий)
    4. is_free (бинарный)
    5. Популярность (favorites_count, normalized)
    6. Временные признаки
    7. Место (one-hot)
    """
    
    def __init__(self, model_name='paraphrase-multilingual-MiniLM-L12-v2'):
        print("Загрузка модели для эмбеддингов...")
        self.sentence_model = SentenceTransformer(model_name, device='cpu')
        print(f"Модель загружена, размерность эмбеддингов: {self.sentence_model.get_sentence_embedding_dimension()}")
        
        # Размерность итогового признакового пространства
        self.embedding_dim = self.sentence_model.get_sentence_embedding_dimension()  # 384
        self.total_features = 450  # фиксированная размерность
        
        # Кэш для эмбеддингов событий
        self.embedding_cache = {}
        self.embedding_cache_file = 'event_embeddings_linear.npy'
        
        # One-hot кодировщики (только для категорий)
        self.category_map = {}
        self.category_embeddings = {}
        
        # Статистика для нормализации
        self.price_stats = {'min': 0, 'max': 10000}
        self.favorites_stats = {'min': 0, 'max': 1000}
        
        # Загружаем кэш
        self.load_embedding_cache()
    
    def load_embedding_cache(self):
        """Загружает кэш эмбеддингов"""
        if os.path.exists(self.embedding_cache_file):
            try:
                cache_data = np.load(self.embedding_cache_file, allow_pickle=True).item()
                self.embedding_cache = cache_data.get('embeddings', {})
                print(f"Загружено {len(self.embedding_cache)} эмбеддингов из кэша")
            except Exception as e:
                print(f"Ошибка загрузки кэша: {e}")
    
    def save_embedding_cache(self):
        """Сохраняет кэш эмбеддингов"""
        try:
            cache_data = {'embeddings': self.embedding_cache}
            np.save(self.embedding_cache_file, cache_data)
            print(f"Сохранено {len(self.embedding_cache)} эмбеддингов")
        except Exception as e:
            print(f"Ошибка сохранения кэша: {e}")
    
    def get_text_embedding(self, event):
        """Получает текстовый эмбеддинг для события"""
        event_id = event['id']
        
        if event_id in self.embedding_cache:
            return self.embedding_cache[event_id]
        
        # Формируем текст для эмбеддинга (без места, так как город один)
        text_parts = [
            str(event.get('title', '')),
            str(event.get('description', '')),
            ' '.join(str(cat) for cat in event.get('categories', [])),
        ]
        text = ' '.join(filter(None, text_parts))
        
        if not text or len(text) < 10:
            text = event.get('title', 'событие')
        
        try:
            embedding = self.sentence_model.encode(text, normalize_embeddings=True)
            self.embedding_cache[event_id] = embedding
            
            # Периодически сохраняем
            if len(self.embedding_cache) % 100 == 0:
                self.save_embedding_cache()
            
            return embedding
        except Exception as e:
            print(f"Ошибка получения эмбеддинга: {e}")
            return np.zeros(self.embedding_dim)
    
    def extract_price_features(self, event):
        """
        Извлекает признаки цены
        Возвращает: [is_free, normalized_price, price_category_one_hot(3)]
        """
        price_str = str(event.get('price', 'Бесплатно')).lower()
        
        features = []
        
        # 1. Бинарный признак is_free
        is_free = 1 if ('бесплат' in price_str or price_str == '0' or price_str == 'free') else 0
        features.append(is_free)
        
        # 2. Нормализованная цена (логарифмическая шкала)
        import re
        numbers = re.findall(r'\d+', price_str)
        if numbers and not is_free:
            price_value = float(numbers[0])
            # Логарифмическая нормализация для сглаживания
            log_price = np.log1p(price_value)
            max_log = np.log1p(10000)
            norm_price = log_price / max_log
            features.append(norm_price)
        else:
            features.append(0.0)
        
        # 3. One-hot категории цены (для бюджетных предпочтений)
        if numbers and not is_free:
            price_val = float(numbers[0])
            if price_val < 500:
                features.extend([1, 0, 0])  # бюджетное
            elif price_val < 2000:
                features.extend([0, 1, 0])  # средняя цена
            else:
                features.extend([0, 0, 1])  # дорогое
        else:
            features.extend([1, 0, 0])  # бесплатное в бюджетную категорию
        
        return features  # 1 + 1 + 3 = 5 признаков
    
    def extract_category_features(self, event):
        """
        Извлекает признаки категорий
        Возвращает: [top_category_one_hot(15), category_embedding(15)]
        """
        categories = event.get('categories', [])
        
        features = []
        
        # 1. Top-15 категорий one-hot (расширил до 15, так как место убрали)
        cat_one_hot = [0] * 15
        for i, cat in enumerate(categories[:3]):  # первые 3 категории
            if cat not in self.category_map:
                self.category_map[cat] = min(len(self.category_map), 14)
            idx = self.category_map[cat]
            cat_one_hot[idx] = 1
        features.extend(cat_one_hot)  # 15 признаков
        
        # 2. Эмбеддинги категорий (15-dim)
        cat_embedding = np.zeros(15)
        for cat in categories[:2]:
            if cat not in self.category_embeddings:
                try:
                    cat_emb = self.sentence_model.encode(cat, normalize_embeddings=True)
                    self.category_embeddings[cat] = cat_emb[:15]
                except:
                    self.category_embeddings[cat] = np.zeros(15)
            cat_embedding += self.category_embeddings[cat]
        
        # Нормализуем
        if np.linalg.norm(cat_embedding) > 0:
            cat_embedding = cat_embedding / np.linalg.norm(cat_embedding)
        
        features.extend(cat_embedding.tolist())  # 15 признаков
        
        return features  # 15 + 15 = 30 признаков
    
    def extract_popularity_features(self, event):
        """
        Извлекает признаки популярности
        favorites_count - сколько пользователей добавило в избранное
        """
        features = []
        
        # Пробуем получить favorites_count из разных полей
        favorites = event.get('favorites_count', 0)
        if not favorites:
            favorites = event.get('participants_count', 0)
        if not favorites:
            favorites = event.get('likes', 0)
        
        if isinstance(favorites, (int, float)) and favorites > 0:
            # Сигмоидальная нормализация: популярность от -1 до 1
            # 0 избранных -> -1, 100 избранных -> 0, 500+ избранных -> 1
            norm_favorites = 2 / (1 + np.exp(-favorites / 100)) - 1
            features.append(norm_favorites)
            
            # Бинарный признак "популярное"
            is_popular = 1 if favorites > 50 else 0
            features.append(is_popular)
        else:
            features.extend([-1.0, 0])  # непопулярное
        
        # Отношение лайков к просмотрам (если есть)
        views = event.get('views_count', 0)
        if views and views > 0 and favorites:
            engagement = favorites / views
            features.append(min(1.0, engagement * 10))  # нормализуем
        else:
            features.append(0.0)
        
        return features  # 3 признака
    
    def extract_temporal_features(self, event):
        """
        Извлекает временные признаки из даты события
        """
        features = []
        
        date_str = event.get('date', '')
        
        if date_str and date_str != 'Дата не указана':
            try:
                import re
                
                # Парсим время
                time_match = re.search(r'(\d{1,2}):(\d{2})', date_str)
                if time_match:
                    hour = int(time_match.group(1))
                    
                    # Циклическое кодирование времени (для нейронных сетей)
                    hour_sin = np.sin(2 * np.pi * hour / 24)
                    hour_cos = np.cos(2 * np.pi * hour / 24)
                    features.extend([hour_sin, hour_cos])
                    
                    # Бинарные признаки времени суток
                    is_morning = 1 if 6 <= hour < 12 else 0
                    is_afternoon = 1 if 12 <= hour < 18 else 0
                    is_evening = 1 if 18 <= hour < 23 else 0
                    is_night = 1 if hour >= 23 or hour < 6 else 0
                    features.extend([is_morning, is_afternoon, is_evening, is_night])
                else:
                    features.extend([0, 0, 0, 0, 0, 0])  # 2 sin/cos + 4 бинарных
                
                # День недели (если можем определить)
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                day_one_hot = [0] * 7
                date_lower = date_str.lower()
                for i, day in enumerate(days):
                    if day in date_lower:
                        day_one_hot[i] = 1
                        break
                
                # Если не нашли день, пробуем по дате
                if sum(day_one_hot) == 0:
                    date_match = re.search(r'(\d{1,2})\s+(\w+)', date_str)
                    if date_match:
                        # Упрощенно: weekend detection
                        month = date_match.group(2).lower()
                        # В реальности нужен парсер дат
                        pass
                
                features.extend(day_one_hot)
                
                # Выходной или будний
                is_weekend = 1 if (day_one_hot[5] or day_one_hot[6]) else 0
                features.append(is_weekend)
                
            except Exception as e:
                print(f"Ошибка парсинга даты: {e}")
                features.extend([0] * 16)  # 2+4+7+1 = 14? Давайте пересчитаем
        else:
            features.extend([0] * 16)  # sin, cos, 4 time_of_day, 7 weekdays, 1 weekend
        
        # Важно: проверим длину
        # 2 (sin/cos) + 4 (time_of_day) + 7 (weekdays) + 1 (weekend) = 14
        # Но в коде выше добавили 2+4+7+1 = 14
        # Если получилось 16, значит где-то лишние
        
        return features[:14]  # гарантируем 14 признаков
    
    def extract_all_features(self, event, precomputed_embedding=None):
        """
        Извлекает признаки, включая косинусное сходство с профилем
        
        Args:
            event: событие для извлечения признаков
            profile_embedding: эмбеддинг профиля пользователя (опционально)
        
        Returns:
            np.array: вектор признаков размерностью 450
        """
        features = []
        
        # 1. Текстовый эмбеддинг (384)
        if precomputed_embedding is not None:
            embedding = precomputed_embedding
        else:
            embedding = self.get_text_embedding(event)
        features.extend(embedding)
        
        # 2. Price features (5)
        price_features = self.extract_price_features(event)
        features.extend(price_features)
        
        # 3. Category features (30)
        category_features = self.extract_category_features(event)
        features.extend(category_features)
        
        # 4. Popularity features (3)
        popularity_features = self.extract_popularity_features(event)
        features.extend(popularity_features)
        
        # 5. Temporal features (14)
        temporal_features = self.extract_temporal_features(event)
        features.extend(temporal_features)
        
        # Дополняем до 450
        target_dim = 450
        if len(features) < target_dim:
            features.extend([0] * (target_dim - len(features)))
        elif len(features) > target_dim:
            features = features[:target_dim]
        
        return np.array(features, dtype=np.float32)
    
    def get_feature_dimension(self):
        """Возвращает размерность признакового пространства"""
        return 450
    
    def parse_event_date(self, date_str):
        """Парсит дату из строки события для фильтрации"""
        if not date_str or date_str == 'Дата не указана':
            return None
        try:
            import re
            from datetime import datetime
            
            patterns = [
                r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # 15 March 2026
                r'(\d{2})\.(\d{2})\.(\d{4})',     # 15.03.2026
                r'(\d{4})-(\d{2})-(\d{2})',       # 2026-03-15
            ]
            for pattern in patterns:
                match = re.search(pattern, date_str)
                if match:
                    if len(match.groups()) == 3:
                        day, month, year = match.groups()
                        months = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 
                                  'may': 5, 'june': 6, 'july': 7, 'august': 8,
                                  'september': 9, 'october': 10, 'november': 11, 'december': 12}
                        if month.lower() in months:
                            month = months[month.lower()]
                        return datetime(int(year), int(month), int(day))
            return None
        except:
            return None
    
    def parse_event_time(self, date_str):
        """Парсит время из строки события для фильтрации (возвращает минуты с начала дня)"""
        if not date_str or date_str == 'Дата не указана':
            return None
        try:
            import re
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_str)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                return hour * 60 + minute
            return None
        except:
            return None
    
    def filter_events_by_time(self, events, date_from=None, date_to=None, 
                               time_from=None, time_to=None, weekdays=None):
        """
        Фильтрует события по временным параметрам.
        
        Args:
            events: список событий
            date_from: дата от (YYYY-MM-DD)
            date_to: дата до (YYYY-MM-DD)
            time_from: время от (HH:MM)
            time_to: время до (HH:MM)
            weekdays: список дней недели (1-7, где 1-пн)
        
        Returns:
            отфильтрованный список событий
        """
        from datetime import datetime
        
        # Парсим фильтры дат
        date_from_obj = None
        date_to_obj = None
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            except:
                pass
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            except:
                pass
        
        # Парсим фильтры времени (в минутах от полуночи)
        time_from_min = None
        time_to_min = None
        if time_from:
            try:
                parts = time_from.split(':')
                time_from_min = int(parts[0]) * 60 + int(parts[1])
            except:
                pass
        if time_to:
            try:
                parts = time_to.split(':')
                time_to_min = int(parts[0]) * 60 + int(parts[1])
            except:
                pass
        
        # Дни недели
        weekdays_set = set(weekdays) if weekdays else None
        
        filtered_events = []
        
        for event in events:
            event_date_str = event.get('date', '')
            
            # Фильтр по дате
            if date_from_obj or date_to_obj:
                event_date = self.parse_event_date(event_date_str)
                if event_date is None:
                    continue  # Нет даты - пропускаем
                if date_from_obj and event_date < date_from_obj:
                    continue
                if date_to_obj and event_date > date_to_obj:
                    continue
            
            # Фильтр по времени
            if time_from_min is not None or time_to_min is not None:
                event_time = self.parse_event_time(event_date_str)
                if event_time is None:
                    continue  # Нет времени - пропускаем
                if time_from_min is not None and event_time < time_from_min:
                    continue
                if time_to_min is not None and event_time > time_to_min:
                    continue
            
            # Фильтр по дням недели (опционально, требует расширения parse_event_date)
            if weekdays_set:
                event_date = self.parse_event_date(event_date_str)
                if event_date:
                    weekday = event_date.isoweekday()  # 1-7, где 1-пн
                    if weekday not in weekdays_set:
                        continue
            
            filtered_events.append(event)
        
        return filtered_events

class LinearUCBRecommendationSystem:
    """
    Рекомендательная система на базе линейного UCB с богатыми признаками
    """
    
    def __init__(self, alpha=1.0, lambda_reg=1.0):
        self.feature_extractor = EventFeatureExtractor()
        self.feature_dim = self.feature_extractor.get_feature_dimension()
        self.alpha = alpha
        self.lambda_reg = lambda_reg
        
        self.bandits = {}
        self.user_profiles = {}

        print(f"✅ Инициализирована LinearUCB система")
        print(f"   Размерность признаков: {self.feature_dim}")
        print(f"   - Эмбеддинги текста: 384")
        print(f"   - Цена и бюджет: 5")
        print(f"   - Категории: 30")
        print(f"   - Популярность: 3")
        print(f"   - Время и дата: 14")
        print(f"   - Резерв: {self.feature_dim - 436}")

    def load_bandit(self, user_id):
        """Загружает состояние бандита для пользователя."""
        bandit_file = f'bandit_state_{user_id}.npz'
        if os.path.exists(bandit_file):
            try:
                data = np.load(bandit_file, allow_pickle=True)
                bandit = LinearUCB(
                    n_features=self.feature_dim,
                    alpha=self.alpha,
                    lambda_reg=self.lambda_reg
                )
                bandit.A = data['A']
                bandit.b = data['b']
                bandit._update_theta()
                self.bandits[user_id] = bandit
                print(f"✅ Бандит для пользователя {user_id} загружен с диска.")
                return True
            except Exception as e:
                print(f"⚠️ Ошибка загрузки бандита {user_id}: {e}")
        return False

    def save_bandit(self, user_id):
        """Сохраняет состояние бандита для пользователя."""
        if user_id in self.bandits:
            bandit = self.bandits[user_id]
            bandit_file = f'bandit_state_{user_id}.npz'
            try:
                np.savez(bandit_file, A=bandit.A, b=bandit.b)
            except Exception as e:
                print(f"⚠️ Ошибка сохранения бандита {user_id}: {e}")
    
    def get_bandit(self, user_id):
        """Получает или создает экземпляр LinearUCB для пользователя."""
        if user_id not in self.bandits:
            # 1. Пытаемся загрузить бандита с диска
            if not self.load_bandit(user_id):
                # 2. Если не вышло (новый пользователь), создаем бандита с нуля (cold start)
                print(f"Новый пользователь {user_id}. Инициализация с нуля (cold start).")
                new_bandit = LinearUCB(
                    n_features=self.feature_dim,
                    alpha=self.alpha,
                    lambda_reg=self.lambda_reg
                )
                # Начинаем с нулевой матрицей и вектором (уже есть по умолчанию)
                self.bandits[user_id] = new_bandit
        return self.bandits[user_id]
    
    def get_user_profile(self, user_id):
        """Загружает профиль пользователя"""
        if user_id in self.user_profiles:
            return self.user_profiles[user_id]
        
        profile_file = f'linear_ucb_profile_{user_id}.json'
        if os.path.exists(profile_file):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)
                    # Убеждаемся, что embedding есть
                    if 'embedding' not in profile:
                        profile['embedding'] = np.zeros(384).tolist()
                    self.user_profiles[user_id] = profile
                    return profile
            except:
                pass
        
        # Создаем новый профиль с embedding
        profile = {
            'total_choices': 0,
            'liked_events': [],
            'disliked_events': [],
            'preferences': {},
            'embedding': np.zeros(384).tolist(),  # ← НОВОЕ ПОЛЕ
            'created_at': datetime.now().isoformat()
        }
        self.user_profiles[user_id] = profile
        return profile
    
    def save_user_profile(self, user_id):
        """Сохраняет профиль пользователя"""
        if user_id in self.user_profiles:
            profile_file = f'linear_ucb_profile_{user_id}.json'
            try:
                with open(profile_file, 'w') as f:
                    json.dump(self.user_profiles[user_id], f, indent=2)
            except Exception as e:
                print(f"Ошибка сохранения профиля: {e}")
    
    def reset_user_profile(self, user_id):
        """Полностью сбрасывает профиль пользователя и его модель."""
        # Удаляем из памяти
        if user_id in self.user_profiles:
            del self.user_profiles[user_id]
        if user_id in self.bandits:
            del self.bandits[user_id]
        
        # Удаляем файл профиля
        profile_file = f'linear_ucb_profile_{user_id}.json'
        if os.path.exists(profile_file):
            try:
                os.remove(profile_file)
                print(f"🗑️ Удален файл профиля: {profile_file}")
            except Exception as e:
                print(f"Ошибка удаления профиля: {e}")
        
        # Удаляем файл состояния бандита
        bandit_file = f'bandit_state_{user_id}.npz'
        if os.path.exists(bandit_file):
            try:
                os.remove(bandit_file)
                print(f"🗑️ Удален файл бандита: {bandit_file}")
            except Exception as e:
                print(f"Ошибка удаления бандита: {e}")
        
        # Создаем новый пустой профиль
        return self.get_user_profile(user_id)

    def update(self, user_id, event, liked):
        bandit = self.get_bandit(user_id)
        profile = self.get_user_profile(user_id)
        
        event_id = event['id']
        
        # Не обрабатываем события, которые уже были дизлайкнуты
        if event_id in profile['disliked_events']:
            return
        
        # Проверка на повторный лайк (но бандит всё равно обновляем)
        is_duplicate_like = liked and event_id in profile['liked_events']
        
        # Убеждаемся, что embedding - это список/массив, а не строка
        current_embedding = profile.get('embedding', np.zeros(384))
        if isinstance(current_embedding, str):
            print(f"⚠️ Исправляем испорченный embedding для {user_id}")
            current_embedding = np.zeros(384)
            profile['embedding'] = current_embedding.tolist()
        
        current_embedding = np.array(current_embedding, dtype=np.float32)
        event_embedding = self.feature_extractor.get_text_embedding(event)
        features = self.feature_extractor.extract_all_features(event, precomputed_embedding=event_embedding)
        
        # Обновляем модели, используя награду -1 для дизлайков
        reward = 1 if liked else -1
        bandit.update(features, reward=reward)

        # Сохраняем состояние бандитов на диск
        self.save_bandit(user_id)
        
        # Если это повторный лайк, дальше профиль не обновляем
        if is_duplicate_like:
            print(f"📊 Повторный лайк: {event_id}, бандиты обновлены и сохранены.")
            return
        
        total_choices = profile['total_choices']
        
        if liked:
            # Новый лайк
            alpha = 1 / (total_choices + 2)
            new_embedding = current_embedding + alpha * event_embedding
            profile['liked_events'].append(event_id)

            # ВРЕМЕННАЯ ОТЛАДКА
            print(f"\n🔥 ЛАЙК: {event['title'][:50]}...")
            print(f"   alpha={alpha:.4f}")
            
            for cat in event.get('categories', []):
                profile['preferences'][cat] = profile['preferences'].get(cat, 0) + 1
        else:
            # Дизлайк
            if event_id in profile['liked_events']:
                # Случай, когда пользователь отменяет свой лайк
                alpha = 1.1 / (total_choices + 2) # Увеличиваем "вес" отмены
                new_embedding = current_embedding - alpha * event_embedding
                profile['liked_events'].remove(event_id)
                for cat in event.get('categories', []):
                    profile['preferences'][cat] = max(0, profile['preferences'].get(cat, 0) - 1)
            else:
                # Обычный дизлайк нового события
                alpha = 0.1 / (total_choices + 2) # Уменьшаем "вес", чтобы не портить профиль
                new_embedding = current_embedding - alpha * event_embedding
            
            profile['disliked_events'].append(event_id)
        
        # Нормализуем эмбеддинг профиля
        norm = np.linalg.norm(new_embedding)
        profile['embedding'] = (new_embedding / norm).tolist() if norm > 0 else np.zeros(384).tolist()
        
        profile['total_choices'] = total_choices + 1
        self.user_profiles[user_id] = profile
        self.save_user_profile(user_id)
    
    def get_recommendations(self, user_id, events, n=20):
        """
        Возвращает топ-n событий на основе UCB score.
        """
        bandit = self.get_bandit(user_id)
        profile = self.get_user_profile(user_id)
        
        # Получаем эмбеддинг профиля для передачи в feature extractor
        profile_embedding = np.array(profile.get('embedding'))

        # Фильтруем события, которые пользователь уже видел (лайкнул ИЛИ дизлайкнул)
        seen_ids = set(profile.get('disliked_events', [])) | set(profile.get('liked_events', []))
        available_events = [e for e in events if e['id'] not in seen_ids]

        if len(available_events) < n:
            n = len(available_events)
        
        if not available_events:
            return []
        
        # Для первых выборов - случайные
        if profile['total_choices'] == 0:
            shuffled = available_events.copy()
            random.shuffle(shuffled)
            recommendations = []
            for event in shuffled[:n]:
                event = event.copy()
                event['_recommendation_type'] = 'random'
                recommendations.append(event)
            return recommendations

        # Вычисляем UCB score для каждого события
        scored_events = []
        for event in available_events:
            event_embedding = self.feature_extractor.get_text_embedding(event)
            features = self.feature_extractor.extract_all_features(event, precomputed_embedding=event_embedding)
            score, mean_reward, uncertainty = bandit.get_score(features)
            
            scored_events.append({
                'event': event,
                'score': score,
                'mean_reward': mean_reward,
                'uncertainty': uncertainty,
                'features': features
            })
        
        # Сортируем по UCB score
        scored_events.sort(key=lambda x: x['score'], reverse=True)
        
        # Формируем итоговый список
        recommendations = []
        for item in scored_events[:n]:
            event = item['event'].copy()
            event['_ucb_score'] = float(item['score'])
            event['_expected_reward'] = float(item['mean_reward'])
            event['_uncertainty'] = float(item['uncertainty'])
            event['_confidence'] = float(bandit.get_confidence(item['features']))
            event['_features'] = item['features'] # Сохраняем для расчета разнообразия
            
            if item['uncertainty'] > abs(item['mean_reward']) * 0.8: # Более мягкое условие для exploration
                event['_recommendation_type'] = 'exploration'
            else:
                event['_recommendation_type'] = 'exploitation'
            
            recommendations.append(event)
        
        return recommendations

    def get_pair_for_comparison(self, user_id, all_events):
        """
        Возвращает пару РАЗНООБРАЗНЫХ событий для сравнения.
        Одно событие - "лидер" по UCB-оценке.
        Второе - наиболее не похожее на лидера из топ-20.
        """
        # 1. Получаем топ-20 кандидатов, отфильтрованных по лайкам/дизлайкам
        candidates = self.get_recommendations(user_id, all_events, n=20)
        
        if len(candidates) < 2:
            print(f"⚠️ Недостаточно кандидатов для формирования разнообразной пары ({len(candidates)} шт.)")
            # Fallback на случайные, если есть хотя бы 2
            profile = self.get_user_profile(user_id)
            seen_ids = set(profile.get('disliked_events', [])) | set(profile.get('liked_events', []))
            available = [e for e in all_events if e['id'] not in seen_ids]
            if len(available) >= 2:
                return np.random.choice(available, 2, replace=False).tolist()
            return None, None

        # 2. Первое событие в паре - это всегда лидер
        leader = candidates[0]
        
        # Если нет features или это случайная рекомендация - не пытаемся искать diverse
        if '_features' not in leader or leader.get('_recommendation_type') == 'random':
            if len(candidates) >= 2:
                return leader, candidates[1]
            return leader, None

        # 3. Ищем второго кандидата, максимально не похожего на лидера
        diverse_candidate = None
        max_distance = -1
        
        leader_features = leader['_features']
        
        for candidate in candidates[1:]:
            candidate_features = candidate['_features']
            # Косинусное расстояние = 1 - косинусное сходство
            # Используем эмбеддинги (первые 384 признака) для расчета содержательного сходства
            distance = 1 - np.dot(leader_features[:384], candidate_features[:384])
            
            if distance > max_distance:
                max_distance = distance
                diverse_candidate = candidate
        
        print(f"↔️ Сформирована разнообразная пара. Расстояние: {max_distance:.3f}")
        
        # Очищаем временные поля перед отправкой
        del leader['_features']
        if diverse_candidate and '_features' in diverse_candidate:
             del diverse_candidate['_features']

        return leader, diverse_candidate
    
    def get_exploitation_recommendations(self, user_id, events, n=50, min_confidence=0.6,
                                       date_from=None, date_to=None, time_from=None, time_to=None, weekdays=None):
        """
        Возвращает топ-n событий на основе чистой эксплуатации (mean_reward)
        с фильтрацией по времени
        """
        bandit = self.get_bandit(user_id)
        profile = self.get_user_profile(user_id)
        total_likes = len(profile.get('liked_events', []))
        total_choices = profile.get('total_choices', 0)
        
        # Проверяем, достаточно ли данных
        if total_choices < 5:
            return {
                'recommendations': [],
                'has_enough_data': False,
                'total_choices': total_choices,
                'total_likes': total_likes,
                'found_count': 0,
                'message': f'Недостаточно данных. Сделайте еще {5 - total_choices} выборов.'
            }
        
        # Фильтруем уже обработанные события
        seen_ids = set(profile.get('disliked_events', [])) | set(profile.get('liked_events', []))
        available_events = [e for e in events if e['id'] not in seen_ids]
        
        # ✅ ПРИМЕНЯЕМ ФИЛЬТРАЦИЮ ПО ВРЕМЕНИ
        filtered_events = self.feature_extractor.filter_events_by_time(
            available_events,
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            weekdays=weekdays
        )
        
        print(f"📊 Фильтрация exploitation: было {len(available_events)} событий, осталось {len(filtered_events)}")
        
        if not filtered_events:
            return {
                'recommendations': [],
                'has_enough_data': True,
                'total_choices': total_choices,
                'total_likes': total_likes,
                'found_count': 0,
                'message': 'Нет событий, соответствующих фильтрам'
            }
        
        # Вычисляем mean_reward для каждого события
        scored_events = []
        for event in filtered_events:
            try:
                features = self.feature_extractor.extract_all_features(event)
                _, mean_reward, uncertainty = bandit.get_score(features)
                confidence = bandit.get_confidence(features)
                
                scored_events.append({
                    'event': event,
                    'mean_reward': mean_reward,
                    'uncertainty': uncertainty,
                    'confidence': confidence
                })
            except Exception as e:
                print(f"Ошибка обработки события {event.get('id')}: {e}")
                continue
        
        # Сортируем по mean_reward
        scored_events.sort(key=lambda x: x['mean_reward'], reverse=True)
        
        # Находим min и max для нормализации
        if scored_events:
            all_mean_rewards = [item['mean_reward'] for item in scored_events]
            min_reward = min(all_mean_rewards)
            max_reward = max(all_mean_rewards)
            
            for item in scored_events:
                normalized = (item['mean_reward'] - min_reward) / (max_reward - min_reward + 1e-8)
                item['normalized_percent'] = int(normalized * 100)
        
        # Формируем результат
        recommendations = []
        for item in scored_events[:n]:
            event = item['event'].copy()
            event['_mean_reward'] = float(item['mean_reward'])
            event['_uncertainty'] = float(item['uncertainty'])
            event['_confidence'] = float(item['confidence'])
            event['_similarity_percent'] = item.get('normalized_percent', 50)
            event['_recommendation_type'] = 'exploitation'
            recommendations.append(event)
        
        return {
            'recommendations': recommendations,
            'has_enough_data': True,
            'total_choices': total_choices,
            'total_likes': total_likes,
            'found_count': len(recommendations),
            'message': None
        }

    def get_cosine_recommendations(self, user_id, events, n=50, similarity_threshold=None,
                                date_from=None, date_to=None, time_from=None, time_to=None, weekdays=None):
        """
        Возвращает топ-n событий на основе косинусного сходства с фильтрацией по времени
        """
        profile = self.get_user_profile(user_id)
        profile_embedding = np.array(profile.get('embedding', np.zeros(384)))
        
        total_likes = len(profile.get('liked_events', []))
        
        # Проверяем, есть ли эмбеддинг профиля
        if np.linalg.norm(profile_embedding) < 0.01 or total_likes == 0:
            print(f"⚠️ Профиль пользователя пуст (лайков: {total_likes})")
            return {
                'recommendations': [],
                'has_enough_likes': False,
                'total_likes': total_likes,
                'similarity_threshold': similarity_threshold
            }
        
        # Фильтруем дизлайкнутые события
        disliked_ids = set(profile.get('disliked_events', []))
        available_events = [e for e in events if e['id'] not in disliked_ids]
        
        # ПРИМЕНЯЕМ ФИЛЬТРАЦИЮ ПО ВРЕМЕНИ
        filtered_events = self.feature_extractor.filter_events_by_time(
            available_events,
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            weekdays=weekdays
        )
        
        print(f"📊 Фильтрация: было {len(available_events)} событий, осталось {len(filtered_events)}")
        
        if not filtered_events:
            return {
                'recommendations': [],
                'has_enough_likes': total_likes >= 3,
                'total_likes': total_likes,
                'similarity_threshold': similarity_threshold,
                'found_count': 0
            }
        
        # Вычисляем косинусное сходство для отфильтрованных событий
        scored_events = []
        for event in filtered_events:
            event_embedding = self.feature_extractor.get_text_embedding(event)
            
            similarity = np.dot(profile_embedding, event_embedding) / (
                np.linalg.norm(profile_embedding) * np.linalg.norm(event_embedding) + 1e-8
            )
            
            scored_events.append((event, similarity))
        
        # Сортируем по убыванию сходства
        scored_events.sort(key=lambda x: x[1], reverse=True)
        
        top_events = scored_events[:min(n, len(scored_events))]
        
        # Формируем результат
        recommendations = []
        for event, similarity in top_events:
            event = event.copy()
            event['_similarity'] = float(similarity)
            event['_similarity_percent'] = int(similarity * 100)
            event['_recommendation_type'] = 'cosine_similarity'
            recommendations.append(event)
        
        print(f"📊 Косинусные рекомендации: найдено {len(recommendations)} событий с сходством > {similarity_threshold}")
        
        return {
            'recommendations': recommendations,
            'has_enough_likes': total_likes >= 3,
            'total_likes': total_likes,
            'similarity_threshold': similarity_threshold,
            'found_count': len(recommendations)
        }

    def get_model_insights(self, user_id):
        """
        Возвращает аналитику модели для пользователя
        """
        bandit = self.bandits.get(user_id)
        profile = self.get_user_profile(user_id)
        
        if not bandit or not profile:
            return None
        
        total_choices = profile.get('total_choices', 0)
        total_likes = len(profile.get('liked_events', []))
        total_dislikes = len(profile.get('disliked_events', []))
        
        # CTR должен быть от 0 до 1
        ctr = total_likes / max(1, total_choices)
        
        # Количество обновлений бандита
        total_updates = bandit.total_updates
        
        return {
            'total_interactions': total_choices,
            'total_likes': total_likes,
            'total_dislikes': total_dislikes,
            'ctr': ctr,  # теперь от 0 до 1
            'model_complexity': float(bandit.get_model_complexity()),
            'top_preferences': sorted(
                profile.get('preferences', {}).items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5],
            'exploration_rate': self.alpha / (1 + total_updates / 50)
        }