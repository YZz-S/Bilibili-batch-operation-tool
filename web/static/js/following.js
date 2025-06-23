/**
 * 关注列表页面JavaScript逻辑
 * Following List Page JavaScript Logic
 */

// 全局变量
let currentPage = 1;
let currentCategory = '';
let currentSearch = '';
let currentSort = 'follow_time';
let currentSortOrder = 'desc';
let selectedUsers = new Set();
let allUsers = [];
let categories = [];
let pageSize = 50; // 默认每页50个
let currentCategoryType = 'system'; // 'system' 或 'bilibili'

/**
 * 加载关注列表
 */
async function loadFollowingList(silent = false) {
    try {
        if (!silent) {
            showLoading();
        }

        const params = new URLSearchParams({
            page: currentPage,
            page_size: pageSize,
            search: currentSearch,
            sort_by: currentSort,
            sort_order: currentSortOrder
        });

        // 根据分类类型添加不同的参数
        if (currentCategoryType === 'bilibili') {
            if (currentCategory) {
                // 查找对应的group_id
                const selectedGroup = categories.find(cat => cat.category === currentCategory);
                if (selectedGroup && selectedGroup.group_id !== undefined) {
                    params.append('group_id', selectedGroup.group_id);
                }
            }
        } else {
            if (currentCategory) {
                params.append('category', currentCategory);
            }
        }

        const endpoint = currentCategoryType === 'bilibili' && currentCategory
            ? `/api/bilibili/groups/${categories.find(cat => cat.category === currentCategory)?.group_id || 0}/following`
            : '/api/bilibili/following';

        const response = await fetch(`${endpoint}?${params}`);
        const result = await response.json();

        if (response.ok) {
            allUsers = result.data || [];
            renderUserList(allUsers);
            renderPagination(result.pagination);
            await updateStatistics();
            updateSortUI();

            if (!silent) {
                showMessage('数据加载成功', 'success');
            }
        } else {
            throw new Error(result.message || '加载失败');
        }
    } catch (error) {
        console.error('加载关注列表失败:', error);
        if (!silent) {
            showMessage('加载关注列表失败: ' + error.message, 'danger');
        }
    } finally {
        if (!silent) {
            hideLoading();
        }
    }
}

/**
 * 加载分类列表
 */
async function loadCategories() {
    try {
        const url = currentCategoryType === 'bilibili'
            ? '/api/bilibili/groups'
            : '/api/bilibili/categories';

        const response = await fetch(url);
        const result = await response.json();

        if (response.ok) {
            if (currentCategoryType === 'bilibili') {
                categories = (result.groups || []).map(group => ({
                    category: group.group_name,
                    count: group.user_count || group.count || 0,
                    group_id: group.group_id
                }));
            } else {
                categories = result.categories || [];
            }
            renderCategoryOptions();
        }
    } catch (error) {
        console.error('加载分类失败:', error);
    }
}

/**
 * 切换分类类型
 */
function switchCategoryType(type) {
    if (currentCategoryType === type) return;

    currentCategoryType = type;
    currentCategory = ''; // 重置当前分类筛选
    currentPage = 1; // 重置页面

    // 更新按钮显示
    const btnElement = document.getElementById('categoryTypeBtn');
    if (type === 'bilibili') {
        btnElement.innerHTML = '<i class="fas fa-users"></i> B站分组';
    } else {
        btnElement.innerHTML = '<i class="fas fa-robot"></i> 系统分类';
    }

    // 更新统计卡片标签
    updateStatisticsLabels();

    // 重新加载数据
    loadCategories();
    loadFollowingList();
}

/**
 * 更新统计卡片标签
 */
function updateStatisticsLabels() {
    const categorizedLabel = document.querySelector('#categorizedCount').parentNode.querySelector('.card-text');
    if (categorizedLabel) {
        if (currentCategoryType === 'bilibili') {
            categorizedLabel.textContent = '已分组';
        } else {
            categorizedLabel.textContent = '已分类';
        }
    }
}

