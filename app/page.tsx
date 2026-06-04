'use client';

import { useState } from 'react';
import { ClaimRequest, AdjudicationDecision } from '@/lib/types';

const TEST_CASES: { id: string; name: string; data: ClaimRequest }[] = [
  {
    id: 'TC001',
    name: 'TC001 – Simple Consultation (Approved)',
    data: {
      member_id: 'EMP001',
      member_name: 'Rajesh Kumar',
      treatment_date: '2024-11-01',
      claim_amount: 1500,
      documents: {
        prescription: {
          doctor_name: 'Dr. Sharma',
          doctor_reg: 'KA/45678/2015',
          diagnosis: 'Viral fever',
          medicines_prescribed: ['Paracetamol 650mg', 'Vitamin C'],
        },
        bill: { consultation_fee: 1000, diagnostic_tests: 500, test_names: ['CBC', 'Dengue test'] },
      },
    },
  },
  {
    id: 'TC002',
    name: 'TC002 – Dental + Cosmetic (Partial)',
    data: {
      member_id: 'EMP002',
      member_name: 'Priya Singh',
      treatment_date: '2024-10-15',
      claim_amount: 12000,
      documents: {
        prescription: {
          doctor_name: 'Dr. Patel',
          doctor_reg: 'MH/23456/2018',
          diagnosis: 'Tooth decay requiring root canal',
          procedures: ['Root canal treatment', 'Teeth whitening'],
        },
        bill: { root_canal: 8000, teeth_whitening: 4000 } as unknown as ClaimRequest['documents']['bill'],
      },
    },
  },
  {
    id: 'TC003',
    name: 'TC003 – Per-Claim Limit Exceeded (Rejected)',
    data: {
      member_id: 'EMP003',
      member_name: 'Amit Verma',
      treatment_date: '2024-10-20',
      claim_amount: 7500,
      documents: {
        prescription: {
          doctor_name: 'Dr. Gupta',
          doctor_reg: 'DL/34567/2016',
          diagnosis: 'Gastroenteritis',
          medicines_prescribed: ['Antibiotics', 'Probiotics'],
        },
        bill: { consultation_fee: 2000, medicines: 5500 },
      },
    },
  },
  {
    id: 'TC004',
    name: 'TC004 – Missing Documents (Rejected)',
    data: {
      member_id: 'EMP004',
      member_name: 'Sneha Reddy',
      treatment_date: '2024-10-25',
      claim_amount: 2000,
      documents: {
        bill: { consultation_fee: 1500, medicines: 500 },
      },
    },
  },
  {
    id: 'TC005',
    name: 'TC005 – Diabetes Waiting Period (Rejected)',
    data: {
      member_id: 'EMP005',
      member_name: 'Vikram Joshi',
      member_join_date: '2024-09-01',
      treatment_date: '2024-10-15',
      claim_amount: 3000,
      documents: {
        prescription: {
          doctor_name: 'Dr. Mehta',
          doctor_reg: 'GJ/56789/2014',
          diagnosis: 'Type 2 Diabetes',
          medicines_prescribed: ['Metformin', 'Glimepiride'],
        },
        bill: { consultation_fee: 1000, medicines: 2000 },
      },
    },
  },
  {
    id: 'TC006',
    name: 'TC006 – Ayurvedic Treatment (Approved)',
    data: {
      member_id: 'EMP006',
      member_name: 'Kavita Nair',
      treatment_date: '2024-10-28',
      claim_amount: 4000,
      documents: {
        prescription: {
          doctor_name: 'Vaidya Krishnan',
          doctor_reg: 'AYUR/KL/2345/2019',
          diagnosis: 'Chronic joint pain',
          treatment: 'Panchakarma therapy',
        },
        bill: { consultation_fee: 1000, diagnostic_tests: 3000 },
      },
    },
  },
  {
    id: 'TC007',
    name: 'TC007 – MRI Without Pre-Auth (Rejected)',
    data: {
      member_id: 'EMP007',
      member_name: 'Suresh Patil',
      treatment_date: '2024-11-02',
      claim_amount: 15000,
      documents: {
        prescription: {
          doctor_name: 'Dr. Rao',
          doctor_reg: 'AP/67890/2017',
          diagnosis: 'Suspected lumbar disc herniation',
          tests_prescribed: ['MRI Lumbar Spine'],
        },
        bill: { diagnostic_tests: 15000 },
      },
    },
  },
  {
    id: 'TC008',
    name: 'TC008 – Fraud Pattern (Manual Review)',
    data: {
      member_id: 'EMP008',
      member_name: 'Ravi Menon',
      treatment_date: '2024-10-30',
      claim_amount: 4800,
      previous_claims_same_day: 3,
      documents: {
        prescription: {
          doctor_name: 'Dr. Khan',
          doctor_reg: 'UP/45678/2016',
          diagnosis: 'Migraine',
          medicines_prescribed: ['Sumatriptan', 'Propranolol'],
        },
        bill: { consultation_fee: 2000, medicines: 2800 },
      },
    },
  },
  {
    id: 'TC009',
    name: 'TC009 – Weight Loss Excluded (Rejected)',
    data: {
      member_id: 'EMP009',
      member_name: 'Anita Desai',
      treatment_date: '2024-10-18',
      claim_amount: 8000,
      documents: {
        prescription: {
          doctor_name: 'Dr. Banerjee',
          doctor_reg: 'WB/34567/2015',
          diagnosis: 'Obesity - BMI 35',
          treatment: 'Bariatric consultation and diet plan',
        },
        bill: { consultation_fee: 3000, medicines: 5000 },
      },
    },
  },
  {
    id: 'TC010',
    name: 'TC010 – Network Hospital Cashless (Approved)',
    data: {
      member_id: 'EMP010',
      member_name: 'Deepak Shah',
      treatment_date: '2024-11-03',
      claim_amount: 4500,
      hospital: 'Apollo Hospitals',
      cashless_request: true,
      documents: {
        prescription: {
          doctor_name: 'Dr. Iyer',
          doctor_reg: 'TN/56789/2013',
          diagnosis: 'Acute bronchitis',
          medicines_prescribed: ['Antibiotics', 'Bronchodilators'],
        },
        bill: { consultation_fee: 1500, medicines: 3000 },
      },
    },
  },
];

