import { ShieldAlert } from "lucide-react";

export function ComplianceNotice() {
  return (
    <aside className="compliance-notice" aria-label="合规与风险提示">
      <ShieldAlert size={17} aria-hidden="true" />
      <p>
        本工具仅提供概率分析与研究参考，不保证结果，不构成投注建议。足球比赛存在高不确定性，请理性使用。
        预测时间、模型版本和数据质量需一并阅读；低质量或过期数据会降低可信度。
      </p>
    </aside>
  );
}
