import profile
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
        Обновляет модель на основе фидбека
        features: вектор признаков события
        reward: 1 (лайк) или 0 (дизлайк)
        """
        features = np.array(features).reshape(-1, 1)
        
        # Обновляем A = A + x*x^T
        self.A += np.outer(features, features)
        
        # Обновляем b = b + reward * x
        self.b += reward * features.flatten()
        
        # Пересчитываем theta
        self._update_theta()
        
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
        self.sentence_model = SentenceTransformer(model_name)
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
    
    def extract_all_features(self, event):
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
    
    def get_bandit(self, user_id):
        """Получает или создает экземпляр LinearUCB для пользователя"""
        if user_id not in self.bandits:
            self.bandits[user_id] = LinearUCB(
                n_features=self.feature_dim,
                alpha=self.alpha,
                lambda_reg=self.lambda_reg
            )
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
        """Полностью сбрасывает профиль пользователя"""
        # Удаляем из памяти
        if user_id in self.user_profiles:
            del self.user_profiles[user_id]
        
        # Удаляем из бандитов
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
        
        # Удаляем файл бандита (если есть)
        bandit_file = f'bandit_{user_id}_state.json'
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
        
        # Дизлайкнутое событие не обрабатываем
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
        features = self.feature_extractor.extract_all_features(event, profile_embedding=current_embedding)
        event_embedding = self.feature_extractor.get_text_embedding(event)
        
        # Бандит обновляем ВСЕГДА (и для повторных лайков тоже!)
        bandit.update(features, reward=1 if liked else 0)
        
        # Если повторный лайк - эмбеддинг не меняем
        if is_duplicate_like:
            print(f"📊 Повторный лайк: {event_id}, бандит обновлен")
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
            print(f"   norm_old={np.linalg.norm(current_embedding):.4f}")
            print(f"   norm_new={np.linalg.norm(new_embedding):.4f}")
            print(f"   event_embedding_norm={np.linalg.norm(event_embedding):.4f}")
            
            for cat in event.get('categories', []):
                profile['preferences'][cat] = profile['preferences'].get(cat, 0) + 1
        else:
            # Дизлайк
            if event_id in profile['liked_events']:
                # Лайк → дизлайк (отменяем лайк)
                alpha = 1.1 / (total_choices + 2)
                new_embedding = current_embedding - alpha * event_embedding
                profile['liked_events'].remove(event_id)
                for cat in event.get('categories', []):
                    profile['preferences'][cat] = max(0, profile['preferences'].get(cat, 0) - 1)
            else:
                # Новый дизлайк
                alpha = 0.1 / (total_choices + 2)
                new_embedding = current_embedding - alpha * event_embedding
                # ВРЕМЕННАЯ ОТЛАДКА
                print(f"\n❌ ДИЗЛАЙК: {event['title'][:50]}...")
                print(f"   alpha={alpha:.4f}")
                print(f"   norm_old={np.linalg.norm(current_embedding):.4f}")
                print(f"   norm_new={np.linalg.norm(new_embedding):.4f}")
            
            profile['disliked_events'].append(event_id)
        
        # Нормализуем эмбеддинг
        norm = np.linalg.norm(new_embedding)
        profile['embedding'] = (new_embedding / norm).tolist() if norm > 0 else np.zeros(384).tolist()
        
        profile['total_choices'] = total_choices + 1
        self.user_profiles[user_id] = profile
        self.save_user_profile(user_id)
    
    def get_recommendations(self, user_id, events, n=2):
        """
        Возвращает топ-n событий на основе UCB score.
        UCB сам балансирует exploration и exploitation!
        """
        bandit = self.get_bandit(user_id)
        profile = self.get_user_profile(user_id)
        
        # Получаем эмбеддинг профиля
        profile_embedding = profile.get('embedding')

        # Фильтруем дизлайкнутые события
        available_events = [
            e for e in events 
            if e['id'] not in profile['disliked_events']
        ]
        
        if len(available_events) < n:
            return available_events
        
        # Вычисляем UCB score для каждого события
        scored_events = []
        for event in available_events:
            features = self.feature_extractor.extract_all_features(event, profile_embedding)
            score, mean_reward, uncertainty = bandit.get_score(features)
            # score = mean_reward + alpha * uncertainty
            # где:
            # - mean_reward: насколько событие похоже на профиль (exploitation)
            # - uncertainty: насколько мы неуверены (exploration)
            
            scored_events.append((event, score, mean_reward, uncertainty, features))
        
        # Сортируем по UCB score
        scored_events.sort(key=lambda x: x[1], reverse=True)
        
        # Возвращаем топ-n
        recommendations = []
        for event, score, mean_reward, uncertainty, features in scored_events[:n]:
            event = event.copy()
            event['_ucb_score'] = float(score)
            event['_expected_reward'] = float(mean_reward)
            event['_uncertainty'] = float(uncertainty)
            event['_confidence'] = float(bandit.get_confidence(features))
            
            # Определяем тип рекомендации
            if uncertainty > abs(mean_reward):
                event['_recommendation_type'] = 'exploration'
            else:
                event['_recommendation_type'] = 'exploitation'
            
            recommendations.append(event)
        
        return recommendations

    def get_pair_for_comparison(self, user_id, all_events):
        """
        Возвращает пару событий для сравнения.
        Показывает топ-1 и топ-2 по UCB score.
        """
        profile = self.get_user_profile(user_id)
        
        # Получаем ID дизлайкнутых событий
        disliked_ids = set(profile.get('disliked_events', []))
        
        # Отладка
        print(f"🔍 get_pair_for_comparison: всего событий={len(all_events)}, дизлайкнуто={len(disliked_ids)}")
        
        # Фильтруем дизлайкнутые события
        available_events = [
            e for e in all_events 
            if e['id'] not in disliked_ids
        ]
        
        print(f"   доступно после фильтрации: {len(available_events)}")
        
        if len(available_events) < 2:
            print(f"⚠️ Недостаточно событий после фильтрации!")
            return None, None
        
        # Получаем топ-2 события по UCB score
        recommendations = self.get_recommendations(user_id, available_events, n=2)
        
        print(f"   получено рекомендаций: {len(recommendations)}")
        
        if len(recommendations) >= 2:
            print(f"   возвращаем топ-1 и топ-2")
            return recommendations[0], recommendations[1]
        
        # Fallback: случайные события из доступных
        import random
        if len(available_events) >= 2:
            selected = random.sample(available_events, 2)
            print(f"   fallback: случайные события")
            return selected[0], selected[1]
        
        return None, None
    

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