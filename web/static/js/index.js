/**
 * 首页JavaScript
 * Index Page JavaScript
 */

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    loadDashboardData();
    initializeCharts();
    setupEventListeners();

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
 * 加载仪表板数据
 */
async function loadDashboardData() {
    try {
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

    // 计算已分类数量
    const categories = data.categories || [];
    const categorizedCount = categories.reduce((sum, cat) => {
        return sum + (cat.category !== '其他' ? cat.count : 0);
    }, 0);

    const categorizedElement = document.getElementById('categorized-count');
    if (categorizedElement) {
        categorizedElement.textContent = formatNumber(categorizedCount);
    }

    // 模拟活跃用户数（实际应该从API获取）
    const activeElement = document.getElementById('active-count');
    if (activeElement) {
        activeElement.textContent = formatNumber(Math.floor(data.total_following * 0.7));
    }

    // 模拟待处理数（实际应该从API获取）
    const pendingElement = document.getElementById('pending-count');
    if (pendingElement) {
        const uncategorized = categories.find(cat => cat.category === '其他');
        pendingElement.textContent = formatNumber(uncategorized ? uncategorized.count : 0);
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
                <img src="${avatarUrl}" 
                     alt="${user.uname}" 
                     class="user-avatar me-3"
                     onerror="this.src='/static/img/default-avatar.svg'"
                     onload="this.style.opacity=1" style="opacity:0; transition: opacity 0.3s ease;">
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

// 全局函数，供其他地方调用
window.startSync = startSync;
window.autoCategories = autoCategories;
window.generateReport = generateReport; 