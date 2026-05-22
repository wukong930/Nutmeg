export function formatPercent(probability: number, digits = 1) {
  return `${(probability * 100).toFixed(digits)}%`;
}

export function formatPp(delta: number) {
  const prefix = delta >= 0 ? "+" : "";
  return `${prefix}${(delta * 100).toFixed(1)}pp`;
}

export function formatDateTime(iso: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(new Date(iso));
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(value);
}

export function qualityLabel(score: number) {
  if (score >= 85) return "数据质量 A";
  if (score >= 70) return "数据质量 B";
  if (score >= 50) return "数据质量 C";
  return "数据质量 D";
}

export function riskLabel(riskLevel: string) {
  const labels: Record<string, string> = {
    low: "低风险",
    medium: "中等风险",
    medium_high: "中高风险",
    high: "高风险",
  };
  return labels[riskLevel] ?? "风险待评估";
}
