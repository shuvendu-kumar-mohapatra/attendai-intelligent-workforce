import React, { useEffect, useState } from 'react';
import {
  Upload,
  FileText,
  Search,
  Trash2,
  BookOpen,
  CheckCircle,
  ExternalLink,
  X,
  Download,
  Maximize2,
  Minimize2,
  FileSpreadsheet,
  Layers,
  ZoomIn,
  ZoomOut,
  AlertCircle,
  RefreshCw,
  FileCheck
} from 'lucide-react';
import { api, API_BASE } from '../services/api';
import { Policy, PolicyChunk } from '../types';
import { useAuth } from '../context/AuthContext';
import { downloadFile } from '../utils/download';

interface PolicyContentElement {
  type: string;
  page_number?: number;
  section?: string;
  text?: string;
  rows?: string[][];
}

interface PolicyContentResponse {
  id: string;
  title: string;
  category: string;
  format: string; // 'pdf' | 'docx' | 'txt' | 'chunk'
  file_size: number;
  total_pages: number;
  elements_count: number;
  elements: PolicyContentElement[];
  download_url: string;
  view_url: string;
}

export const Policies: React.FC = () => {
  const { user } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; error?: boolean } | null>(null);

  // Search across policies
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PolicyChunk[]>([]);
  const [searching, setSearching] = useState(false);

  // Document Reader state
  const [docContent, setDocContent] = useState<PolicyContentResponse | null>(null);
  const [readingPolicy, setReadingPolicy] = useState(false);
  const [docSearch, setDocSearch] = useState('');
  const [readerViewMode, setReaderViewMode] = useState<'embed' | 'text'>('embed');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(100);

  // Upload modal
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState('Attendance & Leave');
  const [uploading, setUploading] = useState(false);

  const token = localStorage.getItem('token') || '';

  const showToast = (text: string, error = false) => {
    setFeedbackMsg({ text, error });
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  const fetchPolicies = async () => {
    setLoading(true);
    try {
      const res = await api.get('/policies');
      setPolicies(res.data);
    } catch (e: any) {
      console.error('Failed to load policies:', e);
      showToast('Failed to load policies from server.', true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleOpenDocument = async (id: string) => {
    setReadingPolicy(true);
    setDocSearch('');
    setZoomLevel(100);
    setIsFullscreen(false);
    try {
      const res = await api.get(`/policies/${id}/content`);
      setDocContent(res.data);
      // Default to structured text reader for all documents for guaranteed instant rendering across all environments
      setReaderViewMode('text');
    } catch (e: any) {
      showToast(e.response?.data?.detail || 'Failed to retrieve document content.', true);
    } finally {
      setReadingPolicy(false);
    }
  };

  const handleDownload = async (policyId: string, title: string, format: string) => {
    const ext = format === 'docx' ? '.docx' : format === 'txt' ? '.txt' : '.pdf';
    const filename = `${title.replace(/[^a-zA-Z0-9_\- ]/g, '_')}${ext}`;
    await downloadFile(
      `/policies/${policyId}/download`,
      filename,
      () => showToast(`Starting download for ${title}...`),
      () => {},
      (err) => showToast(`Download failed: ${err}`, true)
    );
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.get('/policies/search', { params: { query: searchQuery } });
      setSearchResults(res.data);
      if (res.data.length === 0) {
        showToast(`No policy sections matched "${searchQuery}".`);
      }
    } catch (e) {
      console.error('Failed to execute policy search:', e);
      showToast('Error searching policy repository.', true);
    } finally {
      setSearching(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadTitle.trim()) return;

    setUploading(true);
    const form = new FormData();
    form.append('file', uploadFile);
    form.append('title', uploadTitle.trim());
    form.append('category', uploadCategory);

    try {
      await api.post('/policies/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadTitle('');
      showToast(`Document "${uploadTitle}" uploaded and indexed successfully.`);
      fetchPolicies();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Failed to upload document', true);
    } finally {
      setUploading(false);
    }
  };

  const handleDeletePolicy = async (id: string, title: string) => {
    if (!confirm(`Are you sure you want to delete "${title}" and all its indexed sections?`)) return;
    try {
      await api.delete(`/policies/${id}`);
      if (docContent?.id === id) {
        setDocContent(null);
      }
      showToast(`Policy "${title}" deleted.`);
      fetchPolicies();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Failed to delete policy', true);
    }
  };

  const canUpload = user?.role === 'admin' || user?.role === 'hr_manager';

  // Filter elements for structured text view
  const filteredElements = (docContent?.elements || []).filter((el) => {
    if (!docSearch.trim()) return true;
    const q = docSearch.toLowerCase();
    if (el.text && el.text.toLowerCase().includes(q)) return true;
    if (el.section && el.section.toLowerCase().includes(q)) return true;
    if (el.rows && el.rows.some((r) => r.some((c) => c.toLowerCase().includes(q)))) return true;
    return false;
  });

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {feedbackMsg && (
        <div
          className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg border text-xs font-medium transition-all transform animate-in fade-in slide-in-from-top-4 ${
            feedbackMsg.error
              ? 'bg-rose-50 border-rose-200 text-rose-800'
              : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`}
        >
          {feedbackMsg.error ? <AlertCircle className="w-4 h-4 text-rose-500" /> : <FileCheck className="w-4 h-4 text-emerald-500" />}
          <span>{feedbackMsg.text}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <h1 className="text-xl font-bold text-dark tracking-tight">Policies & Guidelines</h1>
          <p className="text-xs text-secondary mt-0.5">
            Full-text policy repository with interactive document viewing, PyMuPDF/python-docx extraction, and AI search citations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchPolicies}
            disabled={loading}
            className="px-3 py-1.5 bg-white border border-border rounded-lg text-xs font-medium text-dark hover:bg-slate-50 flex items-center gap-1.5 shadow-xs transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-primary' : 'text-secondary'}`} />
            <span>Refresh</span>
          </button>
          {canUpload && (
            <button
              onClick={() => setShowUploadModal(true)}
              className="px-3.5 py-1.5 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover flex items-center gap-1.5 shadow-sm transition-colors cursor-pointer"
            >
              <Upload className="w-4 h-4" />
              <span>Upload Document</span>
            </button>
          )}
        </div>
      </div>

      {/* Interactive Policy Search Bar */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-card space-y-4">
        <div>
          <h2 className="text-sm font-bold text-dark">Policy Search & Citation Lookup</h2>
          <p className="text-xs text-secondary mt-0.5">
            Search across company policies, attendance guidelines, overtime rules, and leave regulations.
          </p>
        </div>

        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-secondary" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. grace period, overtime calculation, sick leave medical certificate..."
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:outline-none focus:ring-1 focus:ring-primary focus:bg-white"
            />
          </div>
          <button
            type="submit"
            disabled={searching || !searchQuery.trim()}
            className="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-hover shadow-sm disabled:opacity-50 cursor-pointer"
          >
            {searching ? 'Searching...' : 'Search Policies'}
          </button>
        </form>

        {/* Search Results */}
        {searchResults.length > 0 && (
          <div className="pt-3 border-t border-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-dark">
                Search Results ({searchResults.length} relevant sections found)
              </span>
              <button
                onClick={() => setSearchResults([])}
                className="text-xs text-secondary hover:text-dark underline"
              >
                Clear Results
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {searchResults.map((chunk) => (
                <div key={chunk.id} className="p-3.5 rounded-lg bg-slate-50 border border-border space-y-1.5 text-xs">
                  <div className="flex items-center justify-between pb-1 border-b border-border/60">
                    <span className="font-semibold text-primary">{chunk.title}</span>
                    <span className="text-[10px] bg-white border border-border px-1.5 py-0.5 rounded font-mono text-secondary">
                      Page {chunk.page_number} &bull; {chunk.section || 'General'}
                    </span>
                  </div>
                  <p className="text-secondary leading-relaxed line-clamp-3 font-sans">
                    {chunk.content}
                  </p>
                  <div className="pt-1 flex items-center justify-between text-[11px]">
                    <span className="text-slate-400 italic font-mono text-[10px]">
                      {chunk.citation}
                    </span>
                    <button
                      onClick={() => handleOpenDocument(chunk.policy_id)}
                      className="text-primary hover:underline font-medium flex items-center gap-1 cursor-pointer"
                    >
                      <BookOpen className="w-3 h-3" />
                      <span>Read Document</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Indexed Documents Table */}
      <div className="bg-card border border-border rounded-xl shadow-card overflow-hidden">
        <div className="p-4 border-b border-border flex items-center justify-between bg-slate-50/50">
          <div>
            <h2 className="text-sm font-bold text-dark">Indexed Company Documents</h2>
            <p className="text-xs text-secondary mt-0.5">
              Select any document to read in the interactive viewer or download directly.
            </p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-white border border-border rounded-lg text-secondary">
            {policies.length} {policies.length === 1 ? 'Document' : 'Documents'} Available
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-secondary border-b border-border font-medium">
              <tr>
                <th className="py-3 px-4">Document Title</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Size</th>
                <th className="py-3 px-4">Sections</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-secondary">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-primary" />
                    <span>Loading policy documents...</span>
                  </td>
                </tr>
              ) : policies.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-secondary">
                    No policy documents found in organization library.
                  </td>
                </tr>
              ) : (
                policies.map((p) => {
                  const ext = p.file_path ? p.file_path.split('.').pop()?.toLowerCase() : 'pdf';
                  return (
                    <tr key={p.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4">
                        <button
                          onClick={() => handleOpenDocument(p.id)}
                          className="flex items-center gap-2.5 text-left group cursor-pointer"
                          title="Click to read document"
                        >
                          <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 group-hover:bg-primary group-hover:text-white transition-colors">
                            <FileText className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="font-semibold text-dark group-hover:text-primary transition-colors block">
                              {p.title}
                            </span>
                            <span className="text-[10px] uppercase font-mono text-secondary">
                              Format: {ext}
                            </span>
                          </div>
                        </button>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                          {p.category}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-secondary">
                        {p.file_size ? `${Math.round(p.file_size / 1024)} KB` : '–'}
                      </td>
                      <td className="py-3 px-4 font-mono text-dark">
                        {p.chunk_count || 1} sections
                      </td>
                      <td className="py-3 px-4">
                        {p.status === 'active' || !p.status ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-success border border-emerald-200 capitalize">
                            <CheckCircle className="w-3 h-3" />
                            <span>Active</span>
                          </span>
                        ) : p.status === 'processing' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-primary border border-blue-200 capitalize">
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            <span>Processing</span>
                          </span>
                        ) : p.status === 'empty' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 capitalize">
                            <AlertCircle className="w-3 h-3" />
                            <span>Empty</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-danger border border-rose-200 capitalize">
                            <AlertCircle className="w-3 h-3" />
                            <span>Failed</span>
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => handleOpenDocument(p.id)}
                            className="px-2.5 py-1.5 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover flex items-center gap-1 shadow-xs transition-colors cursor-pointer"
                            title="Read Document in Viewer"
                          >
                            <BookOpen className="w-3.5 h-3.5" />
                            <span>Read</span>
                          </button>
                          <button
                            onClick={() => handleDownload(p.id, p.title, ext || 'pdf')}
                            className="px-2.5 py-1.5 bg-white border border-border text-dark rounded-lg text-xs font-medium hover:bg-slate-50 flex items-center gap-1 shadow-xs transition-colors cursor-pointer"
                            title="Download Original Document"
                          >
                            <Download className="w-3.5 h-3.5 text-secondary" />
                            <span>Download</span>
                          </button>
                          {canUpload && (
                            <button
                              onClick={() => handleDeletePolicy(p.id, p.title)}
                              className="p-1.5 rounded-lg text-secondary hover:text-danger hover:bg-rose-50 transition-colors cursor-pointer"
                              title="Delete Policy"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Professional Interactive Document Reader Modal */}
      {docContent && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5">
          <div
            className={`bg-white border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden transition-all duration-200 ${
              isFullscreen ? 'w-full h-full rounded-none' : 'w-full max-w-5xl max-h-[92vh] h-[850px]'
            }`}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-border bg-slate-50/80 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                  <BookOpen className="w-5 h-5" />
                </div>
                <div className="truncate">
                  <h3 className="text-base font-bold text-dark truncate">{docContent.title}</h3>
                  <div className="flex items-center gap-2 text-xs text-secondary mt-0.5 flex-wrap">
                    <span className="px-2 py-0.5 bg-white border border-border rounded text-[10px] font-semibold text-primary">
                      {docContent.category}
                    </span>
                    <span>&bull;</span>
                    <span className="uppercase font-mono text-[11px] font-semibold text-slate-700">
                      {docContent.format}
                    </span>
                    <span>&bull;</span>
                    <span>{Math.round((docContent.file_size || 0) / 1024)} KB</span>
                    <span>&bull;</span>
                    <span>{docContent.total_pages} {docContent.total_pages === 1 ? 'Page' : 'Pages'}</span>
                  </div>
                </div>
              </div>

              {/* Header Actions */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* View Switcher for PDF */}
                {docContent.format === 'pdf' && (
                  <div className="bg-slate-200/80 p-0.5 rounded-lg flex items-center text-xs">
                    <button
                      onClick={() => setReaderViewMode('embed')}
                      className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                        readerViewMode === 'embed'
                          ? 'bg-white text-dark shadow-xs'
                          : 'text-secondary hover:text-dark'
                      }`}
                    >
                      PDF View
                    </button>
                    <button
                      onClick={() => setReaderViewMode('text')}
                      className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                        readerViewMode === 'text'
                          ? 'bg-white text-dark shadow-xs'
                          : 'text-secondary hover:text-dark'
                      }`}
                    >
                      Text View
                    </button>
                  </div>
                )}

                <button
                  onClick={() => handleDownload(docContent.id, docContent.title, docContent.format)}
                  className="px-3 py-1.5 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover flex items-center gap-1.5 shadow-xs cursor-pointer"
                  title="Download Original File"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download</span>
                </button>

                <button
                  onClick={() => setIsFullscreen(!isFullscreen)}
                  className="p-1.5 rounded-lg border border-border text-secondary hover:text-dark hover:bg-slate-100 cursor-pointer"
                  title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
                >
                  {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>

                <button
                  onClick={() => setDocContent(null)}
                  className="p-1.5 rounded-lg text-secondary hover:text-dark hover:bg-slate-100 cursor-pointer"
                  title="Close Reader"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Sub-toolbar (Search & Zoom Controls) */}
            <div className="px-6 py-2.5 border-b border-border/80 bg-white flex items-center justify-between gap-4">
              <div className="relative flex-1 max-w-md">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-secondary" />
                <input
                  type="text"
                  placeholder="Filter content inside this document..."
                  value={docSearch}
                  onChange={(e) => setDocSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:bg-white focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex items-center gap-3 text-xs text-secondary">
                {readerViewMode === 'embed' && docContent.format === 'pdf' ? (
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setZoomLevel((z) => Math.max(50, z - 15))}
                      className="p-1 rounded hover:bg-slate-100 text-secondary hover:text-dark"
                      title="Zoom Out"
                    >
                      <ZoomOut className="w-3.5 h-3.5" />
                    </button>
                    <span className="font-mono text-[11px] font-semibold w-10 text-center">{zoomLevel}%</span>
                    <button
                      onClick={() => setZoomLevel((z) => Math.min(200, z + 15))}
                      className="p-1 rounded hover:bg-slate-100 text-secondary hover:text-dark"
                      title="Zoom In"
                    >
                      <ZoomIn className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setZoomLevel(100)}
                      className="ml-1 text-[11px] text-primary hover:underline font-medium"
                    >
                      Reset
                    </button>
                  </div>
                ) : (
                  <span>
                    Showing {filteredElements.length} of {docContent.elements.length} document elements
                  </span>
                )}
              </div>
            </div>

            {/* Document Reader Body */}
            <div className="flex-1 overflow-y-auto bg-slate-100/60 p-4 sm:p-6">
              {/* PDF EMBED VIEWER */}
              {readerViewMode === 'embed' && docContent.format === 'pdf' ? (
                <div className="w-full h-full min-h-[500px] flex flex-col bg-slate-200/50 rounded-xl overflow-hidden shadow-inner border border-border">
                  <div className="flex items-center justify-between px-4 py-2 bg-slate-100 border-b border-border text-xs text-secondary flex-shrink-0">
                    <span>Viewing official PDF preview. If your browser blocks embedded PDFs:</span>
                    <button
                      onClick={() => setReaderViewMode('text')}
                      className="text-primary font-semibold hover:underline cursor-pointer ml-2"
                    >
                      Switch to Structured Text Reader &rarr;
                    </button>
                  </div>
                  <iframe
                    src={`${API_BASE}/policies/${docContent.id}/view?token=${encodeURIComponent(token)}#zoom=${zoomLevel}`}
                    title={docContent.title}
                    className="w-full flex-1 min-h-[600px] border-0 bg-white"
                  />
                </div>
              ) : (
                /* STRUCTURED DOCUMENT VIEWER (FOR DOCX, TXT, OR TEXT VIEW) */
                <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm border border-border p-6 sm:p-10 space-y-6 font-sans">
                  <div className="border-b border-border pb-4 space-y-1">
                    <h2 className="text-xl font-bold text-dark">{docContent.title}</h2>
                    <p className="text-xs text-primary font-semibold">{docContent.category} &bull; Official Policy Document</p>
                  </div>

                  {filteredElements.length === 0 ? (
                    <div className="text-center py-12 text-secondary text-xs">
                      No document sections match "{docSearch}".
                    </div>
                  ) : (
                    filteredElements.map((el, idx) => {
                      if (el.type === 'heading1') {
                        return (
                          <h3 key={idx} className="text-lg font-bold text-dark pt-3 pb-1 border-b border-slate-100">
                            {el.text}
                          </h3>
                        );
                      }
                      if (el.type === 'heading2') {
                        return (
                          <h4 key={idx} className="text-sm font-bold text-slate-800 pt-2 text-primary">
                            {el.text}
                          </h4>
                        );
                      }
                      if (el.type === 'heading3') {
                        return (
                          <h5 key={idx} className="text-xs font-bold text-slate-700">
                            {el.text}
                          </h5>
                        );
                      }
                      if (el.type === 'table' && el.rows) {
                        return (
                          <div key={idx} className="overflow-x-auto my-3 border border-border rounded-lg">
                            <table className="w-full text-left text-xs border-collapse">
                              <tbody>
                                {el.rows.map((row, rIdx) => (
                                  <tr key={rIdx} className={rIdx === 0 ? 'bg-slate-100 font-semibold' : 'border-t border-border hover:bg-slate-50'}>
                                    {row.map((cell, cIdx) => (
                                      <td key={cIdx} className="p-2.5 border-r border-border last:border-r-0">
                                        {cell}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        );
                      }
                      if (el.type === 'page') {
                        return (
                          <div key={idx} className="border border-slate-200 rounded-xl p-5 bg-slate-50/50 space-y-3">
                            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                              <span className="px-2 py-0.5 bg-primary/10 text-primary font-semibold rounded text-[11px]">
                                Page {el.page_number || idx + 1}
                              </span>
                              {el.section && (
                                <span className="text-xs font-bold text-slate-800">
                                  {el.section}
                                </span>
                              )}
                            </div>
                            <p className="whitespace-pre-wrap text-xs text-slate-700 leading-relaxed font-sans">
                              {el.text}
                            </p>
                          </div>
                        );
                      }
                      // Regular paragraph
                      return (
                        <div key={idx} className="space-y-1.5 text-xs text-slate-700 leading-relaxed font-sans">
                          {el.section && (
                            <span className="block font-bold text-dark text-xs mb-1">
                              {el.section} {el.page_number ? `(Page ${el.page_number})` : ''}
                            </span>
                          )}
                          <p className="whitespace-pre-wrap">{el.text}</p>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-border bg-slate-50 flex items-center justify-between text-xs text-secondary">
              <div className="flex items-center gap-2">
                <FileCheck className="w-3.5 h-3.5 text-success" />
                <span>Verified Official Workforce Document &bull; AttendAI Secure Policy Vault</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleDownload(docContent.id, docContent.title, docContent.format)}
                  className="px-3 py-1.5 bg-white border border-border text-dark rounded-lg font-medium hover:bg-slate-100 flex items-center gap-1 cursor-pointer"
                >
                  <Download className="w-3 h-3 text-secondary" />
                  <span>Download File</span>
                </button>
                <button
                  onClick={() => setDocContent(null)}
                  className="px-4 py-1.5 bg-primary text-white rounded-lg font-semibold hover:bg-primary-hover cursor-pointer"
                >
                  Done Reading
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-bold text-dark">Upload Policy Document</h3>
              <button onClick={() => setShowUploadModal(false)} className="text-secondary hover:text-dark cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpload} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-dark mb-1">Document Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Employee Handbook 2026"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-dark mb-1">Category</label>
                <select
                  value={uploadCategory}
                  onChange={(e) => setUploadCategory(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:bg-white"
                >
                  <option value="Attendance & Punctuality">Attendance & Punctuality</option>
                  <option value="Leave Management">Leave Management</option>
                  <option value="Code of Conduct">Code of Conduct</option>
                  <option value="Remote Work">Remote Work</option>
                  <option value="General HR">General HR</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-dark mb-1">Select File (PDF, DOCX, TXT)</label>
                <input
                  type="file"
                  required
                  accept=".pdf,.docx,.doc,.txt"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:bg-white cursor-pointer"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 border border-border rounded-lg text-xs font-medium text-secondary hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFile || !uploadTitle}
                  className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {uploading ? 'Processing & Indexing...' : 'Upload & Index'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
