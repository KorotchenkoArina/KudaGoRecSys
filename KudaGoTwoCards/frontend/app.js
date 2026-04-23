// ============================================
// КОНФИГУРАЦИЯ
// ============================================
const API_BASE = 'http://localhost:5000/api';
let comparisonsCount = 0;
let currentPair = null;
let isLocked = false;
let sessionId = null;
let recommendationCheckInterval = null;

// DOM элементы
const comparisonArea = document.getElementById('comparisonArea');
const resultsArea = document.getElementById('resultsArea');
const comparisonsCountElement = document.getElementById('comparisonsCount');
const resetBtn = document.getElementById('resetBtn');
const continueBtn = document.getElementById('continueBtn');
const profileBtn = document.getElementById('profileBtn');
const likesBtn = document.getElementById('likesBtn');
const likesArea = document.getElementById('likesArea');
const likesCountElement = document.getElementById('likesCount');
const backToComparisonBtn = document.getElementById('backToComparisonBtn');
const likedEventsGrid = document.getElementById('likedEventsGrid');

// ============================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================

/**
 * Эскейпинг HTML специальных символов
 */
function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Форматирование даты
 */
function formatDate(dateString) {
    if (!dateString) return 'Дата не указана';
    return dateString;
}

/**
 * Получение или создание ID сессии
 */
function getSessionId() {
    let id = localStorage.getItem('eventchoice_session_id');
    if (!id) {
        id = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('eventchoice_session_id', id);
    }
    return id;
}

/**
 * Показ уведомления
 */
