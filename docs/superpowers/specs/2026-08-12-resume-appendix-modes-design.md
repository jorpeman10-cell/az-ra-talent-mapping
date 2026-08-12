# 简历报告附录双模式设计 / Resume Appendix Dual-Mode Design

## 1. 目标 / Goal

在不降低简历解析质量的前提下，为 T-STAR/通用候选人报告提供两种明确、可审计的交付模式：

1. `structured_only`：仅输出标准化简历，不包含原始简历页面或原始文本附录。
2. `structured_with_source_appendix`：输出同一份标准化简历，并在报告末尾嵌入原始简历内容；根据源文件类型采用对应的保真方式。

AZ 报告继续使用客户指定模板，固定为 `az_client_template`，不允许被 T-STAR 模式覆盖。

## 2. 产品行为 / Product Behavior

### 2.1 标准化简历模式

- 简历始终经过解析，填入标准化模板中的个人信息、教育经历、工作经历、项目经历等字段。
- 不输出原始简历全文。
- 不嵌入任何原始文件页面或原始文本。
- 适合原简历排版简单、外观不适合直接提交客户的场景。

### 2.2 标准化简历 + 原文附录模式

- 先生成与 `structured_only` 完全相同的标准化报告内容。
- 在报告末尾另起新页，追加原始简历附录，不替代结构化简历。
- PDF：按原页比例逐页嵌入高清页面图。
- DOC/DOCX：先用受控的无头办公组件转换为 PDF，再按原页逐页嵌入。
- TXT/MD：不存在可复刻的页面版式，按源文件完整文本、原始顺序和换行生成原文附录，不经过摘要或结构重排。
- 转换失败时返回明确错误；不得静默降级为解析摘要或另一种模板。

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
- `structured_with_source_appendix`
- `az_client_template`（仅 AZ 内部使用）

原始文件二进制不得写入草稿 JSON。上传后保存到受控数据目录，以内容哈希生成不可猜测的文件 ID；草稿只保存引用和元数据。

## 4. 数据流 / Data Flow

```text
上传原始简历文件
  -> 保存原始文件字节并生成 resume_source_file_id
  -> 从同一文件提取文本并生成 Candidate Brief
  -> 顾问选择 appendix mode
  -> 标准化模板渲染
  -> 如为 structured_with_source_appendix：按文件类型生成原文附录并追加到 DOCX
```

解析文本和原始文件必须来自同一次上传，避免报告正文与附录来源不一致。任何格式都必须先保存原始字节，再执行文本提取。

## 5. 原文附录渲染 / Source Appendix Rendering

- PDF 以及由 DOC/DOCX 转换得到的 PDF 使用 PyMuPDF 按 150 DPI 以上渲染为 PNG。
- 每个源文件页面对应一个 DOCX 页面；保持原始宽高比。
- 图片缩放到当前 Word 页面的可用区域内，横向页面也不得裁切。
- 每页图片前强制分页，防止两个源文件页面挤在同一 Word 页面。
- 不在嵌入页上叠加重新解析的文字、页眉或说明文字。
- 设置合理页数和文件大小上限；超限时明确报错，不降级。
- TXT/MD 原文附录必须逐行保留内容和空行，不得使用结构化解析结果重建原文。

## 6. UI 与 Agent 参数 / UI and Agent Contract

T-STAR/Generic 页面显示单选项：

- 标准化简历（默认）
- 标准化简历 + 原始简历附录

组合模式接受系统支持的全部简历格式。界面应说明不同文件类型的附录方式：PDF/DOC/DOCX 保留页面视觉，TXT/MD 保留完整原文与换行。

Agent 工具参数新增：

```json
{
  "resume_appendix_mode": "structured_only"
}
```

Agent 不得根据简历外观自行切换模式；未指定时使用 `structured_only`。

## 7. 错误处理 / Error Handling

- 组合模式缺少原始文件：`source_file_required`。
- 原始文件格式无效：`invalid_source_file`。
- PDF 加密、DOC/DOCX 转换失败或页面无法渲染：`source_appendix_render_failed`。
- 页数或体积超限：`source_file_limit_exceeded`。
- 所有错误必须包含具体原因和下一步操作，不生成半成品报告。

## 8. 测试与验收 / Testing and Acceptance

1. `structured_only` 的 DOCX 中不存在任何原始页面或原始文本附录。
2. `structured_with_source_appendix` 同时包含完整标准化简历和完整原文附录。
3. PDF、DOC 和 DOCX 简历的源页面数量与 DOCX 嵌入图片数量一致，页面顺序一致。
4. TXT/MD 的原始内容、顺序和换行在附录中完整保留。
5. 组合模式缺少原始文件时必须失败，不能回退。
6. 同一原始文件的解析文本和原文附录引用具有同一来源哈希。
7. AZ 报告结果与新增模式无关，继续使用客户模板。
8. T-STAR HTML 输出在组合模式中按源格式提供可验证的原文附录，不伪造页面复刻。
9. DOCX 需完成页面渲染视觉检查，确认无裁切、重叠、空白页和比例失真。

## 9. 非目标 / Non-Goals

- 不生成 ZIP 交付包。
- 不把 PDF 作为 OLE 对象嵌入 Word。
- 不用 OCR 或解析文字重建具备页面版式的原始文件页面。
- 不改变 AZ 客户模板的字段、字体或流程。
