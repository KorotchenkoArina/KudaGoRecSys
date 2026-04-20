// ============================================
// КОНФИГУРАЦИЯ
// ============================================
const API_BASE = 'http://localhost:5000/api';
let currentEvent = null;
let isLocked = false;
let sessionId = null;
let stats = {
    total: 0,
    likes: 0,
    dislikes: 0,
    remaining: 0
};

// DOM элементы
const cardContainer = document.getElementById('cardContainer');
const likeBtn = document.getElementById('likeBtn');
const dislikeBtn = document.getElementById('dislikeBtn');
const resetBtn = document.getElementById('resetBtn');
const profileBtn = document.getElementById('profileBtn');
const statsTotal = document.getElementById('statsTotal');
const statsLikes = document.getElementById('statsLikes');
const statsRemaining = document.getElementById('statsRemaining');
const emptyState = document.getElementById('emptyState');
const loadingState = document.getElementById('loadingState');

// ============================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatDate(dateString) {
    if (!dateString) return 'Дата не указана';
    return dateString;
}

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

function showAnimation(liked) {
    const animation = document.createElement('div');
    animation.className = liked ? 'like-animation' : 'dislike-animation';
    animation.innerHTML = liked ? '❤️ Лайк!' : '👎 Дизлайк!';
    document.body.appendChild(animation);
    
    setTimeout(() => {
        animation.remove();
    }, 600);
}

// ============================================
// ЗАГРУЗКА ДАННЫХ
// ============================================

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const data = await response.json();
        if (data.success) {
            stats = {
                total: data.total_evaluated,
                likes: data.likes,
                dislikes: data.dislikes,
                remaining: data.remaining
            };
            
            statsTotal.textContent = stats.total;
            statsLikes.textContent = stats.likes;
            statsRemaining.textContent = stats.remaining;
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

async function loadNextEvent() {
    // Показываем загрузку
    loadingState.classList.add('show');
    cardContainer.classList.remove('show');
    emptyState.classList.remove('show');
    
    try {
        const response = await fetch(`${API_BASE}/events/next`);
        const data = await response.json();
        
        loadingState.classList.remove('show');
        
        if (data.success) {
            currentEvent = data.event;
            renderEventCard(data.event);
            cardContainer.classList.add('show');
            
            // Обновляем статистику
            await loadStats();
            
            // Отладочная информация
            console.log('\n' + '='.repeat(60));
            console.log('🎯 НОВОЕ СОБЫТИЕ ДЛЯ ОЦЕНКИ');
            console.log('='.repeat(60));
            console.log(`📌 Название: ${data.event.title}`);
            console.log(`📊 Осталось событий: ${data.remaining_count}`);
            console.log(`✅ Всего оценено: ${data.total_evaluated}`);
            if (data.event._ucb_score) {
                console.log(`📊 UCB score: ${data.event._ucb_score.toFixed(4)}`);
                console.log(`🎯 Expected reward: ${data.event._expected_reward?.toFixed(4) || 'N/A'}`);
                console.log(`🏷️ Тип: ${data.event._recommendation_type || 'unknown'}`);
            }
            console.log('='.repeat(60) + '\n');
            
        } else if (data.need_reset) {
            // События закончились
            cardContainer.classList.remove('show');
            emptyState.classList.add('show');
            showMessage(data.error, 'info');
        } else {
            throw new Error(data.error || 'Ошибка загрузки события');
        }
        
    } catch (error) {
        console.error('Ошибка загрузки события:', error);
        loadingState.classList.remove('show');
        showMessage('Ошибка подключения к серверу', 'error');
    }
}

function renderEventCard(event) {
    const categoriesHtml = event.categories && event.categories.length > 0 
        ? `<div class="event-categories">
            ${event.categories.map(cat => `<span class="category-tag">${escapeHtml(cat)}</span>`).join('')}
           </div>`
        : '';
    
    cardContainer.innerHTML = `
        <div class="event-card">
            <div class="event-image">
                <img src="${event.image}" alt="${escapeHtml(event.title)}" 
                     onerror="this.onerror=null; this.src='https://picsum.photos/400/300?random=${event.id}'">
                ${event._recommendation_type === 'exploration' ? 
                    '<div class="event-badge exploration">🎲 Новое!</div>' : 
                    event._recommendation_type === 'exploitation' ? 
                    '<div class="event-badge exploitation">🎯 Для вас</div>' : ''}
            </div>
            <div class="event-content">
                <h2 class="event-title">${escapeHtml(event.title)}</h2>
                
                <div class="event-details">
                    <div class="detail-item">
                        <span class="detail-icon">📍</span>
                        <span class="detail-text">${escapeHtml(event.place)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">📅</span>
                        <span class="detail-text">${formatDate(event.date)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">💰</span>
                        <span class="detail-text">${escapeHtml(event.price)}</span>
                    </div>
                    ${event.address ? `
                    <div class="detail-item">
                        <span class="detail-icon">🏢</span>
                        <span class="detail-text">${escapeHtml(event.address)}</span>
                    </div>
                    ` : ''}
                </div>
                
                ${categoriesHtml}
                
                <p class="event-description">${escapeHtml(event.description)}</p>
                
                <a href="${event.url}" target="_blank" class="event-link" onclick="event.stopPropagation()">
                    🔗 Подробнее на KudaGo
                </a>
            </div>
        </div>
    `;
}

// ============================================
// ОЦЕНИВАНИЕ
// ============================================

async function rateEvent(liked) {
    if (isLocked || !currentEvent) {
        console.log('⚠️ Оценка заблокирована или нет события');
        return;
    }
    
    isLocked = true;
    
    // Визуальная обратная связь
    showAnimation(liked);
    
    // Блокируем кнопки на время
    likeBtn.disabled = true;
    dislikeBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE}/rate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                event_id: currentEvent.id,
                liked: liked
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Обновляем статистику
            await loadStats();
            
            const message = liked ? 'Отличный выбор!' : 'Учтем ваше мнение!';
            showMessage(message, liked ? 'success' : 'info');
            
            // Загружаем следующее событие
            setTimeout(() => {
                loadNextEvent();
                isLocked = false;
                likeBtn.disabled = false;
                dislikeBtn.disabled = false;
            }, 400);
        } else {
            throw new Error(data.error || 'Ошибка при сохранении оценки');
        }
        
    } catch (error) {
        console.error('Ошибка при отправке оценки:', error);
        showMessage('Ошибка при сохранении оценки', 'error');
        isLocked = false;
        likeBtn.disabled = false;
        dislikeBtn.disabled = false;
    }
}