function showMessage(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span>
        <span class="toast-message">${message}</span>
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Загрузка профиля пользователя
 */
async function loadUserProfile() {
    try {
        const response = await fetch(`${API_BASE}/user/profile`);
        const data = await response.json();
        if (data.success) {
            return data;
        }
    } catch (error) {
        console.error('Ошибка загрузки профиля:', error);
    }
    return null;
}

/**
 * Загрузка статистики
 */
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/user/profile`);
        const data = await response.json();
        if (data.success) {
            comparisonsCount = data.total_choices;  // Оставляем для других частей интерфейса (панель профиля)
            likesCountElement.textContent = data.liked_count || 0; // Обновляем новый счетчик лайков
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// После каждого действия обновляем статистику
async function updateStats() {
    await loadStats();
}

// ============================================
// ОСНОВНЫЕ ФУНКЦИИ РЕКОМЕНДАТЕЛЬНОЙ СИСТЕМЫ
// ============================================

/** Временная функция для отладки */
window.debugAPI = {
    insights: async function() {
        const response = await fetch('http://localhost:5000/api/debug/console', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'insights' })
        });
        const data = await response.json();
        console.log('📊 Insights:', data.insights);
        return data;
    },
    
    profile: async function() {
        const response = await fetch('http://localhost:5000/api/debug/console', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'profile' })
        });
        const data = await response.json();
        console.log('👤 Profile:', data.profile);
        return data;
    },
    
    reset: async function() {
        const response = await fetch('http://localhost:5000/api/debug/console', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'reset_debug' })
        });
        const data = await response.json();
        console.log('🔄 Reset:', data.message);
        return data;
    }
};


/**
 * Выводит полную статистику пользователя в консоль
 */
async function logUserStats() {
    console.log('\n' + '='.repeat(70));
    console.log('📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ');
    console.log('='.repeat(70));
    
    try {
        // Получаем профиль
        const profileResponse = await fetch(`${API_BASE}/user/profile`);
        const profileData = await profileResponse.json();
        
        if (profileData.success) {
            console.log(`👤 ID пользователя: ${sessionId || 'unknown'}`);
            console.log(`📊 Всего сравнений: ${profileData.total_choices}`);
            console.log(`👍 Лайков: ${profileData.liked_count}`);
            console.log(`👎 Дизлайков: ${profileData.disliked_count}`);
            
            const total = profileData.total_choices;
            const likes = profileData.liked_count;
            console.log(`📈 Соотношение: ${total > 0 ? (likes / total * 100).toFixed(1) : 0}% лайков`);
            
            // Предпочтения по категориям
            const preferences = profileData.preferences || {};
            const sortedPrefs = Object.entries(preferences).sort((a, b) => b[1] - a[1]);
            
            if (sortedPrefs.length > 0) {
                console.log('\n🏆 ТОП-5 КАТЕГОРИЙ:');
                sortedPrefs.slice(0, 5).forEach(([cat, count], i) => {
                    const bar = '█'.repeat(Math.min(20, Math.floor(count / 2)));
                    console.log(`   ${i+1}. ${cat.padEnd(20)} ${bar} ${count}`);
                });
            } else {
                console.log('\n🏆 Топ категорий: пока нет данных');
            }
        }
        
        // Используем существующий debugAPI для insights (опционально)
        if (window.debugAPI) {
            try {
                const insightsData = await window.debugAPI.insights();
                if (insightsData && insightsData.insights) {
                    const i = insightsData.insights;
                    console.log('\n🤖 МОДЕЛЬ UCB:');
                    console.log(`   CTR (точность): ${(i.ctr * 100).toFixed(1)}%`);
                    console.log(`   Сложность модели: ${i.model_complexity?.toFixed(2) || 'N/A'}`);
                    console.log(`   Exploration rate: ${(i.exploration_rate * 100).toFixed(1)}%`);
                }
            } catch(e) {
                console.log('   (insights временно недоступны)');
            }
        }
        
    } catch (error) {
        console.error('Ошибка получения статистики:', error);
    }
    
    console.log('='.repeat(70) + '\n');
}

/**
 * Отрисовка пары для сравнения (с кнопкой "оба не подходят" под VS)
 */
async function renderComparisonPair(leftEvent, rightEvent, recommendationType) {
    const typeLabel = recommendationType === 'exploration' ? 'Новое!' : 
                      recommendationType === 'exploitation' ? 'Для вас' : 
                      '✨ Рекомендация';
    
    comparisonArea.innerHTML = `
        <div class="comparison-grid">
            <div class="event-card" data-id="${leftEvent.id}" data-side="left">
                <div class="event-image">
                    <img src="${leftEvent.image}" alt="${escapeHtml(leftEvent.title)}" 
                         onerror="this.onerror=null; this.src='https://picsum.photos/400/280?random=${leftEvent.id}'">
                    <div class="event-badge">Вариант A</div>
                </div>
                <div class="event-content">
                    <h3 class="event-title">${escapeHtml(leftEvent.title)}</h3>
                    <div class="event-place">
                        <span>📍</span>
                        <span>${escapeHtml(leftEvent.place)}</span>
                    </div>
                    <div class="event-date">
                        <span>📅</span>
                        <span>${formatDate(leftEvent.date)}</span>
                    </div>
                    <div class="event-price">
                        <span>💰</span>
                        <span>${escapeHtml(leftEvent.price)}</span>
                    </div>
                    <p class="event-description">${escapeHtml(leftEvent.description)}</p>
                    
                    <!-- Ссылка сразу после описания -->
                    <a href="${leftEvent.url}" target="_blank" class="event-link-bold" onclick="event.stopPropagation()">
                        🔗 Подробнее о событии
                    </a>
                    
                    <!-- Кнопка в самом низу -->
                    <button class="btn-choose" data-id="${leftEvent.id}" data-side="left">
                        ✅ Выбрать это
                    </button>
                </div>
            </div>
            
            <div class="vs-container">
                <button class="like-both-btn" id="likeBothBtn">
                            <span class="btn-icon">👍</span>
                            <span class="btn-text">Оба нравятся</span>
                </button>
                <div class="vs-divider">
                    <span class="vs-text">VS</span>
                    <span class="rec-type-badge">${typeLabel}</span>
                </div>
                <button class="dislike-both-btn" id="dislikeBothBtn">
                        <span class="btn-icon">👎</span>
                        <span class="btn-text">Оба не подходят</span>
                </button>
            </div>
            
            <div class="event-card" data-id="${rightEvent.id}" data-side="right">
                <div class="event-image">
                    <img src="${rightEvent.image}" alt="${escapeHtml(rightEvent.title)}" 
                         onerror="this.onerror=null; this.src='https://picsum.photos/400/280?random=${rightEvent.id}'">
                    <div class="event-badge">Вариант B</div>
                </div>
                <div class="event-content">
                    <h3 class="event-title">${escapeHtml(rightEvent.title)}</h3>
                    <div class="event-place">
                        <span>📍</span>
                        <span>${escapeHtml(rightEvent.place)}</span>
                    </div>
                    <div class="event-date">
                        <span>📅</span>
                        <span>${formatDate(rightEvent.date)}</span>
                    </div>
                    <div class="event-price">
                        <span>💰</span>
                        <span>${escapeHtml(rightEvent.price)}</span>
                    </div>
                    <p class="event-description">${escapeHtml(rightEvent.description)}</p>
                    <a href="${rightEvent.url}" target="_blank" class="event-link-bold" onclick="event.stopPropagation()">
                        🔗 Подробнее о событии
                    </a>
                    <button class="btn-choose" data-id="${rightEvent.id}" data-side="right">
                        ✅ Выбрать это
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // ============================================
    // ОТЛАДКА: вывод данных в консоль
    // ============================================
    console.log('\n' + '='.repeat(60));
    console.log('🎯 НОВАЯ ПАРА ДЛЯ СРАВНЕНИЯ');
    console.log('='.repeat(60));
    
    // Левое событие
    console.log('\n📌 ЛЕВОЕ событие (Вариант A):');
    console.log(`   Название: ${leftEvent.title}`);
    console.log(`   ID: ${leftEvent.id}`);
    console.log(`   Категории: ${leftEvent.categories?.join(', ') || 'нет'}`);
    console.log(`   Место: ${leftEvent.place}`);
    console.log(`   Цена: ${leftEvent.price}`);
    console.log(`   Дата: ${leftEvent.date}`);
    if (leftEvent._ucb_score) {
        console.log(`   📊 UCB score: ${leftEvent._ucb_score.toFixed(4)}`);
        console.log(`   🎯 Expected reward: ${leftEvent._expected_reward?.toFixed(4) || 'N/A'}`);
        console.log(`   ❓ Uncertainty: ${leftEvent._uncertainty?.toFixed(4) || 'N/A'}`);
        console.log(`   💪 Confidence: ${leftEvent._confidence?.toFixed(4) || 'N/A'}`);
        console.log(`   🏷️ Тип: ${leftEvent._recommendation_type || 'unknown'}`);
    }
    
    // Правое событие
    console.log('\n📌 ПРАВОЕ событие (Вариант B):');
    console.log(`   Название: ${rightEvent.title}`);
    console.log(`   ID: ${rightEvent.id}`);
    console.log(`   Категории: ${rightEvent.categories?.join(', ') || 'нет'}`);
    console.log(`   Место: ${rightEvent.place}`);
    console.log(`   Цена: ${rightEvent.price}`);
    console.log(`   Дата: ${rightEvent.date}`);
    if (rightEvent._ucb_score) {
        console.log(`   📊 UCB score: ${rightEvent._ucb_score.toFixed(4)}`);
        console.log(`   🎯 Expected reward: ${rightEvent._expected_reward?.toFixed(4) || 'N/A'}`);
        console.log(`   ❓ Uncertainty: ${rightEvent._uncertainty?.toFixed(4) || 'N/A'}`);
        console.log(`   💪 Confidence: ${rightEvent._confidence?.toFixed(4) || 'N/A'}`);
        console.log(`   🏷️ Тип: ${rightEvent._recommendation_type || 'unknown'}`);
    }
    
    // Сравнение
    if (leftEvent._ucb_score && rightEvent._ucb_score) {
        console.log('\n📊 СРАВНЕНИЕ:');
        const diff = leftEvent._ucb_score - rightEvent._ucb_score;
        console.log(`   Разница в UCB score: ${diff > 0 ? '+' : ''}${diff.toFixed(4)}`);
        if (Math.abs(diff) < 0.1) {
            console.log(`   ⚠️ События очень близки по score!`);
        } else if (diff > 0) {
            console.log(`   👑 Левое событие предпочтительнее на ${diff.toFixed(4)}`);
        } else {
            console.log(`   👑 Правое событие предпочтительнее на ${Math.abs(diff).toFixed(4)}`);
        }
    }
    
    console.log('\n💡 Тип пары: ' + 
        (recommendationType === 'exploration' ? '🎲 EXPLORATION (исследование новых)' : 
         recommendationType === 'exploitation' ? '🎯 EXPLOITATION (персональные)' : 
         '✨ Обычная рекомендация'));
    console.log('='.repeat(60) + '\n');

    // Статистика профиля - добавляем await
    await logUserStats();

    // Добавляем обработчики на кнопки выбора
    document.querySelectorAll('.btn-choose').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const winnerId = parseInt(btn.dataset.id);
            const side = btn.dataset.side;
            const loserId = side === 'left' ? rightEvent.id : leftEvent.id;
            makeChoice(winnerId, loserId);
        });
    });
    
    // Добавляем обработчики на карточки
    document.querySelectorAll('.event-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Если кликнули на ссылку или кнопку - не обрабатываем
            if (e.target.classList.contains('btn-choose')) return;
            if (e.target.classList.contains('event-link-bold')) return;
            if (e.target.closest('.event-link-bold')) return;
            
            const winnerId = parseInt(card.dataset.id);
            const loserId = winnerId === leftEvent.id ? rightEvent.id : leftEvent.id;
            makeChoice(winnerId, loserId);
        });
    });
    
    // Добавляем обработчик для кнопки "оба не подходят"
    const dislikeBothBtn = document.getElementById('dislikeBothBtn');
    if (dislikeBothBtn) {
        dislikeBothBtn.addEventListener('click', dislikeBoth);
    }

    // Добавляем обработчик для кнопки "оба нравятся"
    const likeBothBtn = document.getElementById('likeBothBtn');
    if (likeBothBtn) {
        likeBothBtn.addEventListener('click', likeBoth);
    }
}

