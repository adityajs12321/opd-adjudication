export interface Prescription {
  doctor_name: string;
  doctor_reg: string;
  diagnosis: string;
  medicines_prescribed?: string[];
  treatment?: string;
  tests_prescribed?: string[];
  procedures?: string[];
}

export interface Bill {
  consultation_fee?: number;
  medicines?: number;
  diagnostic_tests?: number;
  test_names?: string[];
  [key: string]: unknown;
}

export interface ClaimDocuments {
  prescription?: Prescription;
  bill?: Bill;
}

export interface ClaimRequest {
  member_id: string;
  member_name: string;
  member_join_date?: string;
  treatment_date: string;
  claim_amount: number;
  hospital?: string;
  cashless_request?: boolean;
  previous_claims_same_day?: number;
  documents: ClaimDocuments;
}

export interface AdjudicationDecision {
  claim_id: string;
  decision: 'APPROVED' | 'REJECTED' | 'PARTIAL' | 'MANUAL_REVIEW';
  approved_amount: number;
  rejection_reasons: string[];
  confidence_score: number;
  notes: string;
  next_steps: string;
  reasoning: string;
  cashless_approved?: boolean;
  network_discount?: number;
  flags?: string[];
  deductions?: Record<string, number>;
  rejected_items?: string[];
}
