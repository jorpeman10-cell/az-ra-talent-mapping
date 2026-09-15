# 建档查重与简历接入设计（Steven 已批 2026-09-15）

## 决策记录
1. 查重范围：**Hunter 主候选人库**（20万+，含手机/邮箱/简历全文），含评估档自身
2. 命中交互：**确认卡绑定**（唯一命中→脱敏摘要卡+「绑定并评估」；2-5 命中→选择卡+「都不是，新建档案」）
3. 简历：**可选传、评估侧存储、不回写 Hunter 主库**（二期再评估回写）

## 流程
用户「给X建档」[+简历附件] → Lobe 抽取附件文本（复用 resume_source）→
federation intake executor：
  ① 查重键：有简历→正则抽手机+邮箱；无→姓名
  ② Hunter 只读查询：手机/邮箱精确（各前5）或 姓名相似（top5）
  ③ 0命中→直接建档；1命中→绑定确认卡；2-5命中→选择卡；>5→选择卡+提示补充手机/邮箱
确认后 → headhunt-svc 建档（带绑定+简历）→ 双问卷 → 现有流程

## 关键规则
- 绑定只发生在用户点确认后；executor 首轮只查不绑
- 「不，新建档案」→ 档案标 dedup_skipped: true（审计）
- 手机号脱敏（158****5297）上卡；完整号码只在服务端
- Hunter 查询超时(>2s)→放行建档不查重，卡标「查重暂不可用」+档案 dedup_unavailable: true
- 简历抽取失败（扫描件）→降级纯姓名查重+提示

## 数据模型（headhunt-svc profile.json 增字段，向后兼容）
hunter_resume_id, hunter_matched_at, dedup_skipped, dedup_unavailable,
phone, email, resume_text(≤80KB), resume_source(attachment|hunter|none)
federation workflow 行同步加 hunter_resume_id

## 卡片契约
唯一命中→复用 candidate_search_intent 确认卡骨架（slots: subject/hunter_resume_id/matched_name/masked_phone，summary 带脱敏摘要+简历更新时间），确认 token 签名携带 hunter_resume_id
多命中→复用 ambiguous_subject 卡（candidates 列表）+「都不是，新建档案」动作
黄金卡新增 2 张

## 测试
federation：查重键抽取/三分支/token 签名/超时降级；headhunt：新参数持久化/兼容；Lobe：卡渲染；生产验收：李彩霞全流程

## Non-goals
Hunter 主库写入（二期）；同名自动绑定；OCR（B 线遗留）
