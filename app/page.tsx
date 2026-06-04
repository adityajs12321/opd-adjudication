'use client';

import { useRef, useState } from 'react';
import {
  AdjudicationDecision,
  DocumentAdjudicationResponse,
  ExtractedDiagnosticReport,
  ExtractedMedicalBill,
  ExtractedPharmacyBill,
  ExtractedPrescription,
} from '@/lib/types';

// ── Decision badge config ─────────────────────────────────────────────────────

const DECISION_STYLE = {
  APPROVED: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300', label: 'APPROVED' },
  REJECTED: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300', label: 'REJECTED' },
  PARTIAL: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300', label: 'PARTIAL APPROVAL' },
  MANUAL_REVIEW: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300', label: 'MANUAL REVIEW' },
};

// ── Reusable sub-components ───────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string | number | undefined }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-gray-400 shrink-0 w-36">{label}</span>
      <span className="text-gray-800 font-medium">{String(value)}</span>
    </div>
  );
}

function List({ label, items }: { label: string; items: string[] | undefined }) {
  if (!items?.length) return null;
  return (
    <div className="text-sm">
      <p className="text-gray-400 mb-1">{label}</p>
      <ul className="space-y-0.5 ml-2">
        {items.map((item, i) => (
          <li key={i} className="text-gray-800">• {item}</li>
        ))}
      </ul>
    </div>
  );
}

function ExtractionCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <span>{icon}</span>
          {title}
        </span>
        <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-4 py-4 space-y-3">{children}</div>}
    </div>
  );
}

