/**
 * 首页JavaScript
 * Index Page JavaScript
 */

// 全局变量
let currentTaskId = null;
let currentTaskMode = 'standard';
let currentTaskControlState = 'running';

// 添加服务状态监控
let serviceStatusChecker = null;

function startServiceStatusMonitor() {
    // 如果已经有监控在运行，先停止它
    if (serviceStatusChecker) {
        clearInterval(serviceStatusChecker);
    }

    serviceStatusChecker = setInterval(async () => {
        try {
            const response = await fetch('/api/bilibili/status', {
                method: 'GET',
                timeout: 5000  // 5秒超时
            });

            if (!response.ok) {
                throw new Error(`Service status check failed: ${response.status}`);
            }

            // 服务正常，更新UI状态（如果需要）
            const statusElements = document.querySelectorAll('.service-status-indicator');
            statusElements.forEach(el => {
                el.classList.remove('text-danger', 'text-warning');
                el.classList.add('text-success');
                el.textContent = '服务正常';
            });

        } catch (error) {
            console.error('Service status check failed:', error);

            // 服务异常，更新UI状态
            const statusElements = document.querySelectorAll('.service-status-indicator');
            statusElements.forEach(el => {
                el.classList.remove('text-success', 'text-warning');
                el.classList.add('text-danger');
                el.textContent = '服务异常';
            });

            // 如果有正在进行的任务，显示警告
            if (window.currentPollingTaskId) {
                addLogEntry('警告', '⚠️ 检测到服务连接不稳定，任务可能受到影响');
            }
        }
    }, 30000); // 每30秒检查一次
}

function stopServiceStatusMonitor() {
    if (serviceStatusChecker) {
        clearInterval(serviceStatusChecker);
        serviceStatusChecker = null;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    // 清理可能的遗留状态
    window.currentPollingTaskId = null;
    if (window.progressTimer) {
        clearInterval(window.progressTimer);
        window.progressTimer = null;
    }

    // 设置事件监听器
    setupEventListeners();

    // 启动服务状态监控
    startServiceStatusMonitor();

    // 加载仪表盘数据
    loadDashboardData();

    // 加载最后更新信息
    loadLastUpdatedInfo();

    // 设置自动刷新（每60秒检查一次）
    setInterval(function () {
        if (window.autoRefreshEnabled !== false) {
            loadDashboardData();
        }
    }, 60000);
});

// 启用自动刷新
window.autoRefreshEnabled = true;

/**
 * 设置事件监听器
 */
function setupEventListeners() {
    // 同步按钮点击事件
    const syncBtn = document.getElementById('sync-btn');
    if (syncBtn) {
        syncBtn.addEventListener('click', startSync);
    }
}

/**
 * 显示同步选项模态框
 */
function showSyncOptionsModal() {
    const modal = new bootstrap.Modal(document.getElementById('syncOptionsModal'));
    modal.show();
}

/**
 * 显示快速同步模态框
 */
function showQuickSyncModal() {
    const modal = new bootstrap.Modal(document.getElementById('quickSyncModal'));
    modal.show();
}

/**
 * 启动一键更新（带模式选择）
 */
async function startOneClickUpdate(mode = 'standard') {
    // 关闭模态框
    const modal = bootstrap.Modal.getInstance(document.getElementById('syncOptionsModal'));
    if (modal) {
        modal.hide();
    }

    // 使用默认预估时间，避免启动时的API调用导致风控
    let estimatedTime = '';
    if (mode === 'conservative') {
        estimatedTime = '数小时';
    } else if (mode === 'optimized') {
        estimatedTime = '30分钟-2小时（优化版）';
    } else {
        estimatedTime = '1-3小时';
    }

    const modeNames = {
        'standard': '标准',
        'conservative': '保守',
        'optimized': '优化'
    };

    if (!confirm(`确定要执行一键更新吗？将使用${modeNames[mode]}模式，预计需要${estimatedTime}。`)) {
        return;
    }

    try {
        // 显示全屏进度界面
        showFullScreenProgress();

        showMessage(`正在启动一键更新任务（${modeNames[mode]}模式）...`, 'info');

        let endpoint;
        if (mode === 'conservative') {
            endpoint = '/api/bilibili/one-click-update-conservative';
        } else if (mode === 'optimized') {
            endpoint = '/api/bilibili/one-click-update-optimized';
        } else {
            endpoint = '/api/bilibili/one-click-update';
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                mode: mode
            })
        });

        const result = await response.json();

        if (response.ok) {
            // 设置当前任务ID和模式
            currentTaskId = result.task_id;
            currentTaskMode = mode;
            currentTaskControlState = 'running';

            let successMessage = `一键更新任务已启动！正在后台执行（${modeNames[mode]}模式），预计需要${estimatedTime}。`;

            if (mode === 'optimized' && result.optimization_features) {
                successMessage += '\n\n🚀 启用的优化功能：\n' + result.optimization_features.map(feature => '• ' + feature).join('\n');
            }

            showMessage(successMessage, 'success');

            // 发送启动通知
            if (window.BilibiliTool && window.BilibiliTool.sendInfoNotification) {
                window.BilibiliTool.sendInfoNotification(
                    '一键更新已启动',
                    `${modeNames[mode]}模式执行中，预计需要${estimatedTime}`
                );
            }

            // 初始化进度界面
            initializeProgressInterface();
            showTaskControls(); // 显示任务控制按钮

            // 设置初始状态
            const statusElement = document.getElementById('taskStatus');
            if (statusElement) {
                statusElement.textContent = '正在初始化...';
                statusElement.className = 'text-info';
            }

            startProgressPolling(result.task_id);

        } else {
            throw new Error(result.detail || '启动一键更新失败');
        }
    } catch (error) {
        hideFullScreenProgress();
        console.error('一键更新失败:', error);
        showMessage('一键更新失败: ' + error.message, 'danger');

        // 发送错误通知
        if (window.BilibiliTool && window.BilibiliTool.sendErrorNotification) {
            window.BilibiliTool.sendErrorNotification('一键更新失败', error.message);
        }
    }
}

/**
 * 启动标准同步
 */
async function startStandardSync() {
    // 关闭模态框
    const modal = bootstrap.Modal.getInstance(document.getElementById('quickSyncModal'));
    if (modal) {
        modal.hide();
    }

    await startSync();
}

/**
 * 加载数据更新时间信息
 */
