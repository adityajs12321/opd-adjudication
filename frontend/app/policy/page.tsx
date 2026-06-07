'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  RotateCcw,
  ScrollText,
  Save,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Status =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved' }
  | { kind: 'error'; message: string };

export default function PolicyPage() {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const [dirty, setDirty] = useState(false);

  async function loadPolicy() {
    setLoading(true);
    setLoadError(null);
    setStatus({ kind: 'idle' });
    try {
      const res = await fetch(`${API_URL}/policy`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.error ?? `HTTP ${res.status}`);
      setText(JSON.stringify(data, null, 2));
      setDirty(false);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPolicy();
  }, []);

  async function handleSave() {
    // Validate JSON locally before hitting the API.
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setStatus({ kind: 'error', message: 'Invalid JSON — please fix the syntax before saving.' });
      return;
    }

    setStatus({ kind: 'saving' });
    try {
      const res = await fetch(`${API_URL}/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? data.error ?? `HTTP ${res.status}`);
      setText(JSON.stringify(data, null, 2));
      setDirty(false);
      setStatus({ kind: 'saved' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Unknown error' });
    }
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors mb-3"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to home
        </Link>
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center">
            <ScrollText className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Policy Editor</h1>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          View and edit policy <span className="font-medium text-gray-700">PLUM_OPD_2024</span>.
        </p>
      </div>

      <section className="bg-white rounded-xl border border-gray-200 p-6">
        {loading ? (
          <p className="text-sm text-gray-400 py-12 text-center">Loading policy…</p>
        ) : loadError ? (
          <div className="space-y-4">
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm break-words">
              Couldn’t load policy: {loadError}
            </div>
            <button
              type="button"
              onClick={loadPolicy}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              Retry
            </button>
          </div>
        ) : (
          <>
            <label className="block text-xs font-medium text-gray-600 mb-2">
              Policy JSON
            </label>
            <textarea
              spellCheck={false}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setDirty(true);
                if (status.kind !== 'idle') setStatus({ kind: 'idle' });
              }}
              className="w-full h-[28rem] border border-gray-300 rounded-lg px-3 py-2 font-mono text-xs leading-relaxed text-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 resize-y"
            />

            {/* Status line */}
            {status.kind === 'error' && (
              <div className="mt-3 flex items-start gap-2 text-sm text-red-700">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="break-words">{status.message}</span>
              </div>
            )}
            {status.kind === 'saved' && (
              <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                Policy saved — graph and rule engine updated.
              </div>
            )}

            <div className="mt-5 flex items-center justify-between">
              <button
                type="button"
                onClick={loadPolicy}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Discard changes
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={status.kind === 'saving' || !dirty}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-semibold rounded-xl hover:bg-black disabled:opacity-50 transition-colors"
              >
                <Save className="w-4 h-4" />
                {status.kind === 'saving' ? 'Saving…' : 'Save policy'}
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
