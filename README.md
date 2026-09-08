# 雷达新闻 V15.1 · 多源真实新闻生产版

这版的目标不是继续“修 GDELT”，而是把**每天自动产出、手机浏览器可访问、单一数据源失败不阻断**真正闭环。

## 运行链路

GitHub Actions（每天北京时间 08:00）
→ 多源 RSS
→ 国家/梯队
→ 24h 过滤
→ 事件去重
→ 分类
→ 重要性排序
→ `data/daily.json`
→ GitHub Pages
→ 手机浏览器打开

### 与之前版本最大的区别

**GDELT 不再是关键依赖。**

V15 改为“直接媒体 RSS 优先 + Google/Bing 聚合补充”的结构。原因是 Google News/Bing RSS 都不应作为唯一生产数据源；公开资料也显示这些 RSS/search feed 存在返回空结果的情况。citeturn0search9turn0search23

当前优先读取 BBC、DW、NPR、Guardian、Al Jazeera，以及部分国家的 NHK、TASS、SCMP、France24、ABC、CBC、The Hindu 等直接媒体 RSS；国家专属源失败后，再用全球媒体源和 Google/Bing 新闻搜索补充。

**V15 最重要的变化：**
- 不再允许“Actions 绿色 + 新闻 0 条”的假成功；
- 每个国家打印各数据源的原始条目数、24h 有效条目数；
- 自动兼容 RSS 2.0、RDF/RSS、Atom、ISO-8601 时间；
- 直接媒体来源优先于聚合链接；
- 如果 Tier1 最终为 0，Workflow 明确失败，而不是发布空页面；
- 如果已经存在上一份成功日报，则异常时保留上一份，不覆盖成空数据。

尤其是 HTTP 429：
- 不再几十秒、几分钟反复重试；
- 直接进入备用源；
- 单国家失败不影响其他国家；
- 全部源失败时保留上一版。

## 你的仓库应该保持这个结构

```text
Rader-News/
├── index.html
├── manifest.webmanifest
├── sw.js
├── icon.svg
├── data/
│   ├── daily.json
│   └── history/
├── config/
│   └── country_tiers.json
├── scripts/
│   └── build_daily.py
└── .github/
    └── workflows/
        └── daily.yml
```

## 第一次部署

### 1. 把本包全部文件上传到 `franklee24/Rader-News`

不要只上传 HTML。

### 2. 确认 Actions 权限

你之前已经保存好的：

`Settings → Actions → General → Workflow permissions`

保持：

**Read and write permissions**

本工作流显式声明了：

```yaml
permissions:
  contents: write
```

因此 Actions 才能把每日 `daily.json` 提交回仓库。

### 3. 手动运行一次

进入：

`Actions → 雷达新闻每日更新 → Run workflow`

然后等待：

```text
Checkout              ✓
Setup Python          ✓
Build daily news      ✓
Commit daily snapshot ✓
```

成功后，仓库中的：

```text
data/daily.json
```

会发生变化。

### 4. 开启 GitHub Pages

进入：

`Settings → Pages`

选择：

```text
Build and deployment
Source: Deploy from a branch
Branch: main
Folder: / (root)
Save
```

GitHub Pages 会直接把仓库根目录作为网站。

网站地址通常是：

```text
https://franklee24.github.io/Rader-News/
```

### 5. 手机直接打开

手机浏览器打开上面的地址即可。

也可以：

**添加到主屏幕**

这样基本就是一个轻量 App。

## 每天什么时候更新？

工作流：

```yaml
cron: "0 0 * * *"
```

GitHub Actions 使用 UTC，因此对应：

**北京时间每天 08:00。**

另外保留 `workflow_dispatch`，你可以随时手动更新。

## 新闻数量

按照产品规则：

- 第一梯队：美国、中国、英国、法国、德国、俄罗斯、日本，每国目标 20–30
- 第二梯队：印度、巴西、沙特、韩国、加拿大、澳大利亚，每国最多 20
- 第三梯队：乌克兰、意大利、印度尼西亚、土耳其、阿联酋、墨西哥、伊朗、瑞士，每国最多 15
- 第四梯队：新加坡、南非、荷兰、以色列、西班牙、埃及、尼日利亚、阿根廷、波兰、越南，每国最多 10
- 全球补充：10 条

注意：

**数量是上限/目标，不是虚构填充。**

如果 24 小时内没有足够的独立高价值事件，页面会显示实际数量，而不是为了凑 20 条制造重复新闻。

## 事件处理

同一事件由多个媒体报道时，会尝试聚合成一个事件：

```text
事件
├── 来源 A
├── 来源 B
├── 来源 C
└── 来源 D
```

而不是：

```text
A 报道一次
B 报道一次
C 报道一次
```

这样 Global TOP 才是真正的“事件排名”。

## 失败保护

### 情况 A：一个国家请求失败

继续其他国家。

### 情况 B：Google News RSS 429

立即切 Bing News RSS。