async function loadLastUpdatedInfo() {
    try {
        const response = await fetch('/api/data/user-stats/summary');
        const data = await response.json();

        if (response.ok) {
            const lastUpdatedAlert = document.getElementById('lastUpdatedAlert');
            const lastUpdatedText = document.getElementById('lastUpdatedText');

            if (data.time_info.last_updated && data.time_info.last_updated !== null) {
                try {
                    // 处理时间戳，可能是秒或毫秒，也可能是ISO字符串
                    let updateTime;
                    const lastUpdated = data.time_info.last_updated;

                    if (typeof lastUpdated === 'string') {
                        // ISO字符串格式
                        updateTime = new Date(lastUpdated);
                    } else if (typeof lastUpdated === 'number') {
                        // 时间戳格式，判断是秒还是毫秒
                        if (lastUpdated > 10000000000) {
                            // 毫秒时间戳
                            updateTime = new Date(lastUpdated);
                        } else {
                            // 秒时间戳
                            updateTime = new Date(lastUpdated * 1000);
                        }
                    } else {
                        throw new Error('Invalid timestamp format');
                    }

                    // 检查日期是否有效
                    if (isNaN(updateTime.getTime())) {
                        throw new Error('Invalid date');
                    }

                    const now = new Date();
                    const daysDiff = Math.floor((now - updateTime) / (1000 * 60 * 60 * 24));

                    let alertClass = 'alert-info';
                    let message = '';

                    if (daysDiff === 0) {
                        message = `统计数据已更新至今日 ${updateTime.toLocaleString('zh-CN')}`;
                        alertClass = 'alert-success';
                    } else if (daysDiff <= 3) {
                        message = `统计数据最后更新于 ${daysDiff} 天前 (${updateTime.toLocaleString('zh-CN')})`;
                        alertClass = 'alert-info';
                    } else if (daysDiff <= 7) {
                        message = `统计数据已过期 ${daysDiff} 天 (${updateTime.toLocaleString('zh-CN')})，建议重新同步`;
                        alertClass = 'alert-warning';
                    } else {
                        message = `统计数据严重过期 ${daysDiff} 天 (${updateTime.toLocaleString('zh-CN')})，强烈建议立即同步`;
                        alertClass = 'alert-danger';
                    }

                    lastUpdatedText.textContent = message;

                    // 更新样式
                    lastUpdatedAlert.className = `alert data-status-alert ${alertClass}`;
                    lastUpdatedAlert.style.display = 'block';
                } catch (error) {
                    console.error('时间解析错误:', error, 'lastUpdated:', data.time_info.last_updated);
                    lastUpdatedText.textContent = '暂无统计数据，请先执行"同步真实数据"功能获取准确的用户统计信息';
                    lastUpdatedAlert.className = 'alert data-status-alert alert-warning';
                    lastUpdatedAlert.style.display = 'block';
                }
            } else {
                lastUpdatedText.textContent = '暂无统计数据，请先执行"同步真实数据"功能获取准确的用户统计信息';
                lastUpdatedAlert.className = 'alert data-status-alert alert-warning';
                lastUpdatedAlert.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('获取更新时间失败:', error);
        // 发生错误时不显示提醒框
        const lastUpdatedAlert = document.getElementById('lastUpdatedAlert');
        if (lastUpdatedAlert) {
            lastUpdatedAlert.style.display = 'none';
        }
    }
}

/**
 * 同步用户统计数据
 */
async function syncUserStats() {
    if (!confirm('确定要开始同步用户统计数据吗？这可能需要较长时间。')) {
        return;
    }

    try {
        const response = await fetch('/api/bilibili/sync-user-stats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (response.ok) {
            showMessage('用户统计数据同步已启动', 'success');

            // 跳转到数据分析页面查看进度
            setTimeout(() => {
                window.location.href = '/analysis';
            }, 1500);
        } else {
            throw new Error(result.detail || '启动同步失败');
        }
    } catch (error) {
        console.error('同步用户统计数据失败:', error);
        showMessage('同步失败: ' + error.message, 'danger');
    }
}

/**
 * 加载仪表板数据
 */
async function loadDashboardData() {
    try {
        // 先加载数据更新时间信息
        loadLastUpdatedInfo();

        // 加载概览统计
        const statsResponse = await fetch('/api/data/stats/overview');
        const statsData = await statsResponse.json();

        updateStatistics(statsData);
        loadRecentFollowing(statsData.recent_following);

    } catch (error) {
        console.error('加载仪表板数据失败:', error);
        showMessage('加载数据失败', 'danger');
    }
}

/**
 * 更新统计数据
 */
function updateStatistics(data) {
    // 更新总关注数
    const totalElement = document.getElementById('total-following');
    if (totalElement) {
        totalElement.textContent = formatNumber(data.total_following || 0);
    }

    // 计算已分类数量：排除"其他"、空分类、null分类
    const categories = data.categories || [];
    const categorizedCount = categories.reduce((sum, cat) => {
        const category = cat.category;
        // 排除"其他"、空字符串、null、undefined等未有效分类的情况
        if (category && category.trim() !== '' && category !== '其他' && category !== 'null') {
            return sum + cat.count;
        }
        return sum;
    }, 0);

    const categorizedElement = document.getElementById('categorized-count');
    if (categorizedElement) {
        categorizedElement.textContent = formatNumber(categorizedCount);
    }

    // 计算待处理数（未分类用户）
    const uncategorizedCount = categories.reduce((sum, cat) => {
        const category = cat.category;
        // 包括"其他"、空字符串、null、undefined等未有效分类的情况
        if (!category || category.trim() === '' || category === '其他' || category === 'null') {
            return sum + cat.count;
        }
        return sum;
    }, 0);

    const pendingElement = document.getElementById('pending-count');
    if (pendingElement) {
        pendingElement.textContent = formatNumber(uncategorizedCount);
    }
}

/**
 * 加载最近关注列表
 */
function loadRecentFollowing(recentData) {
    const container = document.getElementById('recent-following');
    if (!container) return;

    if (!recentData || recentData.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="bi bi-inbox display-4"></i>
                <p class="mt-2">暂无数据</p>
                <button class="btn btn-primary" onclick="startSync()">
                    <i class="bi bi-arrow-clockwise"></i>
                    同步关注列表
                </button>
            </div>
        `;
        return;
    }

    const itemsHtml = recentData.map(user => {
        // 头像处理：优先使用真实头像，如果没有或加载失败则使用默认头像
        let avatarUrl = user.face && user.face.trim() !== '' ? user.face : '/static/img/default-avatar.svg';

        // 如果头像URL不是完整URL，添加https协议
        if (avatarUrl && !avatarUrl.startsWith('http') && !avatarUrl.startsWith('/static/')) {
            avatarUrl = 'https:' + avatarUrl;
        }

        // 计算时间显示
        let timeDisplay = '';
        if (user.follow_time && user.follow_time > 0) {
            timeDisplay = formatRelativeTime(user.follow_time);
        } else if (user.created_at) {
            timeDisplay = formatRelativeTime(new Date(user.created_at).getTime() / 1000);
        } else {
            timeDisplay = '未知时间';
        }

        return `
            <div class="list-group-item d-flex align-items-center">
                <a href="https://space.bilibili.com/${user.uid}" target="_blank" class="avatar-link" title="点击访问 ${user.uname} 的主页">
                    <img src="${avatarUrl}" 
                         alt="${user.uname}" 
                         class="user-avatar me-3"
                         onerror="this.src='/static/img/default-avatar.svg'"
                         onload="this.style.opacity=1" style="opacity:0; transition: opacity 0.3s ease;">
                </a>
                <div class="flex-grow-1">
                    <h6 class="mb-1">${user.uname}</h6>
                    <p class="mb-1 text-muted small">${user.sign || '这个人很懒，什么都没有写～'}</p>
                    <small class="text-muted">
                        <i class="bi bi-clock"></i>
                        ${timeDisplay}
                        ${user.category ? `<span class="badge bg-secondary ms-2">${user.category}</span>` : ''}
                    </small>
                </div>
                <a href="https://space.bilibili.com/${user.uid}" 
                   target="_blank" 
                   class="btn btn-sm btn-outline-primary">
                    <i class="bi bi-box-arrow-up-right"></i>
                </a>
            </div>
        `;
    }).join('');

    container.innerHTML = itemsHtml;
}

/**
 * 初始化图表
 */
function initializeCharts() {
    initializeCategoryChart();
    initializeTrendChart();
}

/**
 * 初始化分类饼图
 */
async function initializeCategoryChart() {
    try {
        const response = await fetch('/api/analysis/distribution');
        const data = await response.json();

        const canvas = document.getElementById('categoryChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const distribution = data.distribution?.category_distribution || {};

        const labels = Object.keys(distribution);
        const values = Object.values(distribution);
        const colors = labels.map(label => getCategoryColor(label));

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const label = context.label;
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });

    } catch (error) {
        console.error('加载分类图表失败:', error);
        const canvas = document.getElementById('categoryChart');
        if (canvas) {
            canvas.parentElement.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-exclamation-circle display-4"></i>
                    <p class="mt-2">图表加载失败</p>
                </div>
            `;
        }
    }
}

/**
 * 初始化趋势折线图
 */
async function initializeTrendChart() {
    try {
        const response = await fetch('/api/analysis/trends');
        const data = await response.json();

        const canvas = document.getElementById('trendChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const trends = data.trends || [];

        const labels = trends.map(item => item.month);
        const counts = trends.map(item => item.count);
        const cumulative = trends.map(item => item.cumulative);

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: '当月关注',
                    data: counts,
                    borderColor: '#007bff',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }, {
                    label: '累计关注',
                    data: cumulative,
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: '时间'
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: '关注数量'
                        },
                        beginAtZero: true
                    }
                }
            }
        });

    } catch (error) {
        console.error('加载趋势图表失败:', error);
        const canvas = document.getElementById('trendChart');
        if (canvas) {
            canvas.parentElement.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-exclamation-circle display-4"></i>
                    <p class="mt-2">图表加载失败</p>
                </div>
            `;
        }
    }
}

/**
 * 开始同步关注列表
 */
async function startSync() {
    if (syncInProgress) {
        showMessage('同步正在进行中，请稍等...', 'warning');
        return;
    }

    if (!isOnline) {
        showMessage('请先在设置页面配置哔哩哔哩Cookie', 'warning');
        return;
    }

    try {
        syncInProgress = true;

        // 显示同步模态框
        const syncModal = new bootstrap.Modal(document.getElementById('syncModal'));
        syncModal.show();

        // 开始同步
        const response = await fetch('/api/bilibili/sync', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ force_refresh: false })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');

            // 模拟进度更新
            let progress = 0;
            const progressBar = document.getElementById('sync-progress');
            const statusText = document.getElementById('sync-status');

            const updateProgress = () => {
                progress += Math.random() * 20;
                if (progress > 100) progress = 100;

                if (progressBar) {
                    progressBar.style.width = progress + '%';
                    progressBar.setAttribute('aria-valuenow', progress);
                }

                if (statusText) {
                    statusText.textContent = `同步进度: ${Math.floor(progress)}%`;
                }

                if (progress < 100) {
                    setTimeout(updateProgress, 1000 + Math.random() * 2000);
                } else {
                    setTimeout(() => {
                        syncModal.hide();
                        showMessage('同步完成！正在刷新数据...', 'success');
                        // 重新加载页面数据
                        loadDashboardData();

                        // 延迟5秒后再次刷新，确保同步数据已保存
                        setTimeout(() => {
                            loadDashboardData();
                            showMessage('数据已更新', 'info');
                        }, 5000);
                    }, 1000);
                }
            };

            updateProgress();

        } else {
            throw new Error(result.detail || '同步失败');
        }

    } catch (error) {
        console.error('同步失败:', error);
        showMessage('同步失败: ' + error.message, 'danger');

        // 发送同步失败通知
        if (window.BilibiliTool && window.BilibiliTool.sendErrorNotification) {
            window.BilibiliTool.sendErrorNotification(
                '同步失败',
                error.message,
                { requireInteraction: true }
            );
        }

        // 隐藏模态框
        const syncModal = bootstrap.Modal.getInstance(document.getElementById('syncModal'));
        if (syncModal) {
            syncModal.hide();
        }
    } finally {
        syncInProgress = false;
    }
}

/**
 * 自动分类
 */
async function autoCategories() {
    try {
        showMessage('正在进行自动分类...', 'info');

        const response = await fetch('/api/bilibili/auto-categorize', {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');
            loadDashboardData(); // 重新加载数据
        } else {
            throw new Error(result.detail || '自动分类失败');
        }

    } catch (error) {
        console.error('自动分类失败:', error);
        showMessage('自动分类失败: ' + error.message, 'danger');
    }
}

/**
 * 生成分析报告
 */
async function generateReport() {
    try {
        showMessage('正在生成分析报告...', 'info');

        const response = await fetch('/api/analysis/report');
        const result = await response.json();

        if (response.ok) {
            showMessage('分析报告生成完成', 'success');

            // 跳转到分析页面
            window.location.href = '/analysis';
        } else {
            throw new Error(result.detail || '生成报告失败');
        }

    } catch (error) {
        console.error('生成报告失败:', error);
        showMessage('生成报告失败: ' + error.message, 'danger');
    }
}

/**
 * 显示所有不活跃用户
 */
async function showAllInactiveUsers() {
    try {
        // 显示弹窗
        const modal = new bootstrap.Modal(document.getElementById('inactiveUsersModal'));
        modal.show();

        // 获取当前的忽略未分组设置
        const ignoreUngrouped = document.getElementById('ignoreUngroupedToggle')?.checked || false;

        // 加载数据
        const response = await fetch(`/api/analysis/inactive/all?ignore_ungrouped=${ignoreUngrouped}`);
        const result = await response.json();

        if (response.ok) {
            // 更新统计信息
            document.getElementById('modalInactiveCount').textContent = result.total_count;
            document.getElementById('modalTotalCount').textContent = result.total_following;
            document.getElementById('modalInactivePercentage').textContent = result.inactive_percentage + '%';

            // 更新检测标准
            if (result.criteria) {
                document.getElementById('modalInactiveCriteria').innerHTML = `
                    • 主要标准：${result.criteria.primary}<br>
                    • 辅助标准：${result.criteria.secondary}<br>
                    • 说明：${result.criteria.description}
                `;
            }

            // 显示用户列表
            displayInactiveUsersList(result.inactive_users);

        } else {
            throw new Error(result.detail || '获取不活跃用户失败');
        }

    } catch (error) {
        console.error('获取不活跃用户失败:', error);
        showMessage('获取不活跃用户失败: ' + error.message, 'danger');

        document.getElementById('modalInactiveUsersList').innerHTML = `
            <div class="text-center py-4 text-danger">
                <i class="fas fa-exclamation-circle fa-2x"></i>
                <p class="mt-2">加载失败</p>
            </div>
        `;
    }
}

/**
 * 显示不活跃用户列表
 */
function displayInactiveUsersList(users) {
    const container = document.getElementById('modalInactiveUsersList');

    if (!users || users.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="fas fa-smile fa-2x"></i>
                <p class="mt-2">太好了！没有不活跃用户</p>
            </div>
        `;
        return;
    }

    const usersHtml = users.map(user => {
        const lastVideoText = user.last_video_days > 0
            ? `${user.last_video_days}天前`
            : '无记录';

        const reasonsBadges = user.inactive_reasons.map(reason =>
            `<span class="badge bg-warning text-dark me-1">${reason}</span>`
        ).join('');

        return `
            <div class="user-item border rounded p-3 mb-2" data-username="${user.uname.toLowerCase()}">
                <div class="row align-items-center">
                    <div class="col-auto">
                        <a href="https://space.bilibili.com/${user.uid}" target="_blank" class="avatar-link" title="点击访问 ${user.uname} 的主页">
                            <img src="${user.face || '/static/img/default-avatar.svg'}" 
                                 class="rounded-circle" 
                                 width="40" height="40" 
                                 alt="${user.uname}"
                                 onerror="this.src='/static/img/default-avatar.svg'">
                        </a>
                    </div>
                    <div class="col">
                        <div class="fw-bold">${user.uname}</div>
                        <div class="text-muted small">
                            最后更新: ${lastVideoText} | 
                            活跃度: ${user.activity_score?.toFixed(2) || '0.00'} | 
                            视频: ${user.video_count || 0}个
                        </div>
                        <div class="mt-1">${reasonsBadges}</div>
                    </div>
                    <div class="col-auto">
                        <button class="btn btn-outline-danger btn-sm" 
                                onclick="unfollowUser('${user.uid}', '${user.uname}')">
                            <i class="fas fa-user-minus"></i> 取消关注
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = usersHtml;
}

/**
 * 过滤不活跃用户
 */
function filterInactiveUsers() {
    const searchInput = document.getElementById('inactiveSearchInput');
    const searchTerm = searchInput.value.toLowerCase();
    const userItems = document.querySelectorAll('#modalInactiveUsersList .user-item');

    userItems.forEach(item => {
        const username = item.dataset.username;
        if (username.includes(searchTerm)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

/**
 * 取消关注用户
 */
async function unfollowUser(uid, uname) {
    if (!confirm(`确定要取消关注 "${uname}" 吗？`)) {
        return;
    }

    try {
        const response = await fetch('/api/bilibili/unfollow', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ uid: uid })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`成功取消关注 ${uname}`, 'success');
            // 重新加载不活跃用户列表
            showAllInactiveUsers();
        } else {
            throw new Error(result.detail || '取消关注失败');
        }

    } catch (error) {
        console.error('取消关注失败:', error);
        showMessage('取消关注失败: ' + error.message, 'danger');
    }
}

/**
 * 批量取消关注不活跃用户
 */
async function batchUnfollowInactive() {
    const userItems = document.querySelectorAll('#modalInactiveUsersList .user-item');
    const visibleUsers = Array.from(userItems).filter(item => item.style.display !== 'none');

    if (visibleUsers.length === 0) {
        showMessage('没有可操作的用户', 'warning');
        return;
    }

    if (!confirm(`确定要批量取消关注 ${visibleUsers.length} 个不活跃用户吗？此操作不可撤销！`)) {
        return;
    }

    // TODO: 实现批量取消关注功能
    showMessage('批量操作功能开发中...', 'info');
}

/**
 * 一键更新所有信息（原有版本，保留备用）
 */
async function oneClickUpdateLegacy() {
    if (!isOnline) {
        showMessage('请先在设置页面配置哔哩哔哩Cookie', 'warning');
        return;
    }

    // 显示确认对话框
    const confirmModal = `
        <div class="modal fade" id="oneClickUpdateModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-rocket-takeoff text-primary"></i>
                            一键更新所有信息
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-info">
                            <i class="bi bi-info-circle"></i>
                            此功能将自动执行以下操作：
                        </div>
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item d-flex align-items-center">
                                <i class="bi bi-people text-primary me-2"></i>
                                <div>
                                    <strong>同步关注列表</strong>
                                    <small class="text-muted d-block">更新<strong class="text-primary">所有</strong>关注用户信息</small>
                                </div>
                            </li>
                            <li class="list-group-item d-flex align-items-center">
                                <i class="bi bi-collection text-success me-2"></i>
                                <div>
                                    <strong>更新分组信息</strong>
                                    <small class="text-muted d-block">同步最新的关注分组结构</small>
                                </div>
                            </li>
                            <li class="list-group-item d-flex align-items-center">
                                <i class="bi bi-graph-up text-info me-2"></i>
                                <div>
                                    <strong>同步用户统计</strong>
                                    <small class="text-muted d-block">获取<strong class="text-info">所有</strong>用户粉丝数、视频数等最新数据</small>
                                </div>
                            </li>
                            <li class="list-group-item d-flex align-items-center">
                                <i class="bi bi-trophy text-warning me-2"></i>
                                <div>
                                    <strong>修复等级信息</strong>
                                    <small class="text-muted d-block">更新<strong class="text-warning">所有</strong>等级为0的用户信息</small>
                                </div>
                            </li>
                            <li class="list-group-item d-flex align-items-center">
                                <i class="bi bi-tags text-secondary me-2"></i>
                                <div>
                                    <strong>智能分类</strong>
                                    <small class="text-muted d-block">自动为未分类用户分配合适的类别</small>
                                </div>
                            </li>
                        </ul>
                        <div class="alert alert-warning mt-3">
                            <i class="bi bi-exclamation-triangle"></i>
                            <strong>重要提醒：</strong>
                            <ul class="mb-0 mt-2">
                                <li>本次将同步<strong>全部</strong>用户，可能需要很长时间（1-3小时）</li>
                                <li>已增加API延迟间隔以降低封号风险</li>
                                <li>建议在网络稳定且空闲时执行</li>
                                <li>过程中请保持页面开启，勿关闭浏览器</li>
                                <li>执行过程会有详细的日志记录</li>
                            </ul>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="startOneClickUpdateLegacy()">
                            <i class="bi bi-rocket-takeoff"></i>
                            开始更新
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 移除已存在的模态框
    const existingModal = document.getElementById('oneClickUpdateModal');
    if (existingModal) {
        existingModal.remove();
    }

    // 添加模态框到页面
    document.body.insertAdjacentHTML('beforeend', confirmModal);

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('oneClickUpdateModal'));
    modal.show();
}

/**
 * 开始一键更新（原有版本，保留备用）
 */
async function startOneClickUpdateLegacy() {
    try {
        // 关闭确认对话框
        const confirmModal = bootstrap.Modal.getInstance(document.getElementById('oneClickUpdateModal'));
        confirmModal.hide();

        // 显示全屏进度界面
        showFullScreenProgress();

        // 开始更新
        const response = await fetch('/api/bilibili/one-click-update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (response.ok && result.task_id) {
            showMessage('一键更新任务已启动，正在全力同步...', 'success');

            // 开始轮询获取真实进度
            window.updateTaskId = result.task_id;
            startProgressPolling(result.task_id);
        } else {
            throw new Error(result.detail || '启动更新任务失败');
        }

    } catch (error) {
        console.error('一键更新失败:', error);
        showMessage('一键更新失败: ' + error.message, 'danger');
        hideFullScreenProgress();
    }
}

/**
 * 显示全屏进度界面
 */
function showFullScreenProgress() {
    const fullScreenProgress = `
        <div id="fullScreenProgress" class="position-fixed top-0 start-0 w-100 h-100" 
             style="background: rgba(0,0,0,0.95); z-index: 9999; backdrop-filter: blur(5px);">
            <div class="container-fluid h-100 d-flex flex-column">
                <!-- 顶部标题栏 -->
                <div class="row">
                    <div class="col-12">
                        <div class="text-center text-white pt-4 pb-3">
                            <h2 class="mb-2">
                                <i class="bi bi-rocket-takeoff text-warning me-2"></i>
                                一键更新进行中
                            </h2>
                            <p class="text-light mb-0">正在全力同步您的哔哩哔哩数据，请耐心等待...</p>
                        </div>
                    </div>
                </div>

                <!-- 主要进度区域 -->
                <div class="row flex-grow-1">
                    <!-- 左侧步骤进度 -->
                    <div class="col-lg-4">
                        <div class="card bg-dark border-secondary h-100">
                            <div class="card-header bg-dark border-secondary">
                                <h5 class="text-white mb-0">
                                    <i class="bi bi-list-check me-2"></i>
                                    执行步骤
                                </h5>
                            </div>
                            <div class="card-body">
                                <!-- 总体进度 -->
                                <div class="mb-4">
                                    <div class="d-flex justify-content-between text-light mb-2">
                                        <span>总体进度</span>
                                        <span id="overallProgressText">0%</span>
                                    </div>
                                    <div class="progress" style="height: 12px;">
                                        <div class="progress-bar progress-bar-striped progress-bar-animated bg-success" 
                                             id="overallProgressBar" style="width: 0%"></div>
                                    </div>
                                </div>

                                <!-- 步骤列表 -->
                                <div class="step-list">
                                    <div class="step-item mb-3" id="step-following">
                                        <div class="d-flex align-items-center">
                                            <div class="step-icon me-3">
                                                <div class="spinner-border spinner-border-sm text-primary" id="spinner-following"></div>
                                                <i class="bi bi-check-circle text-success d-none" id="check-following"></i>
                                                <i class="bi bi-x-circle text-danger d-none" id="error-following"></i>
                                            </div>
                                            <div class="flex-grow-1">
                                                <div class="fw-bold text-white">关注列表同步</div>
                                                <small class="text-muted" id="status-following">准备中...</small>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="step-item mb-3" id="step-groups">
                                        <div class="d-flex align-items-center">
                                            <div class="step-icon me-3">
                                                <div class="spinner-border spinner-border-sm text-secondary d-none" id="spinner-groups"></div>
                                                <i class="bi bi-check-circle text-success d-none" id="check-groups"></i>
                                                <i class="bi bi-x-circle text-danger d-none" id="error-groups"></i>
                                            </div>
                                            <div class="flex-grow-1">
                                                <div class="fw-bold text-light">分组信息同步</div>
                                                <small class="text-muted" id="status-groups">等待中...</small>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="step-item mb-3" id="step-stats">
                                        <div class="d-flex align-items-center">
                                            <div class="step-icon me-3">
                                                <div class="spinner-border spinner-border-sm text-secondary d-none" id="spinner-stats"></div>
                                                <i class="bi bi-check-circle text-success d-none" id="check-stats"></i>
                                                <i class="bi bi-x-circle text-danger d-none" id="error-stats"></i>
                                            </div>
                                            <div class="flex-grow-1">
                                                <div class="fw-bold text-light">用户统计同步</div>
                                                <small class="text-muted" id="status-stats">等待中...</small>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="step-item mb-3" id="step-levels">
                                        <div class="d-flex align-items-center">
                                            <div class="step-icon me-3">
                                                <div class="spinner-border spinner-border-sm text-secondary d-none" id="spinner-levels"></div>
                                                <i class="bi bi-check-circle text-success d-none" id="check-levels"></i>
                                                <i class="bi bi-x-circle text-danger d-none" id="error-levels"></i>
                                            </div>
                                            <div class="flex-grow-1">
                                                <div class="fw-bold text-light">等级信息修复</div>
                                                <small class="text-muted" id="status-levels">等待中...</small>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="step-item mb-3" id="step-categorize">
                                        <div class="d-flex align-items-center">
                                            <div class="step-icon me-3">
                                                <div class="spinner-border spinner-border-sm text-secondary d-none" id="spinner-categorize"></div>
                                                <i class="bi bi-check-circle text-success d-none" id="check-categorize"></i>
                                                <i class="bi bi-x-circle text-danger d-none" id="error-categorize"></i>
                                            </div>
                                            <div class="flex-grow-1">
                                                <div class="fw-bold text-light">智能自动分类</div>
                                                <small class="text-muted" id="status-categorize">等待中...</small>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 右侧日志区域 -->
                    <div class="col-lg-8">
                        <div class="card bg-dark border-secondary h-100">
                            <div class="card-header bg-dark border-secondary d-flex justify-content-between align-items-center">
                                <h5 class="text-white mb-0">
                                    <i class="bi bi-terminal me-2"></i>
                                    执行日志
                                </h5>
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-light btn-sm" onclick="clearUpdateLogs()">
                                        <i class="bi bi-trash"></i> 清空
                                    </button>
                                    <button class="btn btn-outline-light btn-sm" onclick="toggleAutoScroll()" id="autoScrollBtn">
                                        <i class="bi bi-arrow-down"></i> 自动滚动
                                    </button>
                                </div>
                            </div>
                            <div class="card-body p-0">
                                <div id="updateLogContainer" class="log-container" 
                                     style="height: 500px; overflow-y: auto; background: #1a1a1a; font-family: 'Courier New', monospace;">
                                    <div class="text-light p-3">
                                        <div class="log-entry">
                                            <span class="text-info">[系统]</span> 
                                            <span class="text-light">一键更新任务已启动，正在初始化...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 底部操作栏 -->
                <div class="row">
                    <div class="col-12">
                        <div class="text-center text-white py-3">
                            <div class="mb-2">
                                <small class="text-muted">开始时间: <span id="startTime">-</span> | 
                                       耗时: <span id="elapsedTime">00:00</span> | 
                                       状态: <span id="taskStatus" class="text-warning">执行中</span>
                                </small>
                            </div>
                            <div id="taskControlsContainer" style="display: none;" class="me-3">
                                <button class="btn btn-outline-warning btn-sm me-2" id="pauseTaskBtn" onclick="controlTask('pause')">
                                    <i class="bi bi-pause-circle"></i> 暂停
                                </button>
                                <button class="btn btn-outline-success btn-sm me-2 d-none" id="resumeTaskBtn" onclick="controlTask('resume')">
                                    <i class="bi bi-play-circle"></i> 继续
                                </button>
                                <button class="btn btn-outline-danger btn-sm" id="stopTaskBtn" onclick="controlTask('stop')">
                                    <i class="bi bi-stop-circle"></i> 停止
                                </button>
                            </div>
                            <button class="btn btn-outline-light btn-sm d-none" id="closeProgressBtn" onclick="hideFullScreenProgress()">
                                <i class="bi bi-x-lg"></i> 关闭
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 移除已存在的全屏进度
    const existing = document.getElementById('fullScreenProgress');
    if (existing) existing.remove();

    // 添加到页面
    document.body.insertAdjacentHTML('beforeend', fullScreenProgress);

    // 初始化
    initializeProgressInterface();
}

/**
 * 初始化进度界面
 */
function initializeProgressInterface() {
    // 设置开始时间
    const startTime = new Date();
    document.getElementById('startTime').textContent = startTime.toLocaleTimeString();

    // 启动时间计时器
    let startTimestamp = Date.now();
    window.progressTimer = setInterval(() => {
        const elapsed = Date.now() - startTimestamp;
        const minutes = Math.floor(elapsed / 60000);
        const seconds = Math.floor((elapsed % 60000) / 1000);
        document.getElementById('elapsedTime').textContent =
            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')} `;
    }, 1000);

    // 初始化自动滚动状态
    window.autoScroll = true;

    // 通知权限在common.js中已自动请求
}

