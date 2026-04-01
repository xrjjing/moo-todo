/*
 * 前端主控脚本总览
 * ----------------
 * 这个文件承担了当前桌面应用几乎全部前端职责：
 * 1. 维护页面运行时状态（任务、分类、当前视图、番茄钟、AI 会话等）
 * 2. 接收 `index.html` 上的点击/输入/弹窗事件
 * 3. 调用 `window.pywebview.api.*` 与 Python 后端通信
 * 4. 把后端返回的数据重新渲染到各个 DOM 容器中
 *
 * 推荐排查顺序：
 * - “页面上某块为什么没数据”：先看对应 `load*()` / `render*()` 函数
 * - “按钮点击后为什么没保存”：看按钮入口函数 -> `pywebview.api.*` -> `api.py`
 * - “显示对了但刷新后丢失”：前端通常没问题，继续追 Python Service / DB 层
 */

// ===== 状态管理 =====
// `state` 是非 AI 功能的前端单例状态树；多数视图和弹窗都从这里读写数据。
const state = {
    // 任务主数据源：列表 / 看板 / 日历 / 四象限这四种主视图都共用它。
    tasks: [],
    // 分类与标签是筛选器、任务表单、侧边栏导航的共享数据源。
    categories: [],
    tags: [],
    // 当前视图与筛选上下文。
    currentView: 'list',
    currentCategory: '',
    currentTag: '',
    // 日历视图当前翻到的月份。
    calendarDate: new Date(),
    // 任务弹窗当前是否处于编辑态；为空表示新建。
    editingTaskId: null,
    // 番茄钟组件运行态。
    pomodoroTaskId: null,
    pomodoroRecordId: null,
    pomodoroRunning: false,
    pomodoroTime: 25 * 60,
    pomodoroInterval: null,
    // 便签状态
    stickyVisible: false,
    stickyMinimized: false,
    stickyOpacity: 1,
    stickyPosition: { x: 30, y: null }, // y=null 表示使用 bottom
    // 键盘导航
    selectedTaskIndex: -1,
    keyboardNavTasks: [],
    // 快捷键配置
    shortcuts: {},
    shortcutLabels: {},
    editingShortcut: null
};

// ===== 工具函数 =====
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeAttr(text) {
    return escapeHtml(text).replace(/`/g, '&#096;');
}

// 根据字符串生成稳定的颜色（用于标签）
function stringToColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash % 360);
    return `hsl(${hue}, 65%, 45%)`;
}

// ===== 日期辅助函数 =====
function getLocalDateStr() {
    const now = new Date();
    const offset = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offset).toISOString().split('T')[0];
}

// ===== 初始化 =====
// 初始化顺序很重要：
// 1. 先等 pywebview API 可用，否则所有后端调用都会报空；
// 2. 再恢复主题/缩放等界面状态；
// 3. 再加载分类、标签、任务，让主工作区有数据；
// 4. 最后初始化拖拽、快捷键、便签等增强交互。
document.addEventListener('DOMContentLoaded', async () => {
    await waitForApi();
    initTheme();
    initZoom();
    initViewSwitcher();
    await loadCategories();
    await loadTags();
    await loadTasks();
    updateStats();
    initDragDrop();
    initKeyboardShortcuts();
    initStickyNotes();
});

/**
 * 等待 pywebview 注入的后端 API 就绪。
 *
 * 调用链：
 * `main.py -> webview.create_window(js_api=Api())`
 *   -> 页面加载
 *   -> `window.pywebview.api`
 *
 * 若页面能打开但所有后端调用都报错，优先检查这里是否一直等不到 API。
 */
async function waitForApi() {
    while (!window.pywebview?.api) {
        await new Promise(r => setTimeout(r, 50));
    }
}

// ===== 主题系统 =====
const THEME_ICONS = {
    'light': '☀️', 'cute': '🐮', 'office': '📊',
    'neon-light': '🌊', 'forest': '🌲', 'sunset': '🌅',
    'dark': '🌙', 'neon': '🌃', 'cyberpunk': '🤖'
};

async function initTheme() {
    let savedTheme = 'cute';
    try {
        savedTheme = await pywebview.api.get_theme();
    } catch (e) {
        savedTheme = localStorage.getItem('theme') || 'cute';
    }
    setTheme(savedTheme, false);

    window.addEventListener('click', (e) => {
        const menu = document.getElementById('themeMenu');
        const btn = document.getElementById('themeToggleBtn');
        if (menu && btn && menu.classList.contains('active')) {
            if (!menu.contains(e.target) && !btn.contains(e.target)) {
                menu.classList.remove('active');
            }
        }
    });
}

function toggleThemeMenu() {
    document.getElementById('themeMenu').classList.toggle('active');
}

function selectTheme(theme) {
    setTheme(theme);
    document.getElementById('themeMenu').classList.remove('active');
}

function setTheme(theme, save = true) {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    updateThemeIcon(theme);
    updateThemeSelector(theme);
    if (save) {
        pywebview.api.save_theme(theme).catch(() => {});
    }
}

function updateThemeIcon(theme) {
    const iconEl = document.getElementById('currentThemeIcon');
    if (iconEl && THEME_ICONS[theme]) {
        iconEl.textContent = THEME_ICONS[theme];
    }
}

function updateThemeSelector(activeTheme) {
    document.querySelectorAll('.theme-item').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.theme === activeTheme);
    });
}

// ===== 缩放系统 =====
async function initZoom() {
    let savedZoom = 100;
    try {
        savedZoom = await pywebview.api.get_zoom();
    } catch (e) {
        savedZoom = parseInt(localStorage.getItem('zoom')) || 100;
    }
    applyZoom(savedZoom);
    localStorage.setItem('zoom', savedZoom);
}

// ===== 视图切换 =====
function initViewSwitcher() {
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            switchView(view);
        });
    });
}

/**
 * 切换当前主视图。
 *
 * 它只做两件事：
 * 1. 更新按钮态和容器显隐；
 * 2. 把真正的内容渲染分发给 `renderCurrentView()`。
 */
function switchView(view) {
    state.currentView = view;

    document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.view-btn[data-view="${view}"]`)?.classList.add('active');

    document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${view}`)?.classList.add('active');

    renderCurrentView();
}

/**
 * 视图分发器。
 *
 * `state.tasks` 是统一输入，不同视图只是展示方式不同：
 * - 列表：按状态分组
 * - 看板：按状态列展示
 * - 日历：按 due_date 映射到日期格子
 * - 四象限：按 quadrant 映射到四宫格
 */
function renderCurrentView() {
    switch (state.currentView) {
        case 'list': renderListView(); break;
        case 'kanban': renderKanbanView(); break;
        case 'calendar': renderCalendarView(); break;
        case 'quadrant': renderQuadrantView(); break;
    }
}

// ===== 数据加载 =====
// 分类加载后要同时刷新：左侧分类导航 + 任务弹窗分类下拉框。
async function loadCategories() {
    state.categories = await pywebview.api.get_categories();
    renderCategoriesList();
    renderCategorySelects();
}

async function loadTags() {
    try {
        state.tags = await pywebview.api.get_all_tags();
        renderTagFilter();
    } catch (e) {
        state.tags = [];
    }
}

// 标签筛选器只承载“过滤入口”，真正的标签数据以任务上的 tags 为准。
function renderTagFilter() {
    const select = document.getElementById('filter-tag');
    if (!select) return;
    select.innerHTML = '<option value="">全部标签</option>' +
        state.tags.map(tag =>
            `<option value="${escapeAttr(tag)}">${escapeHtml(tag)}</option>`
        ).join('');
}

/**
 * 任务总加载入口。
 *
 * 这是最常用的页面主链路之一：
 * 搜索框 / 分类点击 / 筛选器变化 / 保存任务后刷新
 *   -> `loadTasks()`
 *   -> `pywebview.api.get_tasks(...)`
 *   -> Python `Api.get_tasks()` / `TodoService.get_tasks()`
 *   -> 返回后刷新当前视图与顶部统计
 *
 * 如果“页面明明有容器但看起来没数据”，先看这里有没有拿到正确任务集。
 */
async function loadTasks() {
    const status = document.getElementById('filter-status')?.value || '';
    const priority = document.getElementById('filter-priority')?.value || '';
    const category = document.getElementById('filter-category')?.value || '';
    const tag = document.getElementById('filter-tag')?.value || '';
    const search = document.getElementById('search-input')?.value || '';

    state.tasks = await pywebview.api.get_tasks(status, category, priority, '', '', search, tag);
    renderCurrentView();
    updateStats();
    // 刷新标签列表（可能有新标签）
    loadTags();
}

function handleSearch() {
    loadTasks();
}

// 顶部迷你统计是轻量概览，不和总结/专注统计弹窗共用同一套 DOM。
async function updateStats() {
    const todayTasks = await pywebview.api.get_today_tasks();
    const completed = todayTasks.filter(t => t.status === 'completed').length;
    const pomodoroCount = await pywebview.api.get_today_pomodoro_count();

    document.getElementById('stat-today-completed').textContent = completed;
    document.getElementById('stat-today-pomodoro').textContent = pomodoroCount;
}

// ===== 分类渲染 =====
// 左侧分类导航既是展示区，也是“快速切换 filter-category”的操作区。
function renderCategoriesList() {
    const container = document.getElementById('categories-list');
    const taskCounts = {};
    state.tasks.forEach(t => {
        taskCounts[t.category_id] = (taskCounts[t.category_id] || 0) + 1;
    });

    container.innerHTML = `
        <div class="category-item ${!state.currentCategory ? 'active' : ''}"
             onclick="selectCategory('')">
            <div class="category-icon" style="background:#eee">📋</div>
            <span class="category-name">全部</span>
            <span class="category-count">${state.tasks.length}</span>
        </div>
    ` + state.categories.map(c => `
        <div class="category-item ${state.currentCategory === c.id ? 'active' : ''}"
             onclick="selectCategory('${escapeAttr(c.id)}')">
            <div class="category-icon" style="background:${escapeAttr(c.color)}">${escapeHtml(c.icon)}</div>
            <span class="category-name">${escapeHtml(c.name)}</span>
            <span class="category-count">${taskCounts[c.id] || 0}</span>
        </div>
    `).join('');
}

function renderCategorySelects() {
    const options = '<option value="">无分类</option>' +
        state.categories.map(c =>
            `<option value="${escapeAttr(c.id)}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`
        ).join('');

    document.getElementById('task-category').innerHTML = options;
    document.getElementById('filter-category').innerHTML =
        '<option value="">全部分类</option>' +
        state.categories.map(c =>
            `<option value="${escapeAttr(c.id)}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`
        ).join('');
}

function selectCategory(categoryId) {
    state.currentCategory = categoryId;
    document.getElementById('filter-category').value = categoryId;
    loadTasks();
}

// ===== 列表视图 =====
/**
 * 列表视图渲染器。
 *
 * 这是默认主工作区，也是最适合排查任务显示问题的视图：
 * - 先按状态分三组
 * - 没数据时展示空状态
 * - 有数据时委托 `renderTaskCard(task)` 生成卡片
 */
