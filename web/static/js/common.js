/**
 * 通用JavaScript函数
 * Common JavaScript Functions
 */

// 全局变量
let isOnline = false;
let syncInProgress = false;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    initializeApp();
    checkApiStatus();

    // 请求通知权限
    requestNotificationPermission();

    // 每30秒检查一次API状态
    setInterval(checkApiStatus, 30000);
});

/**
 * 初始化应用
 */
function initializeApp() {
    // 初始化工具提示
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 初始化弹出框
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // 绑定通知设置按钮事件
    const notificationBtn = document.getElementById('notification-settings-btn');
    if (notificationBtn) {
        notificationBtn.addEventListener('click', function () {
            // (Re)create the modal's HTML to ensure settings are fresh
            createNotificationSettingsPanel();
            const modalEl = document.getElementById('notificationSettingsModal');
            if (modalEl) {
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
            }
        });
    }

    console.log('应用初始化完成');
}

/**
 * 请求浏览器通知权限
 */
async function requestNotificationPermission() {
    if ("Notification" in window) {
        if (Notification.permission === "default") {
            try {
                const permission = await Notification.requestPermission();
                console.log('通知权限状态:', permission);

                if (permission === "granted") {
                    // 发送欢迎通知
                    sendNotification('哔哩哔哩管理工具', '通知功能已启用，您将收到重要操作的提醒', {
                        silent: true,
                        badge: '/static/img/bilibili-logo.svg'
                    });
                }
            } catch (error) {
                console.error('请求通知权限失败:', error);
            }
        }
    }
}

/**
 * 发送浏览器通知
 */
function sendNotification(title, body, options = {}) {
    if ("Notification" in window && Notification.permission === "granted") {
        const defaultOptions = {
            icon: '/static/img/bilibili-logo.svg',
            badge: '/static/img/bilibili-logo.svg',
            tag: 'bilibili-tool',
            requireInteraction: false,
            silent: false,
            renotify: false,
            ...options
        };

        try {
            const notification = new Notification(title, {
                body: body,
                ...defaultOptions
            });

            // 点击通知时聚焦窗口
            notification.onclick = function (event) {
                event.preventDefault();
                window.focus();
                notification.close();
            };

            // 自动关闭通知（可配置）
            if (options.autoClose !== false) {
                setTimeout(() => {
                    notification.close();
                }, options.duration || 6000);
            }

            return notification;
        } catch (error) {
            console.error('发送通知失败:', error);
        }
    }
}

/**
 * 发送成功通知
 */
function sendSuccessNotification(title, body, options = {}) {
    return sendNotification(title, body, {
        icon: '/static/img/success-icon.svg',
        tag: 'success',
        ...options
    });
}

/**
 * 发送错误通知
 */
function sendErrorNotification(title, body, options = {}) {
    return sendNotification(title, body, {
        icon: '/static/img/error-icon.svg',
        tag: 'error',
        requireInteraction: true,
        ...options
    });
}

/**
 * 发送警告通知
 */
function sendWarningNotification(title, body, options = {}) {
    return sendNotification(title, body, {
        icon: '/static/img/warning-icon.svg',
        tag: 'warning',
        ...options
    });
}

/**
 * 发送信息通知
 */
function sendInfoNotification(title, body, options = {}) {
    return sendNotification(title, body, {
        icon: '/static/img/info-icon.svg',
        tag: 'info',
        ...options
    });
}

/**
 * 发送进度通知
 */
function sendProgressNotification(title, body, progress, options = {}) {
    const progressBody = `${body} (${progress}%)`;
    return sendNotification(title, progressBody, {
        icon: '/static/img/progress-icon.svg',
        tag: 'progress',
        renotify: true,
        ...options
    });
}

/**
 * 检查API状态
 */
async function checkApiStatus() {
    try {
        const response = await fetch('/api/bilibili/status');
        const data = await response.json();

        const wasOnline = isOnline;
        isOnline = data.configured && data.cookie_valid;
        updateStatusIndicator(isOnline);

        // 状态变化时发送通知
        if (wasOnline !== isOnline) {
            if (isOnline) {
                sendSuccessNotification('连接状态', 'B站API连接已恢复');
            } else if (wasOnline) {
                sendErrorNotification('连接状态', 'B站API连接已断开，请检查Cookie配置');
            }
        }

    } catch (error) {
        console.error('检查API状态失败:', error);
        const wasOnline = isOnline;
        isOnline = false;
        updateStatusIndicator(false);

        if (wasOnline) {
            sendErrorNotification('连接错误', 'API状态检查失败，请检查网络连接');
        }
    }
}