// ============================================
// ПРОФИЛЬ И СТАТИСТИКА
// ============================================

async function showUserProfile() {
    try {
        const response = await fetch(`${API_BASE}/user/profile`);
        const data = await response.json();
        
        if (!data.success) {
            showMessage('Не удалось загрузить профиль', 'error');
            return;
        }
        
        const preferences = data.preferences || {};
        const sortedPrefs = Object.entries(preferences).sort((a, b) => b[1] - a[1]);
        
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>📊 Ваш профиль</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="profile-stats">
                        <div class="stat-card">
                            <div class="stat-value">${data.total_choices || 0}</div>
                            <div class="stat-label">всего оценено</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.liked_count || 0}</div>
                            <div class="stat-label">лайков</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.disliked_count || 0}</div>
                            <div class="stat-label">дизлайков</div>
                        </div>
                    </div>
                    
                    ${sortedPrefs.length > 0 ? `
                        <div class="preferences-section">
                            <h4>🏆 Ваши любимые категории</h4>
                            <div class="preferences-list">
                                ${sortedPrefs.slice(0, 5).map(([cat, count]) => `
                                    <div class="preference-item">
                                        <span class="preference-name">${escapeHtml(cat)}</span>
                                        <div class="preference-bar">
                                            <div class="preference-bar-fill" style="width: ${Math.min(100, count * 10)}%"></div>
                                        </div>
                                        <span class="preference-count">${count}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : '<p class="no-preferences">Пока нет данных. Оценивайте события!</p>'}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        modal.querySelector('.modal-close').addEventListener('click', () => {
            modal.remove();
        });
        
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
        
    } catch (error) {
        console.error('Ошибка загрузки профиля:', error);
        showMessage('Ошибка загрузки профиля', 'error');
    }
}

// ============================================
// СБРОС
// ============================================

async function resetGame() {
    if (confirm('Сбросить все оценки и начать заново?')) {
        try {
            const response = await fetch(`${API_BASE}/reset`, { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                // Сбрасываем локальное состояние
                currentEvent = null;
                stats = { total: 0, likes: 0, dislikes: 0, remaining: 0 };
                
                // Обновляем UI
                await loadStats();
                await loadNextEvent();
                
                showMessage(data.message, 'success');
            } else {
                throw new Error(data.error || 'Ошибка сброса');
            }
        } catch (error) {
            console.error('Ошибка сброса:', error);
            showMessage('Ошибка при сбросе данных', 'error');
        }
    }
}

// ============================================
// ГОРЯЧИЕ КЛАВИШИ
// ============================================

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Левая стрелка или L = лайк
        if ((e.key === 'ArrowLeft' || e.key === 'l' || e.key === 'L') && !isLocked && currentEvent) {
            e.preventDefault();
            rateEvent(true);
        }
        // Правая стрелка или D = дизлайк
        else if ((e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') && !isLocked && currentEvent) {
            e.preventDefault();
            rateEvent(false);
        }
        // Клавиша P = показать профиль
        else if (e.key === 'p' || e.key === 'P') {
            e.preventDefault();
            showUserProfile();
        }
        // Клавиша Esc = закрыть модальные окна
        else if (e.key === 'Escape') {
            const modal = document.querySelector('.modal');
            if (modal) modal.remove();
        }
    });
    
    console.log('⌨️ Горячие клавиши: ← или L = лайк, → или D = дизлайк, P = профиль');
}

// ============================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================

async function init() {
    // Загружаем статистику
    await loadStats();
    
    // Загружаем первое событие
    await loadNextEvent();
    
    // Настраиваем обработчики
    likeBtn.addEventListener('click', () => rateEvent(true));
    dislikeBtn.addEventListener('click', () => rateEvent(false));
    resetBtn.addEventListener('click', resetGame);
    profileBtn.addEventListener('click', showUserProfile);
    
    // Настраиваем горячие клавиши
    setupKeyboardShortcuts();
    
    console.log('Приложение инициализировано!');
    console.log('💡 Оценивайте события: ❤️ Лайк или 👎 Дизлайк');
}

// Запуск приложения
init();