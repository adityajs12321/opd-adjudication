'use client';

import { useRef, useState } from 'react';
import {
  ClipboardList,
  ReceiptText,
  Microscope,
  Pill,
  ScrollText,
  ShieldCheck,
  UserPlus,
  X,
} from 'lucide-react';
import {
  AdjudicationDecision,
  DocumentAdjudicationResponse,
  ExtractedDiagnosticReport,
  ExtractedMedicalBill,
  ExtractedPharmacyBill,
  ExtractedPrescription,
  MemberRecord,
  PolicyContext,
} from '@/lib/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
  icon: React.ReactNode;
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
          {icon}
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
  icon: React.ReactNode;
  required?: boolean;
  fileRef: React.RefObject<HTMLInputElement>;
  file: File | null;
  onChange: (f: File | null) => void;
}) {
  return (
    <div
      className={`border-2 border-dashed rounded-xl p-5 flex flex-col items-center gap-2 cursor-pointer transition-colors ${
        file ? 'border-gray-900 bg-gray-50' : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
      }`}
      onClick={() => fileRef.current?.click()}
    >
      <span className={file ? 'text-gray-900' : 'text-gray-400'}>{icon}</span>
      <p className="text-sm font-medium text-gray-700 text-center">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </p>
      {file ? (
        <p className="text-xs text-gray-900 font-medium truncate max-w-full px-2">{file.name}</p>
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
  const [claimedAmount, setClaimedAmount] = useState('');

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

  const [memberModalOpen, setMemberModalOpen] = useState(false);

  function handleMemberCreated(member: MemberRecord) {
    // Pre-fill the claim form with the member we just created.
    setMemberId(member.member_id);
    setMemberJoinDate(member.join_date);
    setMemberModalOpen(false);
  }

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
    if (claimedAmount) form.append('claimed_amount', claimedAmount);
    if (prescriptionFile) form.append('prescription', prescriptionFile);
    if (medicalBillFile) form.append('medical_bill', medicalBillFile);
    if (diagnosticFile) form.append('diagnostic_report', diagnosticFile);
    if (pharmacyFile) form.append('pharmacy_bill', pharmacyFile);

    try {
      const res = await fetch(`${API_URL}/adjudicate-documents`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.error ?? `HTTP ${res.status}`);
      setResult(data);
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
      {memberModalOpen && (
        <CreateMemberModal
          onClose={() => setMemberModalOpen(false)}
          onCreated={handleMemberCreated}
        />
      )}

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">OPD Claim Adjudication</h1>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Member info */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-800">Member Information</h2>
            <button
              type="button"
              onClick={() => setMemberModalOpen(true)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-700 border border-gray-300 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              New Member
            </button>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Member ID *</label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                placeholder="EMP001"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Policy Join Date
                <span className="text-gray-400 ml-1">(waiting period)</span>
              </label>
              <input
                type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                value={memberJoinDate}
                onChange={(e) => setMemberJoinDate(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Claimed Amount (₹) *
              </label>
              <input
                required
                type="number"
                min="0"
                step="1"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                value={claimedAmount}
                onChange={(e) => setClaimedAmount(e.target.value)}
                placeholder="e.g. 1500"
              />
            </div>
          </div>
        </section>

        {/* Document uploads */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-1">Upload Documents</h2>
          <p className="text-xs text-gray-400 mb-4">
            First two are mandatory.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <UploadBox
              label="Medical Prescription"
              icon={<ClipboardList className="w-7 h-7" />}
              required
              fileRef={prescriptionRef}
              file={prescriptionFile}
              onChange={setPrescriptionFile}
            />
            <UploadBox
              label="Medical Bill / Invoice"
              icon={<ReceiptText className="w-7 h-7" />}
              required
              fileRef={medicalBillRef}
              file={medicalBillFile}
              onChange={setMedicalBillFile}
            />
            <UploadBox
              label="Diagnostic Test Report"
              icon={<Microscope className="w-7 h-7" />}
              fileRef={diagnosticRef}
              file={diagnosticFile}
              onChange={setDiagnosticFile}
            />
            <UploadBox
              label="Pharmacy Bill"
              icon={<Pill className="w-7 h-7" />}
              fileRef={pharmacyRef}
              file={pharmacyFile}
              onChange={setPharmacyFile}
            />
          </div>
        </section>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-gray-900 text-white font-semibold rounded-xl hover:bg-black disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Processing documents' : 'Process'}
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
                <ExtractionCard title="Prescription" icon={<ClipboardList className="w-4 h-4" />}>
                  <PrescriptionView data={extractions.prescription} />
                </ExtractionCard>
              )}
              {extractions.medical_bill && (
                <ExtractionCard title="Medical Bill" icon={<ReceiptText className="w-4 h-4" />}>
                  <MedicalBillView data={extractions.medical_bill} />
                </ExtractionCard>
              )}
              {extractions.diagnostic_report && (
                <ExtractionCard title="Diagnostic Report" icon={<Microscope className="w-4 h-4" />}>
                  <DiagnosticView data={extractions.diagnostic_report} />
                </ExtractionCard>
              )}
              {extractions.pharmacy_bill && (
                <ExtractionCard title="Pharmacy Bill" icon={<Pill className="w-4 h-4" />}>
                  <PharmacyView data={extractions.pharmacy_bill} />
                </ExtractionCard>
              )}
            </div>
          </div>

          {/* Policy context */}
          {result.policy_context && Object.keys(result.policy_context).length > 0 && (
            <PolicyContextCard ctx={result.policy_context} />
          )}

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
                  <div className="text-right space-y-1">
                    {claimedAmount && (
                      <p className="text-xs text-gray-500">
                        Claimed ₹{Number(claimedAmount).toLocaleString('en-IN')}
                      </p>
                    )}
                    <div>
                      <p className="text-xs text-gray-500 mb-0.5">Approved Amount</p>
                      <p className="text-2xl font-bold text-gray-900">
                        ₹{decision.approved_amount.toLocaleString('en-IN')}
                      </p>
                    </div>
                    {decision.decision !== 'REJECTED' && claimedAmount && Number(claimedAmount) > decision.approved_amount && (
                      <p className="text-xs text-amber-700 font-medium">
                        Copay ₹{(Number(claimedAmount) - decision.approved_amount).toLocaleString('en-IN')}
                      </p>
                    )}
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

              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

// ── Create member modal ───────────────────────────────────────────────────────

function CreateMemberModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (member: MemberRecord) => void;
}) {
  const [memberId, setMemberId] = useState('');
  const [name, setName] = useState('');
  const [joinDate, setJoinDate] = useState('');
  const [relationship, setRelationship] = useState('employee');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          member_id: memberId.trim(),
          name: name.trim(),
          join_date: joinDate,
          relationship,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.error ?? `HTTP ${res.status}`);
      onCreated(data as MemberRecord);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-800">
            <UserPlus className="w-5 h-5" />
            Create New Member
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleCreate} className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Member ID *</label>
            <input
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
              value={memberId}
              onChange={(e) => setMemberId(e.target.value)}
              placeholder="EMP001"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Full Name *</label>
            <input
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Rajesh Kumar"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Join Date *</label>
              <input
                required
                type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                value={joinDate}
                onChange={(e) => setJoinDate(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Relationship</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-gray-900"
                value={relationship}
                onChange={(e) => setRelationship(e.target.value)}
              >
                <option value="employee">Employee</option>
                <option value="spouse">Spouse</option>
                <option value="child">Child</option>
                <option value="parent">Parent</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs break-words">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-semibold text-white bg-gray-900 rounded-lg hover:bg-black disabled:opacity-50 transition-colors"
            >
              {saving ? 'Creating…' : 'Create Member'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Policy context card ───────────────────────────────────────────────────────

function PolicyContextCard({ ctx }: { ctx: PolicyContext }) {
  const [open, setOpen] = useState(false);

  const fmt = (n: number) => `₹${n.toLocaleString('en-IN')}`;

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <ScrollText className="w-4 h-4" />
          Retrieved Policy Terms
        </span>
        <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 py-4 space-y-4 text-sm">

          {ctx.limits && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Limits</p>
              <div className="flex flex-wrap gap-3">
                <span className="px-2 py-1 bg-gray-100 rounded text-gray-700">Per claim: {fmt(ctx.limits.per_claim)}</span>
                <span className="px-2 py-1 bg-gray-100 rounded text-gray-700">Annual: {fmt(ctx.limits.annual)}</span>
                <span className="px-2 py-1 bg-gray-100 rounded text-gray-700">Family floater: {fmt(ctx.limits.family_floater)}</span>
              </div>
            </div>
          )}

          {ctx.claim_requirements && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Claim Requirements</p>
              <div className="flex flex-wrap gap-3">
                <span className="px-2 py-1 bg-gray-100 rounded text-gray-700">Submit within {ctx.claim_requirements.submission_deadline_days} days</span>
                <span className="px-2 py-1 bg-gray-100 rounded text-gray-700">Min amount: {fmt(ctx.claim_requirements.minimum_claim_amount)}</span>
              </div>
            </div>
          )}

          {ctx.coverage && Object.keys(ctx.coverage).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Coverage Categories</p>
              <div className="space-y-2">
                {Object.entries(ctx.coverage).map(([name, cat]) => (
                  <div key={name} className="border border-gray-100 rounded-lg px-3 py-2">
                    <p className="font-medium text-gray-700 capitalize mb-1">{name.replace(/_/g, ' ')}</p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-500">
                      {cat.sub_limit != null && <span>Sub-limit: {fmt(cat.sub_limit)}</span>}
                      {cat.copay_percentage != null && <span>Copay: {cat.copay_percentage}%</span>}
                      {cat.network_discount != null && <span>Network discount: {cat.network_discount}%</span>}
                      {cat.covered != null && <span>{cat.covered ? 'Covered' : 'Not covered'}</span>}
                    </div>
                    {cat.covered_items && cat.covered_items.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {cat.covered_items.map((item) => (
                          <span key={item} className="px-2 py-0.5 bg-green-50 text-green-700 text-xs rounded border border-green-100">{item}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {ctx.waiting_periods && Object.keys(ctx.waiting_periods).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Waiting Periods (relevant)</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(ctx.waiting_periods).map(([cond, days]) => (
                  <span key={cond} className="px-2 py-1 bg-amber-50 border border-amber-100 rounded text-amber-800 text-xs">
                    {cond.replace(/_/g, ' ')}: {days} days
                  </span>
                ))}
              </div>
            </div>
          )}

          {ctx.exclusions && ctx.exclusions.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Exclusions</p>
              <ul className="space-y-0.5">
                {ctx.exclusions.map((e) => (
                  <li key={e} className="text-gray-600 flex items-start gap-1.5">
                    <span className="text-red-400 mt-0.5 shrink-0">×</span>{e}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ctx.network_hospitals && ctx.network_hospitals.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Network Hospitals</p>
              <div className="flex flex-wrap gap-2">
                {ctx.network_hospitals.map((h) => (
                  <span key={h} className="px-2 py-1 bg-blue-50 border border-blue-100 rounded text-blue-700 text-xs">{h}</span>
                ))}
              </div>
            </div>
          )}

        </div>
      )}
    </div>
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
