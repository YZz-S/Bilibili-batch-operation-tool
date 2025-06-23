# 哔哩哔哩关注列表批量管理工具

一个功能强大的哔哩哔哩关注列表管理工具，支持批量操作、数据可视化和智能分类。

## 功能特性

- 🔍 **自动遍历关注列表**: 自动获取完整关注列表数据
- 📊 **数据可视化**: 支持排序、筛选和统计分析
- 🗂️ **智能分类整理**: 根据UP主类型自动分类
- ✂️ **批量操作**: 支持批量删除、移动分组
- 📈 **观看频次统计**: 分析你的观看习惯
- 🎨 **现代化界面**: 美观易用的Web界面

## 技术栈

- **后端**: Python 3.8+, FastAPI, SQLite
- **前端**: HTML5, CSS3, JavaScript (ES6+)
- **数据处理**: Pandas, Requests
- **可视化**: Chart.js, ECharts

## 安装与使用

### 环境要求

- Python 3.8 或更高版本
- Chrome/Edge 浏览器 (推荐)

### 快速开始

1. **克隆项目**
   ```bash
   git clone https://github.com/your-username/Bilibili-batch-operation-tool.git
   cd Bilibili-batch-operation-tool
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置Cookie**
   - 登录哔哩哔哩网页版
   - 获取Cookie信息
   - 在 `config/config.json` 中配置

4. **启动应用**
   ```bash
   # Windows
   start.bat
   
   # Linux/macOS
   ./start.sh
   ```

5. **访问界面**
   打开浏览器访问: http://localhost:8080

## 配置说明

### Cookie获取方法

1. 登录 https://www.bilibili.com
2. 按F12打开开发者工具
3. 在Network标签页刷新页面
4. 找到第一个请求，复制Cookie值
5. 粘贴到配置文件中

### 配置文件示例

```json
{
  "bilibili": {
    "cookie": "你的Cookie信息",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
  },
  "database": {
    "path": "data/bilibili.db"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8080
  }
}
```

## 功能说明

### 1. 关注列表管理
- 获取完整关注列表
- 查看UP主详细信息
- 支持搜索和筛选

### 2. 智能分类
- 游戏类
- 知识类
- 生活类
- 娱乐类
- 科技类
- 等等...

### 3. 批量操作
- 批量取消关注
- 批量移动到分组
- 批量设置特别关注

### 4. 数据分析
- 关注时间分布
- UP主类型统计
- 观看频次分析
- 活跃度统计

## 免责声明

本工具仅供学习和个人使用，请遵守哔哩哔哩的服务条款。使用本工具所产生的任何后果由用户自行承担。

## 许可证

本项目采用 Apache 2.0 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.0.0 (2025-06-23)
- 初始版本发布
- 基础功能实现
- Web界面完成 