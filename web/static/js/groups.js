/**
 * 关注分组管理页面JavaScript逻辑
 * Groups Management Page JavaScript Logic
 */

// 全局变量
let allGroups = [];
let currentGroupId = null;
let currentGroupUsers = [];
let selectedUsers = new Set();
let currentPage = 1;
let currentSearch = '';
let totalPages = 1;
let pageSize = 50; // 默认每页50个
let currentViewMode = 'detailed'; // 当前视图模式

/**
 * 显示加载状态
 */
function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

/**
 * 隐藏加载状态
 */
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

/**
 * 显示消息提示
 */
function showMessage(message, type = 'info', duration = 3000) {
    const container = document.getElementById('message-container');
    if (!container) return;

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    container.appendChild(alertDiv);

    // 自动移除消息
    if (duration > 0) {
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, duration);
    }
}

/**
 * 加载分组列表
 */
async function loadGroups() {
    try {
        showLoading();

        const response = await fetch('/api/bilibili/groups');

        if (!response.ok) {
            const errorText = await response.text();
            console.error(`分组API请求失败: ${response.status} ${response.statusText}`, errorText);
            throw new Error(`分组API请求失败: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();
        console.log('分组数据:', result);

        allGroups = result.groups || [];
        console.log(`加载了 ${allGroups.length} 个分组:`, allGroups);

        renderGroupsList();
        updateGroupSelectors();
        updateStatistics();

        showMessage(`成功加载 ${allGroups.length} 个分组`, 'success', 1000);
    } catch (error) {
        console.error('加载分组失败:', error);
        showMessage('加载分组失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 渲染分组列表 - 横向布局
 */
function renderGroupsList() {
    const groupsContainer = document.getElementById('groupsHorizontal');
    if (!groupsContainer) return;

    // 保留默认的未分组标签，只更新其他分组
    const ungroupedTag = groupsContainer.querySelector('#group-0');
    groupsContainer.innerHTML = '';

    // 重新添加未分组标签
    if (ungroupedTag) {
        groupsContainer.appendChild(ungroupedTag);
    }

    if (allGroups.length === 0) {
        const emptyTag = document.createElement('div');
        emptyTag.className = 'group-tag disabled';
        emptyTag.innerHTML = `
            <div class="group-tag-content">
                <i class="bi bi-info-circle me-1"></i>
                <span class="group-name">点击"同步分组"获取数据</span>
            </div>
        `;
        groupsContainer.appendChild(emptyTag);
        return;
    }

    // 对分组进行排序：按用户数量降序排列，用户数为0的排在最后
    const sortedGroups = allGroups
        .filter(group => group.group_id !== 0) // 跳过ID为0的分组，因为已经有默认的未分组标签
        .sort((a, b) => {
            const countA = a.actual_count || 0;
            const countB = b.actual_count || 0;

            // 如果都有用户或都没有用户，按数量降序
            if ((countA > 0 && countB > 0) || (countA === 0 && countB === 0)) {
                return countB - countA;
            }
            // 有用户的分组排在前面
            return countA > 0 ? -1 : 1;
        });

    // 渲染排序后的分组
    sortedGroups.forEach(group => {
        const actualCount = group.actual_count || 0;

        const groupTag = document.createElement('div');
        groupTag.className = 'group-tag';
        groupTag.id = `group-${group.group_id}`;
        groupTag.onclick = () => selectGroup(group.group_id);

        // 为空分组添加特殊样式
        if (actualCount === 0) {
            groupTag.classList.add('empty-group-tag');
        }

        groupTag.innerHTML = `
            <div class="group-tag-content">
                <i class="bi bi-collection me-1"></i>
                <span class="group-name" title="${group.group_name}">${group.group_name}</span>
                <span class="group-count-badge">${actualCount}</span>
            </div>
        `;

        groupsContainer.appendChild(groupTag);
    });

    // 更新分组统计信息
    updateGroupsStats();
}

/**
 * 选择分组
 */
async function selectGroup(groupId) {
    // 移除之前的选中状态
    document.querySelectorAll('.group-tag').forEach(tag => {
        tag.classList.remove('active');
    });

    // 添加当前选中状态
    const selectedTag = document.getElementById(`group-${groupId}`);
    if (selectedTag) {
        selectedTag.classList.add('active');
    }

    currentGroupId = groupId;
    currentPage = 1;
    selectedUsers.clear();

    // 更新界面标题
    const groupName = groupId === 0 ? '未分组用户' :
        (allGroups.find(g => g.group_id === groupId)?.group_name || '未知分组');

    document.getElementById('groupContentTitle').textContent = groupName;
    document.getElementById('groupContentDescription').textContent =
        groupId === 0 ? '显示所有未分组的关注用户' : `显示分组"${groupName}"中的关注用户`;

    // 显示操作区域
    document.getElementById('groupContentActions').style.display = 'block';

    // 加载分组用户
    await loadGroupUsers();

    // 更新统计
    updateActiveGroupStats();
}

/**
 * 加载分组用户
 */
async function loadGroupUsers(silent = false) {
    if (currentGroupId === null) return;

    try {
        if (!silent) showLoading();

        const params = new URLSearchParams({
            page: currentPage,
            page_size: pageSize,
            search: currentSearch
        });

        let url = `/api/bilibili/groups/${currentGroupId}/following?${params}`;

        const response = await fetch(url);

        if (!response.ok) {
            const errorText = await response.text();
            console.error(`API请求失败: ${response.status} ${response.statusText}`, errorText);
            throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();
        console.log(`分组 ${currentGroupId} 用户数据:`, result);

        currentGroupUsers = result.data || [];
        renderGroupUsers();
        renderUsersPagination(result.pagination);
        updateBatchActionsVisibility();

        if (!silent) {
            showMessage(`加载成功: 找到 ${currentGroupUsers.length} 个用户`, 'success', 1000);
        }
    } catch (error) {
        console.error('加载分组用户失败:', error);
        if (!silent) {
            showMessage('加载分组用户失败: ' + error.message, 'danger');
        }
    } finally {
        if (!silent) hideLoading();
    }
}

/**
 * 渲染分组用户列表
 */
function renderGroupUsers() {
    const usersList = document.getElementById('groupUsersList');
    if (!usersList) return;

    // 设置视图模式类
    usersList.className = `view-mode-${currentViewMode}`;

    if (currentGroupUsers.length === 0) {
        const groupName = currentGroupId === 0 ? '未分组' :
            (allGroups.find(g => g.group_id === currentGroupId)?.group_name || '该分组');

        usersList.innerHTML = `
            <div class="empty-group">
                <i class="bi bi-person-x"></i>
                <h5>${groupName}暂无用户</h5>
                <p>该分组中还没有关注用户</p>
            </div>
        `;
        return;
    }

    let html = '';
    currentGroupUsers.forEach(user => {
        const isSelected = selectedUsers.has(user.uid);
        const avatarUrl = user.face && user.face.trim() !== '' ?
            (user.face.startsWith('http') ? user.face : 'https:' + user.face) :
            '/static/img/default-avatar.svg';

        // VIP状态
        const vipType = user.vip_type || 0;
        const vipBadge = vipType > 0 ? `<span class="vip-badge">VIP</span>` : '';

        // 认证状态
        const officialType = user.official_type || -1;
        const officialBadge = officialType >= 0 ? `<span class="official-badge">认证</span>` : '';

        // 分类标签
        const category = user.category || '未分类';
        const categoryTag = category !== '未分类' ?
            `<span class="badge bg-secondary me-1">${category}</span>` : '';

        // 根据视图模式生成不同的HTML结构
        if (currentViewMode === 'grid') {
            html += renderUserCardGrid(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag);
        } else if (currentViewMode === 'compact') {
            html += renderUserCardCompact(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag);
        } else {
            html += renderUserCardDetailed(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag);
        }
    });

    usersList.innerHTML = html;
}

/**
 * 切换用户选择状态
 */
function toggleUserSelection(uid) {
    if (selectedUsers.has(uid)) {
        selectedUsers.delete(uid);
    } else {
        selectedUsers.add(uid);
    }

    updateSelectionUI();
    updateBatchActionsVisibility();
}

/**
 * 全选/取消全选用户
 */
function toggleSelectAllUsers() {
    const selectAll = document.getElementById('selectAllUsers');
    const isChecked = selectAll.checked;

    if (isChecked) {
        currentGroupUsers.forEach(user => selectedUsers.add(user.uid));
    } else {
        selectedUsers.clear();
    }

    updateSelectionUI();
    updateBatchActionsVisibility();
}

/**
 * 更新选择状态UI
 */
function updateSelectionUI() {
    // 更新选择计数
    document.getElementById('selectedUsersCount').textContent = selectedUsers.size;

    // 更新全选复选框状态
    const selectAll = document.getElementById('selectAllUsers');
    if (selectedUsers.size === 0) {
        selectAll.indeterminate = false;
        selectAll.checked = false;
    } else if (selectedUsers.size === currentGroupUsers.length) {
        selectAll.indeterminate = false;
        selectAll.checked = true;
    } else {
        selectAll.indeterminate = true;
        selectAll.checked = false;
    }

    // 更新用户卡片选中状态
    document.querySelectorAll('.user-card').forEach(card => {
        const uid = parseInt(card.dataset.uid);
        const checkbox = card.querySelector('input[type="checkbox"]');

        if (selectedUsers.has(uid)) {
            card.classList.add('selected');
            checkbox.checked = true;
        } else {
            card.classList.remove('selected');
            checkbox.checked = false;
        }
    });
}

/**
 * 更新批量操作面板可见性
 */
function updateBatchActionsVisibility() {
    const batchActions = document.getElementById('batchActions');
    if (selectedUsers.size > 0) {
        batchActions.style.display = 'block';
    } else {
        batchActions.style.display = 'none';
    }
}

/**
 * 渲染用户分页
 */
function renderUsersPagination(pagination) {
    const paginationContainer = document.getElementById('usersPagination');
    if (!paginationContainer || !pagination) return;

    const { page, pages, total } = pagination;
    totalPages = pages;

    if (pages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }

    let html = '';

    // 上一页
    html += `
        <li class="page-item ${page <= 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${page - 1})">上一页</a>
        </li>
    `;

    // 页码
    const startPage = Math.max(1, page - 2);
    const endPage = Math.min(pages, page + 2);

    if (startPage > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(1)">1</a></li>`;
        if (startPage > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === page ? 'active' : ''}">
                <a class="page-link" href="#" onclick="goToPage(${i})">${i}</a>
            </li>
        `;
    }

    if (endPage < pages) {
        if (endPage < pages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(${pages})">${pages}</a></li>`;
    }

    // 下一页
    html += `
        <li class="page-item ${page >= pages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${page + 1})">下一页</a>
        </li>
    `;

    paginationContainer.innerHTML = html;
}

/**
 * 跳转到指定页面
 */
async function goToPage(page) {
    if (page < 1 || page > totalPages || page === currentPage) return;

    currentPage = page;
    await loadGroupUsers();
}

/**
 * 搜索用户
 */
function searchUsers() {
    const searchInput = document.getElementById('userSearchInput');
    currentSearch = searchInput.value.trim();
    currentPage = 1;
    loadGroupUsers();
}

/**
 * 搜索分组
 */
function searchGroups() {
    const searchInput = document.getElementById('groupSearchInput');
    const searchTerm = searchInput.value.trim().toLowerCase();

    document.querySelectorAll('.group-card').forEach(card => {
        const groupTitle = card.querySelector('.group-title').textContent.toLowerCase();
        if (groupTitle.includes(searchTerm)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * 更新分组选择器
 */
function updateGroupSelectors() {
    const batchGroupTarget = document.getElementById('batchGroupTarget');
    if (!batchGroupTarget) return;

    let options = '<option value="">选择目标分组</option>';
    options += '<option value="0">未分组</option>';

    allGroups.forEach(group => {
        options += `<option value="${group.group_id}">${group.group_name}</option>`;
    });

    batchGroupTarget.innerHTML = options;
}

/**
 * 同步分组
 */
async function syncGroups() {
    try {
        showLoading();
        showMessage('正在同步分组数据...', 'info');

        await loadGroups();
        showMessage('分组同步成功！', 'success');
    } catch (error) {
        console.error('同步分组失败:', error);
        showMessage('同步分组失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 刷新所有数据
 */
async function refreshAllData() {
    try {
        showLoading();
        showMessage('正在刷新所有数据...', 'info');

        await loadGroups();
        if (currentGroupId !== null) {
            await loadGroupUsers(true);
        }

        showMessage('数据刷新成功！', 'success');
    } catch (error) {
        console.error('刷新数据失败:', error);
        showMessage('刷新数据失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 批量移动到分组
 */
async function batchMoveToGroup() {
    const targetGroupSelect = document.getElementById('batchGroupTarget');
    const targetGroupId = parseInt(targetGroupSelect.value);

    if (isNaN(targetGroupId)) {
        showMessage('请选择目标分组', 'warning');
        return;
    }

    if (selectedUsers.size === 0) {
        showMessage('请先选择用户', 'warning');
        return;
    }

    const targetGroupName = targetGroupId === 0 ? '未分组' :
        (allGroups.find(g => g.group_id === targetGroupId)?.group_name || '未知分组');

    if (!confirm(`确定要将 ${selectedUsers.size} 个用户移动到"${targetGroupName}"吗？`)) {
        return;
    }

    try {
        showLoading();

        const response = await fetch('/api/bilibili/batch-update-group', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                uids: Array.from(selectedUsers),
                group_id: targetGroupId
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');
            selectedUsers.clear();
            updateSelectionUI();
            updateBatchActionsVisibility();

            // 刷新当前分组数据
            await loadGroupUsers(true);
            await loadGroups(); // 更新分组计数
        } else {
            throw new Error(result.message || '批量移动失败');
        }
    } catch (error) {
        console.error('批量移动失败:', error);
        showMessage('批量移动失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 批量取消关注
 */
async function batchUnfollowUsers() {
    if (selectedUsers.size === 0) {
        showMessage('请先选择用户', 'warning');
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
            body: JSON.stringify({
                uids: Array.from(selectedUsers)
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message, 'success');
            selectedUsers.clear();
            updateSelectionUI();
            updateBatchActionsVisibility();

            // 刷新当前分组数据
            await loadGroupUsers(true);
            await loadGroups(); // 更新分组计数
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
 * 取消关注单个用户
 */
async function unfollowSingleUser(uid) {
    const user = currentGroupUsers.find(u => u.uid === uid);
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
                uids: [uid]
            })
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`成功取消关注用户 ${user.uname}`, 'success');

            // 刷新当前分组数据
            await loadGroupUsers(true);
            await loadGroups(); // 更新分组计数
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
 * 显示移动用户对话框
 */
function showMoveUserDialog(uid) {
    // 这里可以实现一个更友好的移动用户对话框
    // 暂时使用简单的prompt
    const user = currentGroupUsers.find(u => u.uid === uid);
    if (!user) return;

    // 创建临时选择
    selectedUsers.clear();
    selectedUsers.add(uid);

    // 显示批量操作面板
    updateBatchActionsVisibility();
    updateSelectionUI();

    showMessage(`已选择用户 ${user.uname}，请在上方选择目标分组并点击"移动到分组"`, 'info');
}

/**
 * 更新统计信息
 */
async function updateStatistics() {
    try {
        // 计算统计数据
        const totalGroups = allGroups.length;
        const groupsWithUsers = allGroups.filter(g => g.actual_count > 0).length;

        // 获取调试数据以检查数据状态
        const debugResponse = await fetch('/api/bilibili/debug/data-status');
        let ungroupedCount = 0;

        if (debugResponse.ok) {
            const debugData = await debugResponse.json();
            ungroupedCount = debugData.ungrouped_users;
            console.log('调试数据:', debugData);
        } else {
            // 备用方案：直接查询未分组用户
            const ungroupedResponse = await fetch('/api/bilibili/groups/0/following?page=1&page_size=1');
            if (ungroupedResponse.ok) {
                const ungroupedResult = await ungroupedResponse.json();
                ungroupedCount = ungroupedResult.pagination ? ungroupedResult.pagination.total : 0;
            }
        }

        // 更新UI
        document.getElementById('totalGroupsCount').innerHTML =
            `<i class="bi bi-collection me-2"></i>${totalGroups}`;
        document.getElementById('groupsWithUsersCount').innerHTML =
            `<i class="bi bi-people me-2"></i>${groupsWithUsers}`;
        document.getElementById('ungroupedUsersCount').innerHTML =
            `<i class="bi bi-person-x me-2"></i>${ungroupedCount}`;

        // 更新未分组数量显示
        const ungroupedCountSpan = document.getElementById('ungrouped-count');
        if (ungroupedCountSpan) {
            ungroupedCountSpan.textContent = ungroupedCount;
        }

        console.log(`统计更新: ${totalGroups} 个分组, ${groupsWithUsers} 个有用户, ${ungroupedCount} 个未分组用户`);

    } catch (error) {
        console.error('更新统计信息失败:', error);
        showMessage('更新统计信息失败: ' + error.message, 'warning');
    }
}

/**
 * 更新当前分组统计
 */
function updateActiveGroupStats() {
    const activeGroupUsersCount = currentGroupUsers ? currentGroupUsers.length : 0;
    document.getElementById('activeGroupUsersCount').innerHTML =
        `<i class="bi bi-person-check me-2"></i>${activeGroupUsersCount}`;
}

/**
 * 统计卡片点击事件
 */
function showAllGroups() {
    // 重置分组选择
    document.querySelectorAll('.group-card').forEach(card => {
        card.classList.remove('active');
    });
    currentGroupId = null;

    document.getElementById('groupContentTitle').textContent = '选择一个分组查看用户';
    document.getElementById('groupContentDescription').textContent = '从左侧分组列表中选择一个分组';
    document.getElementById('groupContentActions').style.display = 'none';

    const usersList = document.getElementById('groupUsersList');
    usersList.innerHTML = `
        <div class="empty-group">
            <i class="bi bi-collection"></i>
            <h5>选择一个分组开始管理</h5>
            <p>从左侧选择分组查看其中的关注用户</p>
        </div>
    `;
}

function showGroupWithUsers() {
    // 高亮显示有用户的分组
    document.querySelectorAll('.group-card').forEach(card => {
        card.classList.remove('active');
    });
    showMessage('已高亮显示有用户的分组', 'info');
}

function showUngroupedUsers() {
    selectGroup(0); // 选择未分组用户
}

function showActiveGroup() {
    if (currentGroupId !== null) {
        showMessage('当前已选择分组', 'info');
    } else {
        showMessage('请先选择一个分组', 'warning');
    }
}

/**
 * 创建新分组
 */
function createNewGroup() {
    const modal = new bootstrap.Modal(document.getElementById('createGroupModal'));
    modal.show();
}

/**
 * 提交创建分组
 */
async function submitCreateGroup() {
    const groupName = document.getElementById('newGroupName').value.trim();

    if (!groupName) {
        showMessage('请输入分组名称', 'warning');
        return;
    }

    try {
        showLoading();

        // 注意：这里只是本地创建，B站API可能不支持创建分组
        showMessage('创建分组功能暂未实现，B站API限制', 'warning');

        // 关闭模态框
        const modal = bootstrap.Modal.getInstance(document.getElementById('createGroupModal'));
        modal.hide();

        // 清空输入
        document.getElementById('newGroupName').value = '';

    } catch (error) {
        console.error('创建分组失败:', error);
        showMessage('创建分组失败: ' + error.message, 'danger');
    } finally {
        hideLoading();
    }
}

/**
 * 编辑分组
 */
function editGroup(groupId) {
    showMessage('编辑分组功能暂未实现', 'info');
}

/**
 * 删除分组
 */
function deleteGroup(groupId) {
    showMessage('删除分组功能暂未实现', 'info');
}

/**
 * 每页显示数量变化处理
 */
function onPageSizeChange() {
    const pageSizeSelect = document.getElementById('pageSizeSelect');
    if (pageSizeSelect) {
        pageSize = parseInt(pageSizeSelect.value);
        currentPage = 1; // 重置到第一页
        loadGroupUsers();
    }
}

/**
 * 渲染详细视图用户卡片
 */
function renderUserCardDetailed(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag) {
    return `
        <div class="user-card ${isSelected ? 'selected' : ''}" data-uid="${user.uid}">
            <div class="d-flex align-items-center">
                <div class="form-check me-3">
                    <input class="form-check-input" type="checkbox" 
                           ${isSelected ? 'checked' : ''} 
                           onchange="toggleUserSelection(${user.uid})" />
                </div>
                <a href="https://space.bilibili.com/${user.uid}" target="_blank" class="avatar-link" title="点击访问 ${user.uname} 的主页">
                    <img src="${avatarUrl}" alt="${user.uname}" class="user-avatar"
                         onerror="this.src='/static/img/default-avatar.svg'" />
                </a>
                <div class="user-info">
                    <div class="user-name">
                        ${user.uname}${vipBadge}${officialBadge}
                    </div>
                    <div class="user-sign">${user.sign || '这个人很懒，什么都没有留下'}</div>
                    <div class="user-stats">
                        <span><i class="bi bi-star"></i> LV${user.level || 0}</span>
                        <span><i class="bi bi-calendar3"></i> 
                            ${user.follow_time ? new Date(user.follow_time * 1000).toLocaleDateString() : '未知'}
                        </span>
                        ${categoryTag}
                    </div>
                </div>
                <div class="ms-auto">
                    ${renderUserActions(user.uid)}
                </div>
            </div>
        </div>
    `;
}

/**
 * 渲染宫格视图用户卡片
 */
function renderUserCardGrid(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag) {
    return `
        <div class="user-card ${isSelected ? 'selected' : ''}" data-uid="${user.uid}">
            <div class="form-check position-absolute top-0 start-0 m-3">
                <input class="form-check-input" type="checkbox" 
                       ${isSelected ? 'checked' : ''} 
                       onchange="toggleUserSelection(${user.uid})" />
            </div>
            <a href="https://space.bilibili.com/${user.uid}" target="_blank" class="avatar-link" title="点击访问 ${user.uname} 的主页">
                <img src="${avatarUrl}" alt="${user.uname}" class="user-avatar"
                     onerror="this.src='/static/img/default-avatar.svg'" />
            </a>
            <div class="user-info">
                <div class="user-name">
                    ${user.uname}${vipBadge}${officialBadge}
                </div>
                <div class="user-sign" style="max-height: 60px; overflow: hidden;">
                    ${user.sign || '这个人很懒，什么都没有留下'}
                </div>
                <div class="user-stats">
                    <span><i class="bi bi-star"></i> LV${user.level || 0}</span>
                    <span><i class="bi bi-calendar3"></i> 
                        ${user.follow_time ? new Date(user.follow_time * 1000).toLocaleDateString() : '未知'}
                    </span>
                    ${categoryTag}
                </div>
            </div>
            <div class="mt-2">
                ${renderUserActions(user.uid)}
            </div>
        </div>
    `;
}

/**
 * 渲染紧凑视图用户卡片
 */
function renderUserCardCompact(user, isSelected, avatarUrl, vipBadge, officialBadge, categoryTag) {
    return `
        <div class="user-card ${isSelected ? 'selected' : ''}" data-uid="${user.uid}">
            <div class="form-check me-2">
                <input class="form-check-input" type="checkbox" 
                       ${isSelected ? 'checked' : ''} 
                       onchange="toggleUserSelection(${user.uid})" />
            </div>
            <a href="https://space.bilibili.com/${user.uid}" target="_blank" class="avatar-link" title="点击访问 ${user.uname} 的主页">
                <img src="${avatarUrl}" alt="${user.uname}" class="user-avatar"
                     onerror="this.src='/static/img/default-avatar.svg'" />
            </a>
            <div class="user-info">
                <div class="user-name">
                    ${user.uname}${vipBadge}${officialBadge}
                </div>
                <div class="user-stats">
                    <span><i class="bi bi-star"></i> LV${user.level || 0}</span>
                    <span><i class="bi bi-calendar3"></i> 
                        ${user.follow_time ? new Date(user.follow_time * 1000).toLocaleDateString() : '未知'}
                    </span>
                    ${categoryTag}
                </div>
            </div>
            <div class="dropdown">
                <button class="btn btn-outline-secondary btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                    <i class="bi bi-three-dots"></i>
                </button>
                <ul class="dropdown-menu">
                    <li><a class="dropdown-item" href="#" onclick="showMoveUserDialog(${user.uid})">
                        <i class="bi bi-arrow-right"></i> 移动到分组
                    </a></li>
                    <li><a class="dropdown-item" href="#" onclick="unfollowSingleUser(${user.uid})">
                        <i class="bi bi-person-dash"></i> 取消关注
                    </a></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><a class="dropdown-item" href="https://space.bilibili.com/${user.uid}" target="_blank">
                        <i class="bi bi-box-arrow-up-right"></i> 访问主页
                    </a></li>
                </ul>
            </div>
        </div>
    `;
}

/**
 * 渲染用户操作菜单
 */
function renderUserActions(uid) {
    return `
        <div class="dropdown">
            <button class="btn btn-outline-secondary btn-sm dropdown-toggle"
                type="button" data-bs-toggle="dropdown">
                操作
            </button>
            <ul class="dropdown-menu">
                <li><a class="dropdown-item" href="#" onclick="showMoveUserDialog(${uid})">
                    <i class="bi bi-arrow-right"></i> 移动到分组
                </a></li>
                <li><a class="dropdown-item" href="#" onclick="unfollowSingleUser(${uid})">
                    <i class="bi bi-person-dash"></i> 取消关注
                </a></li>
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item" href="https://space.bilibili.com/${uid}" target="_blank">
                    <i class="bi bi-box-arrow-up-right"></i> 访问主页
                </a></li>
            </ul>
        </div>
    `;
}

/**
 * 切换视图模式
 */
function changeViewMode(mode) {
    currentViewMode = mode;
    renderGroupUsers();

    // 保存用户偏好
    localStorage.setItem('groupsViewMode', mode);

    showMessage(`已切换到${getViewModeName(mode)}`, 'info', 1000);
}

/**
 * 获取视图模式名称
 */
function getViewModeName(mode) {
    const names = {
        'detailed': '详细视图',
        'grid': '宫格视图',
        'compact': '紧凑视图'
    };
    return names[mode] || '详细视图';
}

/**
 * 更新分组统计信息
 */
function updateGroupsStats() {
    const statsElement = document.getElementById('groupsStats');
    if (!statsElement) return;

    const totalGroups = allGroups.length;
    const groupsWithUsers = allGroups.filter(g => (g.actual_count || 0) > 0).length;
    const emptyGroups = totalGroups - groupsWithUsers;
    const totalUsers = allGroups.reduce((sum, g) => sum + (g.actual_count || 0), 0);

    statsElement.innerHTML = `
        共 ${totalGroups} 个分组，${groupsWithUsers} 个有用户，${emptyGroups} 个空分组，总用户数 ${totalUsers}
    `;
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

            // 刷新当前分组的用户列表
            if (currentGroupId !== null) {
                await loadGroupUsers(true);
            }
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