/**
 * 开始进度轮询
 */
function startProgressPolling(taskId) {
    // 清理之前的轮询
    if (window.progressTimer) {
        clearInterval(window.progressTimer);
    }

    // 记录当前任务ID
    window.currentPollingTaskId = taskId;

    const pollProgress = async () => {
        try {
            // 检查是否还是当前任务（避免多任务冲突）
            if (window.currentPollingTaskId !== taskId) {
                console.log(`任务 ${taskId} 已不是当前任务，停止轮询`);
                return;
            }

            // 根据任务模式选择不同的轮询端点
            let endpoint = `/api/bilibili/one-click-update/${taskId}`;
            if (currentTaskMode === 'optimized') {
                endpoint = `/api/bilibili/one-click-update-optimized/${taskId}`;
            } else if (currentTaskMode === 'conservative') {
                endpoint = `/api/bilibili/one-click-update-conservative/${taskId}`;
            }

            const response = await fetch(endpoint);
            if (response.ok) {
                const data = await response.json();
                updateProgressInterface(data);

                // 如果任务还在进行中，继续轮询
                if (data.overall.status === 'running') {
                    setTimeout(pollProgress, 2000); // 每2秒轮询一次
                } else {
                    // 任务完成或失败
                    handleTaskComplete(data);
                }
            } else if (response.status === 404) {
                // 处理404错误
                try {
                    const errorData = await response.json();
                    console.warn('任务404错误:', errorData);

                    if (errorData.detail && errorData.detail.available_tasks) {
                        const availableTasks = errorData.detail.available_tasks;
                        if (availableTasks.length > 0) {
                            addLogEntry('系统', `当前任务已过期，发现其他活跃任务: ${availableTasks.join(', ')}`);
                        } else {
                            addLogEntry('系统', '任务已过期或服务已重启，请刷新页面重新开始');
                        }
                    } else {
                        addLogEntry('系统', `任务 ${taskId} 不存在或已过期`);
                    }

                    // 显示友好的错误信息
                    document.getElementById('taskStatus').textContent = '任务已过期';
                    document.getElementById('taskStatus').className = 'text-warning';
                    addLogEntry('错误', '任务已过期，请刷新页面重新启动任务');

                    // 停止轮询
                    return;

                } catch (parseError) {
                    addLogEntry('错误', `任务查询失败: 404 - 任务不存在或已过期`);
                }
            } else {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        } catch (error) {
            console.error('轮询进度失败:', error);

            // 检查是否是连接被拒绝（服务关闭）
            if (error.message.includes('Failed to fetch') ||
                error.message.includes('CONNECTION_REFUSED') ||
                error.message.includes('fetch')) {

                // 检查服务是否完全不可用
                try {
                    const healthCheck = await fetch('/api/bilibili/status');
                    if (!healthCheck.ok) {
                        throw new Error('Service unavailable');
                    }
                } catch (healthError) {
                    // 服务确实不可用，显示明确的错误信息并停止轮询
                    document.getElementById('taskStatus').textContent = '服务连接中断';
                    document.getElementById('taskStatus').className = 'text-danger';

                    addLogEntry('错误', '⚠️ 服务连接中断！可能的原因：');
                    addLogEntry('', '  • 后台服务意外关闭');
                    addLogEntry('', '  • 遇到严重的API风控限制');
                    addLogEntry('', '  • 网络连接问题');
                    addLogEntry('解决方案', '请重新启动应用程序，然后刷新页面重试');

                    // 停止轮询，避免无意义的重试
                    window.currentPollingTaskId = null;
                    hideTaskControls();
                    return;
                }
            }

            addLogEntry('错误', `轮询进度失败: ${error.message}`);

            // 网络错误时继续尝试轮询，但增加间隔
            setTimeout(pollProgress, 5000);
        }
    };

    pollProgress();
}

/**
 * 更新进度界面
 */
function updateProgressInterface(data) {
    // 更新总体进度
    const overall = data.overall || {};
    const progress = overall.progress || 0;

    document.getElementById('overallProgressBar').style.width = `${progress}%`;
    document.getElementById('overallProgressText').textContent = `${Math.round(progress)}%`;

    // 动态更新预估时间
    updateEstimatedTime(data);

    // 更新各步骤状态
    updateStepStatus('following', data.steps?.sync_following);
    updateStepStatus('groups', data.steps?.groups_sync);
    updateStepStatus('stats', data.steps?.sync_user_stats);
    updateStepStatus('levels', data.steps?.fix_levels);
    updateStepStatus('categorize', data.steps?.auto_categorize);

    // 添加日志条目
    if (data.steps) {
        Object.entries(data.steps).forEach(([stepName, stepData]) => {
            if (stepData.logs && stepData.logs.length > 0) {
                stepData.logs.forEach(log => {
                    if (!window.displayedLogs) window.displayedLogs = new Set();
                    const logKey = `${stepName}-${log}`;
                    if (!window.displayedLogs.has(logKey)) {
                        // 检查是否是特殊格式的日志（包含时间戳和图标）
                        if (log.includes('🚀') || log.includes('✅') || log.includes('❌') ||
                            log.includes('⏸️') || log.includes('▶️') || log.includes('⚡')) {
                            // 直接添加特殊格式的日志，不添加额外的分类前缀
                            addLogEntry('', log);
                        } else {
                            // 普通日志保持原有格式
                            addLogEntry(getStepDisplayName(stepName), log);
                        }
                        window.displayedLogs.add(logKey);
                    }
                });
            }
        });
    }
}

/**
 * 动态更新预估时间
 */
function updateEstimatedTime(data) {
    const overall = data.overall || {};
    const steps = data.steps || {};

    // 只有在关注同步步骤完成后才能准确计算预估时间
    const followingSync = steps.sync_following;
    if (followingSync && followingSync.status === 'completed' && followingSync.details) {
        const totalUsers = followingSync.details.total || followingSync.details.processed;
        const startTime = overall.start_time;
        const currentTime = new Date().toISOString();

        if (totalUsers && startTime) {
            try {
                const start = new Date(startTime);
                const now = new Date(currentTime);
                const elapsedMinutes = (now - start) / (1000 * 60);
                const progress = overall.progress || 0;

                if (progress > 0 && elapsedMinutes > 0) {
                    const totalMinutes = (elapsedMinutes / progress) * 100;
                    const remainingMinutes = Math.max(0, totalMinutes - elapsedMinutes);

                    let estimatedTime;
                    if (remainingMinutes < 1) {
                        estimatedTime = "少于1分钟";
                    } else if (remainingMinutes >= 60) {
                        const hours = Math.floor(remainingMinutes / 60);
                        const minutes = Math.round(remainingMinutes % 60);
                        if (minutes === 0) {
                            estimatedTime = `约${hours}小时`;
                        } else {
                            estimatedTime = `约${hours}小时${minutes}分钟`;
                        }
                    } else {
                        estimatedTime = `约${Math.round(remainingMinutes)}分钟`;
                    }

                    // 更新状态显示
                    const statusElement = document.getElementById('taskStatus');
                    if (statusElement && overall.status === 'running') {
                        statusElement.textContent = `执行中 (剩余${estimatedTime})`;
                    }
                }
            } catch (error) {
                console.error('计算动态预估时间失败:', error);
            }
        }
    }
}

/**
 * 更新步骤状态
 */
function updateStepStatus(stepName, stepData) {
    if (!stepData) return;

    const spinner = document.getElementById(`spinner-${stepName}`);
    const check = document.getElementById(`check-${stepName}`);
    const error = document.getElementById(`error-${stepName}`);
    const status = document.getElementById(`status-${stepName}`);

    // 隐藏所有图标
    spinner?.classList.add('d-none');
    check?.classList.add('d-none');
    error?.classList.add('d-none');

    // 根据状态显示相应图标
    switch (stepData.status) {
        case 'pending':
            status.textContent = '等待中...';
            break;
        case 'running':
            spinner?.classList.remove('d-none');
            status.textContent = '执行中...';
            break;
        case 'completed':
            check?.classList.remove('d-none');
            const details = stepData.details || {};
            if (details.success !== undefined) {
                status.textContent = `已完成(${details.success} / ${details.total || details.processed || 0})`;
            } else if (details.updated !== undefined) {
                status.textContent = `已完成(更新 ${details.updated} 个)`;
            } else {
                status.textContent = '已完成';
            }
            break;
        case 'failed':
            error?.classList.remove('d-none');
            status.textContent = '失败';
            break;
    }
}

/**
 * 获取步骤显示名称
 */
function getStepDisplayName(stepName) {
    const names = {
        'sync_following': '关注同步',
        'groups_sync': '分组同步',
        'sync_user_stats': '统计同步',
        'fix_levels': '等级修复',
        'auto_categorize': '自动分类'
    };
    return names[stepName] || stepName;
}

/**
 * 添加日志条目
 */
function addLogEntry(category, message) {
    const logContainer = document.getElementById('updateLogContainer');
    if (!logContainer) return;

    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry px-3 py-1';

    // 如果category为空，说明message已经包含完整格式，直接显示
    if (!category || category.trim() === '') {
        logEntry.innerHTML = `<span class="text-light">${message}</span>`;
    } else {
        logEntry.innerHTML = `
            <span class="text-muted">[${timestamp}]</span>
            <span class="text-info">[${category}]</span>
            <span class="text-light">${message}</span>
        `;
    }

    logContainer.appendChild(logEntry);

    // 自动滚动到底部
    if (window.autoScroll !== false) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

/**
 * 处理任务完成
 */
function handleTaskComplete(data) {
    clearInterval(window.progressTimer);
    window.currentPollingTaskId = null; // 清理轮询任务ID

    const overall = data.overall || {};
    const summary = data.summary || {};

    if (overall.status === 'completed') {
        document.getElementById('taskStatus').textContent = '已完成';
        document.getElementById('taskStatus').className = 'text-success';

        // 计算实际耗时
        let duration = '未知';
        if (data.start_time && data.end_time) {
            try {
                const startTime = new Date(data.start_time);
                const endTime = new Date(data.end_time);
                const durationMs = endTime - startTime;
                const durationSeconds = Math.floor(durationMs / 1000);

                if (durationSeconds < 60) {
                    duration = `${durationSeconds}秒`;
                } else if (durationSeconds < 3600) {
                    const minutes = Math.floor(durationSeconds / 60);
                    const seconds = durationSeconds % 60;
                    duration = `${minutes}分${seconds}秒`;
                } else {
                    const hours = Math.floor(durationSeconds / 3600);
                    const minutes = Math.floor((durationSeconds % 3600) / 60);
                    duration = `${hours}小时${minutes}分钟`;
                }
            } catch (e) {
                console.error('计算耗时失败:', e);
                // 使用total_duration作为备选
                if (data.total_duration) {
                    const seconds = Math.floor(data.total_duration);
                    if (seconds < 60) {
                        duration = `${seconds}秒`;
                    } else if (seconds < 3600) {
                        const minutes = Math.floor(seconds / 60);
                        const remainingSeconds = seconds % 60;
                        duration = `${minutes}分${remainingSeconds}秒`;
                    } else {
                        const hours = Math.floor(seconds / 3600);
                        const minutes = Math.floor((seconds % 3600) / 60);
                        duration = `${hours}小时${minutes}分钟`;
                    }
                }
            }
        } else if (data.total_duration) {
            // 直接使用total_duration
            const seconds = Math.floor(data.total_duration);
            if (seconds < 60) {
                duration = `${seconds}秒`;
            } else if (seconds < 3600) {
                const minutes = Math.floor(seconds / 60);
                const remainingSeconds = seconds % 60;
                duration = `${minutes}分${remainingSeconds}秒`;
            } else {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                duration = `${hours}小时${minutes}分钟`;
            }
        }

        addLogEntry('系统', `所有任务已完成! 耗时: ${duration}`);
        if (summary.details) {
            addLogEntry('系统', `执行结果: ${summary.details}`);
        }

        // 显示通知
        if (window.BilibiliTool && window.BilibiliTool.sendSuccessNotification) {
            window.BilibiliTool.sendSuccessNotification(
                '一键更新完成',
                '所有数据已同步完成！',
                { requireInteraction: true }
            );
        }

        showMessage('一键更新完成！所有数据已同步。', 'success');

    } else if (overall.status === 'failed') {
        document.getElementById('taskStatus').textContent = '失败';
        document.getElementById('taskStatus').className = 'text-danger';

        addLogEntry('系统', `任务执行失败: ${overall.error || '未知错误'}`);
        showMessage('一键更新失败，请查看日志了解详情。', 'danger');

        // 发送失败通知
        if (window.BilibiliTool && window.BilibiliTool.sendErrorNotification) {
            window.BilibiliTool.sendErrorNotification(
                '一键更新失败',
                overall.error || '未知错误，请查看日志',
                { requireInteraction: true }
            );
        }
    }

    // 隐藏任务控制按钮
    hideTaskControls();

    // 清理任务状态
    currentTaskId = null;
    currentTaskControlState = 'running';

    // 显示关闭按钮
    document.getElementById('closeProgressBtn')?.classList.remove('d-none');

    // 5秒后自动刷新仪表板数据
    setTimeout(() => {
        loadDashboardData();
    }, 5000);
}

/**
 * 清空日志
 */
function clearUpdateLogs() {
    const logContainer = document.getElementById('updateLogContainer');
    if (logContainer) {
        logContainer.innerHTML = `
            <div class="text-light p-3">
                <div class="log-entry">
                    <span class="text-info">[系统]</span>
                    <span class="text-light">日志已清空</span>
                </div>
            </div>
        `;
    }
    window.displayedLogs = new Set();
}

/**
 * 切换自动滚动
 */
function toggleAutoScroll() {
    window.autoScroll = !window.autoScroll;
    const btn = document.getElementById('autoScrollBtn');
    if (btn) {
        if (window.autoScroll) {
            btn.innerHTML = '<i class="bi bi-arrow-down"></i> 自动滚动';
            btn.classList.remove('btn-outline-warning');
            btn.classList.add('btn-outline-light');
        } else {
            btn.innerHTML = '<i class="bi bi-pause"></i> 手动滚动';
            btn.classList.remove('btn-outline-light');
            btn.classList.add('btn-outline-warning');
        }
    }
}

/**
 * 停止更新任务
 */
function stopUpdate() {
    // 这里可以实现停止任务的逻辑
    if (confirm('确定要停止当前更新任务吗？')) {
        addLogEntry('系统', '用户手动停止了更新任务');
        document.getElementById('taskStatus').textContent = '已停止';
        document.getElementById('taskStatus').className = 'text-warning';
        clearInterval(window.progressTimer);
        document.getElementById('closeProgressBtn')?.classList.remove('d-none');
    }
}

/**
 * 隐藏一键更新进度
 */
function hideOneClickUpdateProgress() {
    const progressModal = document.getElementById('oneClickProgressModal');
    if (progressModal) {
        const modal = bootstrap.Modal.getInstance(progressModal);
        if (modal) {
            modal.hide();
        }
        progressModal.remove();
    }
}

/**
 * 刷新仪表板数据
 */
function refreshDashboard() {
    location.reload();
}

// 绑定一键更新按钮事件
document.addEventListener('DOMContentLoaded', function () {
    const oneClickBtn = document.getElementById('one-click-update-btn');
    if (oneClickBtn) {
        oneClickBtn.addEventListener('click', oneClickUpdate);
    }
});

// 全局函数，供其他地方调用
window.startSync = startSync;
window.autoCategories = autoCategories;
window.generateReport = generateReport;
window.showAllInactiveUsers = showAllInactiveUsers;
window.filterInactiveUsers = filterInactiveUsers;
window.unfollowUser = unfollowUser;
window.batchUnfollowInactive = batchUnfollowInactive;
window.oneClickUpdate = oneClickUpdate;
window.startOneClickUpdate = startOneClickUpdate;
window.refreshDashboard = refreshDashboard;

/**
 * 隐藏全屏进度界面
 */
function hideFullScreenProgress() {
    const element = document.getElementById('fullScreenProgress');
    if (element) {
        element.style.opacity = '0';
        setTimeout(() => {
            element.remove();
            clearInterval(window.progressTimer);
        }, 300);
    }
}

function hideOneClickUpdateProgress() {
    // 兼容旧代码
    hideFullScreenProgress();
}

// =============== 保守同步功能 ===============

/**
 * 显示保守同步对话框
 */
function showConservativeSyncDialog() {
    const modal = new bootstrap.Modal(document.getElementById('conservativeSyncModal'));
    modal.show();
}

/**
 * 显示超级保守同步对话框
 */
function showUltraConservativeSyncDialog() {
    const modal = new bootstrap.Modal(document.getElementById('ultraConservativeSyncModal'));
    modal.show();
}

/**
 * 开始保守同步
 */
async function startConservativeSync() {
    const startPos = document.getElementById('conservativeStartPos').value;
    const count = document.getElementById('conservativeCount').value;
    const confirmed = document.getElementById('conservativeConfirm').checked;

    if (!confirmed) {
        showMessage('请确认你已了解保守模式的特点', 'warning');
        return;
    }

    const startPosNum = parseInt(startPos) - 1; // 转换为0基索引
    const countNum = count ? parseInt(count) : null;

    try {
        showMessage('正在启动保守同步...', 'info');

        const params = new URLSearchParams();
        params.append('start_pos', startPosNum);
        if (countNum) {
            params.append('count', countNum);
        }

        const response = await fetch('/api/bilibili/sync-user-stats-conservative', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: params
        });

        const result = await response.json();

        if (response.ok) {
            // 隐藏设置对话框
            const settingsModal = bootstrap.Modal.getInstance(document.getElementById('conservativeSyncModal'));
            settingsModal.hide();

            // 显示进度对话框
            showConservativeProgressModal(result.task_id, 'conservative', result);

            showMessage('保守同步已启动', 'success');
        } else {
            throw new Error(result.detail || '启动保守同步失败');
        }
    } catch (error) {
        console.error('启动保守同步失败:', error);
        showMessage('启动失败: ' + error.message, 'danger');
    }
}

/**
 * 开始超级保守同步
 */
async function startUltraConservativeSync() {
    const startPos = document.getElementById('ultraStartPos').value;
    const count = document.getElementById('ultraCount').value;
    const confirmed = document.getElementById('ultraConfirm').checked;

    if (!confirmed) {
        showMessage('请确认你已了解超级保守模式将使用极长时间', 'warning');
        return;
    }

    const startPosNum = parseInt(startPos) - 1; // 转换为0基索引
    const countNum = count ? parseInt(count) : null;

    // 二次确认
    const estimatedHours = countNum ? (countNum * 47 / 3600).toFixed(1) : '未知';
    if (!confirm(`超级保守模式预计需要 ${estimatedHours} 小时，确定要继续吗？`)) {
        return;
    }

    try {
        showMessage('正在启动超级保守同步...', 'info');

        const params = new URLSearchParams();
        params.append('start_pos', startPosNum);
        if (countNum) {
            params.append('count', countNum);
        }

        const response = await fetch('/api/bilibili/sync-user-stats-ultra-conservative', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: params
        });

        const result = await response.json();

        if (response.ok) {
            // 隐藏设置对话框
            const settingsModal = bootstrap.Modal.getInstance(document.getElementById('ultraConservativeSyncModal'));
            settingsModal.hide();

            // 显示进度对话框
            showConservativeProgressModal(result.task_id, 'ultra_conservative', result);

            showMessage('超级保守同步已启动', 'success');
        } else {
            throw new Error(result.detail || '启动超级保守同步失败');
        }
    } catch (error) {
        console.error('启动超级保守同步失败:', error);
        showMessage('启动失败: ' + error.message, 'danger');
    }
}

