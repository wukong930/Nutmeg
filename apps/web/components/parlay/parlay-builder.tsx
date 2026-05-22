import { Calculator, Coins, Layers3, SlidersHorizontal } from "lucide-react";

import type { ParlayTicketRequestOptions } from "@/lib/api";
import type { ParlayTicket } from "@/types/api";

import { MultiSelectionLegPreview } from "./parlay-leg-selector";

const marketOptions = [
  { value: "1x2", label: "胜平负" },
  { value: "cn_handicap_1x2", label: "中国让球" },
  { value: "european_handicap_1x2", label: "欧洲让球" },
  { value: "correct_score", label: "比分" },
  { value: "asian_handicap", label: "亚洲让球" },
] as const;

export function ParlayBuilder({
  options,
  tickets,
}: {
  options: ParlayTicketRequestOptions;
  tickets: ParlayTicket[];
}) {
  const allowedMarkets = new Set(options.allowedMarkets ?? ["1x2", "cn_handicap_1x2", "european_handicap_1x2"]);

  return (
    <section className="parlay-builder-panel" aria-label="ParlayBuilder">
      <form className="parlay-builder-form">
        <label className="control">
          <span>
            <Layers3 size={14} aria-hidden="true" /> 过关类型
          </span>
          <select name="pass_type" defaultValue={options.passType ?? "all"}>
            <option value="all">2串1-8串1</option>
            <option value="2x1">2串1</option>
            <option value="3x1">3串1</option>
            <option value="4x1">4串1</option>
            <option value="5x1">5串1</option>
            <option value="6x1">6串1</option>
            <option value="7x1">7串1</option>
            <option value="8x1">8串1</option>
          </select>
        </label>

        <label className="control">
          <span>
            <Calculator size={14} aria-hidden="true" /> 单注金额
          </span>
          <input name="unit_stake" type="number" defaultValue={options.unitStake ?? 2} min={1} step={1} />
        </label>

        <label className="control">
          <span>
            <Coins size={14} aria-hidden="true" /> 预算
          </span>
          <input name="max_budget" type="number" defaultValue={options.maxBudget ?? 20} min={1} step={1} />
        </label>

        <label className="control">
          <span>选择结构</span>
          <select name="allow_multiple" defaultValue={options.allowMultiple === false ? "false" : "true"}>
            <option value="true">复式允许</option>
            <option value="false">单选串关</option>
          </select>
        </label>

        <fieldset className="parlay-market-fieldset">
          <legend>玩法范围</legend>
          {marketOptions.map((option) => (
            <label key={option.value}>
              <input
                type="checkbox"
                name="allowed_market"
                value={option.value}
                defaultChecked={allowedMarkets.has(option.value)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>

        <button className="toolbar-button" type="submit">
          <SlidersHorizontal size={15} aria-hidden="true" />
          应用参数
        </button>
      </form>

      <MultiSelectionLegPreview tickets={tickets} />
      <p className="parlay-compliance-copy">
        候选池会参考玩法范围、预算和数据质量；低质量、过期或规则无效的选项需要降权或排除。
      </p>
    </section>
  );
}