function renderListView() {
    const container = document.getElementById('task-groups');

    const groups = {
        'not_started': { title: '📝 未开始', tasks: [] },
        'in_progress': { title: '🚀 进行中', tasks: [] },
        'completed': { title: '✅ 已完成', tasks: [] }
    };

    state.tasks.forEach(t => {
        if (groups[t.status]) {
            groups[t.status].tasks.push(t);
        }
    });

    if (state.tasks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🐮</div>
                <p>还没有任务哞～</p>
                <button class="btn btn-primary" onclick="showTaskModal()">创建第一个任务</button>
            </div>
        `;
        return;
    }

    container.innerHTML = Object.entries(groups)
        .filter(([_, g]) => g.tasks.length > 0)
        .map(([status, group]) => `
            <div class="task-group">
                <div class="group-header">${group.title} (${group.tasks.length})</div>
                <div class="task-list">
                    ${group.tasks.map(t => renderTaskCard(t)).join('')}
                </div>
            </div>
        `).join('');
}

// 单张任务卡片模板：列表视图里的“最小可操作单元”。
function renderTaskCard(task) {
    const category = state.categories.find(c => c.id === task.category_id);
    const isOverdue = task.due_date && task.due_date < getLocalDateStr() && task.status !== 'completed';
    const tagsHtml = (task.tags || []).filter(t => t && t.trim()).map(tag =>
        `<span class="task-tag" style="background:${stringToColor(tag)}">${escapeHtml(tag)}</span>`
    ).join('');

    // 子任务进度
    const subtasks = task.subtasks || [];
    const subtaskTotal = subtasks.length;
    const subtaskDone = subtasks.filter(s => s.completed).length;
    const subtaskHtml = subtaskTotal > 0
        ? `<span class="task-subtask-progress ${subtaskDone === subtaskTotal ? '' : 'incomplete'}">☑ ${subtaskDone}/${subtaskTotal}</span>`
        : '';

    return `
        <div class="task-card ${task.status === 'completed' ? 'completed' : ''}"
             data-id="${escapeAttr(task.id)}"
             data-priority="${escapeAttr(task.priority)}"
             onclick="showEditTaskModal('${escapeAttr(task.id)}')">
            <div class="task-checkbox" onclick="event.stopPropagation(); toggleTaskStatus('${escapeAttr(task.id)}')">
                ${task.status === 'completed' ? '✓' : ''}
            </div>
            <div class="task-content">
                <div class="task-title">${escapeHtml(task.title)}</div>
                <div class="task-meta">
                    ${category ? `<span style="color:${escapeAttr(category.color)}">${escapeHtml(category.icon)} ${escapeHtml(category.name)}</span>` : ''}
                    ${task.due_date ? `<span class="task-due ${isOverdue ? 'overdue' : ''}">📅 ${task.due_date}</span>` : ''}
                    ${subtaskHtml}
                    ${task.pomodoro_count > 0 ? `<span>🍅 ${task.pomodoro_count}</span>` : ''}
                </div>
                ${tagsHtml ? `<div class="task-tags">${tagsHtml}</div>` : ''}
            </div>
            <div class="task-actions">
                <button class="btn-pomodoro" onclick="event.stopPropagation(); startPomodoro('${escapeAttr(task.id)}')" title="开始番茄钟">🍅</button>
            </div>
        </div>
    `;
}

/**
 * 切换任务完成状态。
 *
 * 这是任务卡片勾选框、键盘快捷键、便签勾选等多个入口复用的状态切换点。
 */
async function toggleTaskStatus(taskId) {
    const task = state.tasks.find(t => t.id === taskId);
    if (!task) return;

    const newStatus = task.status === 'completed' ? 'not_started' : 'completed';
    await pywebview.api.update_task_status(taskId, newStatus);
    await loadTasks();
    showToast(newStatus === 'completed' ? '任务完成哞！' : '任务已恢复');
}

// ===== 看板视图 =====
// 看板视图的核心是“按状态列组织任务”，后续拖拽改状态也依赖这套列结构。
function renderKanbanView() {
    const columns = {
        'not_started': document.getElementById('kanban-not-started'),
        'in_progress': document.getElementById('kanban-in-progress'),
        'completed': document.getElementById('kanban-completed')
    };

    const counts = { 'not_started': 0, 'in_progress': 0, 'completed': 0 };

    Object.values(columns).forEach(col => col.innerHTML = '');

    state.tasks.forEach(task => {
        if (columns[task.status]) {
            columns[task.status].innerHTML += renderKanbanTask(task);
            counts[task.status]++;
        }
    });

    document.getElementById('count-not-started').textContent = counts['not_started'];
    document.getElementById('count-in-progress').textContent = counts['in_progress'];
    document.getElementById('count-completed').textContent = counts['completed'];
}

// 看板卡片比列表卡片轻，主要承载拖拽与快速打开编辑弹窗。
function renderKanbanTask(task) {
    return `
        <div class="kanban-task"
             data-id="${escapeAttr(task.id)}"
             data-priority="${escapeAttr(task.priority)}"
             draggable="true"
             onclick="showEditTaskModal('${escapeAttr(task.id)}')">
            <div class="task-title">${escapeHtml(task.title)}</div>
            ${task.due_date ? `<div class="task-meta"><span class="task-due">📅 ${task.due_date}</span></div>` : ''}
        </div>
    `;
}

// ===== 日历视图 =====
/**
 * 日历视图渲染器。
 *
 * 核心输入：
 * - `state.calendarDate`：当前查看月份
 * - `state.tasks`：当前任务集合
 *
 * 核心输出：
 * - `calendar-grid` 中的日期格子
 * - 每个格子上的任务点提示
 */
function renderCalendarView() {
    const year = state.calendarDate.getFullYear();
    const month = state.calendarDate.getMonth();

    document.getElementById('calendar-title').textContent = `${year}年${month + 1}月`;

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDay = firstDay.getDay();
    const daysInMonth = lastDay.getDate();

    const today = getLocalDateStr();

    // 获取本月任务
    const startDate = `${year}-${String(month + 1).padStart(2, '0')}-01`;
    const endDate = `${year}-${String(month + 1).padStart(2, '0')}-${daysInMonth}`;
    const tasksByDate = {};
    state.tasks.forEach(t => {
        if (t.due_date && t.due_date >= startDate && t.due_date <= endDate) {
            if (!tasksByDate[t.due_date]) tasksByDate[t.due_date] = [];
            tasksByDate[t.due_date].push(t);
        }
    });

    const days = ['日', '一', '二', '三', '四', '五', '六'];
    let html = days.map(d => `<div class="calendar-day-header">${d}</div>`).join('');

    // 上月填充
    const prevMonthDays = new Date(year, month, 0).getDate();
    for (let i = startDay - 1; i >= 0; i--) {
        html += `<div class="calendar-day other-month"><div class="day-number">${prevMonthDays - i}</div></div>`;
    }

    // 本月
    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const isToday = dateStr === today;
        const dayTasks = tasksByDate[dateStr] || [];

        html += `
            <div class="calendar-day ${isToday ? 'today' : ''}"
                 onclick="showDayTasks('${dateStr}')">
                <div class="day-number">${day}</div>
                <div class="task-dots">
                    ${dayTasks.slice(0, 4).map(t => `<div class="task-dot ${t.priority}"></div>`).join('')}
                </div>
            </div>
        `;
    }

    // 下月填充
    const remaining = 42 - (startDay + daysInMonth);
    for (let i = 1; i <= remaining; i++) {
        html += `<div class="calendar-day other-month"><div class="day-number">${i}</div></div>`;
    }

    document.getElementById('calendar-grid').innerHTML = html;
}

function prevMonth() {
    state.calendarDate.setMonth(state.calendarDate.getMonth() - 1);
    renderCalendarView();
}

function nextMonth() {
    state.calendarDate.setMonth(state.calendarDate.getMonth() + 1);
    renderCalendarView();
}

// 点击某一天后，当前实现会先切回列表，再重新拉一遍任务数据。
// 若未来要做“日历点击后真正按日期筛选”，这里是优先改造入口。
function showDayTasks(dateStr) {
    // 简化：筛选该日期任务
    document.getElementById('filter-status').value = '';
    state.tasks = state.tasks.filter(t => t.due_date === dateStr);
    switchView('list');
    loadTasks(); // 重新加载以显示筛选结果
}

// ===== 四象限视图 =====
// 四象限不是独立数据源，而是对已有任务按 `quadrant` 字段再分桶展示。
function renderQuadrantView() {
    const quadrants = {
        'q1': document.getElementById('quadrant-q1'),
        'q2': document.getElementById('quadrant-q2'),
        'q3': document.getElementById('quadrant-q3'),
        'q4': document.getElementById('quadrant-q4')
    };

    Object.values(quadrants).forEach(q => q.innerHTML = '');

    state.tasks.forEach(task => {
        if (task.quadrant && quadrants[task.quadrant]) {
            quadrants[task.quadrant].innerHTML += `
                <div class="quadrant-task"
                     onclick="showEditTaskModal('${escapeAttr(task.id)}')">
                    ${escapeHtml(task.title)}
                </div>
            `;
        }
    });

    // 显示未分配的任务提示
    const unassigned = state.tasks.filter(t => !t.quadrant).length;
    if (unassigned > 0) {
        showToast(`有 ${unassigned} 个任务未分配象限`, true);
    }
}

// ===== 拖拽功能 =====
/**
 * 看板拖拽初始化。
 *
 * 当前只支持“把任务拖到另一列以切换状态”，不负责精细排序。
 * 如果拖拽时视觉反馈正常但状态没改，优先看 drop 回调里的 `update_task_status()`。
 */
function initDragDrop() {
    document.addEventListener('dragstart', (e) => {
        if (e.target.classList.contains('kanban-task')) {
            e.target.classList.add('dragging');
            e.dataTransfer.setData('text/plain', e.target.dataset.id);
        }
    });

    document.addEventListener('dragend', (e) => {
        if (e.target.classList.contains('kanban-task')) {
            e.target.classList.remove('dragging');
        }
    });

    document.querySelectorAll('.column-tasks').forEach(column => {
        column.addEventListener('dragover', (e) => {
            e.preventDefault();
            column.classList.add('drag-over');
        });

        column.addEventListener('dragleave', () => {
            column.classList.remove('drag-over');
        });

        column.addEventListener('drop', async (e) => {
            e.preventDefault();
            column.classList.remove('drag-over');

            const taskId = e.dataTransfer.getData('text/plain');
            const newStatus = column.parentElement.dataset.status;

            await pywebview.api.update_task_status(taskId, newStatus);
            await loadTasks();
            showToast('任务状态已更新哞！');
        });
    });
}

// ===== 任务弹窗 =====
// 新建模式：清空表单、隐藏删除按钮和子任务区。
function showTaskModal() {
    state.editingTaskId = null;
    document.getElementById('task-modal-title').textContent = '新建任务';
    document.getElementById('task-id').value = '';
    document.getElementById('task-title').value = '';
    document.getElementById('task-description').value = '';
    document.getElementById('task-priority').value = 'medium';
    document.getElementById('task-due-date').value = '';
    document.getElementById('task-category').value = '';
    document.getElementById('task-quadrant').value = '';
    document.getElementById('task-tags').value = '';
    document.getElementById('btn-delete-task').style.display = 'none';
    // 新建任务时隐藏子任务区域
    document.getElementById('subtask-section').style.display = 'none';
    document.getElementById('subtask-list').innerHTML = '';
    document.getElementById('subtask-progress').innerHTML = '';
    openModal('task-modal');
    document.getElementById('task-title').focus();
}

/**
 * 编辑模式：把任务对象回填到弹窗。
 *
 * 这个函数是“任务卡片 -> 编辑表单”的桥。
 * 若用户说“点开任务后表单内容不对”，优先查这里的回填逻辑。
 */
function showEditTaskModal(taskId) {
    const task = state.tasks.find(t => t.id === taskId);
    if (!task) return;

    state.editingTaskId = taskId;
    document.getElementById('task-modal-title').textContent = '编辑任务';
    document.getElementById('task-id').value = task.id;
    document.getElementById('task-title').value = task.title;
    document.getElementById('task-description').value = task.description || '';
    document.getElementById('task-priority').value = task.priority;
    document.getElementById('task-due-date').value = task.due_date || '';
    document.getElementById('task-category').value = task.category_id || '';
    document.getElementById('task-quadrant').value = task.quadrant || '';
    // 标签：数组转逗号分隔字符串
    document.getElementById('task-tags').value = (task.tags || []).filter(t => t).join(', ');
    document.getElementById('btn-delete-task').style.display = 'block';
    // 显示子任务区域并渲染子任务
    document.getElementById('subtask-section').style.display = 'block';
    initSubtaskEvents();  // 初始化事件委托
    renderSubtasks(task);
    openModal('task-modal');
}

/**
 * 保存任务。
 *
 * 分两条支线：
 * - `state.editingTaskId` 有值：走更新
 * - 否则：走新增
 *
 * 保存成功后统一关闭弹窗并刷新 `state.tasks`。
 */
async function saveTask() {
    const title = document.getElementById('task-title').value.trim();
    const description = document.getElementById('task-description').value.trim();
    const priority = document.getElementById('task-priority').value;
    const dueDate = document.getElementById('task-due-date').value;
    const categoryId = document.getElementById('task-category').value;
    const quadrant = document.getElementById('task-quadrant').value;
    // 标签：逗号分隔字符串转数组
    const tagsInput = document.getElementById('task-tags').value;
    const tags = tagsInput.split(',').map(t => t.trim()).filter(t => t);

    if (!title) {
        showToast('请输入任务标题哞～', true);
        return;
    }

    try {
        if (state.editingTaskId) {
            await pywebview.api.update_task(state.editingTaskId, {
                title, description, priority, due_date: dueDate,
                category_id: categoryId, quadrant, tags
            });
            showToast('任务已更新哞！');
        } else {
            await pywebview.api.add_task(title, description, priority, categoryId, dueDate, tags, quadrant);
            showToast('任务创建成功哞！');
        }

        closeModal('task-modal');
        await loadTasks();
    } catch (e) {
        showToast('保存失败：' + e, true);
    }
}

// 真正删除动作仍走后端；前端这里只做确认与刷新。
async function deleteCurrentTask() {
    if (!state.editingTaskId) return;
    if (!confirm('确定要删除这个任务吗？')) return;

    await pywebview.api.delete_task(state.editingTaskId);
    closeModal('task-modal');
    await loadTasks();
    showToast('任务已删除');
}

// ===== 子任务功能 =====
// 子任务区只在编辑任务时出现；它是任务弹窗里的局部动态渲染区。
function renderSubtasks(task) {
    const listContainer = document.getElementById('subtask-list');
    const progressContainer = document.getElementById('subtask-progress');
    const subtasks = task.subtasks || [];

    if (subtasks.length === 0) {
        listContainer.innerHTML = '<div class="subtask-empty" style="text-align:center;color:var(--text-light);padding:12px;font-size:0.85rem;">暂无子任务</div>';
        progressContainer.innerHTML = '';
        return;
    }

    // 使用 data 属性存储 ID，避免内联 JS 拼接安全问题
    listContainer.innerHTML = subtasks.map(sub => `
        <div class="subtask-item ${sub.completed ? 'completed' : ''}" data-sub-id="${escapeAttr(sub.id)}" data-task-id="${escapeAttr(task.id)}">
            <div class="subtask-checkbox" data-action="toggle">${sub.completed ? '✓' : ''}</div>
            <span class="subtask-title">${escapeHtml(sub.title)}</span>
            <button class="subtask-delete" data-action="delete" title="删除" aria-label="删除子任务">×</button>
        </div>
    `).join('');

    // 渲染进度条
    const completed = subtasks.filter(s => s.completed).length;
    const total = subtasks.length;
    const percent = Math.round((completed / total) * 100);
    progressContainer.innerHTML = `
        <div class="subtask-progress-bar">
            <div class="subtask-progress-fill" style="width:${percent}%"></div>
        </div>
        <span>${completed}/${total} 完成</span>
    `;
}

// 子任务事件委托（安全方式）
function initSubtaskEvents() {
    const listContainer = document.getElementById('subtask-list');
    if (listContainer._subtaskEventsInit) return;
    listContainer._subtaskEventsInit = true;

    listContainer.addEventListener('click', async (e) => {
        const item = e.target.closest('.subtask-item');
        if (!item) return;

        const { taskId, subId } = item.dataset;
        const action = e.target.closest('[data-action]')?.dataset.action;

        if (action === 'toggle') {
            await toggleSubtask(taskId, subId);
        } else if (action === 'delete') {
            await deleteSubtask(taskId, subId);
        }
    });
}

// 子任务新增入口只服务当前正在编辑的任务。
async function addSubtask() {
    if (!state.editingTaskId) return;

    const input = document.getElementById('subtask-input');
    const title = input.value.trim();
    if (!title) {
        showToast('请输入子任务内容哞～', true);
        return;
    }

    try {
        await pywebview.api.add_subtask(state.editingTaskId, title);
        input.value = '';
        // 重新加载任务数据并刷新显示
        await loadTasks();
        const task = state.tasks.find(t => t.id === state.editingTaskId);
        if (task) renderSubtasks(task);
        showToast('子任务已添加');
    } catch (e) {
        showToast('添加失败：' + e, true);
    }
}

// 子任务的勾选与删除都采用“调用后端 -> 重载当前任务 -> 重绘局部子任务区”的模式。
async function toggleSubtask(taskId, subtaskId) {
    try {
        await pywebview.api.toggle_subtask(taskId, subtaskId);
        await loadTasks();
        const task = state.tasks.find(t => t.id === taskId);
        if (task) renderSubtasks(task);
    } catch (e) {
        showToast('操作失败', true);
    }
}

async function deleteSubtask(taskId, subtaskId) {
    try {
        await pywebview.api.delete_subtask(taskId, subtaskId);
        await loadTasks();
        const task = state.tasks.find(t => t.id === taskId);
        if (task) renderSubtasks(task);
        showToast('子任务已删除');
    } catch (e) {
        showToast('删除失败', true);
    }
}

// ===== 分类弹窗 =====
// 分类弹窗的数据非常轻：只有名称、图标、颜色三类字段。
const EMOJI_OPTIONS = ['💼', '📚', '🏠', '🎮', '🏃', '🛒', '💡', '🎯', '📌', '⭐'];
const COLOR_OPTIONS = ['#FFB347', '#87CEEB', '#B5EAD7', '#C7CEEA', '#E0BBE4', '#FFD93D', '#F59E0B', '#3B82F6', '#10B981', '#6B7280'];

let selectedCategoryEmoji = EMOJI_OPTIONS[0];
let selectedCategoryColor = COLOR_OPTIONS[0];

// 打开时同时初始化表情面板和颜色面板，避免页面常驻大量静态选项 DOM。
function showCategoryModal() {
    document.getElementById('category-name').value = '';
    selectedCategoryEmoji = EMOJI_OPTIONS[0];
    selectedCategoryColor = COLOR_OPTIONS[0];

    document.getElementById('category-emoji-picker').innerHTML = EMOJI_OPTIONS.map(e =>
        `<span class="emoji-item ${e === selectedCategoryEmoji ? 'selected' : ''}"
               data-emoji="${e}" onclick="selectCategoryEmoji('${e}')">${e}</span>`
    ).join('');

    document.getElementById('category-color-picker').innerHTML = COLOR_OPTIONS.map(c =>
        `<span class="color-item ${c === selectedCategoryColor ? 'selected' : ''}"
               style="background:${c}" data-color="${c}" onclick="selectCategoryColor('${c}')"></span>`
    ).join('');

    openModal('category-modal');
}

// 图标/颜色选择都只改前端临时状态，真正保存仍在 `saveCategory()`。
function selectCategoryEmoji(emoji) {
    selectedCategoryEmoji = emoji;
    document.querySelectorAll('#category-emoji-picker .emoji-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.emoji === emoji);
    });
}

function selectCategoryColor(color) {
    selectedCategoryColor = color;
    document.querySelectorAll('#category-color-picker .color-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.color === color);
    });
}

// 分类保存成功后只需刷新分类相关 UI，不必整页重载。
async function saveCategory() {
    const name = document.getElementById('category-name').value.trim();
    if (!name) {
        showToast('请输入分类名称哞～', true);
        return;
    }

    await pywebview.api.add_category(name, selectedCategoryEmoji, selectedCategoryColor);
    closeModal('category-modal');
    await loadCategories();
    showToast('分类创建成功哞！');
}

// ===== 番茄钟 =====
/**
 * 打开番茄钟悬浮窗并创建一条后端专注记录。
 *
 * 前端职责：
 * - 记录当前任务 id
 * - 打开悬浮窗
 * - 启动/暂停/重置本地倒计时
 *
 * 后端职责：
 * - 先创建一条未完成的 pomodoro 记录
 * - 完成时再把记录更新为 completed
 */
async function startPomodoro(taskId) {
    const task = state.tasks.find(t => t.id === taskId);
    if (!task) return;

    // 清除可能正在运行的旧定时器
    if (state.pomodoroInterval) clearInterval(state.pomodoroInterval);
    state.pomodoroTaskId = taskId;
    state.pomodoroTime = 25 * 60;
    state.pomodoroRunning = false;

    document.getElementById('pomodoro-task-title').textContent = task.title;
    updatePomodoroDisplay();
    document.getElementById('pomodoro-widget').classList.remove('hidden');

    // 保存番茄钟记录 ID 以便完成时调用
    const record = await pywebview.api.start_pomodoro(taskId, 25);
    state.pomodoroRecordId = record?.id || null;
}

// 这里只控制前端计时器的暂停/继续；真正“完成一次番茄”仍以 `completePomodoro()` 为准。
function togglePomodoro() {
    if (state.pomodoroRunning) {
        clearInterval(state.pomodoroInterval);
        state.pomodoroRunning = false;
        document.getElementById('btn-pomodoro-toggle').textContent = '继续';
    } else {
        state.pomodoroRunning = true;
        document.getElementById('btn-pomodoro-toggle').textContent = '暂停';
        state.pomodoroInterval = setInterval(() => {
            state.pomodoroTime--;
            updatePomodoroDisplay();

            if (state.pomodoroTime <= 0) {
                completePomodoro();
            }
        }, 1000);
    }
}

// 重置只重置当前悬浮窗倒计时，不会删除已创建的后端记录。
function resetPomodoro() {
    clearInterval(state.pomodoroInterval);
    state.pomodoroTime = 25 * 60;
    state.pomodoroRunning = false;
    document.getElementById('btn-pomodoro-toggle').textContent = '开始';
    updatePomodoroDisplay();
}

/**
 * 完成一次番茄钟。
 *
 * 这里是“番茄钟 -> 任务统计 / 成就”的关键汇合点：
 * - 完成后端 pomodoro 记录
 * - 刷新任务列表和顶部统计
 * - 触发成就检查
 */
async function completePomodoro() {
    clearInterval(state.pomodoroInterval);
    state.pomodoroRunning = false;

    // 调用后端 API 完成番茄钟记录
    if (state.pomodoroRecordId) {
        try {
            await pywebview.api.complete_pomodoro(state.pomodoroRecordId);
        } catch (e) {
            console.error('完成番茄钟失败:', e);
        }
        state.pomodoroRecordId = null;
    }

    showToast('🍅 番茄钟完成！休息一下吧哞～');
    closePomodoroWidget();
    await loadTasks();
    await updateStats();
    await checkAndShowAchievements();
}

// 关闭悬浮窗时只处理本地 UI 状态。
function closePomodoroWidget() {
    clearInterval(state.pomodoroInterval);
    document.getElementById('pomodoro-widget').classList.add('hidden');
    state.pomodoroRunning = false;
}

// 倒计时文本和进度环都从同一个 `state.pomodoroTime` 推导，避免双源状态。
function updatePomodoroDisplay() {
    const minutes = Math.floor(state.pomodoroTime / 60);
    const seconds = state.pomodoroTime % 60;
    document.getElementById('pomodoro-time').textContent =
        `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

    // 更新进度环
    const progress = document.getElementById('pomodoro-progress');
    const total = 25 * 60;
    const offset = 283 * (1 - state.pomodoroTime / total);
    progress.style.strokeDashoffset = offset;
}

// ===== 键盘快捷键 =====
// 先从后端读取用户自定义配置，再统一把监听器挂到 document 上。
async function initKeyboardShortcuts() {
    try {
        const data = await pywebview.api.get_shortcuts();
        state.shortcuts = data.shortcuts || {};
        state.shortcutLabels = data.labels || {};
    } catch (e) {
        console.error('加载快捷键配置失败:', e);
    }

    document.addEventListener('keydown', handleKeyboardShortcut);
}

// 快捷键在输入框、弹窗激活时会适当让位，避免误触影响表单输入。
function handleKeyboardShortcut(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }

    if (document.querySelector('.modal.show')) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
        }
        return;
    }

    const action = matchShortcut(e);
    if (!action) return;

    e.preventDefault();
    executeShortcutAction(action);
}