/**
 * 显示保守同步进度对话框
 */
function showConservativeProgressModal(taskId, mode, initialData) {
    // 更新标题
    const modeTitle = document.getElementById('conservativeSyncModeTitle');
    modeTitle.textContent = mode === 'ultra_conservative' ? '超级保守模式同步进度' : '保守模式同步进度';

    // 设置初始数据
    document.getElementById('conservativeTaskId').textContent = taskId;
    document.getElementById('conservativeStartTime').textContent = new Date().toLocaleString('zh-CN');
    document.getElementById('conservativeTotalCount').textContent = initialData.total_users || 0;

    // 重置进度显示
    resetConservativeProgress();

    // 显示对话框
    const modal = new bootstrap.Modal(document.getElementById('conservativeSyncProgressModal'));
    modal.show();

    // 开始轮询进度
    window.conservativeSyncTaskId = taskId;
    window.conservativeSyncStartTime = Date.now();
    startConservativeProgressPolling(taskId);
}

/**
 * 重置保守同步进度显示
 */
function resetConservativeProgress() {
    document.getElementById('conservativeSyncProgress').style.width = '0%';
    document.getElementById('conservativeSyncProgress').textContent = '0%';
    document.getElementById('conservativeSuccessCount').textContent = '0';
    document.getElementById('conservativeFailedCount').textContent = '0';
    document.getElementById('conservativeSkippedCount').textContent = '0';
    document.getElementById('conservativeSyncStatus').textContent = '准备开始保守同步...';
    document.getElementById('conservativeSyncCurrentUser').textContent = '';
    document.getElementById('conservativeElapsedTime').textContent = '-';

    // 显示/隐藏相关元素
    document.getElementById('conservativeSyncSpinner').style.display = 'block';
    document.getElementById('conservativeSyncCloseBtn').style.display = 'none';
    document.getElementById('conservativeEstimatedTime').style.display = 'none';
}

