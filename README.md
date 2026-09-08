# 雷达新闻｜自动更新修复版

这版专门修复上一版出现的 **GDELT 429 Too Many Requests + 空响应 JSON 解析失败**。

## 为什么上一版会失败
原脚本对 31 个国家连续发起 31+ 次 GDELT 请求，没有处理 429，也没有等待/重试；因此 `daily.json` 最终只有错误列表，页面自然显示 0 条。

## 这版怎么修
- GDELT 请求增加 429 重试、`Retry-After`、指数等待。
- 国家采集改为 **国内媒体优先**：使用 GDELT `sourcecountry:`，再按政治/经济/金融/产业/科技/能源/国防/外交/社会/灾害等主题抓取。
- 每个国家串行采集，默认间隔 6 秒，避免突发请求。
- 空响应、非法 JSON 都会被明确记录，不会再生成看似成功但实际为空的数据。
- 每个国家仍然遵守“宁缺毋滥”，不足目标数量就少于目标，不造新闻。
- 每天北京时间 08:07 自动运行；避开整点高峰。GitHub 官方说明 schedule 默认 UTC，也支持 IANA timezone；整点附近可能发生调度延迟。
- 支持手动 Run workflow。
- 手机页面继续读取 `data/daily.json`，不会因浏览器缓存显示旧数据。

## 你需要做
把本包中的文件覆盖到 `franklee24/Rader-News` 仓库：
`.github/workflows/daily.yml`
`config.json`
`scripts/build_daily.py`
`data/daily.json`
`index.html`
`manifest.webmanifest`
`sw.js`

然后：
1. Actions
2. 雷达新闻每日更新
3. Run workflow
4. 等绿色 Success
5. 打开 https://franklee24.github.io/Rader-News/

## 关于每天08:00
这里故意设置为北京时间 **08:07**，不是 08:00。
原因：GitHub 官方说明整点附近可能因为 Actions 高负载而延迟；07 分钟可以降低排队概率。
如果你坚持必须 08:00，可把 cron 改回 `0 0 * * *` + `timezone: Asia/Shanghai`。

## 重要
“GitHub Actions 成功”只代表程序执行完成，不代表新闻采集成功。
本版增加了验证步骤：`daily.json` 必须是合法 JSON，并显示实际事件数与错误数。

GDELT DOC 2.0 ArticleList 支持 24h 时间窗和最多 250 条记录，但其 API 有访问频率限制，因此必须控制请求频率。