// 这里做的是“按键组合 -> 动作名”的匹配，不直接执行业务逻辑。
function matchShortcut(e) {
    const pressedCtrl = e.ctrlKey || e.metaKey;
    const pressedAlt = e.altKey;
    const pressedShift = e.shiftKey;
    const pressedKey = e.key;

    for (const [action, shortcut] of Object.entries(state.shortcuts)) {
        if (!shortcut || !shortcut.key) continue;
        const matchCtrl = shortcut.ctrl === pressedCtrl;
        const matchAlt = shortcut.alt === pressedAlt;
        const matchShift = shortcut.shift === pressedShift;
        const matchKey = shortcut.key.toLowerCase() === pressedKey.toLowerCase();

        if (matchCtrl && matchAlt && matchShift && matchKey) {
            return action;
        }
    }
    return null;
}

// 动作分发表：把配置层的 action 名字映射到真正的函数入口。
function executeShortcutAction(action) {
    const actions = {
        newTask: () => showTaskModal(),
        editTask: () => editSelectedTask(),
        startPomodoro: () => startPomodoroForSelected(),
        toggleSticky: () => toggleStickyNotes(),
        viewList: () => switchView('list'),
        viewKanban: () => switchView('kanban'),
        viewCalendar: () => switchView('calendar'),
        viewQuadrant: () => switchView('quadrant'),
        focusSearch: () => document.getElementById('search-input').focus(),
        toggleTaskStatus: () => toggleSelectedTaskStatus(),
        navigateUp: () => navigateTask(-1),
        navigateDown: () => navigateTask(1)
    };

    if (actions[action]) {
        actions[action]();
    }
}