/**
 * 开始保守同步进度轮询
 */
function startConservativeProgressPolling(taskId) {
    window.conservativeProgressInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/bilibili/task-progress/${taskId}`);
            const data = await response.json();

            if (response.ok) {
                updateConservativeProgress(data);

                // 检查任务是否完成
                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(window.conservativeProgressInterval);
                    handleConservativeTaskComplete(data);
                }
            } else {
                console.error('获取进度失败:', data);
            }
        } catch (error) {
            console.error('轮询进度时出错:', error);
        }
    }, 2000); // 每2秒轮询一次
}

/**
 * 更新保守同步进度显示
 */
function updateConservativeProgress(data) {
    // 更新进度条
    const progress = data.progress || 0;
    const progressBar = document.getElementById('conservativeSyncProgress');
    progressBar.style.width = progress + '%';
    progressBar.textContent = progress.toFixed(1) + '%';

    // 更新状态文本
    document.getElementById('conservativeSyncStatus').textContent = data.message || '处理中...';
    document.getElementById('conservativeSyncCurrentUser').textContent = data.current_user ? `当前: ${data.current_user}` : '';

    // 更新计数器
    document.getElementById('conservativeSuccessCount').textContent = data.successful_users || 0;
    document.getElementById('conservativeFailedCount').textContent = data.failed_users || 0;
    document.getElementById('conservativeSkippedCount').textContent = data.skipped_users || 0;

    // 更新已用时间
    if (window.conservativeSyncStartTime) {
        const elapsed = Math.floor((Date.now() - window.conservativeSyncStartTime) / 1000);
        const hours = Math.floor(elapsed / 3600);
        const minutes = Math.floor((elapsed % 3600) / 60);
        const seconds = elapsed % 60;

        let timeStr = '';
        if (hours > 0) timeStr += `${hours}小时`;
        if (minutes > 0) timeStr += `${minutes}分钟`;
        timeStr += `${seconds}秒`;

        document.getElementById('conservativeElapsedTime').textContent = timeStr;
    }

    // 预估完成时间
    if (data.processed_users && data.total_users && data.processed_users > 0) {
        const avgTimePerUser = (Date.now() - window.conservativeSyncStartTime) / 1000 / data.processed_users;
        const remainingUsers = data.total_users - data.processed_users;
        const estimatedSeconds = remainingUsers * avgTimePerUser;

        if (estimatedSeconds > 0) {
            const estimatedHours = Math.floor(estimatedSeconds / 3600);
            const estimatedMinutes = Math.floor((estimatedSeconds % 3600) / 60);

            let estimateStr = '';
            if (estimatedHours > 0) estimateStr += `${estimatedHours}小时`;
            if (estimatedMinutes > 0) estimateStr += `${estimatedMinutes}分钟`;

            document.getElementById('conservativeTimeEstimate').textContent = estimateStr || '不到1分钟';
            document.getElementById('conservativeEstimatedTime').style.display = 'block';
        }
    }
}

/**
 * 处理保守同步任务完成
 */
function handleConservativeTaskComplete(data) {
    // 隐藏进度条和Spinner
    document.getElementById('conservativeSyncSpinner').style.display = 'none';
    const progressBar = document.getElementById('conservativeSyncProgress');
    progressBar.classList.remove('progress-bar-animated');

    // 隐藏停止同步按钮，显示关闭和导出按钮
    const stopBtn = document.querySelector('#conservativeSyncProgressModal .btn-danger');
    if (stopBtn) stopBtn.style.display = 'none';
    document.getElementById('conservativeExportBtn').style.display = 'block';
    document.getElementById('conservativeSyncCloseBtn').style.display = 'block';

    // 隐藏预估时间
    document.getElementById('conservativeEstimatedTime').style.display = 'none';

    if (data.status === 'completed') {
        progressBar.classList.add('bg-success');

        // 显示完成状态
        showConservativeCompletionSummary(data);
        showMessage('保守同步完成！', 'success');

        // 更新页面标题
        document.getElementById('conservativeSyncModeTitle').innerHTML =
            '<i class="bi bi-check-circle-fill text-success"></i> 保守同步已完成';

    } else {
        progressBar.classList.add('bg-danger');

        // 显示失败状态
        showConservativeFailureSummary(data);
        showMessage('保守同步失败', 'danger');

        // 更新页面标题
        document.getElementById('conservativeSyncModeTitle').innerHTML =
            '<i class="bi bi-x-circle-fill text-danger"></i> 保守同步失败';
    }

    // 刷新页面数据
    setTimeout(() => {
        loadDashboardData();
    }, 2000);
}

/**
 * 显示保守同步完成摘要
 */
function showConservativeCompletionSummary(data) {
    const startTime = data.start_time ? new Date(data.start_time) : null;
    const endTime = data.end_time ? new Date(data.end_time) : new Date();

    // 计算总耗时
    let duration = '未知';
    if (startTime && endTime) {
        const durationMs = endTime - startTime;
        const hours = Math.floor(durationMs / (1000 * 60 * 60));
        const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((durationMs % (1000 * 60)) / 1000);

        if (hours > 0) {
            duration = `${hours}小时${minutes}分钟${seconds}秒`;
        } else if (minutes > 0) {
            duration = `${minutes}分钟${seconds}秒`;
        } else {
            duration = `${seconds}秒`;
        }
    }

    // 计算平均处理时间
    const avgTime = data.total_users && startTime && endTime ?
        Math.round((endTime - startTime) / 1000 / data.total_users) : 0;

    const summaryHtml = `
        <div class="alert alert-success mb-3">
            <h6 class="mb-3"><i class="bi bi-check-circle-fill"></i> 同步完成摘要</h6>
            <div class="row text-center mb-3">
                <div class="col-3">
                    <div class="h4 text-success mb-1">${data.successful_users || 0}</div>
                    <small class="text-muted">成功处理</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-danger mb-1">${data.failed_users || 0}</div>
                    <small class="text-muted">处理失败</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-warning mb-1">${data.skipped_users || 0}</div>
                    <small class="text-muted">智能跳过</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-info mb-1">${data.total_users || 0}</div>
                    <small class="text-muted">总计</small>
                </div>
            </div>
            
            <hr class="my-3">
            
            <div class="row small text-muted">
                <div class="col-md-6">
                    <div><strong>开始时间：</strong>${startTime ? startTime.toLocaleString('zh-CN') : '未知'}</div>
                    <div><strong>结束时间：</strong>${endTime.toLocaleString('zh-CN')}</div>
                    <div><strong>总耗时：</strong>${duration}</div>
                </div>
                <div class="col-md-6">
                    <div><strong>平均处理时间：</strong>${avgTime}秒/用户</div>
                    <div><strong>成功率：</strong>${data.total_users ? Math.round((data.successful_users || 0) / data.total_users * 100) : 0}%</div>
                    <div><strong>任务ID：</strong>${data.task_id || '未知'}</div>
                </div>
            </div>
            
            ${(data.failed_users || 0) > 0 ? `
                <hr class="my-3">
                <div class="alert alert-warning mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong><i class="bi bi-exclamation-triangle"></i> 处理失败的用户 (${data.failed_users}个)</strong>
                        <button class="btn btn-sm btn-outline-warning" onclick="toggleFailedUserList()">
                            <i class="bi bi-chevron-down"></i> 查看详情
                        </button>
                    </div>
                    <div id="failedUsersList" style="display: none;">
                        ${generateFailedUsersTable(data.failed_user_list || [])}
                    </div>
                    <small><strong>提醒：</strong>失败的用户可稍后重新同步，或查看日志了解详细原因。</small>
                </div>
            ` : ''}
            
            ${(data.skipped_users || 0) > 0 ? `
                <hr class="my-3">
                <div class="alert alert-info mb-0">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong><i class="bi bi-info-circle"></i> 智能跳过的用户 (${data.skipped_users}个)</strong>
                        <button class="btn btn-sm btn-outline-info" onclick="toggleSkippedUserList()">
                            <i class="bi bi-chevron-down"></i> 查看详情
                        </button>
                    </div>
                    <div id="skippedUsersList" style="display: none;">
                        ${generateSkippedUsersTable(data.skipped_user_list || [])}
                    </div>
                    <small><strong>说明：</strong>跳过的用户数据较新，无需重复处理。</small>
                </div>
            ` : ''}
        </div>
    `;

    document.getElementById('conservativeSyncStatus').innerHTML = summaryHtml;
    document.getElementById('conservativeSyncCurrentUser').textContent = '';
}

/**
 * 显示保守同步失败摘要
 */
function showConservativeFailureSummary(data) {
    const startTime = data.start_time ? new Date(data.start_time) : null;
    const endTime = data.end_time ? new Date(data.end_time) : new Date();

    const summaryHtml = `
        <div class="alert alert-danger mb-3">
            <h6 class="mb-3"><i class="bi bi-x-circle-fill"></i> 同步失败摘要</h6>
            <div class="mb-3">
                <strong>失败原因：</strong>${data.message || '未知错误'}
            </div>
            
            <div class="row text-center mb-3">
                <div class="col-3">
                    <div class="h4 text-success mb-1">${data.successful_users || 0}</div>
                    <small class="text-muted">已成功</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-danger mb-1">${data.failed_users || 0}</div>
                    <small class="text-muted">已失败</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-warning mb-1">${data.skipped_users || 0}</div>
                    <small class="text-muted">已跳过</small>
                </div>
                <div class="col-3">
                    <div class="h4 text-muted mb-1">${data.processed_users || 0}</div>
                    <small class="text-muted">已处理</small>
                </div>
            </div>
            
            <hr class="my-3">
            
            <div class="small text-muted">
                <div><strong>开始时间：</strong>${startTime ? startTime.toLocaleString('zh-CN') : '未知'}</div>
                <div><strong>失败时间：</strong>${endTime.toLocaleString('zh-CN')}</div>
                <div><strong>任务ID：</strong>${data.task_id || '未知'}</div>
            </div>
            
            <hr class="my-3">
            
            <div class="alert alert-warning mb-0">
                <small><strong><i class="bi bi-lightbulb"></i> 建议：</strong>
                可以记录当前进度位置，稍后从失败位置继续同步。或尝试使用超级保守模式。</small>
            </div>
        </div>
    `;

    document.getElementById('conservativeSyncStatus').innerHTML = summaryHtml;
    document.getElementById('conservativeSyncCurrentUser').textContent = '';
}

/**
 * 取消保守同步
 */
function cancelConservativeSync() {
    if (window.conservativeProgressInterval) {
        clearInterval(window.conservativeProgressInterval);
    }

    if (window.conservativeSyncTaskId) {
        // 这里可以添加取消任务的API调用
        // 目前只是清理本地状态
        window.conservativeSyncTaskId = null;
        window.conservativeSyncStartTime = null;
    }

    // 隐藏进度对话框
    const modal = bootstrap.Modal.getInstance(document.getElementById('conservativeSyncProgressModal'));
    if (modal) {
        modal.hide();
    }

    showMessage('已取消保守同步监控', 'info');
}

/**
 * 生成失败用户表格
 */
function generateFailedUsersTable(failedUsers) {
    if (!failedUsers || failedUsers.length === 0) {
        return '<small class="text-muted">暂无失败用户详情</small>';
    }

    const maxDisplay = 10; // 最多显示10个
    const displayUsers = failedUsers.slice(0, maxDisplay);
    const hasMore = failedUsers.length > maxDisplay;

    let tableHtml = `
        <div class="table-responsive mt-2">
            <table class="table table-sm table-bordered">
                <thead class="table-warning">
                    <tr>
                        <th width="15%">UID</th>
                        <th width="30%">用户名</th>
                        <th width="55%">失败原因</th>
                    </tr>
                </thead>
                <tbody>
    `;

    displayUsers.forEach(user => {
        tableHtml += `
            <tr>
                <td><small>${user.uid}</small></td>
                <td><small>${user.uname}</small></td>
                <td><small class="text-muted">${user.reason}</small></td>
            </tr>
        `;
    });

    tableHtml += '</tbody></table>';

    if (hasMore) {
        tableHtml += `<small class="text-muted">... 还有 ${failedUsers.length - maxDisplay} 个用户，详情请查看日志</small>`;
    }

    tableHtml += '</div>';

    return tableHtml;
}

/**
 * 生成跳过用户表格
 */
function generateSkippedUsersTable(skippedUsers) {
    if (!skippedUsers || skippedUsers.length === 0) {
        return '<small class="text-muted">暂无跳过用户详情</small>';
    }

    const maxDisplay = 10; // 最多显示10个
    const displayUsers = skippedUsers.slice(0, maxDisplay);
    const hasMore = skippedUsers.length > maxDisplay;

    let tableHtml = `
        <div class="table-responsive mt-2">
            <table class="table table-sm table-bordered">
                <thead class="table-info">
                    <tr>
                        <th width="15%">UID</th>
                        <th width="30%">用户名</th>
                        <th width="55%">跳过原因</th>
                    </tr>
                </thead>
                <tbody>
    `;

    displayUsers.forEach(user => {
        tableHtml += `
            <tr>
                <td><small>${user.uid}</small></td>
                <td><small>${user.uname}</small></td>
                <td><small class="text-muted">${user.reason}</small></td>
            </tr>
        `;
    });

    tableHtml += '</tbody></table>';

    if (hasMore) {
        tableHtml += `<small class="text-muted">... 还有 ${skippedUsers.length - maxDisplay} 个用户</small>`;
    }

    tableHtml += '</div>';

    return tableHtml;
}

/**
 * 切换失败用户列表显示
 */
function toggleFailedUserList() {
    const list = document.getElementById('failedUsersList');
    const btn = event.target.closest('button');
    const icon = btn.querySelector('i');

    if (list.style.display === 'none') {
        list.style.display = 'block';
        icon.className = 'bi bi-chevron-up';
        btn.innerHTML = '<i class="bi bi-chevron-up"></i> 隐藏详情';
    } else {
        list.style.display = 'none';
        icon.className = 'bi bi-chevron-down';
        btn.innerHTML = '<i class="bi bi-chevron-down"></i> 查看详情';
    }
}

/**
 * 切换跳过用户列表显示
 */
function toggleSkippedUserList() {
    const list = document.getElementById('skippedUsersList');
    const btn = event.target.closest('button');
    const icon = btn.querySelector('i');

    if (list.style.display === 'none') {
        list.style.display = 'block';
        icon.className = 'bi bi-chevron-up';
        btn.innerHTML = '<i class="bi bi-chevron-up"></i> 隐藏详情';
    } else {
        list.style.display = 'none';
        icon.className = 'bi bi-chevron-down';
        btn.innerHTML = '<i class="bi bi-chevron-down"></i> 查看详情';
    }
}

/**
 * 导出同步报告
 */
function exportSyncReport() {
    if (!window.conservativeSyncTaskId) {
        showMessage('无法导出报告：任务ID不存在', 'warning');
        return;
    }

    // 获取当前任务数据
    fetch(`/api/bilibili/task-progress/${window.conservativeSyncTaskId}`)
        .then(response => response.json())
        .then(data => {
            const report = generateSyncReport(data);
            downloadReport(report, `保守同步报告_${window.conservativeSyncTaskId}.txt`);
        })
        .catch(error => {
            console.error('导出报告失败:', error);
            showMessage('导出报告失败', 'danger');
        });
}

/**
 * 生成同步报告文本
 */
function generateSyncReport(data) {
    const startTime = data.start_time ? new Date(data.start_time) : null;
    const endTime = data.end_time ? new Date(data.end_time) : new Date();

    // 计算总耗时
    let duration = '未知';
    if (startTime && endTime) {
        const durationMs = endTime - startTime;
        const hours = Math.floor(durationMs / (1000 * 60 * 60));
        const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((durationMs % (1000 * 60)) / 1000);

        if (hours > 0) {
            duration = `${hours}小时${minutes}分钟${seconds}秒`;
        } else if (minutes > 0) {
            duration = `${minutes}分钟${seconds}秒`;
        } else {
            duration = `${seconds}秒`;
        }
    }

    const avgTime = data.total_users && startTime && endTime ?
        Math.round((endTime - startTime) / 1000 / data.total_users) : 0;

    let report = `
=====================================
       哔哩哔哩保守同步报告
=====================================

📊 基本信息
=====================================
任务ID: ${data.task_id}
同步模式: ${data.mode === 'conservative' ? '保守模式' : '超级保守模式'}
开始时间: ${startTime ? startTime.toLocaleString('zh-CN') : '未知'}
结束时间: ${endTime.toLocaleString('zh-CN')}
总耗时: ${duration}
状态: ${data.status === 'completed' ? '已完成' : '失败'}

📈 处理统计
=====================================
总用户数: ${data.total_users || 0}
成功处理: ${data.successful_users || 0}
处理失败: ${data.failed_users || 0}
智能跳过: ${data.skipped_users || 0}
成功率: ${data.total_users ? Math.round((data.successful_users || 0) / data.total_users * 100) : 0}%
平均处理时间: ${avgTime}秒/用户

`;

    // 添加失败用户详情
    if (data.failed_user_list && data.failed_user_list.length > 0) {
        report += `
❌ 处理失败的用户 (${data.failed_user_list.length}个)
=====================================
`;
        data.failed_user_list.forEach((user, index) => {
            report += `${index + 1}. UID: ${user.uid}, 用户名: ${user.uname}\n   失败原因: ${user.reason}\n\n`;
        });
    }

    // 添加跳过用户详情
    if (data.skipped_user_list && data.skipped_user_list.length > 0) {
        report += `
⏭️ 智能跳过的用户 (${data.skipped_user_list.length}个)
=====================================
`;
        data.skipped_user_list.forEach((user, index) => {
            report += `${index + 1}. UID: ${user.uid}, 用户名: ${user.uname}\n   跳过原因: ${user.reason}\n\n`;
        });
    }

    report += `
📝 备注说明
=====================================
• 失败用户可稍后重新同步
• 跳过用户表示数据较新，无需重复处理
• 详细日志请查看系统日志文件

报告生成时间: ${new Date().toLocaleString('zh-CN')}
=====================================
`;

    return report;
}

/**
 * 下载报告文件
 */
function downloadReport(content, filename) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showMessage('同步报告已导出', 'success');
}

// 将保守同步功能暴露到全局作用域
window.showConservativeSyncDialog = showConservativeSyncDialog;
window.showUltraConservativeSyncDialog = showUltraConservativeSyncDialog;
window.startConservativeSync = startConservativeSync;
window.startUltraConservativeSync = startUltraConservativeSync;
window.cancelConservativeSync = cancelConservativeSync;
window.toggleFailedUserList = toggleFailedUserList;
window.toggleSkippedUserList = toggleSkippedUserList;
window.exportSyncReport = exportSyncReport;
window.controlTask = controlTask;
window.updateControlButtons = updateControlButtons;
window.showTaskControls = showTaskControls;
window.hideTaskControls = hideTaskControls;

// 任务控制相关函数

/**
 * 控制任务（暂停/继续/停止）
 */
async function controlTask(action) {
    if (!currentTaskId) {
        showMessage('没有正在运行的任务', 'warning');
        return;
    }

    try {
        const response = await fetch(`/api/bilibili/one-click-update/${currentTaskId}/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                task_id: currentTaskId,
                action: action
            })
        });

        const result = await response.json();

        if (response.ok) {
            currentTaskControlState = action;
            updateControlButtons(action);

            const actionNames = {
                'pause': '暂停',
                'resume': '继续',
                'stop': '停止'
            };
            showMessage(`任务已${actionNames[action]}`, 'success');

            // 添加控制日志
            const timestamp = new Date().toLocaleTimeString();
            const logMessage = `⚡ [${timestamp}] [系统] 用户${actionNames[action]}了任务`;
            addLogEntry('系统', logMessage);

        } else {
            throw new Error(result.error || `${action}任务失败`);
        }
    } catch (error) {
        console.error(`${action}任务失败:`, error);
        showMessage(`${action}任务失败: ` + error.message, 'danger');
    }
}

/**
 * 更新控制按钮状态
 */
function updateControlButtons(state) {
    const pauseBtn = document.getElementById('pauseTaskBtn');
    const resumeBtn = document.getElementById('resumeTaskBtn');
    const stopBtn = document.getElementById('stopTaskBtn');

    if (pauseBtn && resumeBtn && stopBtn) {
        pauseBtn.style.display = state === 'running' ? 'inline-block' : 'none';
        resumeBtn.style.display = state === 'pause' ? 'inline-block' : 'none';
        stopBtn.style.display = (state === 'running' || state === 'pause') ? 'inline-block' : 'none';
    }
}

/**
 * 显示任务控制按钮
 */
function showTaskControls() {
    const controlsContainer = document.getElementById('taskControlsContainer');
    if (controlsContainer) {
        controlsContainer.style.display = 'block';
        updateControlButtons('running');
    }
}

/**
 * 隐藏任务控制按钮
 */
function hideTaskControls() {
    const controlsContainer = document.getElementById('taskControlsContainer');
    if (controlsContainer) {
        controlsContainer.style.display = 'none';
    }
}