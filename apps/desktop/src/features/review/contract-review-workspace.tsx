import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

const reviewIssues = [
  {
    marker: "R1",
    clauseId: "C-03",
    level: "高风险",
    tone: "red",
    title: "付款节点缺少验收前置条件",
    quote: "收到发票后 5 个工作日内支付全部合同价款",
    reviewFocus:
      "付款条件应与交付、验收合格、合法有效发票等前置条件联动，避免未验收即触发全额付款。",
    commonRisk:
      "仅以收到发票作为付款条件，缺少验收合格约束，可能导致标的存在质量或数量争议时我方仍需先付款。",
    fixDirection:
      "建议调整为：甲方在验收合格并收到乙方合法有效发票后【5】个工作日内支付对应款项。",
    basis: "RULE-PROC-001",
    evidence: "dataset/doc/seg 示例证据",
  },
  {
    marker: "R2",
    clauseId: "C-04",
    level: "高风险",
    tone: "red",
    title: "违约责任缺少责任上限",
    quote: "赔偿守约方因此遭受的全部损失",
    reviewFocus:
      "违约责任应明确责任范围、赔偿上限、可得利益和间接损失是否纳入。",
    commonRisk:
      "“全部损失”范围过宽，可能被解释为包括间接损失、预期收益损失和第三方索赔，责任边界不清。",
    fixDirection:
      "建议增加赔偿上限，并明确排除间接损失；如业务必须保留，应提交人工确认谈判底线。",
    basis: "RULE-COMMON-004",
    evidence: "dataset/doc/seg 示例证据",
  },
  {
    marker: "R3",
    clauseId: "C-05",
    level: "中风险",
    tone: "amber",
    title: "单方解除触发条件过宽",
    quote: "甲方可单方通知乙方后立即解除本合同",
    reviewFocus:
      "解除权应区分一般违约、重大违约和补救期，避免解除条件过于笼统。",
    commonRisk:
      "未约定违约程度和合理补救期，可能导致解除权行使争议，并影响后续结算与责任承担。",
    fixDirection:
      "建议补充“经书面催告后【10】日内仍未改正”或限定为重大违约场景。",
    basis: "RULE-TERM-002",
    evidence: "dataset/doc/seg 示例证据",
  },
] as const;

const parsedClauses = [
  {
    id: "C-01",
    title: "第一条 合同标的",
    body: "乙方按照本合同约定向甲方提供采购清单所列设备及配套服务，具体规格、数量、交付批次以双方确认的附件为准。",
  },
  {
    id: "C-02",
    title: "第二条 交付与验收",
    body: "乙方应于合同生效后 15 个工作日内完成交付。甲方在收到货物后组织验收，并在验收单中记录数量、外观及功能测试结果。",
  },
] as const;

function IssueMarker({
  marker,
  tone,
}: {
  marker: string;
  tone: "red" | "amber";
}) {
  const className =
    tone === "red"
      ? "border-red-200 bg-red-600 text-white"
      : "border-amber-200 bg-amber-500 text-white";

  return (
    <span
      className={
        "inline-flex h-6 min-w-6 items-center justify-center rounded-full border px-1.5 text-[11px] font-bold shadow-sm " +
        className
      }
    >
      {marker}
    </span>
  );
}