// 键盘导航：当前只对列表视图和看板视图有效。
function navigateTask(direction) {
    updateKeyboardNavTasks();
    if (state.keyboardNavTasks.length === 0) return;

    state.selectedTaskIndex += direction;
    if (state.selectedTaskIndex < 0) state.selectedTaskIndex = state.keyboardNavTasks.length - 1;
    if (state.selectedTaskIndex >= state.keyboardNavTasks.length) state.selectedTaskIndex = 0;

    highlightSelectedTask();
}

function updateKeyboardNavTasks() {
    if (state.currentView === 'list') {
        state.keyboardNavTasks = Array.from(document.querySelectorAll('.task-card'));
    } else if (state.currentView === 'kanban') {
        state.keyboardNavTasks = Array.from(document.querySelectorAll('.kanban-task'));
    } else {
        state.keyboardNavTasks = [];
    }
}

function highlightSelectedTask() {
    document.querySelectorAll('.keyboard-selected').forEach(el => el.classList.remove('keyboard-selected'));
    if (state.selectedTaskIndex >= 0 && state.selectedTaskIndex < state.keyboardNavTasks.length) {
        const el = state.keyboardNavTasks[state.selectedTaskIndex];
        el.classList.add('keyboard-selected');
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function getSelectedTaskId() {
    if (state.selectedTaskIndex < 0 || state.selectedTaskIndex >= state.keyboardNavTasks.length) return null;
    return state.keyboardNavTasks[state.selectedTaskIndex]?.dataset?.id;
}

function clearTaskSelection() {
    state.selectedTaskIndex = -1;
    document.querySelectorAll('.keyboard-selected').forEach(el => el.classList.remove('keyboard-selected'));
}

function editSelectedTask() {
    const taskId = getSelectedTaskId();
    if (taskId) {
        showEditTaskModal(taskId);
    }
}

function startPomodoroForSelected() {
    const taskId = getSelectedTaskId();
    if (taskId) {
        startPomodoro(taskId);
    }
}

async function toggleSelectedTaskStatus() {
    const taskId = getSelectedTaskId();
    if (taskId) {
        await toggleTaskStatus(taskId);
        updateKeyboardNavTasks();
        highlightSelectedTask();
    }
}

// ===== 便签悬浮窗 =====
/**
 * 便签悬浮窗初始化。
 *
 * 负责三类事情：
 * 1. 恢复持久化的显示状态与位置；
 * 2. 建立拖拽逻辑；
 * 3. 在拖拽结束后把位置写回后端设置。
 */
function initStickyNotes() {
    const sticky = document.getElementById('sticky-notes');
    const handle = document.getElementById('sticky-drag-handle');

    // 加载保存的便签设置
    loadStickySettings();

    let isDragging = false;
    let startX, startY, startLeft, startBottom;

    handle.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('sticky-btn')) return;
        isDragging = true;
        sticky.classList.add('dragging');

        const rect = sticky.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        startLeft = rect.left;
        startBottom = window.innerHeight - rect.bottom;

        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        let newLeft = startLeft + dx;
        let newBottom = startBottom - dy;

        // 边界限制
        newLeft = Math.max(0, Math.min(newLeft, window.innerWidth - sticky.offsetWidth));
        newBottom = Math.max(0, Math.min(newBottom, window.innerHeight - sticky.offsetHeight));

        sticky.style.left = newLeft + 'px';
        sticky.style.bottom = newBottom + 'px';
        sticky.style.right = 'auto';
        sticky.style.top = 'auto';

        state.stickyPosition = { x: newLeft, y: newBottom };
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            sticky.classList.remove('dragging');
            saveStickySettings();
        }
    });
}

// 便签设置和普通设置共用 `update_settings()`，但这里只更新便签相关字段。
async function loadStickySettings() {
    try {
        const settings = await pywebview.api.get_settings();
        state.stickyVisible = settings.sticky_visible || false;
        state.stickyOpacity = settings.sticky_opacity || 1;
        state.stickyPosition = {
            x: settings.sticky_position_x || 30,
            y: settings.sticky_position_y || 30
        };

        const sticky = document.getElementById('sticky-notes');
        if (state.stickyVisible) {
            sticky.classList.remove('hidden');
            sticky.style.opacity = state.stickyOpacity;
            sticky.style.left = state.stickyPosition.x + 'px';
            sticky.style.bottom = state.stickyPosition.y + 'px';
            renderStickyTasks();
        }
    } catch (e) {
        // 默认值已在 state 中设置
    }
}

// 位置、透明度、显隐都会在这里回写，避免下次启动丢失便签状态。
async function saveStickySettings() {
    try {
        await pywebview.api.update_settings({
            sticky_visible: state.stickyVisible,
            sticky_opacity: state.stickyOpacity,
            sticky_position_x: Math.round(state.stickyPosition.x),
            sticky_position_y: Math.round(state.stickyPosition.y)
        });
    } catch (e) {
        // 忽略保存错误
    }
}

// 打开便签时会即时重绘“今日任务”列表，保证它不是旧缓存。
function toggleStickyNotes() {
    const sticky = document.getElementById('sticky-notes');
    state.stickyVisible = !state.stickyVisible;

    if (state.stickyVisible) {
        sticky.classList.remove('hidden');
        sticky.style.opacity = state.stickyOpacity;
        renderStickyTasks();
    } else {
        sticky.classList.add('hidden');
    }
    saveStickySettings();
}

function closeStickyNotes() {
    state.stickyVisible = false;
    document.getElementById('sticky-notes').classList.add('hidden');
    saveStickySettings();
}

function toggleStickyMinimize() {
    const sticky = document.getElementById('sticky-notes');
    state.stickyMinimized = !state.stickyMinimized;
    sticky.classList.toggle('minimized', state.stickyMinimized);
}

function adjustStickyOpacity(delta) {
    state.stickyOpacity = Math.max(0.3, Math.min(1, state.stickyOpacity + delta));
    document.getElementById('sticky-notes').style.opacity = state.stickyOpacity;
}

/**
 * 渲染便签里的今日任务。
 *
 * 优先走后端 `get_today_tasks()`，保证口径与顶部统计一致；
 * 如果后端调用失败，再退回前端基于 `state.tasks` 的简化过滤逻辑。
 */