function UploadBox({
  label,
  icon,
  required,
  fileRef,
  file,
  onChange,
}: {
  label: string;
  icon: string;
  required?: boolean;
  fileRef: React.RefObject<HTMLInputElement>;
  file: File | null;
  onChange: (f: File | null) => void;
}) {
  return (
    <div
      className={`border-2 border-dashed rounded-xl p-5 flex flex-col items-center gap-2 cursor-pointer transition-colors ${
        file ? 'border-violet-400 bg-violet-50' : 'border-gray-300 hover:border-violet-300 hover:bg-gray-50'
      }`}
      onClick={() => fileRef.current?.click()}
    >
      <span className="text-2xl">{icon}</span>
      <p className="text-sm font-medium text-gray-700 text-center">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </p>
      {file ? (
        <p className="text-xs text-violet-700 font-medium truncate max-w-full px-2">{file.name}</p>
      ) : (
        <p className="text-xs text-gray-400">Click to upload (image or PDF)</p>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*,application/pdf"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Home() {
  const [memberId, setMemberId] = useState('');
  const [memberJoinDate, setMemberJoinDate] = useState('');

  const prescriptionRef = useRef<HTMLInputElement>(null!);
  const medicalBillRef = useRef<HTMLInputElement>(null!);
  const diagnosticRef = useRef<HTMLInputElement>(null!);
  const pharmacyRef = useRef<HTMLInputElement>(null!);

  const [prescriptionFile, setPrescriptionFile] = useState<File | null>(null);
  const [medicalBillFile, setMedicalBillFile] = useState<File | null>(null);
  const [diagnosticFile, setDiagnosticFile] = useState<File | null>(null);
  const [pharmacyFile, setPharmacyFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentAdjudicationResponse | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prescriptionFile && !medicalBillFile) {
      setError('Please upload at least a prescription or medical bill.');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.append('member_id', memberId);
    form.append('member_join_date', memberJoinDate);
    if (prescriptionFile) form.append('prescription', prescriptionFile);
    if (medicalBillFile) form.append('medical_bill', medicalBillFile);
    if (diagnosticFile) form.append('diagnostic_report', diagnosticFile);
    if (pharmacyFile) form.append('pharmacy_bill', pharmacyFile);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/adjudicate-documents`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.error ?? `HTTP ${res.status}`);
      setResult(data);
      setShowReasoning(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  const { extractions, decision } = result ?? {};
  const decisionStyle = decision ? DECISION_STYLE[decision.decision] : null;

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center">
            <span className="text-white text-sm font-bold">P</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Plum OPD Claim Adjudication</h1>
        </div>
        <p className="text-gray-500 text-sm ml-11">
          Upload your medical documents — AI agents extract data from each and adjudicate against policy PLUM_OPD_2024
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Member info */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Member Information</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Member ID *</label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                placeholder="EMP001"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Policy Join Date
                <span className="text-gray-400 ml-1">(for waiting period check)</span>
              </label>
              <input
                type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={memberJoinDate}
                onChange={(e) => setMemberJoinDate(e.target.value)}
              />
            </div>
          </div>
        </section>

        {/* Document uploads */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-1">Upload Documents</h2>
          <p className="text-xs text-gray-400 mb-4">
            A separate AI agent processes each document. At least one of the first two is required.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <UploadBox
              label="Medical Prescription"
              icon="📋"
              required
              fileRef={prescriptionRef}
              file={prescriptionFile}
              onChange={setPrescriptionFile}
            />
            <UploadBox
              label="Medical Bill / Invoice"
              icon="🧾"
              required
              fileRef={medicalBillRef}
              file={medicalBillFile}
              onChange={setMedicalBillFile}
            />
            <UploadBox
              label="Diagnostic Test Report"
              icon="🔬"
              fileRef={diagnosticRef}
              file={diagnosticFile}
              onChange={setDiagnosticFile}
            />
            <UploadBox
              label="Pharmacy Bill"
              icon="💊"
              fileRef={pharmacyRef}
              file={pharmacyFile}
              onChange={setPharmacyFile}
            />
          </div>
        </section>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-violet-600 text-white font-semibold rounded-xl hover:bg-violet-700 disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Processing documents & adjudicating…' : 'Process & Adjudicate'}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm break-words">
          {error}
        </div>
      )}

      {/* Results */}
      {result && extractions && decision && decisionStyle && (
        <div className="mt-8 space-y-6">
          {/* Extraction results */}
          <div>
            <h2 className="text-base font-semibold text-gray-800 mb-3">Extracted Data</h2>
            <div className="space-y-3">
              {extractions.prescription && (
                <ExtractionCard title="Prescription" icon="📋">
                  <PrescriptionView data={extractions.prescription} />
                </ExtractionCard>
              )}
              {extractions.medical_bill && (
                <ExtractionCard title="Medical Bill" icon="🧾">
                  <MedicalBillView data={extractions.medical_bill} />
                </ExtractionCard>
              )}
              {extractions.diagnostic_report && (
                <ExtractionCard title="Diagnostic Report" icon="🔬">
                  <DiagnosticView data={extractions.diagnostic_report} />
                </ExtractionCard>
              )}
              {extractions.pharmacy_bill && (
                <ExtractionCard title="Pharmacy Bill" icon="💊">
                  <PharmacyView data={extractions.pharmacy_bill} />
                </ExtractionCard>
              )}
            </div>
          </div>

          {/* Adjudication decision */}
          <div>
            <h2 className="text-base font-semibold text-gray-800 mb-3">Adjudication Decision</h2>
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              {/* Banner */}
              <div className={`${decisionStyle.bg} ${decisionStyle.border} border-b px-6 py-5`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-medium text-gray-500 mb-1">{decision.claim_id}</p>
                    <p className={`text-2xl font-bold ${decisionStyle.text}`}>{decisionStyle.label}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500 mb-1">Approved Amount</p>
                    <p className="text-2xl font-bold text-gray-900">
                      ₹{decision.approved_amount.toLocaleString('en-IN')}
                    </p>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Confidence</span>
                    <span>{Math.round(decision.confidence_score * 100)}%</span>
                  </div>
                  <div className="w-full bg-white/60 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${decisionStyle.text.replace('text', 'bg')}`}
                      style={{ width: `${decision.confidence_score * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="p-6 space-y-5">
                {(decision.rejection_reasons?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Rejection Reasons
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {decision.rejection_reasons.map((r) => (
                        <span
                          key={r}
                          className="px-3 py-1 bg-red-50 text-red-700 text-xs rounded-full border border-red-200"
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {(decision.rejected_items?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Excluded Items
                    </h3>
                    <ul className="space-y-1">
                      {(decision.rejected_items ?? []).map((item) => (
                        <li key={item} className="text-sm text-gray-700 flex items-start gap-2">
                          <span className="text-red-500 mt-0.5">×</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {decision.deductions && Object.keys(decision.deductions).length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Deductions
                    </h3>
                    <div className="flex flex-wrap gap-3">
                      {Object.entries(decision.deductions).map(([k, v]) => (
                        <div
                          key={k}
                          className="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm"
                        >
                          <span className="text-gray-500 capitalize">{k}: </span>
                          <span className="font-semibold text-gray-800">
                            ₹{v.toLocaleString('en-IN')}
                          </span>
                        </div>
                      ))}
                      {decision.network_discount ? (
                        <div className="px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-sm">
                          <span className="text-gray-500">Network discount: </span>
                          <span className="font-semibold text-green-700">
                            –₹{decision.network_discount.toLocaleString('en-IN')}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}

                {(decision.flags?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Flags
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {(decision.flags ?? []).map((f) => (
                        <span
                          key={f}
                          className="px-3 py-1 bg-orange-50 text-orange-700 text-xs rounded-full border border-orange-200"
                        >
                          ⚠ {f}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {decision.notes && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Notes</h3>
                    <p className="text-sm text-gray-700">{decision.notes}</p>
                  </div>
                )}

                {decision.next_steps && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                      Next Steps
                    </h3>
                    <p className="text-sm text-gray-700">{decision.next_steps}</p>
                  </div>
                )}

                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowReasoning((v) => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    <span>View detailed reasoning</span>
                    <span>{showReasoning ? '▲' : '▼'}</span>
                  </button>
                  {showReasoning && (
                    <div className="px-4 pb-4 text-sm text-gray-600 leading-relaxed border-t border-gray-200 pt-3">
                      {decision.reasoning}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

// ── Extraction detail views ───────────────────────────────────────────────────

function PrescriptionView({ data }: { data: ExtractedPrescription }) {
  return (
    <>
      <Field label="Doctor" value={data.doctor_name} />
      <Field label="Registration" value={data.doctor_registration} />
      <Field label="Patient" value={data.patient_name} />
      <Field label="Date" value={data.consultation_date} />
      <Field label="Diagnosis" value={data.diagnosis} />
      <List label="Medicines prescribed" items={data.medicines_prescribed} />
      <List label="Tests advised" items={data.tests_advised} />
      <List label="Procedures" items={data.procedures} />
      {data.notes && <Field label="Notes" value={data.notes} />}
    </>
  );
}

function MedicalBillView({ data }: { data: ExtractedMedicalBill }) {
  return (
    <>
      <Field label="Hospital" value={data.hospital_name} />
      <Field label="Bill No." value={data.bill_number} />
      <Field label="Date" value={data.bill_date} />
      <Field label="Patient" value={data.patient_name} />
      <Field label="Consultation fee" value={data.consultation_fee ? `₹${data.consultation_fee}` : undefined} />
      <Field label="Procedure charges" value={data.procedure_charges ? `₹${data.procedure_charges}` : undefined} />
      <Field label="Other charges" value={data.other_charges ? `₹${data.other_charges}` : undefined} />
      <Field label="Total amount" value={data.total_amount ? `₹${data.total_amount}` : undefined} />
      <List label="Line items" items={data.line_items} />
      <Field label="Payment mode" value={data.payment_mode} />
    </>
  );
}

function DiagnosticView({ data }: { data: ExtractedDiagnosticReport }) {
  return (
    <>
      <Field label="Lab" value={data.lab_name} />
      <Field label="Accreditation" value={data.accreditation} />
      <Field label="Date" value={data.report_date} />
      <Field label="Patient" value={data.patient_name} />
      <List label="Tests performed" items={data.tests_performed} />
      <List label="Abnormal findings" items={data.abnormal_findings} />
      <Field label="Pathologist" value={data.pathologist} />
      {data.summary && <Field label="Summary" value={data.summary} />}
    </>
  );
}

function PharmacyView({ data }: { data: ExtractedPharmacyBill }) {
  return (
    <>
      <Field label="Pharmacy" value={data.pharmacy_name} />
      <Field label="Drug license" value={data.drug_license} />
      <Field label="Date" value={data.bill_date} />
      <Field label="Patient" value={data.patient_name} />
      <Field label="Doctor" value={data.doctor_name} />
      <List label="Medicines purchased" items={data.medicines_purchased} />
      <Field label="Total amount" value={data.total_amount ? `₹${data.total_amount}` : undefined} />
    </>
  );
}
