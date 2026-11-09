/* Логика Telegram Mini App: расписание, листание недели, уведомления. */

const tg = window.Telegram.WebApp;
tg.expand(); // развернуть на весь экран
tg.setHeaderColor('bg_color');
tg.setBackgroundColor('bg_color');

const state = {
    day: 'week',        // today | tomorrow | week
    weekIndex: 0,       // 0=Пн ... 5=Сб
    data: null,         // ответ /api/schedule
    user: null,         // /api/user
};

const WEEKDAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

const $ = (sel) => document.querySelector(sel);

function initData() {
    return tg.initData || '';
}

function fmtDate(d) {
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}`;
}

// --- API ---
async function api(path, opts = {}) {
    const res = await fetch(path, {
        ...opts,
        headers: {
            'Content-Type': 'application/json',
            'X-Init-Data': initData(),
            ...(opts.headers || {}),
        },
    });
    if (res.status === 401) {
        showError('Авторизация не прошла. Переоткрой приложение.');
        throw new Error('unauthorized');
    }
    return res.json();
}

function mondayOf(d) {
    const day = (d.getDay() + 6) % 7; // 0=Пн
    const m = new Date(d);
    m.setDate(d.getDate() - day);
    return m;
}

function addDays(d, n) {
    const r = new Date(d);
    r.setDate(d.getDate() + n);
    return r;
}

// --- загрузка ---
async function loadSchedule() {
    const c = $('#content');
    c.innerHTML = '';
    const loader = document.createElement('div');
    loader.className = 'loader';
    loader.innerHTML = '<div class="spinner"></div><p>Загружаю расписание…</p>';
    c.appendChild(loader);

    try {
        if (state.day === 'week') {
            const monday = mondayOf(new Date());
            const date = fmtDate(addDays(monday, state.weekIndex));
            state.data = await api(`/api/schedule?date=${encodeURIComponent(date)}`);
        } else {
            const offset = state.day === 'tomorrow' ? 1 : 0;
            const date = fmtDate(addDays(new Date(), offset));
            state.data = await api(`/api/schedule?date=${encodeURIComponent(date)}`);
        }
        if (!state.data.ok) {
            if (state.data.error === 'no_group') {
                showError('Сначала выбери группу в боте: /start');
            } else {
                showError(state.data.error || 'Ошибка загрузки');
            }
            return;
        }
        $('#groupLabel').textContent = `Группа: ${state.data.group}`;
        renderSchedule(state.data);
    } catch (e) {
        // unauthorized уже показан
    }
}

function renderSchedule(data) {
    const c = $('#content');
    c.innerHTML = '';

    const title = document.createElement('div');
    title.className = 'week-day-label';
    title.style.marginBottom = '10px';
    title.style.fontSize = '14px';
    title.style.color = 'var(--hint)';
    title.textContent = data.date;
    c.appendChild(title);

    if (!data.lessons.length) {
        c.innerHTML = '<div class="empty"><span class="emoji">🎉</span>Пар нет. Отдыхай!</div>';
        return;
    }

    data.lessons.forEach((lesson) => {
        const card = document.createElement('div');
        card.className = 'lesson';

        const timeParts = (lesson.time || '').split('–');
        const timeHtml = lesson.time
            ? `${lesson.time}`
            : `${lesson.lesson_number} пара`;

        card.innerHTML = `
            <div class="lesson-num">
                <div class="num">${lesson.lesson_number}</div>
                <div class="time">${escapeHtml(timeHtml)}</div>
            </div>
            <div class="lesson-body">
                <div class="lesson-subject">📚 ${escapeHtml(lesson.subject || '')}</div>
                <div class="lesson-meta">
                    ${lesson.room ? `<span>🚪 ${escapeHtml(lesson.room)}</span>` : ''}
                    ${lesson.teacher ? `<span>👤 ${escapeHtml(lesson.teacher)}</span>` : ''}
                </div>
                ${renderSubgroups(lesson.subgroups)}
            </div>
        `;
        c.appendChild(card);
    });
}

function renderSubgroups(subs) {
    if (!Array.isArray(subs) || subs.length < 2) return '';
    return subs
        .map((s, i) => {
            const n = s.number || i + 1;
            const room = s.room ? `ауд. ${escapeHtml(s.room)}` : '';
            const teacher = s.teacher ? escapeHtml(s.teacher) : '';
            const parts = [room, teacher].filter(Boolean).join(' · ');
            return `<div class="subgroup-line"><b>${n} п/г</b>${parts ? ' · ' + parts : ''}</div>`;
        })
        .join('');
}

function showError(msg) {
    $('#content').innerHTML = `<div class="empty"><span class="emoji">⚠️</span>${escapeHtml(msg)}</div>`;
}

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
}

// --- недельная навигация ---
function updateWeekNav() {
    const nav = $('#weekNav');
    const show = state.day === 'week';
    nav.classList.toggle('hidden', !show);
    if (!show) return;

    const monday = mondayOf(new Date());
    const date = addDays(monday, state.weekIndex);
    $('#weekDayLabel').textContent = `${WEEKDAY_NAMES[state.weekIndex]} · ${fmtDate(date)}`;
    $('#prevDay').disabled = state.weekIndex <= 0;
    $('#nextDay').disabled = state.weekIndex >= 5;
}

// --- инициализация ---
async function init() {
    bindEvents();
    updateWeekNav();
    await loadUser();
    await loadSchedule();
}

function bindEvents() {
    $('#refreshBtn').addEventListener('click', () => {
        const btn = $('#refreshBtn');
        btn.classList.add('spinning');
        setTimeout(() => btn.classList.remove('spinning'), 600);
        loadSchedule();
    });

    document.querySelectorAll('.tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
            tab.classList.add('active');
            state.day = tab.dataset.day;
            updateWeekNav();
            loadSchedule();
        });
    });

    $('#prevDay').addEventListener('click', () => {
        if (state.weekIndex > 0) {
            state.weekIndex -= 1;
            updateWeekNav();
            loadSchedule();
        }
    });

    $('#nextDay').addEventListener('click', () => {
        if (state.weekIndex < 5) {
            state.weekIndex += 1;
            updateWeekNav();
            loadSchedule();
        }
    });

    $('#shareBtn').addEventListener('click', () => {
        const url = 'https://t.me/share/url?url=' + encodeURIComponent(location.href) +
            '&text=' + encodeURIComponent('📅 Расписание КГТТ');
        tg.openTelegramLink(url);
    });

    $('#notifyBtn').addEventListener('click', async () => {
        if (!state.user) return;
        const newVal = !state.user.subscribed;
        try {
            await api('/api/subscribe', {
                method: 'POST',
                body: JSON.stringify({ subscribe: newVal }),
            });
            state.user.subscribed = newVal;
            tg.showAlert(newVal
                ? '🔔 Уведомления включены'
                : '🔕 Уведомления выключены');
        } catch (e) {
            tg.showAlert('Не удалось сохранить настройку');
        }
    });
}

async function loadUser() {
    try {
        const res = await api('/api/user');
        if (res.ok) {
            state.user = res;
            $('#notifyBtn').textContent = res.subscribed
                ? '🔔 Уведомления: вкл'
                : '🔕 Уведомления: выкл';
        }
    } catch (e) { /* игнорируем */ }
}

init();
