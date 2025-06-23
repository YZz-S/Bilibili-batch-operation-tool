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
                        <img src="${user.face || '/static/img/default-avatar.svg'}" 
                             class="rounded-circle" 
                             width="40" height="40" 
                             alt="${user.uname}"
                             onerror="this.src='/static/img/default-avatar.svg'">
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

// 全局函数，供其他地方调用
window.startSync = startSync;
window.autoCategories = autoCategories;
window.generateReport = generateReport;
window.showAllInactiveUsers = showAllInactiveUsers;
window.filterInactiveUsers = filterInactiveUsers;
window.unfollowUser = unfollowUser;
window.batchUnfollowInactive = batchUnfollowInactive; 