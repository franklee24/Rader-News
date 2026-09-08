# 雷达新闻｜GitHub Pages 最终自动更新版

这版针对前一版出现的两个问题做了最终收口：

1. GDELT `HTTP 429 Too Many Requests`
2. GitHub Actions 绿色成功但 `daily.json` 实际为 0 条新闻

## 运行方式

- 手机网页：GitHub Pages
- 数据文件：`data/daily.json`
- 新闻采集：GDELT DOC 2.0
- 自动更新时间：北京时间每天 08:07
- 手动更新：Actions → 雷达新闻每日更新 → Run workflow
- 31 个国家：Tier 1/2/3/4 全部参与
- 采集窗口：过去 24 小时
- 空数据不会发布：如果事件数为 0，Actions 直接失败，不会生成“假成功”
- 超过 70% 国家采集失败时，也不会发布

## 你只需要做一次

把本压缩包中的文件覆盖到 `franklee24/Rader-News`：

```text
.github/workflows/daily.yml
scripts/build_daily.py
config.json
data/daily.json
index.html
manifest.webmanifest
sw.js
README.md
```

如果仓库里还有旧版 `daily.yml`，用这里的新版覆盖。

## 第一次验证

进入：

Actions → 雷达新闻每日更新 → Run workflow → Run workflow

正常流程：

```text
Checkout
Setup Python
Build daily news
Validate snapshot
Commit daily snapshot
```

`Build daily news` 会明显比以前慢一些，这是故意的：为了避免 GDELT 429，国家请求之间采用节流，并对 429 做退避重试。

## 看到什么才算成功

不要只看最上面的绿色 Success。

打开 `Build daily news`，应该能看到：

```text
Tier 1/美国: xxx articles -> xx events
Tier 1/中国: xxx articles -> xx events
...
Tier 4/越南: xxx articles -> xx events
WROTE .../data/daily.json xxx
```

然后 `data/daily.json`：

```json
"event_count": 大于0
```

并且：

```json
"country_success": ...
"country_failed": ...
```

## GitHub Pages

你现在的 Pages 地址继续使用：

https://franklee24.github.io/Rader-News/

每天数据更新后，页面会自动读取新的 `data/daily.json`。

## 关于 08:07

这里使用：

```text
cron: 7 0 * * *
```

UTC 00:07 = 北京时间 08:07。

故意避开整点高峰，并且只保留一个每日工作流，避免你之前遇到多个任务同时排队。

## 关于 ChatGPT 每日推送

GitHub Pages 是“网站自动更新”链路。

ChatGPT 内的“每日雷达新闻推送”是另一条链路，二者互不替代。

