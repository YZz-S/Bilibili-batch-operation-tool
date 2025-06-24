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
 * 加载数据更新时间信息
 */
async function loadLastUpdatedInfo() {
    try {
        const response = await fetch('/api/data/user-stats/summary');
        const data = await response.json();

        if (response.ok) {
            const lastUpdatedAlert = document.getElementById('lastUpdatedAlert');
            const lastUpdatedText = document.getElementById('lastUpdatedText');

            if (data.time_info.last_updated) {
                const updateTime = new Date(data.time_info.last_updated * 1000);
                const now = new Date();
                const daysDiff = Math.floor((now - updateTime) / (1000 * 60 * 60 * 24));

                let alertClass = 'alert-info';
                let bgGradient = 'linear-gradient(135deg, #e8f5e8 0%, #d4edda 100%)';
                let message = '';

                if (daysDiff === 0) {
                    message = `统计数据已更新至今日 ${updateTime.toLocaleString('zh-CN')}`;
                    alertClass = 'alert-success';
                    bgGradient = 'linear-gradient(135deg, #e8f5e8 0%, #d4edda 100%)';
                } else if (daysDiff <= 3) {
                    message = `统计数据最后更新于 ${daysDiff} 天前 (${updateTime.toLocaleString('zh-CN')})`;
                    alertClass = 'alert-info';
                    bgGradient = 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)';
                } else if (daysDiff <= 7) {
                    message = `统计数据已过期 ${daysDiff} 天 (${updateTime.toLocaleString('zh-CN')})，建议重新同步`;
                    alertClass = 'alert-warning';
                    bgGradient = 'linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%)';
                } else {
                    message = `统计数据严重过期 ${daysDiff} 天 (${updateTime.toLocaleString('zh-CN')})，强烈建议立即同步`;
                    alertClass = 'alert-danger';
                    bgGradient = 'linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%)';
                }

                lastUpdatedText.textContent = message;

                // 更新样式
                lastUpdatedAlert.className = `alert ${alertClass}`;
                lastUpdatedAlert.style.background = bgGradient;
                lastUpdatedAlert.style.display = 'block';
            } else {
                lastUpdatedText.textContent = '暂无统计数据，请先执行"同步真实数据"功能获取准确的用户统计信息';
                lastUpdatedAlert.className = 'alert alert-warning';
                lastUpdatedAlert.style.background = 'linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%)';
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

/**
 * 一键更新所有信息
 */
async function oneClickUpdate() {
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
                        <button type="button" class="btn btn-primary" onclick="startOneClickUpdate()">
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
 * 开始一键更新
 */
async function startOneClickUpdate() {
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
                            <button class="btn btn-outline-danger btn-sm d-none" id="stopTaskBtn" onclick="stopUpdate()">
                                <i class="bi bi-stop-circle"></i> 停止任务
                            </button>
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

    // 请求通知权限
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

/**
 * 开始进度轮询
 */
function startProgressPolling(taskId) {
    const pollProgress = async () => {
        try {
            const response = await fetch(`/api/bilibili/one-click-update/${taskId}`);
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
            } else {
                throw new Error('获取进度失败');
            }
        } catch (error) {
            console.error('轮询进度失败:', error);
            addLogEntry('错误', `轮询进度失败: ${error.message}`);
            // 继续尝试轮询
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

    // 更新各步骤状态
    updateStepStatus('following', data.steps?.following_sync);
    updateStepStatus('groups', data.steps?.groups_sync);
    updateStepStatus('stats', data.steps?.user_stats);
    updateStepStatus('levels', data.steps?.level_fix);
    updateStepStatus('categorize', data.steps?.auto_categorize);

    // 添加日志条目
    if (data.steps) {
        Object.entries(data.steps).forEach(([stepName, stepData]) => {
            if (stepData.logs && stepData.logs.length > 0) {
                stepData.logs.forEach(log => {
                    if (!window.displayedLogs) window.displayedLogs = new Set();
                    const logKey = `${stepName}-${log}`;
                    if (!window.displayedLogs.has(logKey)) {
                        addLogEntry(getStepDisplayName(stepName), log);
                        window.displayedLogs.add(logKey);
                    }
                });
            }
        });
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
        'following_sync': '关注同步',
        'groups_sync': '分组同步',
        'user_stats': '统计同步',
        'level_fix': '等级修复',
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
    logEntry.innerHTML = `
        <span class="text-muted">[${timestamp}]</span>
        <span class="text-info">[${category}]</span>
        <span class="text-light">${message}</span>
    `;

    logContainer.appendChild(logEntry);

    // 自动滚动到底部
    if (window.autoScroll) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

/**
 * 处理任务完成
 */
function handleTaskComplete(data) {
    clearInterval(window.progressTimer);

    const overall = data.overall || {};
    const summary = data.summary || {};

    if (overall.status === 'completed') {
        document.getElementById('taskStatus').textContent = '已完成';
        document.getElementById('taskStatus').className = 'text-success';

        addLogEntry('系统', `所有任务已完成! 耗时: ${summary.duration || '未知'}`);
        if (summary.details) {
            addLogEntry('系统', `执行结果: ${summary.details}`);
        }

        // 显示通知
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('哔哩哔哩一键更新', {
                body: '所有数据已同步完成！',
                icon: '/static/img/default-avatar.png'
            });
        }

        showMessage('一键更新完成！所有数据已同步。', 'success');

    } else if (overall.status === 'failed') {
        document.getElementById('taskStatus').textContent = '失败';
        document.getElementById('taskStatus').className = 'text-danger';

        addLogEntry('系统', `任务执行失败: ${overall.error || '未知错误'}`);
        showMessage('一键更新失败，请查看日志了解详情。', 'danger');
    }

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