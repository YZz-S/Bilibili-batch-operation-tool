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

    console.log('应用初始化完成');
}

/**
 * 检查API状态
 */
async function checkApiStatus() {
    try {
        const response = await fetch('/api/bilibili/status');
        const data = await response.json();

        isOnline = data.configured && data.cookie_valid;
        updateStatusIndicator(isOnline);

    } catch (error) {
        console.error('检查API状态失败:', error);
        isOnline = false;
        updateStatusIndicator(false);
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
    scrollToElement
}; 