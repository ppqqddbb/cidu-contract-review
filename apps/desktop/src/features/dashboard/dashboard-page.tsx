import { useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { getHealth } from "../../api/http";
import { AppShell } from "../../components/layout/app-shell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { ContractIntakePanel } from "../contracts/contract-intake-panel";
import { ContractReviewWorkspace } from "../review/contract-review-workspace";

const metrics = [
  { label: "待复核", value: "—", tone: "blue", hint: "任务数据待接入" },
  { label: "高风险", value: "—", tone: "red", hint: "未处理不可完成" },
  { label: "分类确认", value: "—", tone: "amber", hint: "低置信度需人工" },
  { label: "可导出", value: "—", tone: "green", hint: "复核完成后生成" },
] as const;

const recentTasks = [
  {
    name: "采购框架协议_2026.docx",
    status: "待解析",
    type: "采购合同",
    updatedAt: "刚刚",
  },
  {
    name: "软件服务协议.pdf",
    status: "分类待确认",
    type: "服务合同",
    updatedAt: "示例",
  },
  {
    name: "保密协议.docx",
    status: "待复核",
    type: "保密协议",
    updatedAt: "示例",
  },
  {
    name: "PDF合并-1-10.pdf",
    status: "已解析",
    type: "采购合同",
    updatedAt: "02-10 19:25",
  },
] as const;

function getStatusTone(status: string) {
  if (status.includes("复核")) return "blue";
  if (status.includes("分类")) return "amber";
  if (status.includes("已解析")) return "green";
  return "slate";
}

function UploadHistoryPanel() {
  return (
    <Card
      className="flex h-full min-h-[calc(100vh-104px)] flex-col overflow-hidden"
      description="历史上传列表作为任务入口。"
      title="历史上传"
    >
      <div className="flex-1 divide-y divide-slate-100 overflow-y-auto">
        {recentTasks.map((task) => (
          <article key={task.name} className="px-4 py-3">
            <div className="flex min-w-0 items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-slate-950">
                  {task.name}
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  {task.type} · {task.updatedAt}
                </p>
              </div>
              <Badge tone={getStatusTone(task.status)}>{task.status}</Badge>
            </div>
          </article>
        ))}
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const health = useQuery({
    queryKey: ["api-health"],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 30_000,
  });

  const statusLabel = health.isPending
    ? "正在连接 API"
    : health.isError
      ? "API 未连接"
      : `API ${health.data.version} 已连接`;
  const statusTone = health.isError
    ? "error"
    : health.isPending
      ? "warning"
      : "success";

  return (
    <AppShell
      actions={
        <Button disabled size="sm" title="合同上传接口接入后启用">
          新建预审
        </Button>
      }
      eyebrow="合同智审"
      navigationAction={
        <Button
          aria-label={historyCollapsed ? "展开历史上传栏" : "收起历史上传栏"}
          className="h-9 min-w-9 px-0 text-base"
          onClick={() => setHistoryCollapsed((value) => !value)}
          size="sm"
          title={historyCollapsed ? "展开历史上传栏" : "收起历史上传栏"}
          variant="ghost"
        >
          ☰
        </Button>
      }
      statusLabel={statusLabel}
      statusTone={statusTone}
      title="标准合同 AI 预审工作台"
      version="MVP 0.1.0"
    >
      <section
        className={
          historyCollapsed
            ? "grid min-h-[calc(100vh-88px)] gap-4"
            : "grid min-h-[calc(100vh-88px)] gap-4 xl:grid-cols-[260px_minmax(0,1fr)]"
        }
      >
        {!historyCollapsed && (
          <aside className="xl:sticky xl:top-[72px] xl:h-[calc(100vh-88px)] xl:self-start">
            <UploadHistoryPanel />
          </aside>
        )}

        <div className="min-w-0 space-y-4">
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => (
              <article
                key={metric.label}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-600">
                    {metric.label}
                  </p>
                  <Badge tone={metric.tone}>{metric.hint}</Badge>
                </div>
                <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">
                  {metric.value}
                </p>
              </article>
            ))}
          </section>

          <Card
            description="仅保留文件上传和合同类型选择，后续接 FastAPI 创建任务接口。"
            title="合同提交"
          >
            <div className="p-4">
              <ContractIntakePanel />
            </div>
          </Card>

          <Card
            action={<Badge tone="red">示例：3 个问题</Badge>}
            description="左侧展示解析出的合同原文，右侧同步高亮问题，并按“审核重点、常见风险、修改方向”三段式标注。"
            title="合同解析与问题标注"
          >
            <ContractReviewWorkspace />
          </Card>
        </div>
      </section>
    </AppShell>
  );
}
