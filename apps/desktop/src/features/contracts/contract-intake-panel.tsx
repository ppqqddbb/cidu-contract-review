import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

const contractTypes = [
  "采购合同",
  "服务合同",
  "保密协议",
  "软件许可合同",
] as const;

export function ContractIntakePanel() {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px_auto] lg:items-end">
      <div>
        <p className="mb-1 text-xs font-semibold text-slate-600">合同文件</p>
        <div className="flex min-h-20 items-center justify-between gap-3 rounded-xl border border-dashed border-blue-200 bg-blue-50/60 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Badge tone="blue">待上传</Badge>
              <p className="truncate text-xs font-semibold text-slate-950">
                支持 DOCX / 文本型 PDF
              </p>
            </div>
            <p className="mt-1 truncate text-[11px] text-slate-500">
              选择合同文件后创建预审任务，扫描件 OCR 后续接入。
            </p>
          </div>
          <Button disabled size="sm" variant="secondary">
            选择文件
          </Button>
        </div>
      </div>

      <label className="block">
        <span className="mb-1 block text-xs font-semibold text-slate-600">
          合同类型
        </span>
        <select
          className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100 disabled:text-slate-500"
          disabled
          value="采购合同"
        >
          {contractTypes.map((type) => (
            <option key={type}>{type}</option>
          ))}
        </select>
      </label>

      <Button disabled size="sm" title="上传接口接入后启用">
        创建预审
      </Button>
    </div>
  );
}
