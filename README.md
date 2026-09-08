# 雷达新闻｜GitHub Pages 自动更新版 V11

这是可直接放进 `franklee24/Rader-News` 的生产版网页项目。

## 目标

- 手机浏览器直接打开，无需 APK。
- 每天北京时间 08:00 自动生成最近 24 小时全球新闻快照。
- Tier 1：美国、中国、英国、法国、德国、俄罗斯、日本，目标 20–30 条/国。
- Tier 2：印度、巴西、沙特阿拉伯、韩国、加拿大、澳大利亚，最多 20 条/国。
- Tier 3：乌克兰、意大利、印度尼西亚、土耳其、阿联酋、墨西哥、伊朗、瑞士，最多 15 条/国。
- Tier 4：新加坡、南非、荷兰、以色列、西班牙、埃及、尼日利亚、阿根廷、波兰、越南，最多 10 条/国。
- Supplement：其他国家/地区/国际组织重大事件，最多 10 条。
- 同一事件多媒体报道合并为一个事件卡，保留多个来源。
- 国内新闻权重：政治/政府、宏观经济/金融、产业/科技、能源、社会/灾害、国防安全、外交等。
- 新闻时间窗口严格限定最近 24 小时。
- GDELT 429 自动重试、退避、限速；单国采用宽查询减少请求次数。
- 如果某国本次抓取失败，不用空数据覆盖已有快照；页面会显示该国数据状态。
- 手动运行与每天定时运行共用同一工作流。

## GitHub 设置

你已经把 Actions 的 Workflow permissions 改成了 Read and write，这正是本项目自动提交 `data/daily.json` 所需要的权限。

另外开启 GitHub Pages：

`Settings → Pages → Build and deployment → Source: GitHub Actions`

然后到：

`Actions → 雷达新闻每日更新 → Run workflow`

第一次建议手动运行。完成后访问：

`https://franklee24.github.io/Rader-News/`

## 自动时间

工作流使用 `Asia/Shanghai` 的 08:00。GitHub Actions 当前支持带 IANA timezone 的 schedule；也可以改成 UTC 00:00。见官方文档。

## 数据源

本项目使用 GDELT DOC 2.0 ArticleList/JSON。GDELT 支持 `timespan=24h`、ArticleList、JSON，并允许 `maxrecords` 提高到 250。

注意：GDELT 是新闻覆盖聚合源，不等于所有事件都来自官方原始发布机构。因此页面保留文章直链，并按来源权威度、来源多样性、事件独立性排序。

## 文件

- `index.html`：手机端雷达新闻界面
- `data/daily.json`：每日静态数据快照
- `scripts/build_daily.py`：抓取、去重、事件聚类、排序、生成快照
- `.github/workflows/daily.yml`：每日 08:00 + 手动运行
- `manifest.webmanifest` / `sw.js`：PWA
- `assets/icon.svg`：雷达图标

## 重要

第一次运行如果 GDELT 临时返回 429，脚本会自动退避重试，并限制请求速率。若仍失败，保留上一份有效快照，不会用空数据把页面清空。


## Pages
工作流会在每日生成后直接把仓库根目录发布到 GitHub Pages，因此不要再配置 `Deploy from branch`。进入 `Settings → Pages`，将 Source 设为 `GitHub Actions`。