const DECISION_CONFIG = {
  APPROVED: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300', label: 'APPROVED' },
  REJECTED: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300', label: 'REJECTED' },
  PARTIAL: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300', label: 'PARTIAL APPROVAL' },
  MANUAL_REVIEW: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300', label: 'MANUAL REVIEW' },
};

function buildEmptyClaim(): ClaimRequest {
  return {
    member_id: '',
    member_name: '',
    member_join_date: '',
    treatment_date: '',
    claim_amount: 0,
    hospital: '',
    cashless_request: false,
    previous_claims_same_day: 0,
    documents: {
      prescription: {
        doctor_name: '',
        doctor_reg: '',
        diagnosis: '',
        medicines_prescribed: [],
        treatment: '',
        tests_prescribed: [],
      },
      bill: {
        consultation_fee: 0,
        medicines: 0,
        diagnostic_tests: 0,
      },
    },
  };
}

export default function Home() {
  const [claim, setClaim] = useState<ClaimRequest>(buildEmptyClaim());
  const [selectedTestCase, setSelectedTestCase] = useState('');
  const [result, setResult] = useState<AdjudicationDecision | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);

  function loadTestCase() {
    const tc = TEST_CASES.find((t) => t.id === selectedTestCase);
    if (tc) {
      setClaim(tc.data);
      setResult(null);
      setError(null);
    }
  }

  function updateClaim(path: string[], value: unknown) {
    setClaim((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as ClaimRequest;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let obj: any = next;
      for (let i = 0; i < path.length - 1; i++) obj = obj[path[i]];
      obj[path[path.length - 1]] = value;
      return next;
    });
  }

  function parseList(val: string): string[] {
    return val
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    // Strip empty optional fields before sending
    const payload = JSON.parse(JSON.stringify(claim));
    if (!payload.hospital) delete payload.hospital;
    if (!payload.member_join_date) delete payload.member_join_date;
    if (!payload.previous_claims_same_day) delete payload.previous_claims_same_day;
    if (!payload.cashless_request) delete payload.cashless_request;
    if (!payload.documents.prescription?.treatment) delete payload.documents.prescription?.treatment;
    if (!payload.documents.prescription?.medicines_prescribed?.length)
      delete payload.documents.prescription?.medicines_prescribed;
    if (!payload.documents.prescription?.tests_prescribed?.length)
      delete payload.documents.prescription?.tests_prescribed;
    if (!payload.documents.prescription) delete payload.documents.prescription;

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/adjudicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

  const decisionStyle = result ? DECISION_CONFIG[result.decision] ?? DECISION_CONFIG.MANUAL_REVIEW : null;

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center">
            <span className="text-white text-sm font-bold">P</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Plum OPD Claim Adjudication</h1>
        </div>
        <p className="text-gray-500 text-sm ml-11">AI-powered claim evaluation against policy PLUM_OPD_2024</p>
      </div>

      {/* Test Case Loader */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex items-center gap-3">
        <span className="text-sm font-medium text-gray-700 whitespace-nowrap">Load test case:</span>
        <select
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
          value={selectedTestCase}
          onChange={(e) => setSelectedTestCase(e.target.value)}
        >
          <option value="">-- Select a test case --</option>
          {TEST_CASES.map((tc) => (
            <option key={tc.id} value={tc.id}>
              {tc.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={loadTestCase}
          disabled={!selectedTestCase}
          className="px-4 py-2 bg-violet-600 text-white text-sm rounded-lg disabled:opacity-40 hover:bg-violet-700 transition-colors"
        >
          Load
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Member Information */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Member Information</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Member ID *</label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.member_id}
                onChange={(e) => updateClaim(['member_id'], e.target.value)}
                placeholder="EMP001"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Member Name *</label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.member_name}
                onChange={(e) => updateClaim(['member_name'], e.target.value)}
                placeholder="Rajesh Kumar"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Policy Join Date</label>
              <input
                type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.member_join_date ?? ''}
                onChange={(e) => updateClaim(['member_join_date'], e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Previous Claims Same Day</label>
              <input
                type="number"
                min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.previous_claims_same_day ?? 0}
                onChange={(e) => updateClaim(['previous_claims_same_day'], Number(e.target.value))}
              />
            </div>
          </div>
        </section>

        {/* Treatment Details */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Treatment Details</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Treatment Date *</label>
              <input
                required
                type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.treatment_date}
                onChange={(e) => updateClaim(['treatment_date'], e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Claim Amount (₹) *</label>
              <input
                required
                type="number"
                min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.claim_amount || ''}
                onChange={(e) => updateClaim(['claim_amount'], Number(e.target.value))}
                placeholder="1500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Hospital / Clinic</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.hospital ?? ''}
                onChange={(e) => updateClaim(['hospital'], e.target.value)}
                placeholder="Apollo Hospitals (leave blank for non-network)"
              />
            </div>
            <div className="flex items-center gap-3 pt-5">
              <input
                type="checkbox"
                id="cashless"
                checked={claim.cashless_request ?? false}
                onChange={(e) => updateClaim(['cashless_request'], e.target.checked)}
                className="w-4 h-4 accent-violet-600"
              />
              <label htmlFor="cashless" className="text-sm text-gray-700">
                Cashless request
              </label>
            </div>
          </div>
        </section>

        {/* Prescription */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Prescription</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Doctor Name</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.prescription?.doctor_name ?? ''}
                onChange={(e) => updateClaim(['documents', 'prescription', 'doctor_name'], e.target.value)}
                placeholder="Dr. Sharma"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Doctor Reg. No.</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.prescription?.doctor_reg ?? ''}
                onChange={(e) => updateClaim(['documents', 'prescription', 'doctor_reg'], e.target.value)}
                placeholder="KA/45678/2015"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Diagnosis</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.prescription?.diagnosis ?? ''}
                onChange={(e) => updateClaim(['documents', 'prescription', 'diagnosis'], e.target.value)}
                placeholder="Viral fever"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Medicines Prescribed (one per line)</label>
              <textarea
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
                value={(claim.documents.prescription?.medicines_prescribed ?? []).join('\n')}
                onChange={(e) =>
                  updateClaim(['documents', 'prescription', 'medicines_prescribed'], parseList(e.target.value))
                }
                placeholder="Paracetamol 650mg&#10;Vitamin C"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Tests Prescribed (one per line)</label>
              <textarea
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
                value={(claim.documents.prescription?.tests_prescribed ?? []).join('\n')}
                onChange={(e) =>
                  updateClaim(['documents', 'prescription', 'tests_prescribed'], parseList(e.target.value))
                }
                placeholder="CBC&#10;Dengue test"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Treatment / Procedures</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.prescription?.treatment ?? ''}
                onChange={(e) => updateClaim(['documents', 'prescription', 'treatment'], e.target.value)}
                placeholder="Panchakarma therapy"
              />
            </div>
          </div>
        </section>

        {/* Bill */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Bill Breakdown (₹)</h2>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Consultation Fee</label>
              <input
                type="number"
                min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.bill?.consultation_fee ?? ''}
                onChange={(e) => updateClaim(['documents', 'bill', 'consultation_fee'], Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Medicines</label>
              <input
                type="number"
                min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.bill?.medicines ?? ''}
                onChange={(e) => updateClaim(['documents', 'bill', 'medicines'], Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Diagnostic Tests</label>
              <input
                type="number"
                min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                value={claim.documents.bill?.diagnostic_tests ?? ''}
                onChange={(e) => updateClaim(['documents', 'bill', 'diagnostic_tests'], Number(e.target.value))}
              />
            </div>
          </div>
        </section>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-violet-600 text-white font-semibold rounded-xl hover:bg-violet-700 disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Adjudicating claim...' : 'Adjudicate Claim'}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">{error}</div>
      )}

      {/* Results */}
      {result && decisionStyle && (
        <div className="mt-8 bg-white rounded-xl border border-gray-200 overflow-hidden">
          {/* Decision Banner */}
          <div className={`${decisionStyle.bg} ${decisionStyle.border} border-b px-6 py-5`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">{result.claim_id}</p>
                <p className={`text-2xl font-bold ${decisionStyle.text}`}>{decisionStyle.label}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 mb-1">Approved Amount</p>
                <p className="text-2xl font-bold text-gray-900">
                  ₹{result.approved_amount.toLocaleString('en-IN')}
                </p>
              </div>
            </div>

            {/* Confidence bar */}
            <div className="mt-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Confidence</span>
                <span>{Math.round(result.confidence_score * 100)}%</span>
              </div>
              <div className="w-full bg-white/60 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${decisionStyle.text.replace('text', 'bg')}`}
                  style={{ width: `${result.confidence_score * 100}%` }}
                />
              </div>
            </div>
          </div>

          <div className="p-6 space-y-5">
            {/* Rejection reasons */}
            {result.rejection_reasons?.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Rejection Reasons</h3>
                <div className="flex flex-wrap gap-2">
                  {result.rejection_reasons.map((r) => (
                    <span key={r} className="px-3 py-1 bg-red-50 text-red-700 text-xs rounded-full border border-red-200">
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Rejected items */}
            {(result.rejected_items?.length ?? 0) > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Excluded Items</h3>
                <ul className="space-y-1">
                  {(result.rejected_items ?? []).map((item) => (
                    <li key={item} className="text-sm text-gray-700 flex items-start gap-2">
                      <span className="text-red-500 mt-0.5">×</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Deductions */}
            {result.deductions && Object.keys(result.deductions).length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Deductions</h3>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(result.deductions).map(([k, v]) => (
                    <div key={k} className="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                      <span className="text-gray-500 capitalize">{k}: </span>
                      <span className="font-semibold text-gray-800">₹{v.toLocaleString('en-IN')}</span>
                    </div>
                  ))}
                  {result.network_discount ? (
                    <div className="px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-sm">
                      <span className="text-gray-500">Network discount: </span>
                      <span className="font-semibold text-green-700">–₹{result.network_discount.toLocaleString('en-IN')}</span>
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {/* Fraud flags */}
            {(result.flags?.length ?? 0) > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Flags</h3>
                <div className="flex flex-wrap gap-2">
                  {(result.flags ?? []).map((f) => (
                    <span key={f} className="px-3 py-1 bg-orange-50 text-orange-700 text-xs rounded-full border border-orange-200">
                      ⚠ {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Notes */}
            {result.notes && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Notes</h3>
                <p className="text-sm text-gray-700">{result.notes}</p>
              </div>
            )}

            {/* Next steps */}
            {result.next_steps && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Next Steps</h3>
                <p className="text-sm text-gray-700">{result.next_steps}</p>
              </div>
            )}

            {/* Reasoning accordion */}
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
                  {result.reasoning}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
