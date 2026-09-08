# 雷达新闻｜GitHub Pages 自动更新版

手机浏览器直接打开即可，不需要 APK。

## 自动更新
每天 **08:00（北京时间）**，GitHub Actions 自动运行 `scripts/build_daily.py`：
GDELT DOC 2.0 → 过去24小时候选新闻 → 国家/类别多轮抓取 → URL去重 → 事件聚类 → 多来源合并 → 重要性排序 → `data/daily.json`。

GitHub Actions 支持定时 workflow，并可直接指定 IANA 时区；GDELT DOC 2.0 支持 ArticleList/JSON、timespan 和每次最多 250 条记录，因此这里采用多轮国家/类别查询提高覆盖。

## 部署
1. 新建 GitHub Repository，例如 `leida-news`。
2. 上传本目录全部文件。
3. `Settings → Actions → General`：允许 Actions。
4. `Settings → Pages`：Source 选择 **GitHub Actions**。
5. `Actions → 雷达新闻每日更新 → Run workflow` 手动先跑一次。
6. Pages 发布后，用手机浏览器访问 `https://你的用户名.github.io/leida-news/`。

## 新闻范围
Tier 1：美国、中国、英国、法国、德国、俄罗斯、日本；每国目标20–30。
Tier 2：印度、巴西、沙特阿拉伯、韩国、加拿大、澳大利亚；最多20。
Tier 3：乌克兰、意大利、印度尼西亚、土耳其、阿联酋、墨西哥、伊朗、瑞士；最多15。
Tier 4：新加坡、南非、荷兰、以色列、西班牙、埃及、尼日利亚、阿根廷、波兰、越南；最多10。
分类：政治、宏观经济、金融、产业/商业、科技、能源、国防安全、外交、社会、灾害。

不足目标数量时宁缺毋滥，不生成虚假新闻。