/**
 * Загрузка пары для сравнения (с учётом рекомендаций)
 */
async function loadComparisonPair() {
    comparisonArea.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>Загружаем события...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/events/compare`);
        const data = await response.json();
        
        if (data.success) {
            currentPair = {
                left: data.event_left,
                right: data.event_right,
                type: data.recommendation_type
            };
            await renderComparisonPair(data.event_left, data.event_right, data.recommendation_type);
        } else {
            comparisonArea.innerHTML = `
                <div class="loading">
                    <p>❌ ${data.error || 'Не удалось загрузить события'}</p>
                    <button class="btn-choose" onclick="location.reload()" style="margin-top: 20px;">
                        🔄 Попробовать снова
                    </button>
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка загрузки пары:', error);
        comparisonArea.innerHTML = `
            <div class="loading">
                <p>❌ Ошибка подключения к серверу</p>
                <p style="font-size: 12px; margin-top: 8px;">Убедитесь, что бэкенд запущен на ${API_BASE}</p>
                <button class="btn-choose" onclick="location.reload()" style="margin-top: 20px;">
                    🔄 Попробовать снова
                </button>
            </div>
        `;
    }
}

/**
 * Обработка выбора пользователя
 */
async function makeChoice(winnerId, loserId) {
    if (isLocked) {
        console.log('⚠️ Выбор заблокирован, ждите...');
        return;
    }
    isLocked = true;
    
    // Визуальная обратная связь
    const cards = document.querySelectorAll('.event-card');
    cards.forEach(card => {
        if (parseInt(card.dataset.id) === winnerId) {
            card.classList.add('selected');
        } else {
            card.classList.add('disabled');
        }
    });
    
    try {
        const response = await fetch(`${API_BASE}/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ winner_id: winnerId, loser_id: loserId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            comparisonsCount++;
            comparisonsCountElement.textContent = comparisonsCount;
            
            showLikeAnimation(winnerId);
            
            
            // Загружаем следующую пару
            setTimeout(() => {
                loadComparisonPair();
                isLocked = false;
            }, 400);
        } else {
            throw new Error(data.error || 'Ошибка при сохранении выбора');
        }
        
    } catch (error) {
        console.error('Ошибка при отправке выбора:', error);
        showMessage('Ошибка при сохранении выбора', 'error');
        isLocked = false;
        cards.forEach(card => {
            card.classList.remove('selected', 'disabled');
        });
    }
}

/**
 * Анимация лайка
 */
function showLikeAnimation(eventId) {
    const likeAnimation = document.createElement('div');
    likeAnimation.className = 'like-animation';
    likeAnimation.innerHTML = '❤️';
    document.body.appendChild(likeAnimation);
    
    setTimeout(() => {
        likeAnimation.remove();
    }, 600);
}

// ============================================
// ФУНКЦИИ РЕКОМЕНДАЦИЙ
// ============================================

/**
 * Показать панель с профилем пользователя
 */
async function showUserProfile() {
    const profile = await loadUserProfile();
    if (!profile) return;
    
    const profileHtml = `
        <div id="profilePanel" class="profile-panel">
            <div class="profile-header">
                <h3>📊 Ваш профиль</h3>
                <button class="profile-close" onclick="document.getElementById('profilePanel').remove()">✕</button>
            </div>
            <div class="profile-stats">
                <div class="profile-stat">
                    <span class="profile-stat-value">${comparisonsCount}</span>
                    <span class="profile-stat-label">сравнений</span>
                </div>
                <div class="profile-stat">
                    <span class="profile-stat-value">${profile.liked_count || 0}</span>
                    <span class="profile-stat-label">лайков</span>
                </div>
            </div>
            <div class="profile-preferences">
                <h4>Ваши предпочтения:</h4>
                <div class="preferences-list">
                    ${Object.entries(profile.preferences || {})
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 5)
                        .map(([cat, count]) => `
                            <div class="preference-item">
                                <span class="preference-name">${escapeHtml(cat)}</span>
                                <span class="preference-count">${count} ❤️</span>
                            </div>
                        `).join('')}
                    ${!profile.preferences || Object.keys(profile.preferences).length === 0 ? 
                        '<p class="no-preferences">Пока нет данных. Выбирайте события!</p>' : ''}
                </div>
            </div>
        </div>
    `;
    
    // Удаляем старую панель, если есть
    const oldPanel = document.getElementById('profilePanel');
    if (oldPanel) oldPanel.remove();
    
    document.body.insertAdjacentHTML('beforeend', profileHtml);
}

/**
 * Управляет отображением основных экранов приложения.
 * @param {'comparison' | 'results' | 'likes'} viewName Имя экрана для показа
 */
function showView(viewName) {
    // Сначала скрываем все экраны
    comparisonArea.style.display = 'none';
    resultsArea.style.display = 'none';
    likesArea.style.display = 'none';

    // Затем показываем нужный
    if (viewName === 'comparison') {
        comparisonArea.style.display = 'flex';
    } else if (viewName === 'results') {
        resultsArea.style.display = 'block';
    } else if (viewName === 'likes') {
        likesArea.style.display = 'block';
    }
}

/**
 * Показывает страницу с лайкнутыми событиями
 */
async function showLikesPage() {
    showView('likes');
    likedEventsGrid.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>Загружаем ваши лайки...</p>
        </div>
    `;

    try {
        // Этот эндпоинт мы создадим на бэкенде следующим шагом
        const response = await fetch(`${API_BASE}/user/liked-events`);
        const data = await response.json();

        if (data.success && data.liked_events.length > 0) {
            likedEventsGrid.innerHTML = data.liked_events.map(event => `
                <div class="recommendation-card" onclick="window.open('${event.url}', '_blank')">
                    <div class="recommendation-image" style="background-image: url('${event.image}')">
                    </div>
                    <div class="recommendation-content">
                        <h4 class="recommendation-title">${escapeHtml(event.title)}</h4>
                        <div class="recommendation-place">
                            <span>📍</span>
                            <span>${escapeHtml(event.place)}</span>
                        </div>
                        <div class="recommendation-date">
                            <span>📅</span>
                            <span>${formatDate(event.date)}</span>
                        </div>
                        <div class="recommendation-price">
                            <span>💰</span>
                            <span>${escapeHtml(event.price)}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        } else {
            likedEventsGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤔</div>
                    <p class="empty-state-text">У вас пока нет лайков.</p>
                    <p class="empty-state-subtext">Начните сравнивать события, чтобы составить свою коллекцию!</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка загрузки лайкнутых событий:', error);
        likedEventsGrid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">❌</div>
                <p class="empty-state-text">Ошибка загрузки данных</p>
            </div>
        `;
    }
}

/**
 * Показать рекомендации (список)
 */
async function showRecommendations() {
    showView('results');
    
    try {
        const response = await fetch(`${API_BASE}/recommendations`);
        const data = await response.json();
        
        if (data.success && data.recommendations.length > 0) {
            const recommendationsContainer = document.getElementById('recommendations');
            recommendationsContainer.innerHTML = data.recommendations.map((rec, index) => `
                <div class="recommendation-card" onclick="window.open('${rec.url}', '_blank')">
                    <div class="recommendation-image" style="background-image: url('${rec.image}')">
                        <div class="recommendation-rank">${index + 1}</div>
                    </div>
                    <div class="recommendation-content">
                        <h4 class="recommendation-title">${escapeHtml(rec.title)}</h4>
                        <div class="recommendation-place">
                            <span>📍</span>
                            <span>${escapeHtml(rec.place)}</span>
                        </div>
                        <div class="recommendation-date">
                            <span>📅</span>
                            <span>${formatDate(rec.date)}</span>
                        </div>
                        <div class="recommendation-price">
                            <span>💰</span>
                            <span>${escapeHtml(rec.price)}</span>
                        </div>
                        <div class="recommendation-score">
                            <span>🏆</span>
                            <span>Побед: ${data.scores[rec.id] || 0}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        } else {
            recommendationsContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤔</div>
                    <p class="empty-state-text">Пока нет рекомендаций. Сделайте больше сравнений!</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка загрузки рекомендаций:', error);
        document.getElementById('recommendations').innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">❌</div>
                <p class="empty-state-text">Ошибка загрузки рекомендаций</p>
            </div>
        `;
    }
}

/**
 * Сброс игры
 */
async function resetGame() {
    if (confirm('Сбросить все сравнения и начать заново?')) {
        try {
            await fetch(`${API_BASE}/reset`, { method: 'POST' });
            await loadStats(); // Обновляем все счетчики
            
            showView('comparison'); // Возвращаемся на главный экран
            
            await loadComparisonPair();
            showMessage('Все данные сброшены! Начинаем заново 🎯', 'success');
        } catch (error) {
            console.error('Ошибка сброса:', error);
            showMessage('Ошибка при сбросе данных', 'error');
        }
    }
}

// ============================================
// ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
// ============================================

/**
 * Анимация для "оба не подходят"
 */
function showDislikeBothAnimation() {
    const animation = document.createElement('div');
    animation.className = 'dislike-both-animation';
    animation.innerHTML = '👎 Оба не подходят 👎';
    document.body.appendChild(animation);
    
    setTimeout(() => {
        animation.remove();
    }, 800);
}

/**
 * Анимация для "оба нравятся"
 */
function showLikeBothAnimation() {
    const animation = document.createElement('div');
    animation.className = 'like-both-animation';
    animation.innerHTML = '👍 Оба нравятся 👍';
    document.body.appendChild(animation);
    
    setTimeout(() => {
        animation.remove();
    }, 800);
}

/**
 * Обработка "оба события не подходят"
 * Отправляет дизлайк на оба события и загружает новую пару
 */
async function dislikeBoth() {
    if (isLocked || !currentPair) return;
    isLocked = true;
    
    const leftEvent = currentPair.left;
    const rightEvent = currentPair.right;
    
    console.log('👎 Оба не подходят:', leftEvent.title, 'и', rightEvent.title);
    
    // Визуальная обратная связь
    const cards = document.querySelectorAll('.event-card');
    cards.forEach(card => {
        card.classList.add('disabled');
    });
    
    showDislikeBothAnimation();
    
    try {
        // Отправляем ОДИН запрос с обоими ID
        const response = await fetch(`${API_BASE}/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                winner_id: null,
                loser_id: null,
                both_disliked: true,
                left_event_id: leftEvent.id,
                right_event_id: rightEvent.id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Увеличиваем счетчик только один раз
            await updateStats();
            
            showMessage('Оба события добавлены в исключённые', 'info');
            
            // Загружаем следующую пару
            setTimeout(() => {
                loadComparisonPair();
                isLocked = false;
            }, 500);
        } else {
            throw new Error(data.error || 'Ошибка');
        }
        
    } catch (error) {
        console.error('Ошибка при отправке дизлайков:', error);
        showMessage('Ошибка при сохранении выбора', 'error');
        isLocked = false;
        cards.forEach(card => {
            card.classList.remove('disabled');
        });
    }
}

/**
 * Обработка "оба нравятся"
 */
async function likeBoth() {
    if (isLocked || !currentPair) return;
    isLocked = true;
    
    const leftEvent = currentPair.left;
    const rightEvent = currentPair.right;
    
    console.log('👍 Оба нравятся:', leftEvent.title, 'и', rightEvent.title);
    
    // Визуальная обратная связь
    const cards = document.querySelectorAll('.event-card');
    cards.forEach(card => {
        card.classList.add('selected');
    });
    
    showLikeBothAnimation();
    
    try {
        const response = await fetch(`${API_BASE}/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                winner_id: null,
                loser_id: null,
                both_liked: true,
                left_event_id: leftEvent.id,
                right_event_id: rightEvent.id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            await updateStats();
            showMessage('Оба события добавлены в понравившиеся! 🎉', 'success');
            
            setTimeout(() => {
                loadComparisonPair();
                isLocked = false;
            }, 500);
        } else {
            throw new Error(data.error || 'Ошибка');
        }
        
    } catch (error) {
        console.error('Ошибка при отправке лайков:', error);
        showMessage('Ошибка при сохранении выбора', 'error');
        isLocked = false;
        cards.forEach(card => {
            card.classList.remove('selected');
        });
    }
}

// ============================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================

/**
 * Настройка горячих клавиш
 */
/**
 * Настройка горячих клавиш
 */
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Проверяем, что currentPair существует и содержит события
        if (!currentPair || !currentPair.left || !currentPair.right) {
            console.log('Клавиша нажата, но currentPair не загружен');
            return;
        }
        
        // Левая стрелка = выбор левого события
        if (e.key === 'ArrowLeft' && !isLocked) {
            e.preventDefault();
            console.log('Выбрано левое событие:', currentPair.left.title);
            const winnerId = currentPair.left.id;
            const loserId = currentPair.right.id;
            makeChoice(winnerId, loserId);
        }
        // Правая стрелка = выбор правого события
        else if (e.key === 'ArrowRight' && !isLocked) {
            e.preventDefault();
            console.log('Выбрано правое событие:', currentPair.right.title);
            const winnerId = currentPair.right.id;
            const loserId = currentPair.left.id;
            makeChoice(winnerId, loserId);
        }
        // Клавиша P = показать профиль
        else if (e.key === 'p' || e.key === 'P') {
            e.preventDefault();
            showUserProfile();
        }
        // Клавиша R = показать рекомендации
        else if (e.key === 'r' || e.key === 'R') {
            e.preventDefault();
            showRecommendations();
        }
        // Клавиша Esc = закрыть модальные окна
        else if (e.key === 'Escape') {
            const modal = document.getElementById('recommendationModal');
            if (modal) modal.remove();
            const profilePanel = document.getElementById('profilePanel');
            if (profilePanel) profilePanel.remove();
        }
    });
    
    console.log('⌨️ Горячие клавиши настроены: ← →, P, R, Esc');
}

/**
 * Инициализация приложения
 */
async function init() {
    sessionId = getSessionId();
    
    await loadStats();
    await loadComparisonPair();

    
    resetBtn.addEventListener('click', resetGame);
    profileBtn.addEventListener('click', showUserProfile);
    likesBtn.addEventListener('click', showLikesPage);
    backToComparisonBtn.addEventListener('click', () => showView('comparison'));
    setupKeyboardShortcuts();
    
    
    console.log('Приложение инициализировано!');
    console.log('💡 Подсказки:');
    console.log('   ← →  - выбор события стрелками');
    console.log('   P    - показать профиль');
    console.log('   R    - показать рекомендации');
}

// Запуск приложения
init();