/**
 * 渲染用户列表
 */
function renderUserList(users) {
    const userList = document.getElementById('userList');

    if (!users || users.length === 0) {
        userList.innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-users fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">暂无关注用户</h5>
                <p class="text-muted">点击"同步关注列表"获取您的关注数据</p>
            </div>
        `;
        return;
    }

    let html = '';
    users.forEach(user => {
        const isSelected = selectedUsers.has(user.uid);
        const followTime = user.follow_time ? new Date(user.follow_time * 1000).toLocaleDateString() : '未知';

        // 头像处理：优先使用真实头像，如果没有或加载失败则使用默认头像
        let avatarUrl = user.face && user.face.trim() !== '' ? user.face : '/static/img/default-avatar.svg';

        // 如果头像URL不是完整URL，添加https协议
        if (avatarUrl && !avatarUrl.startsWith('http') && !avatarUrl.startsWith('/static/')) {
            avatarUrl = 'https:' + avatarUrl;
        }

        html += `
            <div class="user-card ${isSelected ? 'border-primary' : ''}" data-uid="${user.uid}">
                <div class="d-flex align-items-start">
                    <div class="form-check me-3">
                        <input class="form-check-input user-checkbox" type="checkbox" 
                               ${isSelected ? 'checked' : ''} onchange="toggleUser(${user.uid})">
                    </div>
                    <img src="${avatarUrl}" alt="${user.uname}" class="user-avatar" 
                         onerror="this.src='/static/img/default-avatar.svg'"
                         onload="this.style.opacity=1" style="opacity:0; transition: opacity 0.3s ease;">
                    <div class="user-info">
                        <div class="user-name">
                            ${user.uname}
                            ${(user.vip_type && user.vip_type > 0) ? '<span class="vip-badge">VIP</span>' : ''}
                            ${(user.official_type && user.official_type >= 0) ? '<span class="official-badge">认证</span>' : ''}
                        </div>
                        <div class="user-sign">${user.sign || '这个人很懒，什么都没有写～'}</div>
                        <div class="user-stats">
                            <span><i class="fas fa-trophy"></i> Lv.${user.level || 0}</span>
                            <span><i class="fas fa-calendar"></i> ${followTime}</span>
                            ${user.category ? `<span class="category-tag">${user.category}</span>` : ''}
                        </div>
                    </div>
                    <div class="ms-auto">
                        <div class="dropdown">
                            <button class="btn btn-outline-secondary btn-sm dropdown-toggle"
                                type="button" data-bs-toggle="dropdown">
                                操作
                            </button>
                            <ul class="dropdown-menu">
                                <li><a class="dropdown-item" href="#" onclick="updateUserCategory(${user.uid})">
                                    <i class="fas fa-tag"></i> 修改分类
                                </a></li>
                                <li><a class="dropdown-item" href="#" onclick="unfollowUser(${user.uid})">
                                    <i class="fas fa-user-minus"></i> 取消关注
                                </a></li>
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item" href="https://space.bilibili.com/${user.uid}" target="_blank">
                                    <i class="fas fa-external-link-alt"></i> 访问主页
                                </a></li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    userList.innerHTML = html;
}

/**
 * 渲染分页
 */
function renderPagination(pagination) {
    const paginationElement = document.getElementById('pagination');

    if (!pagination || pagination.pages <= 1) {
        paginationElement.innerHTML = '';
        return;
    }

    let html = '';
    const { page, pages } = pagination;

    // 上一页
    html += `
        <li class="page-item ${page <= 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${page - 1})">上一页</a>
        </li>
    `;

    // 页码
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);

    if (start > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(1)">1</a></li>`;
        if (start > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    for (let i = start; i <= end; i++) {
        html += `
            <li class="page-item ${i === page ? 'active' : ''}">
                <a class="page-link" href="#" onclick="changePage(${i})">${i}</a>
            </li>
        `;
    }

    if (end < pages) {
        if (end < pages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(${pages})">${pages}</a></li>`;
    }

    // 下一页
    html += `
        <li class="page-item ${page >= pages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${page + 1})">下一页</a>
        </li>
    `;

    paginationElement.innerHTML = html;
}

/**
 * 渲染分类选项
 */
function renderCategoryOptions() {
    const categoryFilter = document.getElementById('categoryFilter');

    if (!categoryFilter) {
        console.warn('categoryFilter 元素未找到');
        return;
    }

    let options = '<option value="">所有分类</option>';

    categories.forEach(cat => {
        options += `<option value="${cat.category}">${cat.category} (${cat.count})</option>`;
    });

    categoryFilter.innerHTML = options;

    // 只在batchCategory元素存在时更新它
    const batchCategory = document.getElementById('batchCategory');
    if (batchCategory) {
        let batchOptions = '<option value="">选择分类</option>';
        categories.forEach(cat => {
            batchOptions += `<option value="${cat.category}">${cat.category}</option>`;
        });
        batchCategory.innerHTML = batchOptions;
    }
}

/**
 * 更新统计信息
 */
async function updateStatistics() {
    // 添加更新动画
    const statsCards = document.getElementById('statisticsCards');
    if (statsCards) {
        statsCards.classList.add('stats-updating');
    }

    try {
        // 根据分类类型选择不同的API
        const statsUrl = currentCategoryType === 'bilibili'
            ? '/api/bilibili/groups-stats'
            : '/api/bilibili/statistics';

        const response = await fetch(statsUrl);
        if (response.ok) {
            const stats = await response.json();

            animateCountUpdate('totalCount', stats.total_count || 0);

            // 根据分类类型显示不同的统计信息
            if (currentCategoryType === 'bilibili') {
                animateCountUpdate('categorizedCount', stats.grouped_count || 0);
            } else {
                animateCountUpdate('categorizedCount', stats.categorized_count || 0);
            }

            animateCountUpdate('vipCount', stats.vip_count || 0);
            animateCountUpdate('officialCount', stats.official_count || 0);

            // 移除更新动画
            setTimeout(() => {
                if (statsCards) {
                    statsCards.classList.remove('stats-updating');
                }
            }, 300);
            return;
        }
    } catch (error) {
        console.warn('获取统计数据失败，使用本地计算:', error);
    }

    // 如果API失败，则使用本地数据计算
    let totalCount = 0;
    let categorizedCount = 0;
    let vipCount = 0;
    let officialCount = 0;

    allUsers.forEach(user => {
        totalCount++;

        // 已分类用户：有category且不为空、不为null、不为"其他"
        if (user.category && user.category.trim() !== '' && user.category !== '其他' && user.category !== 'null') {
            categorizedCount++;
        }

        // VIP用户：vip_type > 0
        if (user.vip_type && user.vip_type > 0) {
            vipCount++;
        }

        // 认证用户：official_type > 0 (0表示未认证，1表示个人认证，2表示机构认证)
        if (user.official_type && user.official_type > 0) {
            officialCount++;
        }
    });

    animateCountUpdate('totalCount', totalCount);
    animateCountUpdate('categorizedCount', categorizedCount);
    animateCountUpdate('vipCount', vipCount);
    animateCountUpdate('officialCount', officialCount);

    // 移除更新动画
    setTimeout(() => {
        if (statsCards) {
            statsCards.classList.remove('stats-updating');
        }
    }, 300);
}

/**
 * 数字动画更新
 */
function animateCountUpdate(elementId, newValue) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const icon = element.querySelector('i');
    const iconHtml = icon ? icon.outerHTML + ' ' : '';
    const currentValue = parseInt(element.textContent.replace(/\D/g, '')) || 0;

    if (currentValue === newValue) return;

    const increment = newValue > currentValue ? 1 : -1;
    const stepTime = Math.abs(Math.floor(300 / Math.abs(newValue - currentValue)));

    let current = currentValue;
    const timer = setInterval(() => {
        current += increment;
        element.innerHTML = iconHtml + current;

        if (current === newValue) {
            clearInterval(timer);
        }
    }, Math.max(stepTime, 10));
}

/**
 * 刷新数据
 */
async function refreshData() {
    const refreshBtn = document.getElementById('refreshBtn');

    // 添加加载状态
    if (refreshBtn) {
        refreshBtn.classList.add('loading');
        refreshBtn.disabled = true;
    }

    try {
        showMessage('正在刷新数据...', 'info', 1000);

        // 刷新关注列表和分类
        await loadFollowingList(true);
        await loadCategories();

        showMessage('数据刷新成功！', 'success');
    } catch (error) {
        console.error('刷新数据失败:', error);
        showMessage('刷新数据失败: ' + error.message, 'danger');
    } finally {
        // 移除加载状态
        if (refreshBtn) {
            refreshBtn.classList.remove('loading');
            refreshBtn.disabled = false;
        }
    }
}

/**
 * 切换页面
 */
function changePage(page) {
    if (page < 1) return;
    currentPage = page;
    loadFollowingList();
}

/**
 * 搜索用户
 */
function searchUsers() {
    const searchInput = document.getElementById('searchInput');
    currentSearch = searchInput.value.trim();
    currentPage = 1;
    loadFollowingList();
}

/**
 * 按分类筛选
 */
function filterByCategory() {
    const categoryFilter = document.getElementById('categoryFilter');
    currentCategory = categoryFilter.value;
    currentPage = 1;
    loadFollowingList();
}

/**
 * 排序用户
 */
function sortUsers() {
    const sortBy = document.getElementById('sortBy');
    const sortOrder = document.getElementById('sortOrder');

    if (sortBy) {
        currentSort = sortBy.value;
    }
    if (sortOrder) {
        currentSortOrder = sortOrder.value;
    }

    currentPage = 1; // 重置到第一页
    loadFollowingList();
}

/**
 * 切换用户选择
 */
function toggleUser(uid) {
    if (selectedUsers.has(uid)) {
        selectedUsers.delete(uid);
    } else {
        selectedUsers.add(uid);
    }
    updateSelectionUI();
}

/**
 * 全选/取消全选
 */
function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.user-checkbox');

    if (selectAll.checked) {
        allUsers.forEach(user => selectedUsers.add(user.uid));
        checkboxes.forEach(cb => cb.checked = true);
    } else {
        selectedUsers.clear();
        checkboxes.forEach(cb => cb.checked = false);
    }

    updateSelectionUI();
}

/**
 * 更新选择UI
 */
function updateSelectionUI() {
    const selectedCount = selectedUsers.size;
    const batchOperations = document.getElementById('batchOperations');
    const selectedCountElement = document.getElementById('selectedCount');
    const selectAllCheckbox = document.getElementById('selectAll');

    // 更新选择数量
    if (selectedCountElement) {
        selectedCountElement.textContent = selectedCount;
    }

    // 显示/隐藏批量操作面板
    if (batchOperations) {
        batchOperations.style.display = selectedCount > 0 ? 'block' : 'none';
    }

    // 更新全选复选框状态
    if (selectAllCheckbox) {
        if (selectedCount === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
        } else if (selectedCount === allUsers.length) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
        } else {
            selectAllCheckbox.indeterminate = true;
            selectAllCheckbox.checked = false;
        }
    }
}

