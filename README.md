# 雷达新闻 V12｜GitHub Pages 稳定生产版

这一版针对 V11 的实际运行问题进行了重构：

- GitHub-hosted runner，不需要自托管 Runner
- 31 个国家/地区抓取任务
- 最多 3 路并发
- 全局请求间隔控制，降低 GDELT 429 风险
- 单请求 25 秒硬超时
- 429 / 408 / 425 / 500 / 502 / 503 / 504 自动退避
- 每个国家独立失败，不阻塞其他国家
- 国家失败时自动使用上一份成功快照
- 每个国家实时输出进度日志
- 生成前 24 小时独立事件
- Global TOP
- GitHub Pages 自动部署
- 每天北京时间 08:00 自动运行
- 支持 Actions → Run workflow 手动运行

## 你只需要做

1. 取消当前卡住的旧 workflow。
2. 解压本 ZIP，覆盖 `Rader-News` 仓库根目录。
3. 保持 Settings → Actions → General → Workflow permissions 为：
   **Read and write permissions**
4. Settings → Pages：
   **Build and deployment → Source → GitHub Actions**
5. Actions → 雷达新闻每日更新 → Run workflow。

## 正常运行时

Build daily news 日志会逐国显示：

`▶ tier1/美国 开始`
`[tier1/美国] request 1/4`
`[tier1/美国] HTTP 200, xxx articles, xx.xs`
`✓ tier1/美国 完成：xx 个独立事件`

某国失败不会导致整次日报失败；若有上一份成功数据，会显示：

`↩ tier1/美国 使用上一份成功快照：xx 个事件`

## 手机访问

GitHub Pages 成功部署后：

`https://franklee24.github.io/Rader-News/`

手机浏览器直接打开即可。页面读取仓库中的 `data/daily.json`。

## 说明

初始 `data/daily.json` 仍然只是可展示的种子数据；第一次 GitHub Actions 成功执行后才会替换成实时 GDELT 数据。
