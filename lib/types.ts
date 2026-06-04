// ── Extraction types (mirroring backend models.py) ───────────────────────────

export interface ExtractedPrescription {
  doctor_name: string;
  doctor_registration: string;
  patient_name: string;
  consultation_date: string;
  diagnosis: string;
  medicines_prescribed: string[];
  tests_advised: string[];
  procedures: string[];
  notes: string;
}

export interface ExtractedMedicalBill {
  hospital_name: string;
  bill_number: string;
  bill_date: string;
  patient_name: string;
  consultation_fee: number;
  procedure_charges: number;
  other_charges: number;
  total_amount: number;
  line_items: string[];
  payment_mode: string;
}

export interface ExtractedDiagnosticReport {
  lab_name: string;
  accreditation: string;
  report_date: string;
  patient_name: string;
  tests_performed: string[];
  abnormal_findings: string[];
  pathologist: string;
  summary: string;
}

export interface ExtractedPharmacyBill {
  pharmacy_name: string;
  drug_license: string;
  bill_date: string;
  patient_name: string;
  doctor_name: string;
  medicines_purchased: string[];
  total_amount: number;
}

export interface ExtractionResults {
  prescription?: ExtractedPrescription;
  medical_bill?: ExtractedMedicalBill;
  diagnostic_report?: ExtractedDiagnosticReport;
  pharmacy_bill?: ExtractedPharmacyBill;
}

// ── Adjudication decision ─────────────────────────────────────────────────────

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
  deductions?: Record<string, number>;
  rejected_items?: string[];
  flags?: string[];
}

export interface DocumentAdjudicationResponse {
  extractions: ExtractionResults;
  decision: AdjudicationDecision;
}
