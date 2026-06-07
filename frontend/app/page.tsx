'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  ScrollText,
  ShieldCheck,
  UserPlus,
  Workflow,
} from 'lucide-react';
import { MemberRecord } from '@/lib/types';
import CreateMemberModal from '@/app/components/CreateMemberModal';

export default function WelcomePage() {
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [createdMember, setCreatedMember] = useState<MemberRecord | null>(null);

  function handleMemberCreated(member: MemberRecord) {
    setCreatedMember(member);
    setMemberModalOpen(false);
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-16">
      {memberModalOpen && (
        <CreateMemberModal
          onClose={() => setMemberModalOpen(false)}
          onCreated={handleMemberCreated}
        />
      )}

      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-14 h-14 bg-gray-900 rounded-2xl mb-5">
          <ShieldCheck className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-3">
          OPD Claim Adjudication
        </h1>
        <p className="text-gray-500 max-w-xl mx-auto">
          Register members and submit outpatient claims for AI-powered evaluation
        </p>
      </div>

      {/* Registration window */}
      <section className="bg-white rounded-2xl border border-gray-200 p-8 mb-6 text-center">
        {createdMember ? (
          <div>
            <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 rounded-full mb-4">
              <CheckCircle2 className="w-7 h-7 text-green-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Member registered</h2>
            <p className="text-sm text-gray-500 mb-5">
              <span className="font-medium text-gray-700">{createdMember.name}</span>{' '}
              ({createdMember.member_id}) was added successfully.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/adjudicate"
                className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-5 py-2.5 bg-gray-900 text-white text-sm font-semibold rounded-xl hover:bg-black transition-colors"
              >
                Start a claim
                <ArrowRight className="w-4 h-4" />
              </Link>
              <button
                type="button"
                onClick={() => setMemberModalOpen(true)}
                className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-5 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-xl hover:bg-gray-50 transition-colors"
              >
                <UserPlus className="w-4 h-4" />
                Register another
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-4">
              <UserPlus className="w-7 h-7 text-gray-700" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">New here?</h2>
            <p className="text-sm text-gray-500 mb-5 max-w-md mx-auto">
              Register a member to get started. You can then submit their OPD
              documents.
            </p>
            <button
              type="button"
              onClick={() => setMemberModalOpen(true)}
              className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-gray-900 text-white text-sm font-semibold rounded-xl hover:bg-black transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              Register New Member
            </button>
          </div>
        )}
      </section>

      {/* Secondary actions */}
      <div className="flex flex-col items-center gap-4 mb-12">
        <Link
          href="/adjudicate"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
        >
          Already registered? Go to claim adjudication
          <ArrowRight className="w-4 h-4" />
        </Link>
        <Link
          href="/policy"
          className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-white border-2 border-gray-900 text-gray-900 text-sm font-semibold rounded-xl hover:bg-gray-900 hover:text-white transition-colors"
        >
          <ScrollText className="w-4 h-4" />
          View &amp; Edit Policy
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </main>
  );
}
