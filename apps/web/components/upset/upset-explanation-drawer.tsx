import { ChevronDown, Info } from "lucide-react";

import type { UpsetAlert, UpsetExplanationGroup } from "@/types/api";

export function UpsetExplanationDrawer({ alert }: { alert: UpsetAlert }) {
  const groups = explanationGroups(alert);

  return (
    <details className="upset-explanation-drawer">
      <summary>
        <span>
          <Info size={15} aria-hidden="true" />
          查看解释载荷
        </span>
        <ChevronDown size={15} aria-hidden="true" />
      </summary>
      <div className="upset-explanation-body">
        {groups.map((group) => (
          <section className="upset-explanation-group" key={group.title}>
            <h4>{group.title}</h4>
            <ul>
              {group.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}

function explanationGroups(alert: UpsetAlert): UpsetExplanationGroup[] {
  if (alert.explanationGroups?.length) {
    return alert.explanationGroups;
  }
  return [
    {
      title: "触发原因",
      items: alert.explanations,
    },
    {
      title: "边界说明",
      items: [
        `${alert.label} 是观察标签，不代表结果必然发生。`,
        "请结合数据质量、盘口分歧和比分分布一起解读。",
      ],
    },
  ];
}