async function renderStickyTasks() {
    const container = document.getElementById('sticky-tasks');
    let todayTasks = [];

    try {
        todayTasks = await pywebview.api.get_today_tasks();
    } catch (e) {
        todayTasks = state.tasks.filter(t => {
            const today = getLocalDateStr();
            return t.due_date === today || t.status === 'in_progress';
        });
    }

    if (todayTasks.length === 0) {
        container.innerHTML = `
            <div class="sticky-empty">
                <div class="sticky-empty-icon">🐄</div>
                <div>今天没有任务哞～</div>
            </div>
        `;
        document.getElementById('sticky-stat-done').textContent = '0';
        document.getElementById('sticky-stat-total').textContent = '0';
        return;
    }

    const completed = todayTasks.filter(t => t.status === 'completed').length;
    document.getElementById('sticky-stat-done').textContent = completed;
    document.getElementById('sticky-stat-total').textContent = todayTasks.length;

    container.innerHTML = todayTasks.map(task => `
        <div class="sticky-task ${task.status === 'completed' ? 'completed' : ''}"
             data-id="${escapeAttr(task.id)}"
             data-priority="${escapeAttr(task.priority)}"
             onclick="toggleTaskFromSticky('${escapeAttr(task.id)}')">
            <div class="sticky-task-checkbox">${task.status === 'completed' ? '✓' : ''}</div>
            <span class="sticky-task-title">${escapeHtml(task.title)}</span>
        </div>
    `).join('');
}

async function toggleTaskFromSticky(taskId) {
    await toggleTaskStatus(taskId);
    renderStickyTasks();
}

// ===== 工作总结 =====
let currentSummaryPeriod = 'day';

// 打开总结弹窗时默认进入“日报”页签，再由页签切换逻辑触发真实加载。
function showSummaryModal() {
    openModal('summary-modal');
    switchSummaryTab('day');
}

// 页签切换只是更新选中状态，真正的数据装配交给 `loadSummaryData()`。
function switchSummaryTab(period) {
    currentSummaryPeriod = period;
    document.querySelectorAll('.summary-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.period === period);
    });
    loadSummaryData(period);
}

/**
 * 工作总结核心加载函数。
 *
 * 它会同时请求：
 * - 汇总统计：`get_stats(start, end)`
 * - 时间范围内任务：`get_tasks_by_date_range(start, end)`
 *
 * 然后分别回填：
 * - 指标卡片
 * - 任务明细列表
 * - 文本总结区
 */
async function loadSummaryData(period) {
    const { startDate, endDate, periodName } = getDateRange(period);

    try {
        const stats = await pywebview.api.get_stats(startDate, endDate);
        const tasks = await pywebview.api.get_tasks_by_date_range(startDate, endDate);

        // 更新统计卡片
        document.getElementById('summary-completed').textContent = stats.completed_tasks || 0;
        document.getElementById('summary-pomodoros').textContent = stats.pomodoro_count || 0;
        document.getElementById('summary-hours').textContent = stats.pomodoro_hours || 0;

        const total = stats.total_tasks || 0;
        const completed = stats.completed_tasks || 0;
        const rate = total > 0 ? Math.round(completed / total * 100) : 0;
        document.getElementById('summary-rate').textContent = rate + '%';

        // 渲染任务列表
        renderSummaryTasks(tasks);

        // 生成文字总结
        generateSummaryText(periodName, stats, tasks);
    } catch (e) {
        console.error('加载总结数据失败:', e);
    }
}

// 这个函数负责把“日报 / 周报 / 月报”映射成真实日期范围。
function getDateRange(period) {
    const now = new Date();
    const today = getLocalDateStr();
    let startDate, endDate, periodName;

    if (period === 'day') {
        startDate = endDate = today;
        periodName = '今日';
    } else if (period === 'week') {
        const dayOfWeek = now.getDay();
        const monday = new Date(now);
        monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
        startDate = monday.toISOString().split('T')[0];
        endDate = today;
        periodName = '本周';
    } else {
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        startDate = firstDay.toISOString().split('T')[0];
        endDate = today;
        periodName = '本月';
    }

    return { startDate, endDate, periodName };
}

// 总结里的任务明细是只读结果区，不复用主任务卡片模板。
function renderSummaryTasks(tasks) {
    const container = document.getElementById('summary-task-list');

    if (tasks.length === 0) {
        container.innerHTML = '<div class="summary-empty">暂无任务数据</div>';
        return;
    }

    container.innerHTML = tasks.map(task => `
        <div class="summary-task-item">
            <div class="task-status ${task.status === 'completed' ? 'completed' : 'incomplete'}">
                ${task.status === 'completed' ? '✓' : ''}
            </div>
            <span class="task-title">${escapeHtml(task.title)}</span>
            ${task.pomodoro_count > 0 ? `<span class="task-pomodoro">🍅 ${task.pomodoro_count}</span>` : ''}
        </div>
    `).join('');
}

// 文本总结区是为了方便用户直接复制到外部日报/周报渠道。
function generateSummaryText(periodName, stats, tasks) {
    const completed = stats.completed_tasks || 0;
    const total = stats.total_tasks || 0;
    const pomodoros = stats.pomodoro_count || 0;
    const hours = stats.pomodoro_hours || 0;

    const completedTasks = tasks.filter(t => t.status === 'completed');
    const inProgressTasks = tasks.filter(t => t.status === 'in_progress');

    let text = `📊 ${periodName}工作总结\n`;
    text += `━━━━━━━━━━━━━━━━━━\n\n`;

    text += `📈 数据概览\n`;
    text += `• 完成任务: ${completed}/${total} 项\n`;
    text += `• 番茄数量: ${pomodoros} 个\n`;
    text += `• 专注时长: ${hours} 小时\n\n`;

    if (completedTasks.length > 0) {
        text += `✅ 已完成任务\n`;
        completedTasks.forEach(t => {
            text += `• ${t.title}`;
            if (t.pomodoro_count > 0) text += ` (🍅${t.pomodoro_count})`;
            text += '\n';
        });
        text += '\n';
    }

    if (inProgressTasks.length > 0) {
        text += `🚀 进行中任务\n`;
        inProgressTasks.forEach(t => {
            text += `• ${t.title}\n`;
        });
        text += '\n';
    }

    text += `━━━━━━━━━━━━━━━━━━\n`;
    text += `牛牛待办 · ${new Date().toLocaleDateString('zh-CN')}`;

    document.getElementById('summary-text').value = text;
}

async function copySummary() {
    const text = document.getElementById('summary-text').value;
    try {
        await navigator.clipboard.writeText(text);
        showToast('总结已复制到剪贴板哞！');
    } catch (e) {
        // 降级方案
        const textarea = document.getElementById('summary-text');
        textarea.select();
        document.execCommand('copy');
        showToast('总结已复制哞！');
    }
}

// ===== 设置 =====
// 设置弹窗打开前先回填后端设置，避免用户看到旧值。
async function showSettingsModal() {
    await loadSettingsData();
    openModal('settings-modal');
}

/**
 * 设置弹窗数据加载。
 *
 * 这里同时聚合两类数据：
 * - 用户设置：番茄钟时长、缩放
 * - 数据概览：任务数、分类数、番茄记录数
 */