/**
 * 同步关注列表
 */
async function syncFollowing() {
    try {
        showLoading();

        const response = await fetch('/api/bilibili/sync', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ force_refresh: true })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage('同步任务已启动，请稍后刷新页面查看结果', 'success');

            // 延迟刷新数据
            setTimeout(() => {
                loadFollowingList();
                loadCategories();
            }, 5000);
        } else {
            throw new Error(result.message || '同步失败');
        }
    } catch (error) {
        console.error('同步失败:', error);
        showMessage('同步失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 自动分类
 */
async function autoCategories() {
    try {
        showLoading();

        const response = await fetch('/api/bilibili/auto-categorize', {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');

            // 刷新数据
            setTimeout(() => {
                loadFollowingList();
                loadCategories();
            }, 2000);
        } else {
            throw new Error(result.message || '自动分类失败');
        }
    } catch (error) {
        console.error('自动分类失败:', error);
        showMessage('自动分类失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 批量更新分类
 */
async function batchUpdateCategory() {
    const batchCategory = document.getElementById('batchCategory');

    if (!batchCategory) {
        showMessage('批量分类功能暂不可用', 'warning');
        return;
    }

    const category = batchCategory.value;
    if (!category) {
        showMessage('请选择分类', 'warning');
        return;
    }

    if (selectedUsers.size === 0) {
        showMessage('请先选择用户', 'warning');
        return;
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/batch-update-category', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                uids: Array.from(selectedUsers),
                category: category
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`成功更新 ${selectedUsers.size} 个用户的分类`, 'success');
            selectedUsers.clear();
            updateSelectionUI();
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '批量更新失败');
        }
    } catch (error) {
        console.error('批量更新分类失败:', error);
        showMessage('批量更新分类失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 批量取消关注
 */
async function batchUnfollow() {
    if (selectedUsers.size === 0) {
        showMessage('请先选择用户', 'warning');
        return;
    }

    if (!confirm(`确定要取消关注 ${selectedUsers.size} 个用户吗？此操作不可撤销！`)) {
        return;
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/batch-unfollow', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                uids: Array.from(selectedUsers)
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');
            selectedUsers.clear();
            updateSelectionUI();
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '批量取消关注失败');
        }
    } catch (error) {
        console.error('批量取消关注失败:', error);
        showMessage('批量取消关注失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 显示加载状态
 */
function showLoading() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'flex';
    }
}

/**
 * 隐藏加载状态
 */
function hideLoading() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
}

/**
 * 更新排序UI
 */
function updateSortUI() {
    const sortBy = document.getElementById('sortBy');
    const sortOrder = document.getElementById('sortOrder');

    if (sortBy) {
        sortBy.value = currentSort;
    }
    if (sortOrder) {
        sortOrder.value = currentSortOrder;
    }
}

/**
 * 更新单个用户分类
 */
async function updateUserCategory(uid) {
    // 获取当前用户信息
    const user = allUsers.find(u => u.uid === uid);
    if (!user) {
        showMessage('用户信息未找到', 'danger');
        return;
    }

    // 创建分类选择提示
    const categoryOptions = categories.map(cat => cat.category).join('\n');
    const newCategory = prompt(`请为用户 ${user.uname} 选择新分类：\n\n可选分类：\n${categoryOptions}\n\n或输入新分类名称：`, user.category || '');

    if (newCategory === null) {
        return; // 用户取消了操作
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/update-category', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                uid: uid,
                category: newCategory.trim()
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`成功更新用户 ${user.uname} 的分类`, 'success');
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '更新失败');
        }
    } catch (error) {
        console.error('更新用户分类失败:', error);
        showMessage('更新用户分类失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 取消关注单个用户
 */
async function unfollowUser(uid) {
    // 获取当前用户信息
    const user = allUsers.find(u => u.uid === uid);
    if (!user) {
        showMessage('用户信息未找到', 'danger');
        return;
    }

    if (!confirm(`确定要取消关注用户 ${user.uname} 吗？此操作不可撤销！`)) {
        return;
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/unfollow', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                uid: uid
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`成功取消关注用户 ${user.uname}`, 'success');
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '取消关注失败');
        }
    } catch (error) {
        console.error('取消关注失败:', error);
        showMessage('取消关注失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 每页显示数量变化处理
 */
function onPageSizeChange() {
    const pageSizeSelect = document.getElementById('pageSizeSelect');
    if (pageSizeSelect) {
        pageSize = parseInt(pageSizeSelect.value);
        currentPage = 1; // 重置到第一页
        loadFollowingList();
    }
}

/**
 * 修复用户等级信息
 */
async function fixUserLevels() {
    if (!confirm('确定要修复所有用户的等级信息吗？这个过程可能需要一些时间，请耐心等待。')) {
        return;
    }

    try {
        showLoading();
        showMessage('正在修复用户等级信息，请耐心等待...', 'info');

        const response = await fetch('/api/bilibili/fix-user-levels', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`等级信息修复完成！总计处理 ${result.total_users} 个用户，成功修复 ${result.fixed_count} 个，失败 ${result.error_count} 个`, 'success');

            // 刷新页面数据
            await loadFollowingList();
        } else {
            throw new Error(result.detail || '修复失败');
        }
    } catch (error) {
        console.error('修复用户等级信息失败:', error);
        showMessage('修复用户等级信息失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 一键更新所有信息
 */
async function oneClickUpdate() {
    // 使用更详细的确认对话框
    const confirmed = confirm(`一键更新全部信息确认

将执行以下操作：
• 同步全部关注列表和分组信息
• 同步全部用户统计数据  
• 修复全部等级为0的用户信息
• 智能自动分类

⚠️ 重要提醒：
• 本次将同步全部用户，可能需要很长时间（1-3小时）
• 已增加API延迟以降低封号风险
• 建议在网络稳定且空闲时执行
• 请保持页面开启，勿关闭浏览器

确定要继续吗？`);

    if (!confirmed) {
        return;
    }

    try {
        showLoading();
        showMessage('正在启动一键更新任务，正在全力同步...', 'info');

        const response = await fetch('/api/bilibili/one-click-update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (response.ok && result.task_id) {
            showMessage('一键更新任务已启动，正在后台执行...', 'success');

            // 显示详细进度提示
            setTimeout(() => {
                showMessage('一键更新正在进行中，这可能需要很长时间，请耐心等待...', 'info');
            }, 3000);

            // 请求通知权限
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }

            // 定时刷新数据（每60秒检查一次）
            let refreshCount = 0;
            const maxRefreshes = 180; // 最多刷新180次（3小时）

            const refreshInterval = setInterval(async () => {
                refreshCount++;
                console.log(`自动刷新数据 ${refreshCount}/${maxRefreshes}`);

                try {
                    await loadFollowingList(true); // 静默刷新
                    await loadCategories();
                } catch (error) {
                    console.error('自动刷新失败:', error);
                }

                if (refreshCount >= maxRefreshes) {
                    clearInterval(refreshInterval);
                    showMessage('已达到最大刷新次数，请手动检查任务状态', 'warning');
                }
            }, 60000);

            // 监控任务状态
            const monitorTask = async () => {
                try {
                    const statusResponse = await fetch(`/api/bilibili/one-click-update/${result.task_id}`);
                    if (statusResponse.ok) {
                        const statusData = await statusResponse.json();
                        if (statusData.overall.status === 'completed') {
                            clearInterval(refreshInterval);
                            showMessage('一键更新已完成！正在刷新数据...', 'success');
                            await loadFollowingList();
                            await loadCategories();

                            // 显示通知
                            if ('Notification' in window && Notification.permission === 'granted') {
                                new Notification('哔哩哔哩一键更新', {
                                    body: '关注列表数据已全部同步完成！',
                                    icon: '/static/img/default-avatar.png'
                                });
                            }
                        } else if (statusData.overall.status === 'failed') {
                            clearInterval(refreshInterval);
                            showMessage('一键更新失败，请检查网络或重试', 'danger');
                        } else {
                            // 任务仍在进行中，继续监控
                            setTimeout(monitorTask, 60000);
                        }
                    }
                } catch (error) {
                    console.error('监控任务状态失败:', error);
                    setTimeout(monitorTask, 60000);
                }
            };

            // 开始监控任务（1分钟后开始）
            setTimeout(monitorTask, 60000);

        } else {
            throw new Error(result.detail || '启动一键更新失败');
        }
    } catch (error) {
        console.error('一键更新失败:', error);
        showMessage('一键更新失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
} 