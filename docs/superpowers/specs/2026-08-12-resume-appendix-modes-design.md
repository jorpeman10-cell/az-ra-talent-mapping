# 简历报告附录双模式设计 / Resume Appendix Dual-Mode Design

## 1. 目标 / Goal

在不降低简历解析质量的前提下，为 T-STAR/通用候选人报告提供两种明确、可审计的交付模式：

1. `structured_only`：仅输出标准化简历，不包含原始简历页面或原始文本附录。
2. `structured_with_original_pdf`：输出同一份标准化简历，并在报告末尾逐页嵌入原始 PDF 页面。

AZ 报告继续使用客户指定模板，固定为 `az_client_template`，不允许被 T-STAR 模式覆盖。

## 2. 产品行为 / Product Behavior

### 2.1 标准化简历模式

- 简历始终经过解析，填入标准化模板中的个人信息、教育经历、工作经历、项目经历等字段。
- 不输出原始简历全文。
- 不嵌入原始 PDF 页面。
- 适合原简历排版简单、外观不适合直接提交客户的场景。

### 2.2 标准化简历 + 原始 PDF 模式

- 先生成与 `structured_only` 完全相同的标准化报告内容。
- 在报告末尾另起新页，按原页比例逐页嵌入上传 PDF 的高清页面图。
- PDF 页面仅作为视觉附录，不参与重新排版，不替代结构化简历。
- 若没有可用 PDF 原文件，创建草稿或渲染时返回明确校验错误；不得静默降级为文本附录。

### 2.3 AZ 客户模板

- AZ 工具和模板保持独立。
- 固定使用 `az_client_template`。
- 不读取或接受 T-STAR 的 `resume_appendix_mode` 来改变输出结构。
- 生成失败时返回真实错误，不退回 T-STAR、Generic 或简版模板。

## 3. 数据契约 / Data Contract

报告草稿新增字段：

```json
{
  "resume_appendix_mode": "structured_only",
  "resume_source_file_id": "rf_<hash>",
  "resume_source_file_name": "candidate.pdf",
  "resume_source_mime_type": "application/pdf"
}
```

允许值：

- `structured_only`
- `structured_with_original_pdf`
- `az_client_template`（仅 AZ 内部使用）

原始文件二进制不得写入草稿 JSON。上传后保存到受控数据目录，以内容哈希生成不可猜测的文件 ID；草稿只保存引用和元数据。

## 4. 数据流 / Data Flow

```text
上传 PDF
  -> 保存原始 PDF 字节并生成 resume_source_file_id
  -> 从同一 PDF 提取文本并生成 Candidate Brief
  -> 顾问选择 appendix mode
  -> 标准化模板渲染
  -> 如为 structured_with_original_pdf：PDF 逐页转图并追加到 DOCX
```

解析文本和原始文件必须来自同一次上传，避免报告正文与附录来源不一致。

## 5. PDF 页面嵌入 / PDF Page Embedding

- 使用 PyMuPDF 将页面按 150 DPI 以上渲染为 PNG。
- 每个 PDF 页面对应一个 DOCX 页面；保持原始宽高比。
- 图片缩放到当前 Word 页面的可用区域内，横向页面也不得裁切。
- 每页图片前强制分页，防止两个 PDF 页面挤在同一 Word 页面。
- 不在嵌入页上叠加重新解析的文字、页眉或说明文字。
- 设置合理页数和文件大小上限；超限时明确报错，不降级。

## 6. UI 与 Agent 参数 / UI and Agent Contract

T-STAR/Generic 页面显示单选项：

- 标准化简历（默认）
- 标准化简历 + 原始 PDF 页面

选择组合模式时，文件控件只接受 PDF，并在提交前校验。

Agent 工具参数新增：

```json
{
  "resume_appendix_mode": "structured_only"
}
```

Agent 不得根据简历外观自行切换模式；未指定时使用 `structured_only`。

## 7. 错误处理 / Error Handling

- 组合模式缺少 PDF：`original_pdf_required`。
- 文件不是有效 PDF：`invalid_original_pdf`。
- PDF 加密或无法渲染：`original_pdf_render_failed`。
- 页数或体积超限：`original_pdf_limit_exceeded`。
- 所有错误必须包含具体原因和下一步操作，不生成半成品报告。

## 8. 测试与验收 / Testing and Acceptance

1. `structured_only` 的 DOCX 中不存在原始 PDF 页面和原始文本附录。
2. `structured_with_original_pdf` 同时包含完整标准化简历和全部原始 PDF 页面。
3. 原始 PDF 页数与 DOCX 嵌入图片数一致，页面顺序一致。
4. 组合模式缺少 PDF 时必须失败，不能回退。
5. 同一 PDF 的解析文本和原页引用具有同一来源哈希。
6. AZ 报告结果与新增模式无关，继续使用客户模板。
7. T-STAR HTML 输出在组合模式中提供原始 PDF 内嵌预览或明确说明 DOCX 才包含逐页附录，不伪造文本复刻。
8. DOCX 需完成页面渲染视觉检查，确认无裁切、重叠、空白页和比例失真。

## 9. 非目标 / Non-Goals

- 不生成 ZIP 交付包。
- 不把 PDF 作为 OLE 对象嵌入 Word。
- 不用 OCR 或解析文字重建“原始 PDF 页面”。
- 不改变 AZ 客户模板的字段、字体或流程。