async function loadSettingsData() {
    try {
        const settings = await pywebview.api.get_settings();
        document.getElementById('settings-pomodoro-work').value = settings.pomodoro_work || 25;
        document.getElementById('settings-pomodoro-break').value = settings.pomodoro_break || 5;
        document.getElementById('settings-pomodoro-long-break').value = settings.pomodoro_long_break || 15;

        const zoom = settings.zoom || 100;
        document.getElementById('settings-zoom').value = zoom;
        document.getElementById('zoom-value').textContent = zoom + '%';

        const dataStats = await pywebview.api.get_data_stats();
        document.getElementById('data-stat-tasks').textContent = dataStats.tasks || 0;
        document.getElementById('data-stat-categories').textContent = dataStats.categories || 0;
        document.getElementById('data-stat-pomodoros').textContent = dataStats.pomodoros || 0;
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

// 拖动缩放滑块时先做本地预览，真正持久化发生在 `saveSettings()`。
function previewZoom(value) {
    document.getElementById('zoom-value').textContent = value + '%';
    applyZoom(value);
}

// 当前项目直接用 `document.body.style.zoom` 做整体缩放，逻辑简单但影响全局。
function applyZoom(zoom) {
    document.body.style.zoom = zoom / 100;
}

// ===== 快捷键配置 =====
// 设置弹窗里的快捷键面板与全局运行时快捷键共享同一套 `state.shortcuts`。
async function loadShortcutsConfig() {
    try {
        const data = await pywebview.api.get_shortcuts();
        state.shortcuts = data.shortcuts || {};
        state.shortcutLabels = data.labels || {};
        renderShortcutsConfig();
    } catch (e) {
        console.error('加载快捷键配置失败:', e);
    }
}

// 快捷键配置区是纯动态列表；每一行都对应一个可执行动作。
function renderShortcutsConfig() {
    const container = document.getElementById('shortcuts-config-list');
    if (!container) return;

    container.innerHTML = '';
    const orderedKeys = [
        'newTask', 'editTask', 'toggleTaskStatus', 'startPomodoro', 'toggleSticky',
        'focusSearch', 'viewList', 'viewKanban', 'viewCalendar', 'viewQuadrant',
        'navigateUp', 'navigateDown'
    ];

    for (const action of orderedKeys) {
        if (!state.shortcutLabels[action]) continue;
        const shortcut = state.shortcuts[action] || {};
        const label = state.shortcutLabels[action];
        const displayText = formatShortcut(shortcut);

        const item = document.createElement('div');
        item.className = 'shortcut-config-item';
        item.innerHTML = `
            <span class="shortcut-label">${escapeHtml(label)}</span>
            <input type="text" class="shortcut-input" data-action="${action}"
                   value="${escapeHtml(displayText)}" readonly
                   placeholder="点击录入快捷键">
            <button class="shortcut-clear" data-action="${action}" title="清除">✕</button>
        `;
        container.appendChild(item);
    }

    container.querySelectorAll('.shortcut-input').forEach(input => {
        input.addEventListener('focus', startShortcutRecording);
        input.addEventListener('blur', stopShortcutRecording);
        input.addEventListener('keydown', recordShortcut);
    });

    container.querySelectorAll('.shortcut-clear').forEach(btn => {
        btn.addEventListener('click', clearShortcut);
    });
}

// 录制快捷键时会按平台差异展示 Cmd / Ctrl 等文案，但内部存的仍是统一结构。
function formatShortcut(shortcut) {
    if (!shortcut || !shortcut.key) return '未设置';
    const parts = [];
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    if (shortcut.ctrl) parts.push(isMac ? '⌘' : 'Ctrl');
    if (shortcut.alt) parts.push(isMac ? '⌥' : 'Alt');
    if (shortcut.shift) parts.push(isMac ? '⇧' : 'Shift');
    parts.push(formatKeyName(shortcut.key));
    return parts.join(' + ');
}

function formatKeyName(key) {
    const keyMap = {
        ' ': 'Space',
        'ArrowUp': '↑',
        'ArrowDown': '↓',
        'ArrowLeft': '←',
        'ArrowRight': '→',
        'Escape': 'Esc',
        'Enter': 'Enter',
        'Backspace': '⌫',
        'Delete': 'Del',
        'Tab': 'Tab'
    };
    return keyMap[key] || key.toUpperCase();
}

// 聚焦输入框后进入“录制模式”，此时后续 keydown 会被解释为快捷键配置输入。
function startShortcutRecording(e) {
    const input = e.target;
    input.classList.add('recording');
    input.value = '按下组合键...';
    state.editingShortcut = input.dataset.action;
}

function stopShortcutRecording(e) {
    const input = e.target;
    input.classList.remove('recording');
    state.editingShortcut = null;
    const action = input.dataset.action;
    const shortcut = state.shortcuts[action];
    input.value = formatShortcut(shortcut);
}

// 快捷键录入时会先做冲突检测，避免两个动作绑定同一组合键。
function recordShortcut(e) {
    e.preventDefault();
    e.stopPropagation();

    const action = state.editingShortcut;
    if (!action) return;

    const key = e.key;
    if (['Control', 'Alt', 'Shift', 'Meta'].includes(key)) return;

    const newShortcut = {
        ctrl: e.ctrlKey || e.metaKey,
        alt: e.altKey,
        shift: e.shiftKey,
        key: key
    };

    const conflict = checkShortcutConflict(action, newShortcut);
    const input = e.target;

    if (conflict) {
        input.classList.add('conflict');
        input.value = `冲突: ${state.shortcutLabels[conflict]}`;
        setTimeout(() => {
            input.classList.remove('conflict');
            input.value = formatShortcut(state.shortcuts[action]);
        }, 1500);
        return;
    }

    state.shortcuts[action] = newShortcut;
    input.value = formatShortcut(newShortcut);
    input.classList.remove('recording');
    input.blur();
}

function checkShortcutConflict(currentAction, newShortcut) {
    for (const [action, shortcut] of Object.entries(state.shortcuts)) {
        if (action === currentAction) continue;
        if (!shortcut || !shortcut.key) continue;
        if (shortcut.ctrl === newShortcut.ctrl &&
            shortcut.alt === newShortcut.alt &&
            shortcut.shift === newShortcut.shift &&
            shortcut.key.toLowerCase() === newShortcut.key.toLowerCase()) {
            return action;
        }
    }
    return null;
}

// 快捷键配置弹窗只是配置 UI；保存仍需显式调用后端接口。
function clearShortcut(e) {
    const action = e.target.dataset.action;
    state.shortcuts[action] = { ctrl: false, alt: false, shift: false, key: '' };
    const input = document.querySelector(`.shortcut-input[data-action="${action}"]`);
    if (input) input.value = '未设置';
}

async function showShortcutsModal() {
    await loadShortcutsConfig();
    openModal('shortcuts-modal');
}

// 这里会把整套动作映射一次性提交给后端，不是逐项保存。
async function saveShortcutsAndClose() {
    try {
        await pywebview.api.save_shortcuts(state.shortcuts);
        closeModal('shortcuts-modal');
        showToast('快捷键已保存哞！');
    } catch (e) {
        showToast('保存失败：' + e, true);
    }
}

async function resetShortcuts() {
    if (!confirm('确定要恢复所有快捷键为默认设置吗？')) return;
    try {
        const data = await pywebview.api.reset_shortcuts();
        state.shortcuts = data.shortcuts || {};
        state.shortcutLabels = data.labels || {};
        renderShortcutsConfig();
        showToast('快捷键已恢复默认哞！');
    } catch (e) {
        showToast('重置失败：' + e, true);
    }
}

/**
 * 保存设置。
 *
 * 当前拆成两类接口：
 * - 番茄钟参数：`update_settings`
 * - 缩放：`save_zoom`
 *
 * 这是因为历史上这两类设置在后端入口上是分开的。
 */
async function saveSettings() {
    const pomodoroWork = parseInt(document.getElementById('settings-pomodoro-work').value) || 25;
    const pomodoroBreak = parseInt(document.getElementById('settings-pomodoro-break').value) || 5;
    const pomodoroLongBreak = parseInt(document.getElementById('settings-pomodoro-long-break').value) || 15;
    const zoom = parseInt(document.getElementById('settings-zoom').value) || 100;

    try {
        await pywebview.api.update_settings({
            pomodoro_work: pomodoroWork,
            pomodoro_break: pomodoroBreak,
            pomodoro_long_break: pomodoroLongBreak
        });
        await pywebview.api.save_zoom(zoom);
        closeModal('settings-modal');
        showToast('设置已保存哞！');
    } catch (e) {
        showToast('保存失败：' + e, true);
    }
}

// 导出逻辑会先取数据库真实路径，再在同目录拼一个带日期的备份文件名。
async function exportData() {
    try {
        const dbPath = await pywebview.api.get_db_path();
        const date = new Date().toISOString().split('T')[0];
        const exportPath = dbPath.replace(/[^/\\]+$/, `牛牛待办_备份_${date}.db`);

        const result = await pywebview.api.export_db(exportPath);
        if (result.success) {
            showToast(`数据已导出到: ${result.path}`);
        } else {
            showToast('导出失败：' + result.error, true);
        }
    } catch (e) {
        showToast('导出失败：' + e, true);
    }
}

// 导入是高影响操作：先校验文件类型，再让后端做真正的备份/覆盖/回滚。
async function handleImportFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.endsWith('.db')) {
        showToast('请选择 .db 格式的数据库文件', true);
        event.target.value = '';
        return;
    }

    if (!confirm('导入数据将覆盖现有数据，确定继续吗？')) {
        event.target.value = '';
        return;
    }

    try {
        const result = await pywebview.api.import_db(file.path || file.name);
        if (result.success) {
            showToast('数据导入成功哞！正在刷新...');
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('导入失败：' + (result.error || '未知错误'), true);
        }
    } catch (e) {
        showToast('导入失败：' + e, true);
    }
    event.target.value = '';
}

// ===== 弹窗 =====
// 当前项目所有 modal 都走统一的 `show` class 显隐方案。
function openModal(id) {
    document.getElementById(id).classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

// ===== Toast =====
// 通用轻提示。这里只负责展示，不负责业务恢复或重试。
function showToast(msg, isError = false) {
    const toast = document.getElementById('toast');
    const msgEl = document.getElementById('toast-message');
    const iconEl = toast.querySelector('.toast-icon');

    msgEl.textContent = msg;
    iconEl.textContent = isError ? '🐮' : '🐄';
    toast.className = 'toast' + (isError ? ' error' : '');

    setTimeout(() => toast.classList.add('hidden'), 2500);
}

// ===== 专注统计图表 =====
let trendChart = null;

// 打开统计弹窗后立即开始加载数据，避免先显示空白结果。
function showStatsModal() {
    openModal('stats-modal');
    loadStatsData();
}

/**
 * 专注统计总加载入口。
 *
 * 这里特意并行请求三类数据：
 * - 每日趋势
 * - 年度热力图
 * - 分类分布
 *
 * 如果统计弹窗慢，首先看这里的三个接口是否有某一个明显拖后腿。
 */
async function loadStatsData() {
    try {
        // 并行加载所有统计数据
        const [dailyStats, heatmapData, categoryStats] = await Promise.all([
            pywebview.api.get_pomodoro_daily_stats(30),
            pywebview.api.get_pomodoro_heatmap(new Date().getFullYear()),
            pywebview.api.get_category_pomodoro_stats()
        ]);

        // 延迟渲染以等待弹窗动画
        setTimeout(() => {
            renderTrendChart(dailyStats);
            renderHeatmap(heatmapData);
            renderCategoryStats(categoryStats);
        }, 100);
    } catch (e) {
        console.error('加载统计数据失败:', e);
        showToast('加载统计数据失败', true);
    }
}

// 趋势图是最依赖第三方库 uPlot 的区域；若图表异常，优先查这里和容器尺寸。
function renderTrendChart(dailyStats) {
    const container = document.getElementById('pomodoro-trend-chart');
    container.innerHTML = '';

    if (!dailyStats || dailyStats.length === 0) {
        container.innerHTML = '<div class="stats-empty"><div class="stats-empty-icon">📊</div><div>暂无专注数据</div></div>';
        return;
    }

    // 准备 uPlot 数据格式
    const dates = dailyStats.map(d => new Date(d.date).getTime() / 1000);
    const counts = dailyStats.map(d => d.count);

    const style = getComputedStyle(document.body);
    const accent = style.getPropertyValue('--accent').trim() || '#FFB347';
    const text = style.getPropertyValue('--text').trim() || '#4A4A4A';
    const border = style.getPropertyValue('--border').trim() || '#F0E8E8';

    const opts = {
        width: container.clientWidth - 20,
        height: container.clientHeight - 20,
        cursor: { show: true, points: { show: false } },
        scales: { x: { time: true } },
        axes: [
            { stroke: text, grid: { show: false }, font: "10px 'Nunito'", gap: 8 },
            { stroke: text, grid: { stroke: border, width: 1 }, font: "10px 'Nunito'", gap: 8 }
        ],
        series: [
            {},
            {
                label: "番茄数",
                stroke: accent,
                width: 2,
                fill: accent + "40",
                points: { size: 5, fill: accent, stroke: "#fff" }
            }
        ]
    };

    // 销毁旧图表
    if (trendChart) {
        trendChart.destroy();
        trendChart = null;
    }

    trendChart = new uPlot(opts, [dates, counts], container);
}

// 热力图不依赖第三方图表库，而是直接动态生成一整年的日期格子。
function renderHeatmap(data) {
    const container = document.getElementById('pomodoro-heatmap');
    container.innerHTML = '';

    const year = new Date().getFullYear();
    const start = new Date(year, 0, 1);
    const end = new Date(year, 11, 31);
    const today = new Date();

    // 填充到年初第一个周日
    const startDay = start.getDay();
    if (startDay > 0) {
        start.setDate(start.getDate() - startDay);
    }

    for (let d = new Date(start); d <= end || d <= today; d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().split('T')[0];
        const count = data[dateStr] || 0;

        // 计算级别 (0-4)
        let level = 0;
        if (count > 0) level = 1;
        if (count > 2) level = 2;
        if (count > 5) level = 3;
        if (count > 8) level = 4;

        const cell = document.createElement('div');
        cell.className = `heatmap-cell level-${level}`;
        cell.title = `${dateStr}: ${count} 个番茄`;
        container.appendChild(cell);
    }
}

// 分类统计区本质是一个“排名卡片列表”，不是图表库生成的图。
function renderCategoryStats(categories) {
    const container = document.getElementById('category-stats');
    container.innerHTML = '';

    if (!categories || categories.length === 0) {
        container.innerHTML = '<div class="stats-empty"><div class="stats-empty-icon">📁</div><div>暂无分类统计</div></div>';
        return;
    }

    const total = categories.reduce((sum, c) => sum + c.count, 0);

    categories.sort((a, b) => b.count - a.count).forEach(cat => {
        const percent = total > 0 ? Math.round((cat.count / total) * 100) : 0;
        const color = cat.color || '#FFB347';

        const card = document.createElement('div');
        card.className = 'category-stat-card';
        card.style.borderLeftColor = color;

        card.innerHTML = `
            <div class="cat-stat-header">
                <span>${escapeHtml(cat.icon || '📁')}</span>
                <span>${escapeHtml(cat.name || '未分类')}</span>
            </div>
            <div class="cat-stat-value">
                ${cat.count}
                <span class="cat-stat-pct">${percent}%</span>
            </div>
            <div class="cat-stat-bar-bg">
                <div class="cat-stat-bar-fill" style="width:${percent}%; background:${color}"></div>
            </div>
        `;
        container.appendChild(card);
    });
}

// ===== 成就系统 =====

const TIER_NAMES = {
    bronze: '铜牌',
    silver: '银牌',
    gold: '金牌',
    diamond: '钻石'
};

// 成就弹窗打开时只做一件事：加载并重绘整张成就面板。
async function showAchievementModal() {
    openModal('achievement-modal');
    await loadAchievements();
}

/**
 * 成就面板数据装配。
 *
 * 后端已经返回了“展示友好结构”，这里主要负责：
 * - 更新顶部统计
 * - 排序
 * - 渲染成就卡片
 */
async function loadAchievements() {
    const data = await pywebview.api.get_achievements();
    if (!data || !data.achievements) return;

    // 更新统计
    document.getElementById('achievement-unlocked').textContent = data.stats.unlocked;
    document.getElementById('achievement-total').textContent = data.stats.total;
    document.getElementById('achievement-streak').textContent = data.stats.streak;

    // 渲染成就卡片
    const grid = document.getElementById('achievement-grid');
    grid.innerHTML = '';

    // 按类别分组排序：已解锁优先
    const sorted = [...data.achievements].sort((a, b) => {
        if (a.unlocked !== b.unlocked) return b.unlocked - a.unlocked;
        return a.target - b.target;
    });

    sorted.forEach(ach => {
        const progress = Math.min(100, Math.round((ach.current / ach.target) * 100));
        const card = document.createElement('div');
        card.className = `achievement-card ${ach.unlocked ? 'unlocked' : 'locked'}`;
        card.style.setProperty('--tier-color', ach.tier_color);

        card.innerHTML = `
            <div class="achievement-icon">${ach.icon}</div>
            <div class="achievement-info">
                <div class="achievement-name">${escapeHtml(ach.name)}</div>
                <div class="achievement-desc">${escapeHtml(ach.desc)}</div>
                <div class="achievement-progress">
                    <div class="achievement-progress-bar">
                        <div class="achievement-progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <span class="achievement-progress-text">${ach.current}/${ach.target}</span>
                </div>
            </div>
            <span class="achievement-tier" style="background: ${ach.tier_color}">${TIER_NAMES[ach.tier] || ach.tier}</span>
        `;
        grid.appendChild(card);
    });
}

// 任务完成、番茄完成后都会走这里，负责把“新解锁成就列表”转成顺序弹出的提示。
async function checkAndShowAchievements() {
    const newAchievements = await pywebview.api.check_achievements();
    if (newAchievements && newAchievements.length > 0) {
        // 依次显示每个新解锁的成就
        for (const ach of newAchievements) {
            await showAchievementToast(ach);
        }
    }
}

function showAchievementToast(achievement) {
    return new Promise(resolve => {
        const toast = document.getElementById('achievement-toast');
        const icon = document.getElementById('achievement-toast-icon');
        const name = document.getElementById('achievement-toast-name');

        icon.textContent = achievement.icon;
        name.textContent = achievement.name;

        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('show'), 10);

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.classList.add('hidden');
                resolve();
            }, 500);
        }, 3000);
    });
}

