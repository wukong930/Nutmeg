import type { ReactNode } from "react";

type TabItem = {
  value: string;
  label: ReactNode;
  href?: string;
  count?: number;
};

type TabsProps = {
  items: TabItem[];
  activeValue: string;
  ariaLabel: string;
};

export function Tabs({ items, activeValue, ariaLabel }: TabsProps) {
  return (
    <div className="ui-tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const isActive = item.value === activeValue;
        const className = isActive ? "ui-tab ui-tab-active" : "ui-tab";
        const content = (
          <>
            <span>{item.label}</span>
            {typeof item.count === "number" ? <span className="ui-tab-count">{item.count}</span> : null}
          </>
        );

        return item.href ? (
          <a className={className} href={item.href} role="tab" aria-selected={isActive} key={item.value}>
            {content}
          </a>
        ) : (
          <span className={className} role="tab" aria-selected={isActive} key={item.value}>
            {content}
          </span>
        );
      })}
    </div>
  );
}
