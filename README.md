# 雷达新闻｜GitHub Pages 自动更新修复版

## 这版解决什么
- 手机浏览器直接访问 GitHub Pages。
- 页面固定读取 `./data/daily.json`，并使用 `cache:no-store` + 时间戳防止旧缓存。
- GitHub Actions 每天北京时间 08:00 自动运行。
- 支持手动 `Run workflow` 立即测试。
- GDELT DOC 2.0 ArticleList 作为新闻入口；程序按国家梯队采集过去 24 小时数据、分类、去重、评分后生成日报。
- 页面即使数据加载失败，也会明确显示 DATA ERROR，而不是静默显示 0 条。

## 你现在要做的
1. 把本目录中的文件上传到 `Rader-News` 仓库根目录，覆盖原来的同名文件。
2. 重点确保：
   `.github/workflows/daily.yml`
   `index.html`
   `data/daily.json`
   `scripts/build_daily.py`
   `config.json`
   `manifest.webmanifest`
   `sw.js`
   都在仓库根目录对应位置。
3. GitHub → Actions → `雷达新闻每日更新` → `Run workflow` → `Run workflow`。
4. 等运行完成并显示绿色。
5. 打开：
   https://franklee24.github.io/Rader-News/
6. 手机浏览器刷新页面。第一次运行后会出现真实新闻。

## 每日更新
GitHub Actions 的 cron 使用 UTC；`0 0 * * *` 对应北京时间每天 08:00。
如果某天 GitHub 调度延迟，手动运行仍可立即更新。

## 注意
- 当前环境不能替你执行 GitHub 上的真实 GDELT 网络请求，所以首次真实数据采集必须在 GitHub Actions runner 上运行。
- 新闻数量是“目标上限”，不是硬造数量；如果过去 24 小时独立高价值事件不足，程序会少于目标。
- 原始来源链接来自 GDELT 返回的文章 URL，点击事件可查看来源。