// 在不改原有调用点的前提下，对 `toggleTaskStatus` 做一层包装：
// 只有任务从“未完成 -> 已完成”时，才额外触发成就检查。
const originalToggleTaskStatus = toggleTaskStatus;
toggleTaskStatus = async function(taskId) {
    const taskBefore = state.tasks.find(t => t.id === taskId);
    const wasCompleted = taskBefore && taskBefore.status === 'completed';

    await originalToggleTaskStatus(taskId);

    // 只有当任务从未完成变为完成时才检查成就
    const taskAfter = state.tasks.find(t => t.id === taskId);
    if (taskAfter && taskAfter.status === 'completed' && !wasCompleted) {
        await checkAndShowAchievements();
    }
};

// ========== AI 聊天功能 ==========

// `aiState` 独立于普通 `state`，避免待办主界面状态和 AI 会话状态互相污染。
const aiState = {
    sessions: [],
    currentSessionId: null,
    messages: [],
    providers: [],
    activeProvider: null,
    isLoading: false
};

/**
 * 打开 AI 聊天主面板。
 *
 * 进入顺序：
 * 1. 打开弹窗壳
 * 2. 加载 Provider 状态
 * 3. 加载会话列表
 * 4. 更新顶部 Provider 指示灯
 */
async function showAIChatModal() {
    openModal('ai-chat-modal');
    await loadAIProviders();
    await loadAISessions();
    updateAIProviderIndicator();
}

// Provider 状态决定右下角输入区是否允许真正发送消息。
async function loadAIProviders() {
    try {
        aiState.providers = await pywebview.api.get_ai_providers();
        aiState.activeProvider = aiState.providers.find(p => p.active);
        updateAIProviderIndicator();
    } catch (e) {
        console.error('加载 AI Provider 失败:', e);
    }
}

// 这个指示器只做“当前激活服务商”展示，不代表网络一定健康。
function updateAIProviderIndicator() {
    const indicator = document.getElementById('ai-provider-indicator');
    if (!indicator) return;

    const dot = indicator.querySelector('.ai-provider-dot');
    const name = indicator.querySelector('.ai-provider-name');

    if (aiState.activeProvider) {
        dot.classList.add('connected');
        name.textContent = aiState.activeProvider.name;
    } else {
        dot.classList.remove('connected');
        name.textContent = '未配置';
    }
}

// 左侧会话栏的真实数据源是后端的 `chat_sessions`，不是前端缓存。
async function loadAISessions() {
    try {
        aiState.sessions = await pywebview.api.get_chat_sessions(false);
        renderAISessions();
    } catch (e) {
        console.error('加载会话失败:', e);
    }
}

// 会话列表是典型的动态导航区：点击切换会话，删除按钮则直接删整条会话记录。
function renderAISessions() {
    const container = document.getElementById('ai-sessions-list');
    if (!container) return;

    if (aiState.sessions.length === 0) {
        container.innerHTML = '<div class="ai-empty-state">暂无会话</div>';
        return;
    }

    container.innerHTML = aiState.sessions.map(session => `
        <div class="ai-session-item ${session.id === aiState.currentSessionId ? 'active' : ''}"
             onclick="selectAISession('${session.id}')">
            <span class="ai-session-title">${escapeHtml(session.title || '新对话')}</span>
            <button class="ai-session-delete" onclick="event.stopPropagation(); deleteAISession('${session.id}')">×</button>
        </div>
    `).join('');
}

// 如果当前没有会话但用户直接发消息，前面逻辑会先调用这里自动补一个新会话。
async function createAISession() {
    try {
        const result = await pywebview.api.create_chat_session('新对话');
        if (!result || !result.id) {
            showToast('创建会话失败', true);
            return false;
        }
        aiState.currentSessionId = result.id;
        await loadAISessions();
        clearAIChatMessages();
        showToast('新会话已创建');
        return true;
    } catch (e) {
        showToast('创建会话失败', true);
        return false;
    }
}

// 切换会话时要防止异步串话，所以这里保留了 `requestedId` 检查。
async function selectAISession(sessionId) {
    aiState.currentSessionId = sessionId;
    renderAISessions();

    const requestedId = sessionId;
    const messages = await loadAIChatMessages(sessionId);

    if (aiState.currentSessionId === requestedId) {
        aiState.messages = messages || [];
        renderAIChatMessages();
    }
}

async function deleteAISession(sessionId) {
    if (!confirm('确定删除此会话？')) return;

    try {
        await pywebview.api.delete_chat_session(sessionId);
        if (aiState.currentSessionId === sessionId) {
            aiState.currentSessionId = null;
            clearAIChatMessages();
        }
        await loadAISessions();
        showToast('会话已删除');
    } catch (e) {
        showToast('删除失败');
    }
}

// 消息历史是右侧聊天结果区的唯一输入来源。
async function loadAIChatMessages(sessionId) {
    try {
        const messages = await pywebview.api.get_chat_messages(sessionId);
        return messages || [];
    } catch (e) {
        console.error('加载消息失败:', e);
        showToast('加载消息失败', true);
        return [];
    }
}

// 聊天结果区既要处理欢迎态，也要处理真实消息流渲染。
function renderAIChatMessages() {
    const container = document.getElementById('ai-chat-messages');
    if (!container) return;

    if (aiState.messages.length === 0) {
        container.innerHTML = `
            <div class="ai-chat-welcome">
                <div class="ai-welcome-icon">🤖</div>
                <div class="ai-welcome-text">你好！我是 AI 助手，有什么可以帮助你的吗？</div>
                <div class="ai-welcome-tips">
                    <div class="ai-tip">💡 可以问我关于任务管理的建议</div>
                    <div class="ai-tip">📝 帮你整理和规划待办事项</div>
                    <div class="ai-tip">🎯 提供时间管理和效率提升技巧</div>
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = aiState.messages.map(msg => `
        <div class="ai-message ${msg.role}">
            <div class="ai-message-avatar">${msg.role === 'user' ? '👤' : '🤖'}</div>
            <div class="ai-message-content">${formatAIMessage(msg.content)}</div>
        </div>
    `).join('');

    container.scrollTop = container.scrollHeight;
}

// 当前只做轻量 Markdown 兼容，属于“展示增强”而不是完整 Markdown 渲染器。
function formatAIMessage(content) {
    // 简单的 Markdown 转换
    let html = escapeHtml(content);
    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // 换行
    html = html.replace(/\n/g, '<br>');
    return html;
}

function clearAIChatMessages() {
    aiState.messages = [];
    renderAIChatMessages();
}

// 清空的是当前会话的消息，不是删除整条会话。
async function clearAIChat() {
    if (!aiState.currentSessionId) {
        showToast('请先选择或创建会话');
        return;
    }

    if (!confirm('确定清空当前会话的所有消息？')) return;

    try {
        await pywebview.api.clear_chat_messages(aiState.currentSessionId);
        clearAIChatMessages();
        showToast('消息已清空');
    } catch (e) {
        showToast('清空失败');
    }
}

// Enter 发送、Shift+Enter 换行，是聊天输入区的标准行为。
function handleAIChatKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!aiState.isLoading) {
            sendAIMessage();
        }
    }
}

/**
 * AI 发送消息主链路。
 *
 * 关键步骤：
 * 1. 校验输入、Provider、会话是否准备好
 * 2. 先把用户消息插入前端消息流，立即给出界面反馈
 * 3. 显示“AI 正在输入”占位
 * 4. 调后端 `send_chat_message`
 * 5. 成功则插入 AI 回复；失败则插入错误消息
 *
 * 如果 AI 会话看起来“卡住”或“串会话”，这里是首要排查点。
 */
async function sendAIMessage() {
    const input = document.getElementById('ai-chat-input');
    if (!input) return;

    const content = input.value.trim();
    if (!content) return;

    if (aiState.isLoading) return;

    if (!aiState.activeProvider) {
        showToast('请先配置 AI 服务商', true);
        showAISettingsModal();
        return;
    }

    if (!aiState.currentSessionId) {
        const created = await createAISession();
        if (!created || !aiState.currentSessionId) {
            return;
        }
    }

    const sessionId = aiState.currentSessionId;
    input.value = '';
    input.style.height = 'auto';

    const userMessage = { role: 'user', content };
    aiState.messages.push(userMessage);
    renderAIChatMessages();

    aiState.isLoading = true;
    const sendBtn = document.getElementById('ai-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    const container = document.getElementById('ai-chat-messages');
    let typingDiv = null;
    if (container) {
        typingDiv = document.createElement('div');
        typingDiv.className = 'ai-message assistant';
        typingDiv.innerHTML = `
            <div class="ai-message-avatar">🤖</div>
            <div class="ai-typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        container.appendChild(typingDiv);
        container.scrollTop = container.scrollHeight;
    }

    try {
        const result = await pywebview.api.send_chat_message(sessionId, content);

        if (typingDiv) typingDiv.remove();

        if (sessionId !== aiState.currentSessionId) {
            return;
        }

        if (result.success) {
            aiState.messages.push({
                role: 'assistant',
                content: result.ai_message.content
            });
            renderAIChatMessages();
        } else {
            showToast(result.error || 'AI 回复失败', true);
            aiState.messages.push({
                role: 'assistant',
                content: `❌ 发送失败: ${result.error || '未知错误'}`,
                isError: true
            });
            renderAIChatMessages();
        }
    } catch (e) {
        if (typingDiv) typingDiv.remove();
        showToast('发送失败: ' + e.message, true);
        aiState.messages.push({
            role: 'assistant',
            content: `❌ 发送失败: ${e.message}`,
            isError: true
        });
        renderAIChatMessages();
    } finally {
        aiState.isLoading = false;
        if (sendBtn) sendBtn.disabled = false;
    }
}

