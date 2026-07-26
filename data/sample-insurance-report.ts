export type OpportunityLevel = "low" | "medium" | "high" | "very_high";
export type EvidenceLabel =
  | "Observed discussion theme"
  | "Commercial opportunity"
  | "Needs professional care";

export interface InsuranceOpportunity {
  id: string;
  isDemo: boolean;
  title: string;
  opportunityType: string;
  quote: string;
  location: string;
  product: string;
  insurer?: string;
  postedAt: string;
  level: OpportunityLevel;
  confidence: number;
  whyItMatters: string;
  publicContext: string;
  knownFacts: string[];
  unknownFacts: string[];
  riskNotes: string[];
  suggestedResponse: string;
  responseWarnings: string[];
  sourceUrl?: string;
}

export interface ExecutiveTheme {
  title: string;
  description: string;
  evidence: EvidenceLabel;
}

export interface ConcernTrend {
  name: string;
  mentions: number;
}

export interface MentionTheme {
  name: string;
  mentions: number;
  note: string;
}

export const reportMeta = {
  title: "Malaysia Insurance Customer Voice Report",
  subtitle:
    "What Malaysian customers are asking, complaining about, comparing, and considering right now.",
  edition: "July 2026 sample",
  dateRange: "Illustrative 7-day window",
  updatedAt: "Updated 26 July 2026",
  conversations: 126,
  highIntent: 18,
  leadingProduct: "Medical card",
  fastestGrowing: "Premium increase",
};

export const executiveThemes: ExecutiveTheme[] = [
  {
    title: "Premium increases",
    description:
      "Customers are concerned about rising medical-card premiums, affordability, co-insurance, deductibles, and whether switching will affect existing coverage.",
    evidence: "Observed discussion theme",
  },
  {
    title: "Policy comparison",
    description:
      "People are asking how to compare annual limits, exclusions, waiting periods, investment-linked policies, and takaful alternatives.",
    evidence: "Commercial opportunity",
  },
  {
    title: "Agent trust and service",
    description:
      "Customers mention agents who do not reply, poor explanations, hard selling, and uncertainty about who to contact after an agent leaves.",
    evidence: "Commercial opportunity",
  },
  {
    title: "Claims and hospital admission",
    description:
      "People seek help understanding rejected claims, guarantee-letter delays, exclusions, missing documents, and appeal options.",
    evidence: "Needs professional care",
  },
];
export const concernTrends: ConcernTrend[] = [
  { name: "Premium increase", mentions: 34 },
  { name: "Medical-card comparison", mentions: 27 },
  { name: "Claim assistance", mentions: 21 },
  { name: "Looking for agent", mentions: 18 },
  { name: "Parents' coverage", mentions: 14 },
  { name: "Switching consideration", mentions: 12 },
  { name: "Agent-service complaint", mentions: 9 },
];

export const insurerMentions: MentionTheme[] = [
  { name: "Great Eastern", mentions: 22, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "AIA", mentions: 20, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "Prudential", mentions: 18, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "Allianz", mentions: 14, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "Etiqa", mentions: 12, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "PruBSN", mentions: 10, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "Zurich", mentions: 8, note: "Questions, comparisons, complaints and neutral mentions" },
  { name: "Takaful Malaysia", mentions: 7, note: "Questions, comparisons, complaints and neutral mentions" },
];

export const productThemes: MentionTheme[] = [
  { name: "Medical card", mentions: 39, note: "Limits, premiums and hospital coverage" },
  { name: "Life insurance", mentions: 24, note: "Family protection and affordability" },
  { name: "Critical illness", mentions: 19, note: "Lump-sum coverage and exclusions" },
  { name: "Parents' medical coverage", mentions: 17, note: "Age eligibility and monthly budget" },
  { name: "Child insurance", mentions: 14, note: "Newborn and family planning questions" },
  { name: "Takaful", mentions: 13, note: "Shariah-compliant alternatives" },
  { name: "Investment-linked policy", mentions: 11, note: "Sustainability and policy charges" },
  { name: "Group medical insurance", mentions: 8, note: "SME budget and employee coverage" },
];

const sharedWarnings = [
  "I guarantee I can give you a cheaper policy.",
  "Cancel your current policy immediately.",
  "Your current insurer is cheating you.",
  "Your claim will definitely be approved.",
];