export function ContractReviewWorkspace() {
  return (
    <div className="grid min-h-[640px] gap-4 bg-slate-100/70 p-4 xl:grid-cols-[minmax(0,1fr)_460px]">
      <section className="min-w-0 rounded-2xl border-2 border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              左侧：合同原文区
            </p>
            <h3 className="mt-1 text-[11px] font-bold text-slate-950">
              采购框架协议_示例.docx
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="green">已解析 5 条款</Badge>
            <Badge tone="slate">示例脱敏文本</Badge>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50 shadow-inner">
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
            <div>
              <p className="text-[11px] font-bold text-slate-950">
                合同原文解析结果
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500">
                仅展示解析出的条款正文；命中风险的片段会在原文中同步高亮并编号。
              </p>
            </div>
            <Badge tone="amber">3 处标注</Badge>
          </div>

          <div className="max-h-[535px] space-y-3 overflow-y-auto border-t-4 border-slate-200 p-4 text-[13px] leading-6 text-slate-700">
            {parsedClauses.map((clause) => (
              <article
                key={clause.id}
                className="rounded-xl border border-slate-200 bg-white p-3"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <h4 className="font-bold text-slate-950">{clause.title}</h4>
                  <Badge>{clause.id}</Badge>
                </div>
                <p>{clause.body}</p>
              </article>
            ))}

            <article className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <h4 className="font-bold text-slate-950">第三条 价款与支付</h4>
                <Badge>C-03</Badge>
              </div>
              <p>
                合同总价款为人民币【金额】元。甲方应于
                <mark className="mx-1 rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 font-semibold text-red-900 ring-1 ring-red-100">
                  收到发票后 5 个工作日内支付全部合同价款
                </mark>
                。
                <IssueMarker marker="R1" tone="red" />
              </p>
            </article>

            <article className="rounded-xl border border-red-200 bg-red-50/30 p-3 ring-1 ring-red-100">
              <div className="mb-1 flex items-center justify-between gap-2">
                <h4 className="font-bold text-slate-950">第四条 违约责任</h4>
                <Badge tone="red">C-04</Badge>
              </div>
              <p>
                任一方违反本合同约定，应继续履行、采取补救措施，并
                <mark className="mx-1 rounded-md border border-red-300 bg-red-100 px-1.5 py-0.5 font-semibold text-red-950 ring-1 ring-red-200">
                  赔偿守约方因此遭受的全部损失
                </mark>
                。
                <IssueMarker marker="R2" tone="red" />
              </p>
            </article>

            <article className="rounded-xl border border-amber-200 bg-amber-50/30 p-3 ring-1 ring-amber-100">
              <div className="mb-1 flex items-center justify-between gap-2">
                <h4 className="font-bold text-slate-950">第五条 合同解除</h4>
                <Badge tone="amber">C-05</Badge>
              </div>
              <p>
                如乙方未按约定完成交付，
                <mark className="mx-1 rounded-md border border-amber-300 bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-950 ring-1 ring-amber-200">
                  甲方可单方通知乙方后立即解除本合同
                </mark>
                ，并要求乙方承担相应责任。
                <IssueMarker marker="R3" tone="amber" />
              </p>
            </article>
          </div>
        </div>
      </section>

      <aside className="min-w-0 rounded-2xl border-2 border-red-100 bg-red-50/30 p-4 shadow-sm">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              右侧：问题高亮区
            </p>
            <h3 className="mt-1 text-[11px] font-bold text-slate-950">
              按三段式标注风险
            </h3>
          </div>
          <Badge tone="red">待人工确认</Badge>
        </div>

        <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs font-semibold">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 text-slate-600">
            审核重点
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 text-slate-600">
            常见风险
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 text-slate-600">
            修改方向
          </div>
        </div>

        <div className="max-h-[560px] space-y-3 overflow-y-auto border-t-4 border-red-200 pt-3 pr-1">
          {reviewIssues.map((issue) => (
            <article
              key={issue.marker}
              className="rounded-2xl border border-red-100 bg-white p-3 shadow-sm ring-1 ring-red-50"
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2">
                  <IssueMarker
                    marker={issue.marker}
                    tone={issue.tone === "red" ? "red" : "amber"}
                  />
                  <div className="min-w-0">
                    <h4 className="text-[11px] font-bold leading-5 text-slate-950">
                      {issue.title}
                    </h4>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {issue.clauseId} · {issue.basis}
                    </p>
                  </div>
                </div>
                <Badge tone={issue.tone}>{issue.level}</Badge>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-700">
                <span className="font-semibold text-slate-950">原文高亮：</span>
                “{issue.quote}”
              </div>

              <div className="mt-3 space-y-2">
                <section className="rounded-xl border border-slate-200 p-3">
                  <p className="text-[11px] font-bold text-slate-950">
                    第一段：审核重点
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-slate-600">
                    {issue.reviewFocus}
                  </p>
                </section>
                <section className="rounded-xl border border-red-100 bg-red-50/60 p-3">
                  <p className="text-[11px] font-bold text-red-900">
                    第二段：常见风险
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-red-800">
                    {issue.commonRisk}
                  </p>
                </section>
                <section className="rounded-xl border border-green-100 bg-green-50/70 p-3">
                  <p className="text-[11px] font-bold text-green-900">
                    第三段：修改方向
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-green-800">
                    {issue.fixDirection}
                  </p>
                </section>
              </div>

              <div className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">
                证据状态：{issue.evidence} · 当前仅为静态界面骨架
              </div>

              <div className="mt-3 grid grid-cols-3 gap-2">
                <Button disabled size="sm" variant="outline">
                  确认
                </Button>
                <Button disabled size="sm" variant="secondary">
                  修改
                </Button>
                <Button disabled size="sm" variant="ghost">
                  忽略
                </Button>
              </div>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}
