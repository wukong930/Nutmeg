import Link from "next/link";
import {
  Activity,
  BarChart3,
  DatabaseZap,
  Gauge,
  ListChecks,
  Radar,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import { ComplianceNotice } from "./compliance-notice";

const primaryNavigation = [
  { href: "/dashboard", label: "推荐", icon: ListChecks },
  { href: "/upsets", label: "冷门观察", icon: Radar },
  { href: "/parlays", label: "串关推荐", icon: Activity },
  { href: "/accuracy", label: "准确性", icon: BarChart3 },
  { href: "/providers", label: "数据源", icon: DatabaseZap },
] as const;

const plannedNavigation = [
  { label: "赛事", icon: ShieldCheck },
  { label: "模型说明", icon: Gauge },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="top-nav">
        <div className="top-nav-inner">
          <Link href="/dashboard" className="brand" aria-label="Nutmeg Dashboard">
            <span className="brand-mark">N</span>
            <span>
              <span className="brand-name">Nutmeg</span>
              <span className="brand-subtitle">最佳答案工作台</span>
            </span>
          </Link>
          <nav className="nav-links" aria-label="主导航">
            {primaryNavigation.map(({ href, label, icon: Icon }) => (
              <Link href={href} className="nav-link" key={href}>
                <Icon size={16} aria-hidden="true" />
                {label}
              </Link>
            ))}
            {plannedNavigation.map(({ label, icon: Icon }) => (
              <span className="nav-link nav-link-muted" aria-disabled="true" key={label}>
                <Icon size={16} aria-hidden="true" />
                {label}
              </span>
            ))}
            <span className="shell-status" aria-label="模型状态">
              <Gauge size={16} aria-hidden="true" />
              模型在线
            </span>
          </nav>
        </div>
      </header>
      {children}
      <footer className="app-footer">
        <ComplianceNotice />
      </footer>
    </div>
  );
}
