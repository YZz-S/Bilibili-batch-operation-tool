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
            page_size: 20,
            category: currentCategory,
            search: currentSearch,
            sort_by: currentSort,
            sort_order: currentSortOrder
        });

        const response = await fetch(`/api/bilibili/following?${params}`);
        const result = await response.json();

        if (response.ok) {
            allUsers = result.data || [];
            renderUserList(allUsers);
            renderPagination(result.pagination);
            updateStatistics();
            updateSortUI();

            if (!silent) {
                showNotification('数据加载成功', 'success');
            }
        } else {
            throw new Error(result.message || '加载失败');
        }
    } catch (error) {
        console.error('加载关注列表失败:', error);
        if (!silent) {
            showNotification('加载关注列表失败: ' + error.message, 'error');
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
        const response = await fetch('/api/bilibili/categories');
        const result = await response.json();

        if (response.ok) {
            categories = result.categories || [];
            renderCategoryOptions();
        }
    } catch (error) {
        console.error('加载分类失败:', error);
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
                            ${user.vip_type > 0 ? '<span class="vip-badge">VIP</span>' : ''}
                            ${user.official_type >= 0 ? '<span class="official-badge">认证</span>' : ''}
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
            < li class="page-item ${page <= 1 ? 'disabled' : ''}" >
                <a class="page-link" href="#" onclick="changePage(${page - 1})">上一页</a>
        </li >
            `;

    // 页码
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);

    if (start > 1) {
        html += `< li class="page-item" > <a class="page-link" href="#" onclick="changePage(1)">1</a></li > `;
        if (start > 2) {
            html += `< li class="page-item disabled" > <span class="page-link">...</span></li > `;
        }
    }

    for (let i = start; i <= end; i++) {
        html += `
            < li class="page-item ${i === page ? 'active' : ''}" >
                <a class="page-link" href="#" onclick="changePage(${i})">${i}</a>
            </li >
            `;
    }

    if (end < pages) {
        if (end < pages - 1) {
            html += `< li class="page-item disabled" > <span class="page-link">...</span></li > `;
        }
        html += `< li class="page-item" > <a class="page-link" href="#" onclick="changePage(${pages})">${pages}</a></li > `;
    }

    // 下一页
    html += `
            < li class="page-item ${page >= pages ? 'disabled' : ''}" >
                <a class="page-link" href="#" onclick="changePage(${page + 1})">下一页</a>
        </li >
            `;

    paginationElement.innerHTML = html;
}

/**
 * 渲染分类选项
 */
function renderCategoryOptions() {
    const categoryFilter = document.getElementById('categoryFilter');
    const batchCategory = document.getElementById('batchCategory');

    let options = '<option value="">所有分类</option>';
    let batchOptions = '<option value="">选择分类</option>';

    categories.forEach(cat => {
        options += `< option value = "${cat.category}" > ${cat.category} (${cat.count})</option > `;
        batchOptions += `< option value = "${cat.category}" > ${cat.category}</option > `;
    });

    categoryFilter.innerHTML = options;
    batchCategory.innerHTML = batchOptions;
}

/**
 * 更新统计信息
 */
function updateStatistics() {
    let totalCount = 0;
    let categorizedCount = 0;
    let vipCount = 0;
    let officialCount = 0;

    allUsers.forEach(user => {
        totalCount++;
        if (user.category && user.category !== '其他') {
            categorizedCount++;
        }
        if (user.vip_type > 0) {
            vipCount++;
        }
        if (user.official_type >= 0) {
            officialCount++;
        }
    });

    document.getElementById('totalCount').textContent = totalCount;
    document.getElementById('categorizedCount').textContent = categorizedCount;
    document.getElementById('vipCount').textContent = vipCount;
    document.getElementById('officialCount').textContent = officialCount;
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
            showNotification('同步任务已启动，请稍后刷新页面查看结果', 'success');

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
        showNotification('同步失败: ' + error.message, 'error');
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
            showNotification(result.message, 'success');
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '自动分类失败');
        }
    } catch (error) {
        console.error('自动分类失败:', error);
        showNotification('自动分类失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

/**
 * 批量更新分类
 */
async function batchUpdateCategory() {
    const batchCategory = document.getElementById('batchCategory');
    const category = batchCategory.value;

    if (!category) {
        showNotification('请选择分类', 'warning');
        return;
    }

    if (selectedUsers.size === 0) {
        showNotification('请先选择用户', 'warning');
        return;
    }

    try {
        showLoading();

        const promises = Array.from(selectedUsers).map(uid =>
            fetch('/api/bilibili/update-category', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ uid, category })
            })
        );

        await Promise.all(promises);

        showNotification(`成功更新 ${selectedUsers.size} 个用户的分类`, 'success');
        selectedUsers.clear();
        updateSelectionUI();
        loadFollowingList();
        loadCategories();
    } catch (error) {
        console.error('批量更新分类失败:', error);
        showNotification('批量更新分类失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

/**
 * 批量取消关注
 */
async function batchUnfollow() {
    if (selectedUsers.size === 0) {
        showNotification('请先选择用户', 'warning');
        return;
    }

    if (!confirm(`确定要取消关注 ${selectedUsers.size} 个用户吗？此操作不可撤销！`)) {
        return;
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/unfollow', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ uids: Array.from(selectedUsers) })
        });

        const result = await response.json();

        if (response.ok) {
            showNotification(result.message, 'success');
            selectedUsers.clear();
            updateSelectionUI();
            loadFollowingList();
            loadCategories();
        } else {
            throw new Error(result.message || '批量取消关注失败');
        }
    } catch (error) {
        console.error('批量取消关注失败:', error);
        showNotification('批量取消关注失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

/**
 * 显示加载状态
 */
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

/**
 * 隐藏加载状态
 */
function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
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