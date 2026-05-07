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

// DOM элементы для рекоменаций
const cosineBtn = document.getElementById('cosineBtn');
const exploitationBtn = document.getElementById('exploitationBtn');
const cosineArea = document.getElementById('cosineArea');
const exploitationArea = document.getElementById('exploitationArea');
const cosineGrid = document.getElementById('cosineGrid');
const exploitationGrid = document.getElementById('exploitationGrid');
const backFromCosineBtn = document.getElementById('backFromCosineBtn');
const backFromExploitationBtn = document.getElementById('backFromExploitationBtn');

// DOM элементы для лайков
const likesBtn = document.getElementById('likesBtn');
const likesArea = document.getElementById('likesArea');
const likedEventsGrid = document.getElementById('likedEventsGrid');
const backFromLikesBtn = document.getElementById('backFromLikesBtn');

// DOM элементы для фильтров
const showFilterBtnCosine = document.getElementById('showFilterBtnCosine');
const showFilterBtnExploitation = document.getElementById('showFilterBtnExploitation');
const filterModal = document.getElementById('filterModal');
const closeFilterModal = document.getElementById('closeFilterModal');
const applyFiltersBtn = document.getElementById('applyFiltersBtn');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');
const filterDateFrom = document.getElementById('filterDateFrom');
const filterDateTo = document.getElementById('filterDateTo');
const filterTimeFrom = document.getElementById('filterTimeFrom');
const filterTimeTo = document.getElementById('filterTimeTo');

// ============================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИ
// ============================================

// Фильтрация
// Глобальные переменные для фильтров
let currentFilters = {
    date_from: null,
    date_to: null,
    time_from: null,
    time_to: null,
    weekdays: []
};

// Функции фильтрации
function openFilterModal() {
    if (!filterModal) {
        console.error('❌ filterModal не найден в DOM');
        return;
    }
    filterModal.style.display = 'flex';
}

function closeFilterModalFunc() {
    if (!filterModal) {
        console.error('❌ filterModal не найден в DOM');
        return;
    }
    filterModal.style.display = 'none';
}

function getSelectedWeekdays() {
    const checkboxes = document.querySelectorAll('.weekdays input:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

async function applyFilters() {
    currentFilters = {
        date_from: filterDateFrom.value || null,
        date_to: filterDateTo.value || null,
        time_from: filterTimeFrom.value || null,
        time_to: filterTimeTo.value || null,
        weekdays: getSelectedWeekdays()
    };
    
    closeFilterModalFunc();
    updateFilterButtons();
    
    // Обновляем текущую страницу рекомендаций
    if (cosineArea.style.display === 'block') {
        await showCosineRecommendations();
    } else if (exploitationArea.style.display === 'block') {
        await showExploitationRecommendations();
    }
}

async function resetFilters() {
    filterDateFrom.value = '';
    filterDateTo.value = '';
    filterTimeFrom.value = '';
    filterTimeTo.value = '';
    document.querySelectorAll('.weekdays input').forEach(cb => cb.checked = false);
    
    currentFilters = {
        date_from: null,
        date_to: null,
        time_from: null,
        time_to: null,
        weekdays: []
    };
    
    closeFilterModalFunc();
    updateFilterButtons();
    
    if (cosineArea.style.display === 'block') {
        await showCosineRecommendations();
    } else if (exploitationArea.style.display === 'block') {
        await showExploitationRecommendations();
    }
}

/**
 * Обновляет внешний вид кнопок фильтров в зависимости от активных фильтров
 */
function updateFilterButtons() {
    const hasActiveFilters = currentFilters.date_from || currentFilters.date_to || 
                             currentFilters.time_from || currentFilters.time_to || 
                             currentFilters.weekdays.length > 0;
    
    // Обновляем кнопку в косинусных рекомендациях
    if (showFilterBtnCosine) {
        if (hasActiveFilters) {
            showFilterBtnCosine.classList.add('active');
            showFilterBtnCosine.innerHTML = '<span>🔧</span> Фильтры активны';
        } else {
            showFilterBtnCosine.classList.remove('active');
            showFilterBtnCosine.innerHTML = '<span>🔧</span> Настроить фильтры по времени';
        }
    }
    
    // Обновляем кнопку в exploitation рекомендациях
    if (showFilterBtnExploitation) {
        if (hasActiveFilters) {
            showFilterBtnExploitation.classList.add('active');
            showFilterBtnExploitation.innerHTML = '<span>🔧</span> Фильтры активны';
        } else {
            showFilterBtnExploitation.classList.remove('active');
            showFilterBtnExploitation.innerHTML = '<span>🔧</span> Настроить фильтры по времени';
        }
    }
}

function initFilters() {
    console.log('🔧 Инициализация фильтров...');
    
    if (showFilterBtnCosine) {
        showFilterBtnCosine.addEventListener('click', openFilterModal);
        console.log('✅ Обработчик для косинусных фильтров добавлен');
    } else {
        console.warn('⚠️ showFilterBtnCosine не найден');
    }
    
    if (showFilterBtnExploitation) {
        showFilterBtnExploitation.addEventListener('click', openFilterModal);
        console.log('✅ Обработчик для exploitation фильтров добавлен');
    } else {
        console.warn('⚠️ showFilterBtnExploitation не найден');
    }
    
    if (closeFilterModal) {
        closeFilterModal.addEventListener('click', closeFilterModalFunc);
        console.log('✅ Обработчик закрытия добавлен');
    }
    
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', applyFilters);
    }
    
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', resetFilters);
    }
    
    // Закрытие по клику вне окна
    window.addEventListener('click', (e) => {
        if (filterModal && e.target === filterModal) {
            closeFilterModalFunc();
        }
    });
}