### 情况 C：Google + Bing 都失败

记录失败，不阻断整个任务。

### 情况 D：整轮没有拿到任何有效新闻

保留上一份成功 `daily.json`。

**绝不会因为一次网络异常把线上页面刷成空白。**

## 本地测试

不需要安装第三方 Python 包：

```bash
python scripts/build_daily.py
```

生产环境 GitHub Actions 使用 Python 3.12。

## 后续升级方向

V15.1 先把“稳定运营”跑通。

之后再增加：

1. Reuters / AP / BBC / DW / NHK / FT 等来源的直接 RSS/站点适配
2. 来源权威度评分
3. 多语言语义事件聚类
4. 国内新闻专项源
5. 突发新闻 15 分钟监测
6. Telegram / 邮件 / PWA Push
7. Android APK
8. 历史趋势
9. 事件时间线
10. AI 摘要与“为什么重要”

---

## 重要

首次运行前 `data/daily.json` 是**空的启动快照**，这是故意的：

**不使用假新闻充数。**

第一次 Actions 成功以后，它会被真实新闻覆盖。

## V15.1.1 修复说明

本版本修复 GitHub Actions 中可能出现的 `config/country_tiers.json` 路径错误。

`build_daily.py` 现在按以下顺序读取配置：
1. `config.json`（当前 Rader-News 仓库布局）
2. `config/country_tiers.json`（V15.1 原始布局）

因此即使仓库当前已经是 `config.json`，也不会因为找不到旧路径而在启动阶段直接 `exit code 1`。

启动时会先输出 `Config OK: tier1=...` 等配置校验结果，只有配置通过后才开始访问新闻 RSS。

## V15.1.1 / Root-ready 修复

这是**仓库根目录直接覆盖版**。压缩包解压后应直接看到 `.github/`、`scripts/`、`config.json`、`index.html`、`data/` 等文件，不要再套一层文件夹。

本版同时修复：
- `build_daily.py` 错误读取 `config/country_tiers.json` 导致 Actions 启动即 `exit code 1`
- 配置统一使用根目录 `config.json`
- Actions 使用稳定的 `actions/checkout@v4`、`actions/setup-python@v5`
- 每日任务使用 UTC `0 0 * * *`，对应北京时间 08:00
- 执行前增加 Python 语法校验

## V15.1.3 修复说明

修复 GitHub Actions 实际运行时的 `KeyError: 0`。

日志显示配置加载已经成功：

`Config OK: tier1=7, tier2=6, tier3=8, tier4=10`

随后程序在 `name=c[0]` 崩溃。原因是当前 `config.json` 的国家条目是对象（dict），例如 `{"name":"美国","en":"United States","code":"US","min":20,"max":30}`，旧代码却把它当作位置列表。Python 对不存在的字典键 `0` 会抛出 `KeyError`。citeturn0search1

本版统一通过 `normalize_country()` 读取，并兼容旧列表格式；同时增加启动前配置结构校验。


## V15.1 本次修复

本次针对 GitHub Actions 已成功但网站显示 `Tier 1=0 / 全部国家=0 / GLOBAL TOP=0` 的问题进行重构。

根因不是 GitHub Pages，而是新闻采集层过度依赖单一 Google News RSS 查询；即使 HTTP 请求没有报错，也可能得到空 RSS，因此旧版本会“正常结束”并生成空日报。

V15.1 改为多源直连：国家专属媒体 RSS → 全球媒体 RSS → Google News RSS → Bing News RSS，并加入真实数据质量门禁。

首次运行时请重点查看 Actions 的 `Build daily news` 日志。每个国家都会出现类似：

```text
[美国] sources=NPR World:xx | BBC US:xx | ... | Google:xx | pool24h=xx
[tier1] 美国: xx candidates
```

其中 `pool24h` 是通过 24 小时过滤后的真实候选新闻数。

## V15.1 本次修复重点

1. **不再把空的 bootstrap 快照当成成功结果**：首次真实采集如果没有任何事件，`build_daily.py` 直接返回失败，Actions 会显示红色，而不会提交“0 条新闻”的假成功。
2. **Tier 1 零数据直接阻止发布**：美国、中国、英国、法国、德国、俄罗斯、日本全部没有可用事件时，不允许生成成功日报。
3. **多源采集**：国家专属媒体 RSS + 全球媒体 RSS + Google News RSS + Bing News RSS；聚合源只作为补充。
4. **Google News 按国家本地化参数请求**，避免所有国家都使用美国英文区域。
5. **保留来源诊断**：每个国家的源数量、抓取结果和失败信息写入 `source_diagnostics`，方便在 Actions 日志定位。
6. **Pages 独立部署工作流**：`deploy.yml` 在“每日更新”成功后再发布 Pages，避免数据提交和网页部署时序问题。
7. **前端状态**：bootstrap 显示 `WAITING`，异常快照显示 `STALE`，真正成功才显示 `LIVE`，不再把 0 条数据伪装成 LIVE。
