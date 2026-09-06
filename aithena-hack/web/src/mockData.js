// Mock data matching the agreed schema
// Person C builds against this until the real backend lands at hour 5.

export const mockContracts = [
  {
    id: 1,
    filename: "CloudVendor_SaaS_Agreement_2023.pdf",
    parties: "Acme Pte Ltd / CloudVendor Inc.",
    contract_type: "SaaS Subscription",
    start_date: "2023-06-01",
    end_date: "2026-06-01",
    renewal_type: "auto",
    notice_period_days: 60,
    notice_deadline: "2026-04-02",
    governing_law: "Singapore",
    is_scanned: false,
    clauses_total: 34,
    clauses_covered: 22,
    fields: [
      {
        field_name: "payment_obligation",
        value: "S$40,000 per annum, payable quarterly in advance",
        verbatim_quote: "The Customer shall pay the Subscription Fee of S$40,000 per annum, payable quarterly in advance within 30 days of invoice.",
        quote_match_score: 97.2,
        page: 4,
        bbox: "72,340,540,365",
        confidence: "VERIFIED",
      },
    ],
  },
  {
    id: 2,
    filename: "Distributor_Agreement_APAC_2024.pdf",
    parties: "Acme Pte Ltd / PacificDist Co.",
    contract_type: "Distribution Agreement",
    start_date: "2024-01-15",
    end_date: "2027-01-15",
    renewal_type: "manual",
    notice_period_days: 90,
    notice_deadline: "2026-10-17",
    governing_law: "Singapore",
    is_scanned: false,
    clauses_total: 41,
    clauses_covered: 12,
    fields: [],
  },
];

export const mockConflicts = [
  {
    id: 1,
    contract_a_filename: "Distributor_Agreement_APAC_2024.pdf",
    contract_b_filename: "Reseller_Agreement_SG_2024.pdf",
    kind: "exclusivity_overlap",
    description: "PacificDist has exclusive APAC rights but Reseller has SG rights — overlap detected",
    severity: "high",
  },
];

export const mockCalendarEvents = [
  {
    contract_filename: "CloudVendor_SaaS_Agreement_2023.pdf",
    event_type: "notice_deadline",
    date: "2026-04-02",
    days_remaining: 28,
    description: "Last day to give 60-day non-renewal notice for S$40,000/yr SaaS",
    urgency: "critical",
  },
  {
    contract_filename: "CloudVendor_SaaS_Agreement_2023.pdf",
    event_type: "renewal",
    date: "2026-06-01",
    days_remaining: 88,
    description: "SaaS subscription auto-renews for another year",
    urgency: "warning",
  },
];