function showView(viewName) {
    // Скрываем все
    const cardContainer = document.getElementById('cardContainer');
    const emptyStateDiv = document.getElementById('emptyState');
    const loadingStateDiv = document.getElementById('loadingState');
    const actionButtons = document.querySelector('.action-buttons');
    
    if (cardContainer) cardContainer.style.display = 'none';
    if (emptyStateDiv) emptyStateDiv.style.display = 'none';
    if (loadingStateDiv) loadingStateDiv.style.display = 'none';
    if (cosineArea) cosineArea.style.display = 'none';
    if (exploitationArea) exploitationArea.style.display = 'none';
    if (likesArea) likesArea.style.display = 'none';
    
    if (viewName === 'comparison') {
        if (cardContainer) {
            cardContainer.style.display = 'flex';
            if (currentEvent) cardContainer.classList.add('show');
        }
        if (actionButtons) actionButtons.style.display = 'flex';
        const emptyDiv = document.getElementById('emptyState');
        if (emptyDiv && emptyDiv.classList && emptyDiv.classList.contains('show')) {
            emptyDiv.style.display = 'flex';
        }
    } else if (viewName === 'cosine') {
        if (cosineArea) cosineArea.style.display = 'block';
        if (actionButtons) actionButtons.style.display = 'none';
    } else if (viewName === 'exploitation') {
        if (exploitationArea) exploitationArea.style.display = 'block';
        if (actionButtons) actionButtons.style.display = 'none';
    } else if (viewName === 'likes') {
        if (likesArea) likesArea.style.display = 'block';
        if (actionButtons) actionButtons.style.display = 'none';
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
        const response = await fetch(`${API_BASE}/user/liked-events`);
        const data = await response.json();

        if (data.success && data.liked_events.length > 0) {
            likedEventsGrid.innerHTML = data.liked_events.map(event => `
                <div class="recommendation-card" onclick="window.open('${event.url}', '_blank')">
                    <div class="recommendation-image" style="background-image: url('${event.image}')"></div>
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
                    <p class="empty-state-subtext">Начните оценивать события, чтобы составить свою коллекцию!</p>
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

async function showCosineRecommendations() {
    showView('cosine');
    cosineGrid.innerHTML = `<div class="loading"><div class="spinner"></div><p>Ищем похожее событие...</p></div>`;
    
    // Добавляем фильтры в URL
    let url = `${API_BASE}/recommendations/cosine`;
    const params = new URLSearchParams();
    if (currentFilters.date_from) params.append('date_from', currentFilters.date_from);
    if (currentFilters.date_to) params.append('date_to', currentFilters.date_to);
    if (currentFilters.time_from) params.append('time_from', currentFilters.time_from);
    if (currentFilters.time_to) params.append('time_to', currentFilters.time_to);
    currentFilters.weekdays.forEach(d => params.append('weekdays', d));
    
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success && data.recommendations.length > 0) {
            const rec = data.recommendations[0];
            const similarityPercent = rec._similarity_percent || Math.round(rec._similarity * 100);
            

            cosineGrid.innerHTML = `
                <div class="recommendation-card" onclick="window.open('${rec.url}', '_blank')">
                    <div class="recommendation-image">
                        <img src="${rec.image}" alt="${escapeHtml(rec.title)}" onerror="this.src='https://via.placeholder.com/400x300?text=No+Image'">
                        <div class="similarity-badge">Сходство: ${similarityPercent}%</div>
                    </div>
                    <div class="recommendation-content">
                        <h4>${escapeHtml(rec.title)}</h4>
                        <div class="detail-item">
                            <span class="detail-icon">📍</span>
                            <span>${escapeHtml(rec.place)}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">📅</span>
                            <span>${formatDate(rec.date)}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">💰</span>
                            <span>${escapeHtml(rec.price)}</span>
                        </div>
                        <p class="event-description">${escapeHtml(rec.description)}</p>
                        <a href="${rec.url}" target="_blank" class="event-link">🔗 Подробнее на KudaGo</a>
                    </div>
                </div>
            `;
        } else if (!data.has_enough_likes) {
            cosineGrid.innerHTML = `<div class="empty-state"><p>👍 Поставьте ещё ${3 - data.total_likes} лайка(ов) для персонализации</p></div>`;
        } else {
            cosineGrid.innerHTML = `<div class="empty-state"><p>🔍 Нет событий, похожих на ваши предпочтения</p></div>`;
        }
    } catch (error) {
        console.error(error);
        cosineGrid.innerHTML = `<div class="empty-state"><p>❌ Ошибка загрузки</p></div>`;
    }
}

async function showExploitationRecommendations() {
    showView('exploitation');
    exploitationGrid.innerHTML = `<div class="loading"><div class="spinner"></div><p>Анализируем предпочтения...</p></div>`;
    
    // Добавляем фильтры в URL
    let url = `${API_BASE}/recommendations/exploitation`;
    const params = new URLSearchParams();
    if (currentFilters.date_from) params.append('date_from', currentFilters.date_from);
    if (currentFilters.date_to) params.append('date_to', currentFilters.date_to);
    if (currentFilters.time_from) params.append('time_from', currentFilters.time_from);
    if (currentFilters.time_to) params.append('time_to', currentFilters.time_to);
    currentFilters.weekdays.forEach(d => params.append('weekdays', d));
    
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success && data.recommendations.length > 0) {
            const rec = data.recommendations[0];
            const matchPercent = rec._similarity_percent || 100;
            
            exploitationGrid.innerHTML = `
                <div class="recommendation-card" onclick="window.open('${rec.url}', '_blank')">
                    <div class="recommendation-image">
                        <img src="${rec.image}" alt="${escapeHtml(rec.title)}" onerror="this.src='https://via.placeholder.com/400x300?text=No+Image'">
                        <div class="similarity-badge">Совпадение: ${matchPercent}%</div>
                    </div>
                    <div class="recommendation-content">
                        <h4>${escapeHtml(rec.title)}</h4>
                        <div class="detail-item">
                            <span class="detail-icon">📍</span>
                            <span>${escapeHtml(rec.place)}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">📅</span>
                            <span>${formatDate(rec.date)}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-icon">💰</span>
                            <span>${escapeHtml(rec.price)}</span>
                        </div>
                        <p class="event-description">${escapeHtml(rec.description)}</p>
                        <a href="${rec.url}" target="_blank" class="event-link">🔗 Подробнее на KudaGo</a>
                    </div>
                </div>
            `;
        } else if (!data.has_enough_data) {
            exploitationGrid.innerHTML = `<div class="empty-state"><p>🎯 Нужно больше оценок (${data.total_choices}/5)</p></div>`;
        } else {
            exploitationGrid.innerHTML = `<div class="empty-state"><p>🎯 Нет подходящих событий</p></div>`;
        }
    } catch (error) {
        console.error(error);
        exploitationGrid.innerHTML = `<div class="empty-state"><p>❌ Ошибка загрузки</p></div>`;
    }
}

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

    cosineBtn.addEventListener('click', showCosineRecommendations);
    exploitationBtn.addEventListener('click', showExploitationRecommendations);
    backFromCosineBtn.addEventListener('click', () => showView('comparison'));
    backFromExploitationBtn.addEventListener('click', () => showView('comparison'));

    likesBtn.addEventListener('click', showLikesPage);
    backFromLikesBtn.addEventListener('click', () => showView('comparison'));
    initFilters();
    updateFilterButtons();
}

// Запуск приложения
init();