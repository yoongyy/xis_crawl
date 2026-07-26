"use client";

import Link from "next/link";
import {
  ArrowRight,
  Check,
  CircleDot,
  LockKeyhole,
  SearchCheck,
  X,
} from "lucide-react";
import {
  concernTrends,
  executiveThemes,
  freeFeatures,
  insurerMentions,
  methodologyPrinciples,
  methodologySteps,
  productThemes,
  proFeatures,
} from "@/data/sample-insurance-report";
import {
  ConcernChart,
  DemoLabel,
  MentionBars,
  SectionHeading,
} from "@/components/reports/report-ui";
import { useLanguage } from "@/lib/language-context";

const evidenceStyles = {
  "Observed discussion theme": "border-sky-200 bg-sky-50 text-sky-700",
  "Commercial opportunity": "border-emerald-200 bg-emerald-50 text-emerald-700",
  "Needs professional care": "border-amber-200 bg-amber-50 text-amber-800",
};

export function ExecutiveSummary() {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <section className="py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow={isEnglish ? "Executive summary" : "执行摘要"}
          title={
            isEnglish
              ? "What Malaysian insurance customers are talking about"
              : "马来西亚保险客户正在讨论什么"
          }
          description={
            isEnglish
              ? "Four recurring themes in this targeted demo sample, separated by commercial relevance and care required."
              : "此目标演示样本中的四个反复出现的主题，并按商业相关性与专业谨慎程度区分。"
          }
        />
        <div className="grid gap-5 md:grid-cols-2">
          {executiveThemes.map((theme) => (
            <article
              key={theme.title}
              className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
            >
              <span
                className={`inline-flex rounded border px-2 py-1 text-[10px] font-bold uppercase ${evidenceStyles[theme.evidence]}`}
              >
                {theme.evidence}
              </span>
              <h3 className="mt-4 text-lg font-bold text-navy">{theme.title}</h3>
              <p className="mt-2 text-xs leading-5 text-slate-600">
                {theme.description}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
export function TrendAndMentionSections() {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <>
      <section className="border-y border-slate-200 bg-white py-16">
        <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
          <div>
            <SectionHeading
              eyebrow={isEnglish ? "Trend preview" : "趋势预览"}
              title={
                isEnglish
                  ? "Customer concerns detected this month"
                  : "本月检测到的客户关注点"
              }
            />
            <p className="text-sm leading-6 text-slate-600">
              {isEnglish
                ? "The category mix helps agents understand where education and comparison support may be useful. It does not estimate the size of Malaysia's insurance market."
                : "主题组合帮助代理人了解哪些地方可能需要教育和比较支持，并不估算马来西亚保险市场规模。"}
            </p>
            <div className="mt-5">
              <DemoLabel text={isEnglish ? "Targeted sample" : "目标样本"} />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-5 sm:p-7">
            <ConcernChart data={concernTrends} />
            <p className="mt-6 border-t border-slate-200 pt-4 text-[11px] leading-5 text-slate-500">
              {isEnglish
                ? "Based on a targeted sample of public Malaysian insurance conversations. This is not a market-size estimate."
                : "基于马来西亚公开保险对话的目标样本，不属于市场规模估算。"}
            </p>
          </div>
        </div>
      </section>

      <section className="py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow={isEnglish ? "Insurer and product themes" : "保险公司与产品主题"}
            title={
              isEnglish
                ? "What customers mention while evaluating options"
                : "客户评估选择时提及的内容"
            }
            description={
              isEnglish
                ? "Demo mention counts show visibility inside this sample, not market share, product quality, or dissatisfaction."
                : "演示提及量仅显示在此样本中的可见度，不代表市场份额、产品质量或不满程度。"
            }
          />
          <div className="grid gap-6 lg:grid-cols-2">
            <MentionBars
              title={isEnglish ? "Insurers mentioned" : "提及的保险公司"}
              data={insurerMentions}
            />
            <MentionBars
              title={isEnglish ? "Products discussed" : "讨论的产品"}
              data={productThemes}
            />
          </div>
          <p className="mt-5 text-[11px] leading-5 text-slate-500">
            {isEnglish
              ? "Mentions include complaints, comparisons, questions, neutral discussions, and positive comments. Mention count does not equal dissatisfaction."
              : "提及内容包括投诉、比较、问题、中立讨论和正面评论。提及量不等于不满程度。"}
          </p>
        </div>
      </section>
    </>
  );
}

const comparisonFeatures = Array.from(new Set([...freeFeatures, ...proFeatures]));

export function FreeVsPro({
  onOpenEarlyAccess,
}: {
  onOpenEarlyAccess: () => void;
}) {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <section className="border-y border-slate-200 bg-white py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow={isEnglish ? "Free intelligence vs Pro detail" : "免费情报与 Pro 详情"}
          title={
            isEnglish
              ? "What you see for free - and what members unlock"
              : "免费可见内容与会员解锁内容"
          }
          description={
            isEnglish
              ? "The free report tells you what customers are talking about. CariLead Pro shows where the conversation happened and helps you respond while the need is still active."
              : "免费报告告诉您客户正在讨论什么。CariLead Pro 显示对话发生在哪里，并帮助您在需求仍然活跃时作出回应。"
          }
        />

        <div className="min-w-0 overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[680px] bg-white text-left text-xs">
            <thead className="bg-slate-50">
              <tr>
                <th className="p-4 text-navy">{isEnglish ? "Capability" : "功能"}</th>
                <th className="p-4 text-navy">
                  {isEnglish ? "Free Weekly Report" : "免费周报"}
                </th>
                <th className="p-4 text-navy">CariLead Pro</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {comparisonFeatures.map((feature) => {
                const free = freeFeatures.includes(feature);
                const pro = proFeatures.includes(feature) || free;
                return (
                  <tr key={feature}>
                    <th className="p-4 font-semibold text-slate-700">{feature}</th>
                    <td className="p-4">
                      {free ? (
                        <Check className="h-4 w-4 text-primary" aria-label="Included" />
                      ) : (
                        <X className="h-4 w-4 text-slate-300" aria-label="Not included" />
                      )}
                    </td>
                    <td className="p-4">
                      {pro ? (
                        <Check className="h-4 w-4 text-primary" aria-label="Included" />
                      ) : (
                        <X className="h-4 w-4 text-slate-300" aria-label="Not included" />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/#free-report"
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white hover:bg-primary-dark"
          >
            {isEnglish ? "Get Free Insurance Report" : "获取免费保险报告"}
            <ArrowRight className="h-4 w-4" />
          </Link>
          <button
            type="button"
            onClick={onOpenEarlyAccess}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-navy hover:border-primary hover:text-primary"
          >
            <LockKeyhole className="h-4 w-4" />
            {isEnglish ? "Join CariLead Pro Early Access" : "加入 CariLead Pro 早期体验"}
          </button>
        </div>
      </div>
    </section>
  );
}

export function MethodologySection() {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <section className="py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow={isEnglish ? "Methodology and credibility" : "方法与可信度"}
          title={
            isEnglish
              ? "How CariLead turns conversations into useful signals"
              : "CariLead 如何将对话转化为有用信号"
          }
          description={
            isEnglish
              ? "A structured research process reduces promotional noise and prevents every complaint from being treated as a lead."
              : "结构化研究流程减少推广噪音，并避免把每一条投诉都当作线索。"
          }
        />

        <ol className="grid gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 md:grid-cols-5">
          {methodologySteps.map((step, index) => (
            <li key={step} className="bg-white p-5">
              <span className="text-xs font-extrabold text-primary">
                {String(index + 1).padStart(2, "0")}
              </span>
              <p className="mt-3 text-xs font-semibold leading-5 text-slate-700">
                {step}
              </p>
            </li>
          ))}
        </ol>

        <div className="mt-10 grid gap-8 lg:grid-cols-[0.7fr_1.3fr]">
          <div>
            <div className="flex items-center gap-2 text-primary">
              <SearchCheck className="h-5 w-5" />
              <h3 className="text-sm font-bold uppercase">
                {isEnglish ? "Interpretation principles" : "解释原则"}
              </h3>
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-600">
              {isEnglish
                ? "These rules keep the report directional, source-aware, and suitable for human review."
                : "这些规则使报告保持方向性、来源意识，并适合人工审核。"}
            </p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {methodologyPrinciples.map((principle) => (
              <li
                key={principle}
                className="flex gap-3 border-b border-slate-200 pb-3 text-xs leading-5 text-slate-700"
              >
                <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-teal" />
                {principle}
              </li>
            ))}
          </ul>
        </div>

        <p
          id="demo-source"
          className="mt-8 border-l-4 border-teal bg-white p-4 text-[11px] leading-5 text-slate-500"
        >
          {isEnglish
            ? "Demo source buttons use safe placeholders. A production Pro record would link to an eligible original public source for human verification without exposing hidden contact data, private medical details, or private messages."
            : "演示来源按钮使用安全占位符。实际 Pro 记录会链接到合适的原始公开来源供人工核实，不会暴露隐藏联系方式、私人医疗细节或私信。"}
        </p>
      </div>
    </section>
  );
}