export const opportunities: InsuranceOpportunity[] = [
  {
    id: "parents-medical-card",
    isDemo: true,
    title: "Parents' medical-card request",
    opportunityType: "Active purchase request",
    quote:
      "Looking for a medical card for my parents, both above 60. Any recommendation around RM400 each per month?",
    location: "Selangor",
    product: "Parents' medical insurance",
    postedAt: "2 hours ago",
    level: "very_high",
    confidence: 96,
    whyItMatters:
      "The customer stated the target users, product requirement, location, and budget.",
    publicContext:
      "A public recommendation request from an adult child researching medical coverage for both parents.",
    knownFacts: [
      "Coverage is for two parents above age 60",
      "Target budget is around RM400 each per month",
      "The user is asking for recommendations",
    ],
    unknownFacts: [
      "Parents' health and underwriting history",
      "Existing medical coverage",
      "Required annual limit, room rate, and deductible preference",
    ],
    riskNotes: [
      "Eligibility and price depend on underwriting and product terms",
      "Do not request medical details in a public reply",
    ],
    suggestedResponse:
      "For parents above 60, it helps to compare entry-age eligibility, annual limits, room rate, co-insurance or deductibles, exclusions, and renewal terms before focusing on premium alone. I am an insurance agent and can share a neutral checklist of questions to ask each provider if useful.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "trusted-agent-request",
    isDemo: true,
    title: "Insurance-agent recommendation request",
    opportunityType: "Looking for agent",
    quote:
      "Any reliable insurance agent who can explain medical cards properly? I don't want someone who only pushes me to sign.",
    location: "Kuala Lumpur",
    product: "Medical card",
    postedAt: "4 hours ago",
    level: "high",
    confidence: 94,
    whyItMatters:
      "The user is explicitly asking for a trustworthy agent and values explanation over hard selling.",
    publicContext:
      "A public request for an agent who can explain medical-card trade-offs without using pressure tactics.",
    knownFacts: [
      "The user wants medical-card guidance",
      "Trust and explanation quality are important",
      "The user is open to an agent recommendation",
    ],
    unknownFacts: [
      "Coverage needs and budget",
      "Existing policies",
      "Preferred insurer or takaful requirement",
    ],
    riskNotes: [
      "Lead with education rather than a product pitch",
      "Do not claim to be more trustworthy than another agent without evidence",
    ],
    suggestedResponse:
      "A useful comparison should cover annual limits, room rate, co-insurance, waiting periods, exclusions, and how premiums may change over time. I am an insurance agent and can share a plain-language checklist first, with no obligation to choose a plan.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "considering-switch",
    isDemo: true,
    title: "Considering-switch request",
    opportunityType: "Considering switch",
    quote:
      "My medical-card premium increased again. I am thinking of changing, but I'm worried about waiting periods and exclusions.",
    location: "Penang",
    product: "Medical card",
    postedAt: "6 hours ago",
    level: "high",
    confidence: 93,
    whyItMatters:
      "There is clear dissatisfaction and comparison intent, but continuity risks must be explained carefully.",
    publicContext:
      "A policyholder is considering alternatives after another renewal increase and is concerned about replacement-policy risks.",
    knownFacts: [
      "The current medical-card premium increased",
      "The customer is considering changing plans",
      "Waiting periods and exclusions are explicit concerns",
    ],
    unknownFacts: [
      "Current policy benefits and exclusions",
      "Health and underwriting status",
      "Whether adjusting the current policy is possible",
    ],
    riskNotes: [
      "Replacing coverage can affect continuity and existing-condition treatment",
      "The current policy should not be cancelled before suitable replacement coverage is confirmed",
    ],
    suggestedResponse:
      "Sorry to hear about the increase. Before changing plans, it may help to compare the new premium, annual limit, deductible, exclusions, waiting periods, and whether changing affects existing-condition coverage. I'm an insurance agent and can share a neutral comparison checklist if that would be useful.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "claim-appeal",
    isDemo: true,
    title: "Claim appeal guidance",
    opportunityType: "Claim assistance request",
    quote:
      "My hospital claim was rejected because they said it was pre-existing. What documents should I prepare if I want to appeal?",
    location: "Johor",
    product: "Health insurance",
    postedAt: "Yesterday",
    level: "medium",
    confidence: 88,
    whyItMatters:
      "This person needs guidance, but the agent must not promise claim approval or use the situation for aggressive selling.",
    publicContext:
      "A public request for process guidance after a hospital claim was declined.",
    knownFacts: [
      "The hospital claim was rejected",
      "The stated reason relates to a pre-existing condition",
      "The customer wants to understand the appeal process",
    ],
    unknownFacts: [
      "Policy wording and disclosure history",
      "Insurer's formal rejection letter",
      "Appeal deadline and required evidence",
    ],
    riskNotes: [
      "Claims guidance must follow the insurer's official process",
      "No approval outcome should be implied",
    ],
    suggestedResponse:
      "You may want to start with the written rejection reason, policy wording, medical reports requested by the insurer, admission records, and any original disclosure documents. The insurer's official appeal channel should confirm the exact checklist. Avoid sharing medical documents publicly.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "provider-comparison",
    isDemo: true,
    title: "Medical-card provider comparison",
    opportunityType: "Provider comparison",
    quote:
      "AIA, Great Eastern and Prudential medical cards - which points should I compare besides the premium?",
    location: "Malaysia",
    product: "Medical card",
    insurer: "AIA, Great Eastern, Prudential",
    postedAt: "Yesterday",
    level: "high",
    confidence: 91,
    whyItMatters:
      "The customer is actively evaluating alternatives and asking for decision criteria.",
    publicContext:
      "A public comparison request naming three insurers and asking for a decision framework.",
    knownFacts: [
      "Three insurers are being compared",
      "The product is a medical card",
      "The customer wants criteria beyond price",
    ],
    unknownFacts: [
      "Age, budget, and medical history",
      "Preferred hospital and room rate",
      "Existing coverage and exclusions",
    ],
    riskNotes: [
      "Product details must be checked against current disclosure documents",
      "Mention volume or familiarity does not establish product suitability",
    ],
    suggestedResponse:
      "Besides premium, compare annual and lifetime limits, room rate, co-insurance or deductible, panel hospitals, exclusions, waiting periods, renewal terms, and how benefits change over time. A like-for-like table is more useful than a brand ranking.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "new-family-planning",
    isDemo: true,
    title: "New-family protection planning",
    opportunityType: "Advice and planning request",
    quote:
      "Just had our first baby. Should we prioritise medical insurance, life insurance, or education savings first?",
    location: "Petaling Jaya",
    product: "Family protection",
    postedAt: "2 days ago",
    level: "high",
    confidence: 90,
    whyItMatters:
      "The customer is at a life-event trigger and actively requesting guidance.",
    publicContext:
      "New parents are publicly asking how to sequence protection and savings priorities.",
    knownFacts: [
      "The family recently had its first baby",
      "Medical, life, and education savings are being considered",
      "The user wants prioritisation guidance",
    ],
    unknownFacts: [
      "Household income and emergency savings",
      "Existing employer and personal coverage",
      "Debts, dependants, and monthly budget",
    ],
    riskNotes: [
      "A recommendation requires a proper family fact-find",
      "Avoid fear-based messaging around the new child",
    ],
    suggestedResponse:
      "A common starting point is emergency cash flow, essential medical protection, and income protection for the parents before longer-term education savings. The right order depends on existing benefits, dependants, debts, and monthly affordability. A simple needs checklist can make the trade-offs clearer.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "sme-group-medical",
    isDemo: true,
    title: "SME group-medical request",
    opportunityType: "Business purchase request",
    quote:
      "I run a company with 12 staff. Looking for affordable group medical coverage. Where should I start?",
    location: "Kuala Lumpur",
    product: "SME group medical",
    postedAt: "2 days ago",
    level: "very_high",
    confidence: 97,
    whyItMatters:
      "The user disclosed team size and a clear business requirement.",
    publicContext:
      "A business owner is publicly seeking a starting point for employee medical coverage.",
    knownFacts: [
      "The company has 12 employees",
      "The requirement is group medical coverage",
      "Affordability is important",
    ],
    unknownFacts: [
      "Employee age profile and locations",
      "Desired inpatient and outpatient benefits",
      "Current benefits and annual budget",
    ],
    riskNotes: [
      "Final terms depend on census data and insurer underwriting",
      "Do not ask for employee personal data in public",
    ],
    suggestedResponse:
      "For a 12-person team, start with the employee census, inpatient versus outpatient priorities, annual limit, panel access, exclusions, and target budget. I can share a non-sensitive checklist for comparing group plans before any employee details are collected.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
  {
    id: "complaint-only",
    isDemo: true,
    title: "Premium complaint without help-seeking intent",
    opportunityType: "Complaint only",
    quote: "My insurance premium is getting too expensive.",
    location: "Unknown",
    product: "Unknown",
    postedAt: "3 days ago",
    level: "low",
    confidence: 62,
    whyItMatters:
      "This is dissatisfaction, but there is no request for an alternative, advice, or agent. CariLead does not classify every complaint as a qualified opportunity.",
    publicContext:
      "A short public complaint that contains no product detail, budget, location, or request for help.",
    knownFacts: ["The poster feels the premium is expensive"],
    unknownFacts: [
      "Product and insurer",
      "Whether the price changed",
      "Whether the user wants advice or alternatives",
    ],
    riskNotes: [
      "Low context and no explicit help-seeking signal",
      "A sales response may be intrusive",
    ],
    suggestedResponse:
      "No sales response is recommended from this text alone. Monitor for a follow-up question or a clear request for comparison help.",
    responseWarnings: sharedWarnings,
    sourceUrl: "#demo-source",
  },
];

export const freeFeatures = [
  "Top customer complaint themes",
  "Popular insurance questions",
  "Product demand trends",
  "Anonymised opportunity examples",
  "Insurer and product mention summaries",
  "Weekly email report",
];

export const proFeatures = [
  "Original public source links",
  "Full public conversation context",
  "Recent opportunity alerts",
  "Industry and location filters",
  "Insurance-product filters",
  "Opportunity scoring",
  "Suggested response angles",
  "Save and track opportunities",
  "Faster alerts before conversations become old",
];

export const methodologySteps = [
  "Search relevant public discussions.",
  "Remove duplicated, promotional, and unrelated content.",
  "Identify complaints, questions, comparisons, purchase requests, and switching signals.",
  "Separate low-value complaints from genuine help-seeking behaviour.",
  "Link members back to the original public source.",
];

export const methodologyPrinciples = [
  "Complaint volume is not market size.",
  "An insurer mention is not automatically negative.",
  "Promotion is not customer adoption.",
  "Switching intent is not counted unless the text supports it.",
  "A public question is a signal, not a guaranteed customer.",
  "Source context should always be reviewed before responding.",
];