/**
 * 更新状态指示器
 */
function updateStatusIndicator(online) {
    const indicator = document.getElementById('status-indicator');
    if (!indicator) return;

    if (online) {
        indicator.className = 'badge bg-success';
        indicator.innerHTML = '<i class="bi bi-circle-fill"></i> 已连接';
    } else {
        indicator.className = 'badge bg-secondary';
        indicator.innerHTML = '<i class="bi bi-circle-fill"></i> 未连接';
    }
}

/**
 * 显示消息提示
 */
function showMessage(message, type = 'info', duration = 5000) {
    const container = document.getElementById('message-container');
    if (!container) return;

    const alertId = 'alert-' + Date.now();
    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
            <i class="bi bi-${getIconForType(type)}"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', alertHtml);

    // 自动移除
    if (duration > 0) {
        setTimeout(() => {
            const alert = document.getElementById(alertId);
            if (alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, duration);
    }

    // 根据消息类型发送通知
    if (type === 'success') {
        sendNotificationWithSettings('操作成功', message, 'success', { silent: true });
    } else if (type === 'danger') {
        sendNotificationWithSettings('操作失败', message, 'error');
    } else if (type === 'warning') {
        sendNotificationWithSettings('注意', message, 'warning', { silent: true });
    } else if (type === 'info') {
        sendNotificationWithSettings('信息', message, 'info', { silent: true });
    }
}

/**
 * 获取消息类型对应的图标
 */
function getIconForType(type) {
    const icons = {
        'success': 'check-circle',
        'warning': 'exclamation-triangle',
        'danger': 'exclamation-circle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

/**
 * 显示加载状态
 */
function showLoading(element, text = '加载中...') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }

    if (element) {
        element.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">${text}</span>
                </div>
                <p class="mt-2 text-muted">${text}</p>
            </div>
        `;
    }
}

/**
 * 隐藏加载状态
 */
function hideLoading(element) {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }

    if (element) {
        const loading = element.querySelector('.spinner-border');
        if (loading) {
            loading.parentElement.remove();
        }
    }
}

/**
 * 格式化数字
 */
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

/**
 * 格式化日期
 */
function formatDate(timestamp, format = 'YYYY-MM-DD HH:mm:ss') {
    const date = new Date(timestamp * 1000);

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');

    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hours)
        .replace('mm', minutes)
        .replace('ss', seconds);
}

/**
 * 格式化相对时间
 */
function formatRelativeTime(timestamp) {
    const now = new Date();
    const date = new Date(timestamp * 1000);
    const diff = now - date;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(months / 12);

    if (years > 0) return `${years}年前`;
    if (months > 0) return `${months}个月前`;
    if (days > 0) return `${days}天前`;
    if (hours > 0) return `${hours}小时前`;
    if (minutes > 0) return `${minutes}分钟前`;
    return '刚刚';
}

/**
 * 获取用户分类颜色
 */
function getCategoryColor(category) {
    const colors = {
        '游戏': '#e74c3c',
        '科技': '#3498db',
        '知识': '#2ecc71',
        '生活': '#f39c12',
        '娱乐': '#9b59b6',
        '美食': '#e67e22',
        '时尚': '#1abc9c',
        '汽车': '#34495e',
        '财经': '#16a085',
        '体育': '#27ae60',
        '其他': '#95a5a6'
    };
    return colors[category] || '#95a5a6';
}

/**
 * 获取VIP类型文本
 */
function getVipTypeText(vipType) {
    const types = {
        0: '普通用户',
        1: '月度大会员',
        2: '年度大会员'
    };
    return types[vipType] || '普通用户';
}

/**
 * 获取认证类型文本
 */
function getOfficialTypeText(officialType) {
    const types = {
        '-1': '未认证',
        0: '个人认证',
        1: '机构认证'
    };
    return types[officialType] || '未认证';
}

/**
 * 确认对话框
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * 复制到剪贴板
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showMessage('已复制到剪贴板', 'success', 2000);
    } catch (err) {
        console.error('复制失败:', err);
        showMessage('复制失败', 'danger', 2000);
    }
}

/**
 * 下载文件
 */
function downloadFile(url, filename) {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

/**
 * 防抖函数
 */
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
}

/**
 * 节流函数
 */
function throttle(func, limit) {
    let inThrottle;
    return function (...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * 获取URL参数
 */
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * 设置URL参数
 */
function setUrlParameter(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.pushState({}, '', url);
}

/**
 * 平滑滚动到元素
 */
function scrollToElement(element, offset = 0) {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }

    if (element) {
        const top = element.offsetTop - offset;
        window.scrollTo({
            top: top,
            behavior: 'smooth'
        });
    }
}

/**
 * 通知设置管理
 */
const NotificationSettings = {
    // 默认设置
    defaults: {
        enabled: true,
        showSuccess: true,
        showError: true,
        showWarning: true,
        showInfo: false,
        autoClose: true,
        duration: 6000,
        requireInteraction: false
    },

    // 获取设置
    get: function (key) {
        const settings = JSON.parse(localStorage.getItem('notification-settings') || '{}');
        return settings[key] !== undefined ? settings[key] : this.defaults[key];
    },

    // 设置
    set: function (key, value) {
        const settings = JSON.parse(localStorage.getItem('notification-settings') || '{}');
        settings[key] = value;
        localStorage.setItem('notification-settings', JSON.stringify(settings));
    },

    // 获取所有设置
    getAll: function () {
        const settings = JSON.parse(localStorage.getItem('notification-settings') || '{}');
        return { ...this.defaults, ...settings };
    },

    // 重置设置
    reset: function () {
        localStorage.removeItem('notification-settings');
    }
};

/**
 * 增强的发送通知函数，支持设置控制
 */
function sendNotificationWithSettings(title, body, type = 'info', options = {}) {
    // 检查通知是否启用
    if (!NotificationSettings.get('enabled')) {
        return null;
    }

    // 检查特定类型通知是否启用
    const typeKey = `show${type.charAt(0).toUpperCase() + type.slice(1)}`;
    if (!NotificationSettings.get(typeKey)) {
        return null;
    }

    // 应用用户设置
    const userSettings = {
        autoClose: NotificationSettings.get('autoClose'),
        duration: NotificationSettings.get('duration'),
        requireInteraction: NotificationSettings.get('requireInteraction'),
        ...options
    };

    // 根据类型发送对应通知
    switch (type) {
        case 'success':
            return sendSuccessNotification(title, body, userSettings);
        case 'error':
            return sendErrorNotification(title, body, userSettings);
        case 'warning':
            return sendWarningNotification(title, body, userSettings);
        case 'info':
            return sendInfoNotification(title, body, userSettings);
        default:
            return sendNotification(title, body, userSettings);
    }
}

/**
 * 创建通知设置面板
 */
function createNotificationSettingsPanel() {
    const settings = NotificationSettings.getAll();

    // 移除已存在的面板和实例
    const existingModalEl = document.getElementById('notificationSettingsModal');
    if (existingModalEl) {
        const modalInstance = bootstrap.Modal.getInstance(existingModalEl);
        if (modalInstance) {
            modalInstance.dispose();
        }
        existingModalEl.remove();
    }

    const panelHtml = `
        <div class="modal fade" id="notificationSettingsModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-bell"></i> 通知设置
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="enableNotifications" ${settings.enabled ? 'checked' : ''}>
                                <label class="form-check-label" for="enableNotifications">
                                    启用浏览器通知
                                </label>
                            </div>
                        </div>
                        
                        <hr>
                        
                        <div class="mb-3">
                            <label class="form-label">通知类型</label>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="showSuccess" ${settings.showSuccess ? 'checked' : ''}>
                                <label class="form-check-label" for="showSuccess">
                                    <span class="text-success">✓</span> 成功通知
                                </label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="showError" ${settings.showError ? 'checked' : ''}>
                                <label class="form-check-label" for="showError">
                                    <span class="text-danger">✗</span> 错误通知
                                </label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="showWarning" ${settings.showWarning ? 'checked' : ''}>
                                <label class="form-check-label" for="showWarning">
                                    <span class="text-warning">⚠</span> 警告通知
                                </label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="showInfo" ${settings.showInfo ? 'checked' : ''}>
                                <label class="form-check-label" for="showInfo">
                                    <span class="text-info">ℹ</span> 信息通知
                                </label>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="notificationDuration" class="form-label">自动关闭时间</label>
                            <div class="input-group">
                                <input type="range" class="form-range" id="notificationDuration" 
                                       min="2000" max="10000" step="1000" value="${settings.duration}">
                                <span class="input-group-text" id="durationDisplay">${settings.duration / 1000}秒</span>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="requireInteraction" ${settings.requireInteraction ? 'checked' : ''}>
                                <label class="form-check-label" for="requireInteraction">
                                    重要通知需要用户操作才能关闭
                                </label>
                            </div>
                        </div>
                        
                        <div class="alert alert-info">
                            <i class="bi bi-info-circle"></i>
                            <small>通知功能需要浏览器权限，如果没有权限请点击下方按钮申请。</small>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-primary" onclick="testNotification()">
                            <i class="bi bi-bell"></i> 测试通知
                        </button>
                        <button type="button" class="btn btn-outline-secondary" onclick="resetNotificationSettings()">
                            <i class="bi bi-arrow-clockwise"></i> 重置
                        </button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="saveNotificationSettings()">
                            <i class="bi bi-check"></i> 保存
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 添加新面板
    document.body.insertAdjacentHTML('beforeend', panelHtml);

    // 绑定事件
    const durationSlider = document.getElementById('notificationDuration');
    const durationDisplay = document.getElementById('durationDisplay');

    durationSlider.addEventListener('input', function () {
        durationDisplay.textContent = `${this.value / 1000}秒`;
    });
}

/**
 * 保存通知设置
 */
function saveNotificationSettings() {
    const settings = {
        enabled: document.getElementById('enableNotifications').checked,
        showSuccess: document.getElementById('showSuccess').checked,
        showError: document.getElementById('showError').checked,
        showWarning: document.getElementById('showWarning').checked,
        showInfo: document.getElementById('showInfo').checked,
        duration: parseInt(document.getElementById('notificationDuration').value),
        requireInteraction: document.getElementById('requireInteraction').checked
    };

    // 保存设置
    Object.keys(settings).forEach(key => {
        NotificationSettings.set(key, settings[key]);
    });

    // 关闭面板
    const modal = bootstrap.Modal.getInstance(document.getElementById('notificationSettingsModal'));
    modal.hide();

    showMessage('通知设置已保存', 'success', 2000);
}

/**
 * 重置通知设置
 */
function resetNotificationSettings() {
    if (confirm('确定要重置所有通知设置吗？')) {
        NotificationSettings.reset();

        // 关闭并重新创建面板
        const modal = bootstrap.Modal.getInstance(document.getElementById('notificationSettingsModal'));
        modal.hide();

        setTimeout(() => {
            createNotificationSettingsPanel();
            const newModal = new bootstrap.Modal(document.getElementById('notificationSettingsModal'));
            newModal.show();
        }, 300);

        showMessage('通知设置已重置', 'success', 2000);
    }
}

/**
 * 测试通知
 */
function testNotification() {
    const types = ['success', 'info', 'warning', 'error'];
    const messages = [
        { type: 'success', title: '测试成功通知', body: '这是一个成功通知的示例' },
        { type: 'info', title: '测试信息通知', body: '这是一个信息通知的示例' },
        { type: 'warning', title: '测试警告通知', body: '这是一个警告通知的示例' },
        { type: 'error', title: '测试错误通知', body: '这是一个错误通知的示例' }
    ];

    messages.forEach((msg, index) => {
        setTimeout(() => {
            sendNotificationWithSettings(msg.title, msg.body, msg.type);
        }, index * 1000);
    });
}

// 导出函数供其他脚本使用
window.BilibiliTool = {
    showMessage,
    showLoading,
    hideLoading,
    formatNumber,
    formatDate,
    formatRelativeTime,
    getCategoryColor,
    getVipTypeText,
    getOfficialTypeText,
    confirmAction,
    copyToClipboard,
    downloadFile,
    debounce,
    throttle,
    getUrlParameter,
    setUrlParameter,
    scrollToElement,
    // 通知相关函数
    requestNotificationPermission,
    sendNotification,
    sendSuccessNotification,
    sendErrorNotification,
    sendWarningNotification,
    sendInfoNotification,
    sendProgressNotification,
    sendNotificationWithSettings,
    NotificationSettings,
    createNotificationSettingsPanel,
    saveNotificationSettings,
    resetNotificationSettings,
    testNotification
}; 