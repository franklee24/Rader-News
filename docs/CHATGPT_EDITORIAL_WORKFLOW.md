# Radar-News：无 API 的 ChatGPT 编辑审核流程

该流程不调用模型 API、不需要 API Key，也不自动操作 ChatGPT 网页。它采用可审计的人工交接：GitHub Actions 生成新闻包，用户把提示词交给 ChatGPT，再将返回的 JSON 交回脚本。

## 1. 生成待审核新闻包

在 GitHub Actions 运行 **ChatGPT 新闻编辑审核包（无 API）** 工作流。PR 修改相关脚本时也会自动运行隔离验证；该工作流会重新抓取新闻、应用规则评分并生成 artifact，只上传文件，不提交日报、不部署 GitHub Pages。

下载 artifact `chatgpt-editorial-review`，其中包含：
- `chatgpt_review_prompt.md`：可直接整体粘贴到 ChatGPT 的提示词和新闻 JSON。
- `chatgpt_review_input.json`：本批输入及每条新闻的稳定 id。

单批最多 120 条新闻，避免提示词过长。

## 2. 在 ChatGPT 对话框筛选

将 `chatgpt_review_prompt.md` 的完整内容粘贴进 ChatGPT。提示词要求它只返回 JSON，并对每条新闻给出中文标题、0–100 分、置信度、评分理由、事件归类键和待核实事实。

## 3. 导入审核结果

将 ChatGPT 返回的 JSON 保存为 `data/ai_review/chatgpt_response.json`，并确保它与生成该批次的输入属于同一批次。然后运行：

```bash
python scripts/apply_chatgpt_review.py --dry-run
python scripts/apply_chatgpt_review.py
```

导入器会仅接受已知 id，检查评分范围 0–100、置信度至少 0.55、中文标题有效性，并保存原规则分数、AI 评分理由、事件键和待核实事项。未知 id、无效结果和低置信度结果会被跳过。注意：当前 `decision=deprioritize` 仅作为编辑标记保存，不会自动隐藏或移除新闻；页面过滤/抑制逻辑尚未实现。

建议先 dry-run。审核结果必须与原始日报同批，不要把旧批次结果应用到新日报。

## 4. 生产保护

该流程的 Actions 仅生成 artifact，不部署网站，也不会自动合并到 main。应用审核结果前建议在独立分支操作、检查 diff 和测试。生产日报工作流保持独立，只有明确批准发布后才合并/部署。

## 验证范围

PR 自动验证包括 Python 语法、离线契约测试、实时抓取后的日报结构检查、候选 ID 唯一性、候选数量上限和提示词文件生成。真实 ChatGPT 返回结果的质量仍需人工抽查；该流程不把模型输出视为事实来源，待核实事项仍需查证。

## 注意

- ChatGPT 对话不是可被 GitHub Actions 直接调用的后台接口。
- 本流程不需要 API，但从抓取到发布仍需人工将提示词交给 ChatGPT 并回传结果。
- 不要把 API 密钥、Cookie、登录凭据或私人信息放进审核文件。