// ========== AI 设置功能 ==========

// AI 设置面板是聊天面板的后台管理区，不直接承载聊天记录。
async function showAISettingsModal() {
    openModal('ai-settings-modal');
    await loadAIProvidersList();
    hideProviderForm();
}

/**
 * 加载 Provider 列表并渲染操作区。
 *
 * 这里展示的是“配置管理视图”：
 * - 当前有哪些服务商
 * - 谁是已启用状态
 * - 每条记录的编辑/删除/启用入口
 */
async function loadAIProvidersList() {
    try {
        const providers = await pywebview.api.get_ai_providers();
        const container = document.getElementById('ai-providers-list');

        if (providers.length === 0) {
            container.innerHTML = '<div class="ai-empty-state">暂无配置的 AI 服务商<br>点击上方"添加"按钮开始配置</div>';
            return;
        }

        container.innerHTML = providers.map(p => `
            <div class="ai-provider-item ${p.active ? 'active' : ''}">
                <div class="ai-provider-info">
                    <div class="ai-provider-icon">${getProviderIcon(p.type)}</div>
                    <div class="ai-provider-details">
                        <span class="ai-provider-name">${escapeHtml(p.name)}</span>
                        <span class="ai-provider-type">${getProviderTypeName(p.type)}</span>
                    </div>
                </div>
                <div class="ai-provider-actions">
                    ${!p.active ? `<button class="btn btn-sm" onclick="switchAIProvider('${p.id}')">启用</button>` : '<span style="color:var(--positive);font-size:0.8rem">✓ 已启用</span>'}
                    <button class="btn btn-sm btn-ghost" onclick="editAIProvider('${p.id}')">编辑</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteAIProvider('${p.id}')">删除</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载 Provider 列表失败:', e);
    }
}

// 这两个函数只负责前端展示文案，不参与真实请求逻辑。
function getProviderIcon(type) {
    const icons = {
        'openai': '🟢',
        'claude': '🟣',
        'openai-compatible': '🔵'
    };
    return icons[type] || '🤖';
}

function getProviderTypeName(type) {
    const names = {
        'openai': 'OpenAI',
        'claude': 'Claude (Anthropic)',
        'openai-compatible': 'OpenAI 兼容'
    };
    return names[type] || type;
}

// 新增 Provider 时先重置表单到默认状态，再按类型联动 base_url。
function showAddProviderForm() {
    document.getElementById('ai-provider-form').style.display = 'block';
    document.getElementById('ai-provider-form-title').textContent = '添加 AI 服务商';
    document.getElementById('ai-provider-id').value = '';
    document.getElementById('ai-provider-name').value = '';
    document.getElementById('ai-provider-type').value = 'openai';
    document.getElementById('ai-provider-apikey').value = '';
    document.getElementById('ai-provider-baseurl').value = 'https://api.openai.com/v1';
    document.getElementById('ai-provider-model').innerHTML = '<option value="">请先获取模型列表</option>';
    onProviderTypeChange();
}

function hideProviderForm() {
    document.getElementById('ai-provider-form').style.display = 'none';
}

// Provider 类型变化时，默认地址和占位提示也会跟着变化。
function onProviderTypeChange() {
    const type = document.getElementById('ai-provider-type').value;
    const baseUrlInput = document.getElementById('ai-provider-baseurl');

    const defaultUrls = {
        'openai': 'https://api.openai.com/v1',
        'claude': 'https://api.anthropic.com',
        'openai-compatible': ''
    };

    baseUrlInput.value = defaultUrls[type] || '';
    baseUrlInput.placeholder = type === 'openai-compatible' ? '输入 API 地址' : defaultUrls[type];
}

// “获取模型”是配置辅助动作，便于用户从远端拉取可选模型列表。
async function fetchAIModels() {
    const type = document.getElementById('ai-provider-type').value;
    const apiKey = document.getElementById('ai-provider-apikey').value;
    const baseUrl = document.getElementById('ai-provider-baseurl').value;

    if (!apiKey) {
        showToast('请先输入 API Key', true);
        return;
    }

    try {
        showToast('正在获取模型列表...');
        const models = await pywebview.api.fetch_ai_models({
            type,
            api_key: apiKey,
            base_url: baseUrl
        });

        const select = document.getElementById('ai-provider-model');
        if (!Array.isArray(models)) {
            select.innerHTML = '<option value="">获取模型失败</option>';
            showToast('获取模型失败', true);
            return;
        }

        if (models.length === 0) {
            select.innerHTML = '<option value="">未找到可用模型</option>';
        } else {
            select.innerHTML = models.map(m => `<option value="${escapeAttr(m.id)}">${escapeHtml(m.name || m.id)}</option>`).join('');
        }
        showToast(`找到 ${models.length} 个模型`);
    } catch (e) {
        showToast('获取模型失败: ' + e.message, true);
        const select = document.getElementById('ai-provider-model');
        if (select) select.innerHTML = '<option value="">获取失败</option>';
    }
}

// 测试连接不会保存配置，只验证当前表单里的临时参数是否可用。
async function testAIConnection() {
    const type = document.getElementById('ai-provider-type').value;
    const apiKey = document.getElementById('ai-provider-apikey').value;
    const baseUrl = document.getElementById('ai-provider-baseurl').value;
    const model = document.getElementById('ai-provider-model').value;

    if (!apiKey) {
        showToast('请先输入 API Key');
        return;
    }

    try {
        showToast('正在测试连接...');
        const result = await pywebview.api.test_ai_connection({
            type,
            config: {
                api_key: apiKey,
                base_url: baseUrl,
                default_model: model || undefined
            }
        });

        if (result.success) {
            showToast(`连接成功！延迟: ${result.latency}s`);
        } else {
            showToast('连接失败: ' + result.error);
        }
    } catch (e) {
        showToast('测试失败: ' + e.message);
    }
}

/**
 * 保存 Provider 配置。
 *
 * 保存成功后需要同时刷新两处：
 * - 设置面板里的 Provider 列表
 * - 聊天面板里的 activeProvider 状态
 */
async function saveAIProvider() {
    const id = document.getElementById('ai-provider-id').value || `provider_${Date.now()}`;
    const name = document.getElementById('ai-provider-name').value.trim();
    const type = document.getElementById('ai-provider-type').value;
    const apiKey = document.getElementById('ai-provider-apikey').value;
    const baseUrl = document.getElementById('ai-provider-baseurl').value;
    const model = document.getElementById('ai-provider-model').value;

    if (!name) {
        showToast('请输入名称');
        return;
    }
    if (!apiKey) {
        showToast('请输入 API Key');
        return;
    }

    try {
        const result = await pywebview.api.save_ai_provider({
            id,
            name,
            type,
            enabled: true,
            config: {
                api_key: apiKey,
                base_url: baseUrl,
                default_model: model
            }
        });

        if (result.success) {
            showToast('保存成功');
            hideProviderForm();
            await loadAIProvidersList();
            await loadAIProviders();
        } else {
            showToast('保存失败: ' + result.error);
        }
    } catch (e) {
        showToast('保存失败: ' + e.message);
    }
}

// 编辑时会把已有配置回填到表单，但不会自动重新拉模型列表。
async function editAIProvider(providerId) {
    try {
        const providers = await pywebview.api.get_ai_providers();
        const provider = providers.find(p => p.id === providerId);
        if (!provider) return;

        document.getElementById('ai-provider-form').style.display = 'block';
        document.getElementById('ai-provider-form-title').textContent = '编辑 AI 服务商';
        document.getElementById('ai-provider-id').value = provider.id;
        document.getElementById('ai-provider-name').value = provider.name;
        document.getElementById('ai-provider-type').value = provider.type;
        document.getElementById('ai-provider-apikey').value = provider.config?.api_key || '';
        document.getElementById('ai-provider-baseurl').value = provider.config?.base_url || '';

        const modelSelect = document.getElementById('ai-provider-model');
        const currentModel = provider.config?.default_model;
        if (currentModel) {
            modelSelect.innerHTML = `<option value="${currentModel}">${currentModel}</option>`;
        }
    } catch (e) {
        showToast('加载配置失败');
    }
}

// 启用服务商后，要同时刷新设置页和聊天页的状态指示。
async function switchAIProvider(providerId) {
    try {
        await pywebview.api.switch_ai_provider(providerId);
        showToast('已切换 AI 服务商');
        await loadAIProvidersList();
        await loadAIProviders();
    } catch (e) {
        showToast('切换失败: ' + e.message);
    }
}

// 删除的是配置项，不会删除历史聊天会话数据。
async function deleteAIProvider(providerId) {
    if (!confirm('确定删除此 AI 服务商配置？')) return;

    try {
        const result = await pywebview.api.delete_ai_provider(providerId);
        if (result.success) {
            showToast('已删除');
            await loadAIProvidersList();
            await loadAIProviders();
        } else {
            showToast('删除失败: ' + result.error);
        }
    } catch (e) {
        showToast('删除失败: ' + e.message);
    }
}
