import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  FileDown,
  FileJson,
  FileSearch2,
  FileText,
  FlaskConical,
  Gauge,
  Image as ImageIcon,
  Info,
  Layers3,
  Link2,
  ListChecks,
  Loader2,
  Menu,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UploadCloud,
  FileUp,
  FileSpreadsheet,
  Sun,
  Moon,
  X,
} from 'lucide-react';
import { type ReactNode } from 'react';
import axios from 'axios';
import { jsPDF } from 'jspdf';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Route, Switch, useLocation, Router as WouterRouter } from 'wouter';

export type ExtractedPDFProduct = {
  manufacturer_part_number: string;
  brand: string;
  short_description: string;
  quantity?: number | null;
  category?: string | null;
  supporting_text?: string | null;
};

export type PDFExtractionResult = {
  filename: string;
  total_products_found: number;
  raw_text_length: number;
  products: ExtractedPDFProduct[];
  warnings?: string[];
};

export type PDFBatchProcessResult = {
  filename: string;
  total_products_found: number;
  processed_count: number;
  results: BackendProductIntelligence[];
};

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

type FormState = {
  mpn: string;
  manufacturer: string;
  description: string;
  website: string;
  additionalUrls: string;
  supportingText: string;
  processAction: string;
};

export type BackendSpec = {
  name: string;
  value: string;
  unit?: string | null;
  source?: string | null;
};

export type BackendEvidence = {
  source_type: string;
  locator: string;
  excerpt: string;
  confidence: 'low' | 'medium' | 'high';
};

export type BackendProductIntelligence = {
  manufacturer_part_number: string;
  brand: string;
  title: string;
  category: string;
  commerce_description: string;
  image_url?: string | null;
  images?: string[];
  key_features?: string[];
  specifications?: BackendSpec[];
  applications?: string[];
  compatible_products?: string[];
  normalized_attributes?: Record<string, string>;
  source_evidence?: BackendEvidence[];
  quality_warnings?: string[];
  confidence?: 'low' | 'medium' | 'high' | string;
  created_at?: string;
};

type ProcessStatus = 'empty' | 'loading' | 'success' | 'warning' | 'error';

const initialForm: FormState = {
  mpn: '',
  manufacturer: '',
  description: '',
  website: '',
  additionalUrls: '',
  supportingText: '',
  processAction: 'full-enrichment',
};

const presets: { id: string; label: string; detail: string; form: FormState }[] = [
  {
    id: 'festo',
    label: 'Pneumatic actuator',
    detail: 'Festo · DNC-32-100-PPV-A',
    form: {
      mpn: 'DNC-32-100-PPV-A',
      manufacturer: 'Festo',
      description: 'Double-acting compact cylinder, 32 mm bore, 100 mm stroke',
      website: 'https://www.festo.com/us/en/p/dnc-32-100-ppv-a-id_163375/',
      additionalUrls: 'https://www.festo.com/us/en/c/pneumatic-cylinders/',
      supportingText: 'Used in automated assembly lines. Confirm cushioning and mounting details.',
      processAction: 'full-enrichment',
    },
  },
  {
    id: 'schneider',
    label: 'Proximity sensor',
    detail: 'Schneider · XS618B1PAL2',
    form: {
      mpn: 'XS618B1PAL2',
      manufacturer: 'Schneider Electric',
      description: 'Inductive proximity sensor 18mm 24VDC PNP NO flush mount M12',
      website: 'https://www.se.com/ww/en/product/XS618B1PAL2/',
      additionalUrls: '',
      supportingText: 'Standard automation catalog part. Check sensing range and output wiring.',
      processAction: 'full-enrichment',
    },
  },
  {
    id: 'ifm',
    label: 'Inductive sensor',
    detail: 'ifm · IFS204',
    form: {
      mpn: 'IFS204',
      manufacturer: 'ifm electronic',
      description: 'Inductive proximity sensor, flush mount, M12 connector',
      website: 'https://www.ifm.com/us/en/product/IFS204',
      additionalUrls: '',
      supportingText: 'Legacy catalog record; verify electrical connection and sensing range.',
      processAction: 'full-enrichment',
    },
  },
  {
    id: 'skf',
    label: 'Deep groove bearing',
    detail: 'SKF · 6205-2RS1',
    form: {
      mpn: '6205-2RS1',
      manufacturer: 'SKF',
      description: 'Single row deep groove ball bearing with contact seals',
      website: 'https://www.skf.com/group/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings',
      additionalUrls: 'https://www.skf.com/binaries/pub12/Images/0901d196802809de-6205-2RS1_tcm_12-136585.pdf',
      supportingText: 'For a conveyor drive rebuild. Dimensional data is high priority.',
      processAction: 'specifications-only',
    },
  },
  {
    id: 'siemens',
    label: 'Industrial Motor',
    detail: 'Siemens · 1LA7096-4AA10',
    form: {
      mpn: '1LA7096-4AA10',
      manufacturer: 'Siemens',
      description: '3-phase asynchronous motor 1.5 kW 230/400V 1420 RPM',
      website: 'https://mall.industry.siemens.com/',
      additionalUrls: '',
      supportingText: 'High efficiency squirrel-cage motor for industrial conveyor applications.',
      processAction: 'full-enrichment',
    },
  },
];

const fallbackSample: BackendProductIntelligence = {
  manufacturer_part_number: 'DNC-32-100-PPV-A',
  brand: 'Festo',
  title: 'DNC compact pneumatic cylinder — 32 mm bore, 100 mm stroke',
  category: 'Pneumatic cylinders / compact cylinders',
  commerce_description:
    'The Festo DNC-32-100-PPV-A is a double-acting ISO 6432-style pneumatic cylinder with a 32 mm bore and 100 mm stroke. Its adjustable end-position cushioning helps reduce impact in automated handling, clamping, and light assembly applications. The proven tie-rod construction supports straightforward installation across machine platforms.',
  confidence: 'high',
  specifications: [
    { name: 'Cylinder bore', value: '32 mm', unit: 'mm', source: 'Festo product page' },
    { name: 'Stroke length', value: '100 mm', unit: 'mm', source: 'Festo product page' },
    { name: 'Operating pressure', value: '1.5–10 bar', unit: 'bar', source: 'Festo catalogue' },
    { name: 'Cushioning', value: 'Adjustable at both ends', unit: undefined, source: 'Festo catalogue' },
    { name: 'Port connection', value: 'G 1/8', unit: undefined, source: 'Festo technical sheet' },
    { name: 'Ambient temperature', value: '−20 to 80 °C', unit: '°C', source: 'Festo technical sheet' },
  ],
  key_features: [
    'Double-acting operation for powered extend and retract',
    'Adjustable pneumatic cushioning at both end positions',
    'Position sensing compatible with SMT-8M sensor family',
    'Corrosion-resistant anodized aluminium barrel',
  ],
  applications: ['Assembly automation', 'Material handling', 'Clamping fixtures', 'Packaging machinery'],
  normalized_attributes: {
    'Product type': 'Pneumatic cylinder',
    'Actuation': 'Double-acting',
    'Bore diameter': '32 mm',
    'Stroke': '100 mm',
    'Mounting standard': 'DNC / ISO profile',
    'Seal material': 'NBR / polyurethane',
  },
  source_evidence: [
    { locator: 'festo.com', source_type: 'Manufacturer page', excerpt: 'Identity, title, bore and stroke align', confidence: 'high' },
    { locator: 'Festo catalogue 2024', source_type: 'PDF document', excerpt: 'Pressure, port and cushioning details', confidence: 'high' },
    { locator: 'Motion Industries', source_type: 'Distributor listing', excerpt: 'Cross-check for market naming', confidence: 'medium' },
  ],
  quality_warnings: [
    'Mounting accessories are not included in the source record.',
    'Seal material is inferred from the family catalogue and should be confirmed for regulated applications.',
  ],
  images: [],
};

const processingSteps = [
  { label: 'Reading supplied sources', note: 'URLs, notes, and manufacturer context' },
  { label: 'Resolving product identity', note: 'Matching MPN across web and RAG databases' },
  { label: 'AI Extraction & Parsing', note: 'Qwen VL and LLM parameter structuring' },
  { label: 'Assembling commerce payload', note: 'Technical specs, evidence, and quality rubric' },
];

function IconButton({
  label,
  children,
  onClick,
  className = '',
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      data-testid={`button-${label.toLowerCase().replaceAll(' ', '-')}`}
      onClick={onClick}
      className={`focus-ring inline-flex h-9 w-9 items-center justify-center rounded-sm border border-transparent text-[hsl(var(--muted-foreground))] transition-all duration-200 hover:border-[hsl(var(--border))] hover:bg-[hsl(var(--card))] hover:text-[hsl(var(--foreground))] ${className}`}
    >
      {children}
    </button>
  );
}

function BrandMark() {
  return (
    <div className="relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-[3px_3px_0_hsl(204_28%_8%/0.35)]">
      <span className="absolute left-0 top-0 h-2 w-2 border-l-2 border-t-2 border-[hsl(var(--primary-foreground)/0.45)]" />
      <span className="font-mono-app text-[15px] font-semibold tracking-[-0.12em]">pi</span>
      <span className="absolute bottom-0 right-0 h-2 w-2 border-b-2 border-r-2 border-[hsl(var(--primary-foreground)/0.45)]" />
    </div>
  );
}

function Sidebar({
  activeView,
  onViewChange,
  historyCount,
  backendConnected,
}: {
  activeView: string;
  onViewChange: (view: string) => void;
  historyCount: number;
  backendConnected: boolean;
}) {
  const nav = [
    { id: 'workspace', label: 'Intelligence workspace', icon: FlaskConical },
    { id: 'runs', label: 'Run history', icon: Clock3 },
    { id: 'library', label: 'Source library', icon: BookOpen },
    { id: 'pdf-preview', label: 'PDF Product List', icon: FileSpreadsheet },
  ];
  return (
    <aside className="hidden min-h-[100dvh] w-[240px] shrink-0 flex-col bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] md:flex">
      <div className="flex h-[76px] items-center gap-3 border-b border-[hsl(var(--sidebar-border))] px-5">
        <BrandMark />
        <div>
          <div className="font-display text-[17px] font-semibold leading-none tracking-[-0.04em]">part intelligence</div>
          <div className="eyebrow mt-1.5 text-[hsl(var(--sidebar-foreground)/0.46)]">operations console</div>
        </div>
      </div>
      <div className="px-3 pt-6">
        <div className="eyebrow px-3 pb-2 text-[hsl(var(--sidebar-foreground)/0.38)]">Workspace</div>
        <nav className="space-y-1" aria-label="Primary navigation">
          {nav.map(({ id, label, icon: NavIcon }) => (
            <button
              type="button"
              key={id}
              data-testid={`button-nav-${id}`}
              onClick={() => onViewChange(id)}
              className={`focus-ring group flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-left text-[12px] transition-colors ${
                activeView === id
                  ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))] shadow-[inset_3px_0_hsl(var(--primary))]'
                  : 'text-[hsl(var(--sidebar-foreground)/0.62)] hover:bg-[hsl(var(--sidebar-accent)/0.7)] hover:text-[hsl(var(--sidebar-foreground))]'
              }`}
            >
              <NavIcon size={16} strokeWidth={activeView === id ? 2.3 : 1.7} />
              <span>{label}</span>
              {id === 'runs' && (
                <span className="ml-auto font-mono-app text-[10px] text-[hsl(var(--sidebar-foreground)/0.6)] bg-[hsl(var(--sidebar-border))] px-1.5 py-0.5 rounded">
                  {historyCount}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>
      <div className="mt-auto border-t border-[hsl(var(--sidebar-border))] p-4">
        <div className="mb-4 rounded-sm border border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-accent)/0.46)] p-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                backendConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className="eyebrow text-[hsl(var(--sidebar-foreground)/0.7)]">
              {backendConnected ? 'API Connected' : 'FastAPI Offline'}
            </span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[hsl(var(--sidebar-foreground)/0.52)] font-mono">
            {API_BASE_URL}
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[hsl(var(--accent))] text-[10px] font-semibold text-[hsl(var(--accent-foreground))]">
            AI
          </div>
          <div className="min-w-0">
            <div className="truncate text-[11px] font-medium">Cluster Agent</div>
            <div className="truncate text-[10px] text-[hsl(var(--sidebar-foreground)/0.43)]">Industrial Commerce</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  onNewRun,
  onToggleSidebar,
  backendConnected,
  theme,
  onToggleTheme,
}: {
  onNewRun: () => void;
  onToggleSidebar: () => void;
  backendConnected: boolean;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}) {
  return (
    <header className="flex min-h-[76px] items-center justify-between border-b border-[hsl(var(--border))] bg-[hsl(var(--background)/0.86)] px-4 backdrop-blur-sm sm:px-7">
      <div className="flex items-center gap-3">
        <IconButton label="open navigation" className="md:hidden" onClick={onToggleSidebar}>
          <Menu size={18} />
        </IconButton>
        <div>
          <div className="eyebrow text-[hsl(var(--muted-foreground))]">
            Product intelligence / <span className="text-[hsl(var(--accent))]">new run</span>
          </div>
          <h1 className="font-display mt-1 text-[19px] font-semibold tracking-[-0.04em] sm:text-[21px]">
            Resolve a manufacturer part
          </h1>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 border-r border-[hsl(var(--border))] pr-4 sm:flex">
          <div className={`h-2 w-2 rounded-full ${backendConnected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          <span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">
            {backendConnected ? 'FASTAPI · v0.1.0' : 'LOCAL BACKEND CHECKING'}
          </span>
        </div>
        <button
          type="button"
          data-testid="button-theme-toggle"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-[11px] font-semibold text-[hsl(var(--foreground))] transition-colors hover:bg-[hsl(var(--muted))]"
        >
          {theme === 'dark' ? (
            <>
              <Sun size={14} className="text-amber-400" />
              <span className="hidden sm:inline">Light</span>
            </>
          ) : (
            <>
              <Moon size={14} className="text-[hsl(var(--primary))]" />
              <span className="hidden sm:inline">Dark</span>
            </>
          )}
        </button>
        <button
          type="button"
          data-testid="button-new-run"
          onClick={onNewRun}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm bg-[hsl(var(--foreground))] px-3 text-[11px] font-semibold text-[hsl(var(--background))] transition-transform hover:-translate-y-0.5"
        >
          <Plus size={14} /> <span className="hidden sm:inline">New run</span>
        </button>
      </div>
    </header>
  );
}

function MobileNav({
  activeView,
  onViewChange,
  onClose,
}: {
  activeView: string;
  onViewChange: (view: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 bg-[hsl(var(--foreground)/0.28)] md:hidden" onClick={onClose}>
      <div
        className="h-full w-[276px] bg-[hsl(var(--sidebar))] p-4 text-[hsl(var(--sidebar-foreground))]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BrandMark />
            <span className="font-display text-[16px] font-semibold">part intelligence</span>
          </div>
          <IconButton label="close navigation" onClick={onClose} className="text-[hsl(var(--sidebar-foreground)/0.7)]">
            <X size={17} />
          </IconButton>
        </div>
        {['workspace', 'runs', 'library', 'pdf-preview'].map((id) => (
          <button
            type="button"
            key={id}
            data-testid={`button-mobile-nav-${id}`}
            onClick={() => {
              onViewChange(id);
              onClose();
            }}
            className={`mb-1 flex w-full items-center gap-3 rounded-sm px-3 py-3 text-left text-[12px] ${
              activeView === id
                ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-foreground))]'
                : 'text-[hsl(var(--sidebar-foreground)/0.62)]'
            }`}
          >
            {id === 'workspace' ? <FlaskConical size={16} /> : id === 'runs' ? <Clock3 size={16} /> : id === 'pdf-preview' ? <FileSpreadsheet size={16} /> : <BookOpen size={16} />}
            {id === 'workspace' ? 'Intelligence workspace' : id === 'runs' ? 'Run history' : id === 'pdf-preview' ? 'PDF Product List' : 'Source library'}
          </button>
        ))}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  required,
  error,
  multiline,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
  error?: string;
  multiline?: boolean;
}) {
  const id = `field-${label.toLowerCase().replaceAll(' ', '-')}`;
  return (
    <label className="block" htmlFor={id}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold text-[hsl(var(--foreground))]">
          {label} {required && <span className="text-[hsl(var(--primary))]">*</span>}
        </span>
        {hint && <span className="font-mono-app text-[9px] text-[hsl(var(--muted-foreground))]">{hint}</span>}
      </div>
      {multiline ? (
        <textarea
          id={id}
          data-testid={`textarea-${id.replace('field-', '')}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          rows={3}
          className={`focus-ring w-full resize-y rounded-sm border bg-[hsl(var(--card))] px-3 py-2.5 text-[12px] leading-relaxed text-[hsl(var(--foreground))] shadow-[inset_0_1px_2px_hsl(var(--foreground)/0.025)] placeholder:text-[hsl(var(--muted-foreground)/0.68)] ${
            error ? 'border-[hsl(var(--destructive))]' : 'border-[hsl(var(--input))]'
          } transition-colors focus:border-[hsl(var(--primary))]`}
        />
      ) : (
        <input
          id={id}
          data-testid={`input-${id.replace('field-', '')}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className={`focus-ring h-10 w-full rounded-sm border bg-[hsl(var(--card))] px-3 text-[12px] text-[hsl(var(--foreground))] shadow-[inset_0_1px_2px_hsl(var(--foreground)/0.025)] placeholder:text-[hsl(var(--muted-foreground)/0.68)] ${
            error ? 'border-[hsl(var(--destructive))]' : 'border-[hsl(var(--input))]'
          } transition-colors focus:border-[hsl(var(--primary))]`}
        />
      )}
      {error && <span className="mt-1 block text-[10px] text-[hsl(var(--destructive))]">{error}</span>}
    </label>
  );
}

function PresetCard({
  preset,
  selected,
  onClick,
}: {
  preset: (typeof presets)[number];
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={`button-preset-${preset.id}`}
      onClick={onClick}
      className={`focus-ring group w-full rounded-sm border p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-sm)] ${
        selected
          ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.09)]'
          : 'border-[hsl(var(--border))] bg-[hsl(var(--card)/0.55)] hover:border-[hsl(var(--input))]'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-sm ${
            selected
              ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
              : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
          }`}
        >
          {selected ? <Check size={13} /> : <Layers3 size={13} />}
        </span>
        <ArrowRight
          size={13}
          className="mt-1 text-[hsl(var(--muted-foreground)/0.5)] transition-transform group-hover:translate-x-0.5"
        />
      </div>
      <div className="mt-3 text-[11px] font-semibold">{preset.label}</div>
      <div className="mt-1 truncate font-mono-app text-[9px] text-[hsl(var(--muted-foreground))]">{preset.detail}</div>
    </button>
  );
}

function FormPanel({
  form,
  setForm,
  onProcess,
  onClear,
  status,
  errors,
  pdfFile,
  setPdfFile,
  pdfExtraction,
  onExtractPdf,
  onProcessPdfBatch,
  onSelectExtractedProduct,
  pdfLoading,
}: {
  form: FormState;
  setForm: (form: FormState) => void;
  onProcess: () => void;
  onClear: () => void;
  status: ProcessStatus;
  errors: Partial<Record<keyof FormState, string>>;
  pdfFile: File | null;
  setPdfFile: (file: File | null) => void;
  pdfExtraction: PDFExtractionResult | null;
  onExtractPdf: (file: File) => void;
  onProcessPdfBatch: (file: File) => void;
  onSelectExtractedProduct: (prod: ExtractedPDFProduct) => void;
  pdfLoading: boolean;
}) {
  const [intakeMode, setIntakeMode] = useState<'single' | 'pdf'>('single');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const update = (key: keyof FormState) => (value: string) => setForm({ ...form, [key]: value });

  return (
    <section
      className="overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card)/0.78)] shadow-[var(--shadow-sm)]"
      data-testid="panel-product-input"
    >
      <div className="flex items-center justify-between border-b border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.42)] px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-[hsl(var(--foreground))] text-[hsl(var(--background))]">
            <FileSearch2 size={13} />
          </div>
          <div>
            <h2 className="text-[12px] font-semibold">Source intake</h2>
            <p className="mt-0.5 text-[10px] text-[hsl(var(--muted-foreground))]">
              Provide minimal identifiers, URLs, or upload a PDF product list.
            </p>
          </div>
        </div>
        <div className="flex rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-0.5">
          <button
            type="button"
            onClick={() => setIntakeMode('single')}
            className={`px-2.5 py-1 text-[10px] font-medium rounded-sm transition-colors ${
              intakeMode === 'single'
                ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-semibold'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Single Part
          </button>
          <button
            type="button"
            onClick={() => setIntakeMode('pdf')}
            className={`px-2.5 py-1 text-[10px] font-medium rounded-sm transition-colors flex items-center gap-1.5 ${
              intakeMode === 'pdf'
                ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-semibold'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            <FileText size={11} /> Upload PDF
          </button>
        </div>
      </div>

      {intakeMode === 'pdf' ? (
        <div className="p-4 sm:p-5 space-y-4">
          <div
            onClick={() => fileInputRef.current?.click()}
            className="cursor-pointer border-2 border-dashed border-[hsl(var(--border))] hover:border-[hsl(var(--primary))] rounded-sm p-6 text-center bg-[hsl(var(--card)/0.4)] hover:bg-[hsl(var(--primary)/0.04)] transition-all"
          >
            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) setPdfFile(f);
              }}
            />
            <div className="flex flex-col items-center justify-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(var(--primary)/0.1)] text-[hsl(var(--primary))]">
                <UploadCloud size={20} />
              </div>
              <div className="text-[12px] font-semibold text-[hsl(var(--foreground))]">
                {pdfFile ? pdfFile.name : 'Click to select or drop a PDF product list'}
              </div>
              <div className="text-[10px] text-[hsl(var(--muted-foreground))]">
                Supports Bills of Materials (BOM), RFQ documents, purchase orders & equipment lists (.pdf)
              </div>
              {pdfFile && (
                <div className="font-mono-app text-[9px] text-[hsl(var(--accent))] bg-[hsl(var(--accent)/0.1)] px-2 py-0.5 rounded">
                  {(pdfFile.size / 1024).toFixed(1)} KB selected
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))]">
            <FileDown size={11} className="text-[hsl(var(--accent))]" />
            Don't have a PDF?{' '}
            <a
              href="/sample_bom.pdf"
              download="sample_bom.pdf"
              className="font-semibold text-[hsl(var(--primary))] hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              Download sample BOM
            </a>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              disabled={!pdfFile || pdfLoading}
              onClick={() => pdfFile && onExtractPdf(pdfFile)}
              className="focus-ring flex-1 inline-flex h-10 items-center justify-center gap-2 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-[11px] font-semibold text-[hsl(var(--foreground))] transition-colors hover:bg-[hsl(var(--muted))] disabled:opacity-50"
            >
              {pdfLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
              Extract Products List from PDF
            </button>
            <button
              type="button"
              disabled={!pdfFile || pdfLoading}
              onClick={() => pdfFile && onProcessPdfBatch(pdfFile)}
              className="focus-ring flex-1 inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-[hsl(var(--primary))] px-3 text-[11px] font-semibold text-[hsl(var(--primary-foreground))] transition-colors hover:opacity-95 disabled:opacity-50"
            >
              {pdfLoading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              Enrich All from PDF with AI
            </button>
          </div>

          {pdfExtraction && (
            <div className="mt-4 border border-[hsl(var(--border))] rounded-sm bg-[hsl(var(--card))] p-3 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-[11px]">
                  Detected Products ({pdfExtraction.total_products_found})
                </span>
                <span className="font-mono-app text-[9px] text-[hsl(var(--accent))] bg-[hsl(var(--accent)/0.1)] px-1.5 py-0.5 rounded">
                  {pdfExtraction.filename}
                </span>
              </div>

              {pdfExtraction.warnings && pdfExtraction.warnings.length > 0 && (
                <div className="text-[10px] text-amber-500 bg-amber-500/10 p-2 rounded">
                  {pdfExtraction.warnings.join(' ')}
                </div>
              )}

              <div className="max-h-[220px] overflow-y-auto space-y-1.5 pr-1">
                {pdfExtraction.products.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between border border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.3)] p-2 rounded-sm hover:border-[hsl(var(--primary))] transition-all"
                  >
                    <div className="min-w-0 flex-1 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[11px] font-bold text-[hsl(var(--foreground))]">
                          {item.manufacturer_part_number}
                        </span>
                        <span className="text-[10px] text-[hsl(var(--muted-foreground))]">· {item.brand}</span>
                        {item.quantity && (
                          <span className="text-[9px] bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))] font-mono px-1 rounded">
                            Qty: {item.quantity}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-[hsl(var(--muted-foreground))] truncate">
                        {item.short_description}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onSelectExtractedProduct(item)}
                      className="shrink-0 text-[10px] text-[hsl(var(--primary))] hover:underline flex items-center gap-1 font-semibold"
                    >
                      Analyze <ArrowRight size={11} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="p-4 sm:p-5">
          <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Manufacturer part number"
              hint="required"
              required
              value={form.mpn}
              onChange={update('mpn')}
              placeholder="e.g. DNC-32-100-PPV-A"
              error={errors.mpn}
            />
            <Field
              label="Brand / manufacturer"
              hint="recommended"
              required
              value={form.manufacturer}
              onChange={update('manufacturer')}
              placeholder="e.g. Festo"
              error={errors.manufacturer}
            />
          </div>
          <div className="space-y-4">
            <Field
              label="Short description"
              hint="recommended"
              value={form.description}
              onChange={update('description')}
              placeholder="e.g. Double-acting compact cylinder, 32 mm bore"
              multiline
            />
            <Field
              label="Product website URL"
              hint="optional"
              value={form.website}
              onChange={update('website')}
              placeholder="https://manufacturer.com/product/..."
              error={errors.website}
            />
            <Field
              label="Additional URLs"
              hint="one per line"
              value={form.additionalUrls}
              onChange={update('additionalUrls')}
              placeholder="Datasheets, distributor links, catalog URLs..."
              multiline
            />
            <Field
              label="Supporting text"
              hint="optional context"
              value={form.supportingText}
              onChange={update('supportingText')}
              placeholder="Application context, known specs, or target requirements"
              multiline
            />
          </div>
          <div className="mt-5 border-t border-[hsl(var(--border))] pt-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label htmlFor="process-action" className="text-[11px] font-semibold">
                Process action
              </label>
              <span className="font-mono-app text-[9px] text-[hsl(var(--accent))]">AI PIPELINE</span>
            </div>
            <div className="relative">
              <select
                id="process-action"
                data-testid="select-process-action"
                value={form.processAction}
                onChange={(event) => update('processAction')(event.target.value)}
                className="focus-ring h-10 w-full appearance-none rounded-sm border border-[hsl(var(--input))] bg-[hsl(var(--card))] px-3 pr-9 text-[12px] text-[hsl(var(--foreground))]"
              >
                <option value="full-enrichment">Full enrichment — Web scraping + Qwen VL + Hybrid RAG</option>
                <option value="specifications-only">Specifications only — Fast extraction</option>
                <option value="identity-check">Identity check — Resolve MPN & Citations</option>
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-3 top-3 text-[hsl(var(--muted-foreground))]"
              />
            </div>
          </div>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="button"
              data-testid="button-process-product"
              onClick={onProcess}
              disabled={status === 'loading'}
              className="focus-ring group inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-sm bg-[hsl(var(--primary))] px-4 text-[12px] font-bold text-[hsl(var(--primary-foreground))] shadow-[3px_3px_0_hsl(204_28%_12%/0.18)] transition-all hover:-translate-y-0.5 hover:shadow-[4px_5px_0_hsl(204_28%_12%/0.18)] disabled:cursor-wait disabled:opacity-70"
            >
              {status === 'loading' ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Resolving with AI Agent...
                </>
              ) : (
                <>
                  <Sparkles size={15} /> Process product{' '}
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
            <button
              type="button"
              data-testid="button-clear-inputs"
              onClick={onClear}
              className="focus-ring inline-flex h-11 items-center justify-center gap-2 rounded-sm border border-[hsl(var(--border))] px-4 text-[11px] font-semibold text-[hsl(var(--muted-foreground))] transition-colors hover:bg-[hsl(var(--muted)/0.6)] hover:text-[hsl(var(--foreground))]"
            >
              <RotateCcw size={14} /> Clear
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.23)] px-4 py-2.5 sm:px-5">
        <div className="flex items-start gap-2 text-[10px] leading-relaxed text-[hsl(var(--muted-foreground))]">
          <Info size={13} className="mt-0.5 shrink-0 text-[hsl(var(--accent))]" />
          <span>Every extracted parameter is backed by verifiable web, datasheet, or catalog citations.</span>
        </div>
      </div>
    </section>
  );
}

function LoadingPanel() {
  const [activeStep, setActiveStep] = useState(0);
  useEffect(() => {
    const interval = window.setInterval(
      () => setActiveStep((current) => Math.min(current + 1, processingSteps.length - 1)),
      2400
    );
    return () => window.clearInterval(interval);
  }, []);
  return (
    <section
      className="relative min-h-[500px] overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-5 shadow-[var(--shadow-sm)] sm:p-7"
      data-testid="panel-loading"
    >
      <div className="scan-line pointer-events-none absolute left-0 right-0 top-0 h-24 bg-gradient-to-b from-transparent via-[hsl(var(--primary)/0.12)] to-transparent" />
      <div className="relative flex h-full min-h-[455px] flex-col justify-between">
        <div>
          <div className="eyebrow text-[hsl(var(--accent))]">Agent Orchestrator in flight</div>
          <h2 className="font-display mt-3 max-w-[340px] text-[30px] font-semibold leading-[1.02] tracking-[-0.05em]">
            Turning raw signals into validated product intelligence.
          </h2>
          <p className="mt-4 max-w-[390px] text-[12px] leading-relaxed text-[hsl(var(--muted-foreground))]">
            DeepAgents is coordinating web scraping, Qwen vision-language extraction, and hybrid RAG retrieval.
          </p>
        </div>
        <div className="my-10 flex items-center justify-center">
          <div className="relative flex h-36 w-36 items-center justify-center rounded-full border border-[hsl(var(--primary)/0.24)] bg-[hsl(var(--primary)/0.06)]">
            <div className="absolute inset-3 rounded-full border border-dashed border-[hsl(var(--primary)/0.45)]" />
            <div className="absolute inset-7 rounded-full border border-[hsl(var(--accent)/0.28)]" />
            <Gauge size={31} strokeWidth={1.3} className="text-[hsl(var(--primary))]" />
            <span className="signal-dot absolute right-5 top-5 h-2 w-2 rounded-full bg-[hsl(var(--accent))]" />
          </div>
        </div>
        <div className="space-y-2">
          {processingSteps.map((step, index) => (
            <div
              key={step.label}
              className={`flex items-center gap-3 rounded-sm border px-3 py-2.5 transition-all duration-500 ${
                index < activeStep
                  ? 'border-[hsl(var(--accent)/0.2)] bg-[hsl(var(--accent)/0.06)]'
                  : index === activeStep
                  ? 'border-[hsl(var(--primary)/0.4)] bg-[hsl(var(--primary)/0.08)]'
                  : 'border-transparent'
              }`}
            >
              <div
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                  index < activeStep
                    ? 'border-[hsl(var(--accent))] bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))]'
                    : index === activeStep
                    ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
                    : 'border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]'
                }`}
              >
                {index < activeStep ? (
                  <Check size={11} />
                ) : index === activeStep ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : (
                  <span className="font-mono-app text-[9px]">{String(index + 1).padStart(2, '0')}</span>
                )}
              </div>
              <div className="min-w-0">
                <div
                  className={`text-[11px] font-semibold ${
                    index === activeStep ? 'text-[hsl(var(--foreground))]' : 'text-[hsl(var(--muted-foreground))]'
                  }`}
                >
                  {step.label}
                </div>
                <div className="text-[10px] text-[hsl(var(--muted-foreground)/0.7)]">{step.note}</div>
              </div>
              {index === activeStep && <span className="eyebrow ml-auto text-[hsl(var(--primary))]">running</span>}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProductVisual({ product }: { product: BackendProductIntelligence }) {
  const imageUrl = product.image_url || (product.images && product.images[0]);
  if (imageUrl) {
    return (
      <div
        className="relative flex h-[220px] items-center justify-center overflow-hidden rounded-sm border border-[hsl(204_25%_30%)] bg-[hsl(var(--card))]"
        data-testid="img-product-visual"
      >
        <img
          src={imageUrl}
          alt={product.title}
          className="h-full w-full object-contain p-4 transition-transform duration-300 hover:scale-105"
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 font-mono-app text-[9px] bg-black/60 px-2 py-1 rounded text-white backdrop-blur">
          <ImageIcon size={11} /> {product.images?.length || 1} asset(s)
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative flex h-[190px] items-center justify-center overflow-hidden rounded-sm border border-[hsl(204_25%_30%)] bg-[linear-gradient(135deg,hsl(204_29%_20%),hsl(204_26%_13%))]"
      data-testid="img-product-visual"
    >
      <div className="absolute inset-0 opacity-30 console-grid" />
      <div className="absolute left-4 top-4 eyebrow text-[hsl(42_23%_90%/0.44)]">FIG. 01 / SCHEMATIC VISUAL</div>
      <svg viewBox="0 0 460 190" className="relative h-full w-full max-w-[500px]" role="img" aria-label="Part schema">
        <defs>
          <linearGradient id="metal" x1="0" x2="1">
            <stop offset="0" stopColor="#89969a" />
            <stop offset=".45" stopColor="#d2d2c7" />
            <stop offset="1" stopColor="#69777b" />
          </linearGradient>
          <linearGradient id="darkmetal" x1="0" x2="1">
            <stop offset="0" stopColor="#4a585b" />
            <stop offset=".5" stopColor="#a4b0ae" />
            <stop offset="1" stopColor="#354245" />
          </linearGradient>
        </defs>
        <g transform="translate(44 49)">
          <rect x="49" y="17" width="227" height="76" rx="6" fill="url(#metal)" stroke="#253437" strokeWidth="3" />
          <rect x="65" y="26" width="196" height="58" rx="3" fill="#aeb9b3" opacity=".35" />
          <rect x="30" y="11" width="31" height="88" rx="5" fill="url(#darkmetal)" stroke="#253437" strokeWidth="3" />
          <rect x="276" y="11" width="27" height="88" rx="5" fill="url(#darkmetal)" stroke="#253437" strokeWidth="3" />
          <rect x="302" y="43" width="70" height="24" rx="4" fill="url(#metal)" stroke="#253437" strokeWidth="3" />
          <rect x="371" y="49" width="18" height="12" rx="2" fill="#c8cdc4" stroke="#253437" strokeWidth="3" />
          <circle cx="45" cy="29" r="6" fill="#d7a73e" stroke="#253437" strokeWidth="2" />
          <circle cx="290" cy="29" r="6" fill="#d7a73e" stroke="#253437" strokeWidth="2" />
          <rect x="95" y="0" width="28" height="18" rx="3" fill="#59686b" stroke="#253437" strokeWidth="3" />
          <rect x="227" y="0" width="28" height="18" rx="3" fill="#59686b" stroke="#253437" strokeWidth="3" />
          <path d="M82 100v17h23v-17M246 100v17h23v-17" fill="none" stroke="#89969a" strokeWidth="7" />
          <text x="110" y="65" fill="#34484a" fontFamily="DM Mono, monospace" fontSize="12" fontWeight="600">
            {product.brand?.toUpperCase()} · {product.manufacturer_part_number}
          </text>
        </g>
      </svg>
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5 font-mono-app text-[9px] text-[hsl(42_23%_90%/0.52)]">
        <ImageIcon size={11} /> AI schematic
      </div>
    </div>
  );
}

function ConfidenceMeter({ confidence }: { confidence?: string }) {
  const normalized = (confidence || 'medium').toLowerCase();
  const value = normalized === 'high' ? 95 : normalized === 'low' ? 45 : 78;
  const color =
    normalized === 'high'
      ? 'text-emerald-500'
      : normalized === 'low'
      ? 'text-amber-500'
      : 'text-[hsl(var(--accent))]';
  const barColor =
    normalized === 'high' ? 'bg-emerald-500' : normalized === 'low' ? 'bg-amber-500' : 'bg-[hsl(var(--accent))]';

  return (
    <div
      className="rounded-sm border border-[hsl(var(--accent)/0.22)] bg-[hsl(var(--accent)/0.07)] p-3.5"
      data-testid="status-confidence"
    >
      <div className="flex items-center justify-between">
        <span className="eyebrow text-[hsl(var(--accent))]">Extraction Confidence</span>
        <span className={`font-mono-app text-[16px] font-bold uppercase ${color}`}>
          {normalized} ({value}%)
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[hsl(var(--accent)/0.14)]">
        <div className={`h-full rounded-full ${barColor} transition-all duration-700`} style={{ width: `${value}%` }} />
      </div>
      <div className={`mt-2 flex items-center gap-1.5 text-[10px] ${color}`}>
        <ShieldCheck size={12} />
        {normalized === 'high'
          ? 'High confidence · multi-source cross-validation verified'
          : normalized === 'low'
          ? 'Low confidence · manual verification suggested'
          : 'Medium confidence · primary attributes structured'}
      </div>
    </div>
  );
}

function ResultsPanel({
  data,
  onDownloadJSON,
  onDownloadPDF,
  onCopy,
}: {
  data: BackendProductIntelligence;
  onDownloadJSON: () => void;
  onDownloadPDF: () => void;
  onCopy: () => void;
}) {
  const [expanded, setExpanded] = useState<string | null>('specs');
  const sections = [
    { id: 'specs', title: `Technical specifications (${data.specifications?.length || 0})`, icon: ListChecks },
    {
      id: 'features',
      title: `Key features & applications (${(data.key_features?.length || 0) + (data.applications?.length || 0)})`,
      icon: ClipboardCheck,
    },
    {
      id: 'attributes',
      title: `Normalized attributes (${Object.keys(data.normalized_attributes || {}).length})`,
      icon: BarChart3,
    },
    { id: 'evidence', title: `Source evidence (${data.source_evidence?.length || 0})`, icon: Link2 },
  ];

  return (
    <section className="animate-rise space-y-3" data-testid="panel-product-result">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow text-[hsl(var(--accent))]">02 / Intelligence result</div>
          <h2 className="font-display mt-2 text-[28px] font-semibold leading-none tracking-[-0.05em]">
            Record assembled.
          </h2>
          <p className="mt-2 text-[11px] text-[hsl(var(--muted-foreground))]">
            Verified structured intelligence payload ready for commerce catalogs.
          </p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <IconButton label="copy result json" onClick={onCopy}>
            <Copy size={15} />
          </IconButton>
          <button
            type="button"
            data-testid="button-download-json"
            onClick={onDownloadJSON}
            className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-[10px] font-bold text-[hsl(var(--foreground))] transition-colors hover:border-[hsl(var(--primary))] hover:bg-[hsl(var(--primary)/0.1)]"
          >
            <ArrowDownToLine size={14} /> <span className="hidden sm:inline">JSON</span>
          </button>
          <button
            type="button"
            data-testid="button-download-pdf"
            onClick={onDownloadPDF}
            className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm border border-[hsl(var(--accent)/0.4)] bg-[hsl(var(--accent)/0.1)] px-3 text-[10px] font-bold text-[hsl(var(--accent))] transition-colors hover:bg-[hsl(var(--accent)/0.2)]"
          >
            <FileText size={14} /> <span className="hidden sm:inline">PDF Report</span>
          </button>
        </div>
      </div>
      <div className="overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[var(--shadow-sm)]">
        <div className="p-4 sm:p-5">
          <ProductVisual product={data} />
          <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="eyebrow text-[hsl(var(--muted-foreground))]">{data.category || 'Industrial Equipment'}</div>
              <h3 className="font-display mt-1 text-[20px] font-semibold leading-tight tracking-[-0.04em]">
                {data.title || `${data.brand} ${data.manufacturer_part_number}`}
              </h3>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">
                <span>
                  MPN / <b className="text-[hsl(var(--foreground))]">{data.manufacturer_part_number}</b>
                </span>
                <span>
                  BRAND / <b className="text-[hsl(var(--foreground))]">{data.brand}</b>
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-sm border border-[hsl(var(--primary)/0.3)] bg-[hsl(var(--primary)/0.11)] px-2.5 py-2 text-[10px] font-semibold text-[hsl(var(--foreground))]">
              <CheckCircle2 size={14} className="text-[hsl(var(--accent))]" /> Identity confirmed
            </div>
          </div>
          <div className="mt-5">
            <ConfidenceMeter confidence={data.confidence} />
          </div>
          <div className="mt-5 border-l-2 border-[hsl(var(--primary))] pl-3.5 text-[12px] leading-[1.7] text-[hsl(var(--foreground)/0.88)]">
            {data.commerce_description}
          </div>
        </div>
        <div className="border-t border-[hsl(var(--border))]">
          {sections.map(({ id, title, icon: SectionIcon }) => (
            <div key={id} className="border-b border-[hsl(var(--border))] last:border-0">
              <button
                type="button"
                data-testid={`button-toggle-${id}`}
                onClick={() => setExpanded(expanded === id ? null : id)}
                className="focus-ring flex w-full items-center gap-2.5 px-4 py-3.5 text-left transition-colors hover:bg-[hsl(var(--muted)/0.38)] sm:px-5"
              >
                <SectionIcon size={14} className="text-[hsl(var(--accent))]" />
                <span className="text-[11px] font-bold">{title}</span>
                <ChevronDown
                  size={14}
                  className={`ml-auto text-[hsl(var(--muted-foreground))] transition-transform ${
                    expanded === id ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {expanded === id && (
                <div className="animate-rise px-4 pb-4 sm:px-5">
                  {id === 'specs' && (
                    <div className="grid gap-x-6 gap-y-0 sm:grid-cols-2">
                      {(data.specifications || []).length === 0 ? (
                        <div className="text-[11px] text-[hsl(var(--muted-foreground))] py-2">
                          No specific parameters extracted.
                        </div>
                      ) : (
                        data.specifications?.map((spec, idx) => (
                          <div
                            key={`${spec.name}-${idx}`}
                            className="flex items-start justify-between gap-3 border-t border-[hsl(var(--border)/0.7)] py-2.5"
                          >
                            <span className="text-[10px] text-[hsl(var(--muted-foreground))]">{spec.name}</span>
                            <span className="text-right text-[10px] font-semibold">
                              {spec.value} {spec.unit || ''}
                              {spec.source && (
                                <small className="ml-1 block font-mono-app text-[8px] font-normal text-[hsl(var(--muted-foreground)/0.72)]">
                                  {spec.source}
                                </small>
                              )}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                  {id === 'features' && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <div className="eyebrow mb-2 text-[hsl(var(--muted-foreground))]">Key features</div>
                        <ul className="space-y-2">
                          {(data.key_features || []).map((feature, idx) => (
                            <li key={idx} className="flex gap-2 text-[11px] leading-relaxed">
                              <Check size={13} className="mt-0.5 shrink-0 text-[hsl(var(--accent))]" />
                              {feature}
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <div className="eyebrow mb-2 text-[hsl(var(--muted-foreground))]">Applications</div>
                        <div className="flex flex-wrap gap-1.5">
                          {(data.applications || []).map((app, idx) => (
                            <span
                              key={idx}
                              className="rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.5)] px-2 py-1 text-[10px]"
                            >
                              {app}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                  {id === 'attributes' && (
                    <div className="grid gap-x-6 sm:grid-cols-2">
                      {Object.entries(data.normalized_attributes || {}).map(([key, val]) => (
                        <div
                          key={key}
                          className="flex items-center justify-between border-t border-[hsl(var(--border)/0.7)] py-2.5"
                        >
                          <div>
                            <div className="text-[10px] text-[hsl(var(--muted-foreground))]">{key}</div>
                            <div className="mt-0.5 text-[11px] font-semibold">{val}</div>
                          </div>
                          <span className="font-mono-app text-[8px] text-[hsl(var(--accent))]">NORMALIZED</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {id === 'evidence' && (
                    <div className="space-y-2">
                      {(data.source_evidence || []).map((source, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-3 rounded-sm border border-[hsl(var(--border)/0.75)] p-2.5"
                        >
                          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--accent)/0.12)] text-[hsl(var(--accent))]">
                            <Check size={11} />
                          </div>
                          <div className="min-w-0">
                            <div className="text-[10px] font-semibold">
                              {source.locator}{' '}
                              <span className="ml-1 font-normal text-[hsl(var(--muted-foreground))]">
                                · {source.source_type}
                              </span>
                            </div>
                            <div className="mt-0.5 text-[10px] text-[hsl(var(--muted-foreground))]">
                              {source.excerpt}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      {(data.quality_warnings || []).length > 0 && (
        <div
          className="rounded-sm border border-[hsl(var(--primary)/0.4)] bg-[hsl(var(--primary)/0.11)] p-4"
          data-testid="status-quality-warnings"
        >
          <div className="flex items-start gap-2.5">
            <TriangleAlert size={16} className="mt-0.5 shrink-0 text-[hsl(var(--primary))]" />
            <div>
              <div className="text-[11px] font-bold">Quality notes & validation flags</div>
              <ul className="mt-2 space-y-1.5">
                {data.quality_warnings?.map((warning, idx) => (
                  <li key={idx} className="flex gap-2 text-[10px] leading-relaxed text-[hsl(var(--foreground)/0.82)]">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[hsl(var(--primary))]" />
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function EmptyResultPanel({ onPreset }: { onPreset: (preset: (typeof presets)[number]) => void }) {
  return (
    <section
      className="overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card)/0.46)] shadow-[var(--shadow-sm)]"
      data-testid="panel-empty-result"
    >
      <div className="console-grid relative flex min-h-[500px] flex-col items-center justify-center px-5 py-12 text-center">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,hsl(var(--primary)/0.12),transparent_34%)]" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-sm border border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.11)] text-[hsl(var(--primary))]">
          <Search size={25} strokeWidth={1.5} />
          <span className="signal-dot absolute -right-1 -top-1 h-2 w-2 rounded-full bg-[hsl(var(--accent))]" />
        </div>
        <div className="relative mt-6 max-w-[320px]">
          <div className="eyebrow text-[hsl(var(--muted-foreground))]">Awaiting source intake</div>
          <h2 className="font-display mt-3 text-[28px] font-semibold leading-[1.04] tracking-[-0.05em]">
            Your next trustworthy record starts here.
          </h2>
          <p className="mt-3 text-[12px] leading-relaxed text-[hsl(var(--muted-foreground))]">
            Enter a manufacturer part number, add reference links, and let DeepAgents orchestrate the extraction.
          </p>
        </div>
        <div className="relative mt-8 flex flex-wrap justify-center gap-2">
          <button
            type="button"
            data-testid="button-empty-load-sample"
            onClick={() => onPreset(presets[0])}
            className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm bg-[hsl(var(--foreground))] px-3 text-[10px] font-bold text-[hsl(var(--background))] transition-transform hover:-translate-y-0.5"
          >
            <FlaskConical size={13} /> Load a sample
          </button>
          <span className="flex items-center gap-1.5 px-2 text-[10px] text-[hsl(var(--muted-foreground))]">
            <ShieldCheck size={13} className="text-[hsl(var(--accent))]" /> Traceable by default
          </span>
        </div>
        <div className="relative mt-10 grid w-full max-w-[390px] grid-cols-3 gap-2 border-t border-[hsl(var(--border))] pt-5">
          <div>
            <div className="font-mono-app text-[16px] text-[hsl(var(--foreground))]">01</div>
            <div className="mt-1 text-[9px] text-[hsl(var(--muted-foreground))]">Scrape & Fetch</div>
          </div>
          <div>
            <div className="font-mono-app text-[16px] text-[hsl(var(--foreground))]">02</div>
            <div className="mt-1 text-[9px] text-[hsl(var(--muted-foreground))]">VLM & RAG</div>
          </div>
          <div>
            <div className="font-mono-app text-[16px] text-[hsl(var(--foreground))]">03</div>
            <div className="mt-1 text-[9px] text-[hsl(var(--muted-foreground))]">Publish</div>
          </div>
        </div>
      </div>
    </section>
  );
}

function RunHistoryView({
  runs,
  onSelectRun,
  onRefresh,
  loading,
}: {
  runs: BackendProductIntelligence[];
  onSelectRun: (product: BackendProductIntelligence) => void;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <div className="animate-rise space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow text-[hsl(var(--accent))]">Catalog Database</div>
          <h2 className="font-display text-[26px] font-semibold tracking-[-0.04em]">Run History</h2>
          <p className="text-[12px] text-[hsl(var(--muted-foreground))]">
            All stored products processed by the AI orchestrator.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-[11px] font-semibold"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {runs.length === 0 ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-8 text-center">
          <Clock3 size={32} className="text-[hsl(var(--muted-foreground))]" />
          <h3 className="mt-4 font-display text-[18px] font-semibold">No run history yet</h3>
          <p className="mt-1 text-[12px] text-[hsl(var(--muted-foreground))] max-w-sm">
            Process parts from the Intelligence workspace to see them indexed and saved here.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {runs.map((run, i) => (
            <div
              key={i}
              onClick={() => onSelectRun(run)}
              className="cursor-pointer group rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4 hover:border-[hsl(var(--primary))] transition-all hover:-translate-y-0.5 shadow-[var(--shadow-sm)]"
            >
              <div className="flex items-start justify-between">
                <span className="eyebrow text-[hsl(var(--accent))]">{run.category || 'Product'}</span>
                <span className="font-mono-app text-[9px] uppercase px-1.5 py-0.5 rounded bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]">
                  {run.confidence || 'medium'}
                </span>
              </div>
              <h4 className="mt-2 font-display text-[14px] font-semibold line-clamp-2">{run.title}</h4>
              <div className="mt-3 flex items-center justify-between font-mono-app text-[10px] text-[hsl(var(--muted-foreground))] border-t border-[hsl(var(--border)/0.5)] pt-2">
                <span>MPN: {run.manufacturer_part_number}</span>
                <span>{run.brand}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceLibraryView({ runs }: { runs: BackendProductIntelligence[] }) {
  const allEvidence = useMemo(() => {
    const list: { locator: string; type: string; mpn: string; brand: string }[] = [];
    runs.forEach((r) => {
      (r.source_evidence || []).forEach((ev) => {
        list.push({
          locator: ev.locator,
          type: ev.source_type,
          mpn: r.manufacturer_part_number,
          brand: r.brand,
        });
      });
    });
    return list;
  }, [runs]);

  return (
    <div className="animate-rise space-y-4">
      <div>
        <div className="eyebrow text-[hsl(var(--accent))]">Reference Assets</div>
        <h2 className="font-display text-[26px] font-semibold tracking-[-0.04em]">Source Library</h2>
        <p className="text-[12px] text-[hsl(var(--muted-foreground))]">
          Discovered manufacturer portals, datasheets, and citation sources.
        </p>
      </div>

      {allEvidence.length === 0 ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-8 text-center">
          <BookOpen size={32} className="text-[hsl(var(--muted-foreground))]" />
          <h3 className="mt-4 font-display text-[18px] font-semibold">Library is indexing</h3>
          <p className="mt-1 text-[12px] text-[hsl(var(--muted-foreground))] max-w-sm">
            Discovered citations and manufacturer reference URLs will be collected here across runs.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {allEvidence.map((item, idx) => (
            <div key={idx} className="flex items-start gap-3 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-3.5">
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]">
                <Link2 size={14} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-semibold truncate">{item.locator}</div>
                <div className="mt-1 flex items-center gap-2 font-mono-app text-[9px] text-[hsl(var(--muted-foreground))]">
                  <span>{item.type}</span>
                  <span>·</span>
                  <span>
                    {item.brand} ({item.mpn})
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PdfPreviewView({
  pdfFile,
  pdfExtraction,
  onSelectProduct,
  onGoToWorkspace,
}: {
  pdfFile: File | null;
  pdfExtraction: PDFExtractionResult | null;
  onSelectProduct: (prod: ExtractedPDFProduct) => void;
  onGoToWorkspace: () => void;
}) {
  const objectUrl = useMemo(() => {
    if (!pdfFile) return null;
    const url = URL.createObjectURL(pdfFile);
    return url;
  }, [pdfFile]);

  if (!pdfFile && !pdfExtraction) {
    return (
      <div className="animate-rise flex min-h-[500px] flex-col items-center justify-center rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-10 text-center">
        <FileSpreadsheet size={40} className="text-[hsl(var(--muted-foreground))]" />
        <h3 className="font-display mt-4 text-[20px] font-semibold">No PDF uploaded yet</h3>
        <p className="mt-2 max-w-sm text-[12px] text-[hsl(var(--muted-foreground))]">
          Go to the workspace, switch to "Upload PDF" and extract a product list — it will appear here.
        </p>
        <button
          type="button"
          onClick={onGoToWorkspace}
          className="focus-ring mt-5 inline-flex h-9 items-center gap-2 rounded-sm bg-[hsl(var(--primary))] px-4 text-[11px] font-bold text-[hsl(var(--primary-foreground))] transition-opacity hover:opacity-90"
        >
          <ArrowRight size={14} /> Go to workspace
        </button>
      </div>
    );
  }

  return (
    <div className="animate-rise space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="eyebrow text-[hsl(var(--accent))]">PDF Document</div>
          <h2 className="font-display mt-2 text-[26px] font-semibold tracking-[-0.04em]">
            {pdfFile?.name ?? pdfExtraction?.filename ?? 'Uploaded PDF'}
          </h2>
          {pdfExtraction && (
            <p className="mt-1 text-[12px] text-[hsl(var(--muted-foreground))]">
              {pdfExtraction.total_products_found} product{pdfExtraction.total_products_found !== 1 ? 's' : ''} detected
              {pdfFile && <span className="ml-2">· {(pdfFile.size / 1024).toFixed(1)} KB</span>}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onGoToWorkspace}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-[11px] font-semibold text-[hsl(var(--foreground))] transition-colors hover:bg-[hsl(var(--muted))]"
        >
          <ArrowRight size={13} /> Back to workspace
        </button>
      </div>

      {/* Two-column layout */}
      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">

        {/* LEFT — PDF Viewer */}
        <div className="overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[var(--shadow-sm)]">
          <div className="flex items-center gap-2 border-b border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.42)] px-4 py-2.5">
            <FileText size={13} className="text-[hsl(var(--accent))]" />
            <span className="text-[11px] font-semibold">Document Preview</span>
            {objectUrl && (
              <a
                href={objectUrl}
                download={pdfFile?.name}
                className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold text-[hsl(var(--primary))] hover:underline"
              >
                <Download size={11} /> Download
              </a>
            )}
          </div>
          {objectUrl ? (
            <iframe
              src={objectUrl}
              title="PDF Preview"
              className="h-[680px] w-full border-0 bg-white"
            />
          ) : (
            <div className="flex h-[400px] items-center justify-center text-[12px] text-[hsl(var(--muted-foreground))]">
              <FileText size={28} className="mr-3 opacity-40" />
              PDF preview not available — file was not retained in memory.
            </div>
          )}
        </div>

        {/* RIGHT — Extracted Product Table */}
        <div className="overflow-hidden rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[var(--shadow-sm)]">
          <div className="flex items-center gap-2 border-b border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.42)] px-4 py-2.5">
            <FileSpreadsheet size={13} className="text-[hsl(var(--accent))]" />
            <span className="text-[11px] font-semibold">
              Extracted Products
            </span>
            {pdfExtraction && (
              <span className="ml-auto font-mono-app text-[10px] bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))] px-1.5 py-0.5 rounded">
                {pdfExtraction.total_products_found} items
              </span>
            )}
          </div>

          {pdfExtraction && pdfExtraction.products.length > 0 ? (
            <div className="divide-y divide-[hsl(var(--border))] overflow-y-auto" style={{ maxHeight: '680px' }}>
              {pdfExtraction.products.map((item, idx) => (
                <div
                  key={idx}
                  className="group flex items-start gap-3 p-3.5 transition-colors hover:bg-[hsl(var(--muted)/0.4)]"
                >
                  {/* Index badge */}
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-[hsl(var(--muted))] font-mono-app text-[10px] font-semibold text-[hsl(var(--muted-foreground))]">
                    {idx + 1}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-[12px] font-bold text-[hsl(var(--foreground))]">
                        {item.manufacturer_part_number}
                      </span>
                      {item.brand && item.brand !== 'Generic / Unspecified' && (
                        <span className="rounded bg-[hsl(var(--accent)/0.12)] px-1.5 py-0.5 text-[10px] font-semibold text-[hsl(var(--accent))]">
                          {item.brand}
                        </span>
                      )}
                      {item.quantity != null && (
                        <span className="rounded bg-[hsl(var(--primary)/0.12)] px-1.5 py-0.5 font-mono-app text-[9px] font-semibold text-[hsl(var(--primary))]">
                          Qty: {item.quantity}
                        </span>
                      )}
                    </div>
                    {item.short_description && (
                      <p className="mt-1 text-[11px] leading-snug text-[hsl(var(--muted-foreground))]">
                        {item.short_description}
                      </p>
                    )}
                    {item.category && (
                      <span className="mt-1.5 inline-block text-[9px] text-[hsl(var(--muted-foreground)/0.7)] font-mono-app">
                        {item.category}
                      </span>
                    )}
                  </div>

                  {/* Analyze button */}
                  <button
                    type="button"
                    onClick={() => onSelectProduct(item)}
                    className="shrink-0 inline-flex items-center gap-1 rounded-sm border border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.08)] px-2 py-1.5 text-[10px] font-bold text-[hsl(var(--primary))] opacity-0 transition-all group-hover:opacity-100 hover:bg-[hsl(var(--primary)/0.18)]"
                  >
                    Analyze <ArrowRight size={10} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-[300px] flex-col items-center justify-center p-6 text-center">
              <Search size={26} className="text-[hsl(var(--muted-foreground)/0.5)]" />
              <p className="mt-3 text-[12px] text-[hsl(var(--muted-foreground))]">
                No products extracted yet. Go to the workspace and click "Extract Products List from PDF".
              </p>
              <button
                type="button"
                onClick={onGoToWorkspace}
                className="focus-ring mt-4 inline-flex h-9 items-center gap-2 rounded-sm bg-[hsl(var(--primary))] px-3 text-[11px] font-bold text-[hsl(var(--primary-foreground))] transition-opacity hover:opacity-90"
              >
                <ArrowRight size={13} /> Extract now
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Home() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [status, setStatus] = useState<ProcessStatus>('empty');
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [activeView, setActiveView] = useState('workspace');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [toast, setToast] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('app-theme') as 'light' | 'dark' | null;
      if (saved) return saved;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  });

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('app-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const [backendProduct, setBackendProduct] = useState<BackendProductIntelligence | null>(null);
  const [runHistory, setRunHistory] = useState<BackendProductIntelligence[]>([fallbackSample]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [backendConnected, setBackendConnected] = useState(true);

  // PDF Extraction & Batch states
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfExtraction, setPdfExtraction] = useState<PDFExtractionResult | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Check health and load initial products from backend
  const fetchProducts = async () => {
    setHistoryLoading(true);
    try {
      const res = await axios.get<BackendProductIntelligence[]>(`${API_BASE_URL}/products?limit=50`, { timeout: 6000 });
      if (Array.isArray(res.data) && res.data.length > 0) {
        setRunHistory(res.data);
      }
      setBackendConnected(true);
    } catch {
      setBackendConnected(false);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeResult = backendProduct || fallbackSample;
  const jsonOutput = useMemo(() => JSON.stringify(activeResult, null, 2), [activeResult]);

  const loadPreset = (preset: (typeof presets)[number]) => {
    setForm(preset.form);
    setSelectedPreset(preset.id);
    setErrors({});
    setStatus('empty');
    setToast(`${preset.label} sample loaded`);
  };

  const reset = () => {
    setForm(initialForm);
    setSelectedPreset(null);
    setErrors({});
    setStatus('empty');
    setBackendProduct(null);
    setPdfExtraction(null);
    setPdfFile(null);
  };

  const handleExtractPdf = async (file: File) => {
    setPdfLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post<PDFExtractionResult>(`${API_BASE_URL}/upload-pdf-extract`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      });
      setPdfExtraction(res.data);
      setActiveView('pdf-preview');
      setToast(`Extracted ${res.data.total_products_found} products from ${file.name}`);
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || err.message || 'Failed to extract PDF';
      setToast(`PDF extraction error: ${errMsg}`);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleProcessPdfBatch = async (file: File) => {
    setPdfLoading(true);
    setStatus('loading');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post<PDFBatchProcessResult>(`${API_BASE_URL}/upload-pdf-process`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000,
      });
      if (res.data.results && res.data.results.length > 0) {
        setBackendProduct(res.data.results[0]);
        setRunHistory((prev) => [...res.data.results, ...prev]);
        setStatus('success');
        setToast(`Successfully enriched ${res.data.processed_count} products from PDF!`);
      } else {
        setStatus('warning');
        setToast(`No products found to enrich in ${file.name}`);
      }
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || err.message || 'Batch PDF process failed';
      setStatus('error');
      setToast(`PDF batch error: ${errMsg}`);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleSelectExtractedProduct = (prod: ExtractedPDFProduct) => {
    setForm({
      mpn: prod.manufacturer_part_number,
      manufacturer: prod.brand && prod.brand !== 'Generic / Unspecified' ? prod.brand : '',
      description: prod.short_description,
      website: '',
      additionalUrls: '',
      supportingText: prod.supporting_text || '',
      processAction: 'full-enrichment',
    });
    setToast(`Loaded ${prod.manufacturer_part_number} into form`);
  };

  const processProduct = async () => {
    const nextErrors: Partial<Record<keyof FormState, string>> = {};
    if (!form.mpn.trim()) nextErrors.mpn = 'A manufacturer part number is required.';
    if (!form.manufacturer.trim()) nextErrors.manufacturer = 'Brand/manufacturer is required.';
    if (form.website && !/^https?:\/\/\S+/i.test(form.website.trim())) {
      nextErrors.website = 'Use a full URL starting with http:// or https://.';
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setToast('Check the highlighted source fields');
      return;
    }

    setStatus('loading');

    const urls = [form.website, ...form.additionalUrls.split('\n')]
      .map((u) => u.trim())
      .filter((u) => u.length > 0 && /^https?:\/\//i.test(u));

    const payload = {
      manufacturer_part_number: form.mpn.trim(),
      brand: form.manufacturer.trim(),
      short_description: form.description.trim() || `${form.manufacturer} ${form.mpn}`,
      supporting_urls: urls,
      supporting_text: form.supportingText.trim() || undefined,
    };

    try {
      const response = await axios.post<BackendProductIntelligence>(`${API_BASE_URL}/process-product`, payload, {
        timeout: 300000,
      });

      setBackendProduct(response.data);
      setRunHistory((prev) => [response.data, ...prev.filter((p) => p.manufacturer_part_number !== response.data.manufacturer_part_number)]);
      setStatus(response.data.quality_warnings && response.data.quality_warnings.length > 0 ? 'warning' : 'success');
      setToast('Product intelligence resolved successfully!');
      setBackendConnected(true);
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || err.message || 'Error communicating with backend';
      console.warn('Backend process-product fallback:', errMsg);

      // Graceful fallback for offline demo testing if backend is not running
      const demoData: BackendProductIntelligence = {
        manufacturer_part_number: form.mpn.trim(),
        brand: form.manufacturer.trim(),
        title: `${form.manufacturer.trim()} ${form.mpn.trim()} — ${form.description || 'Industrial Component'}`,
        category: form.processAction === 'specifications-only' ? 'Mechanical Components' : 'Industrial Automation',
        commerce_description:
          form.description.trim() ||
          `The ${form.manufacturer} ${form.mpn} is an engineered industrial catalog component resolved for commerce workflows.`,
        confidence: 'medium',
        specifications: [
          { name: 'Part Number', value: form.mpn.trim(), source: 'Intake' },
          { name: 'Manufacturer', value: form.manufacturer.trim(), source: 'Intake' },
          { name: 'Extraction Mode', value: form.processAction, source: 'Pipeline' },
        ],
        key_features: [
          'Direct manufacturer identifier resolution',
          'Standardized technical spec normalization',
          'Export-ready commerce payload',
        ],
        applications: ['General Industrial Machinery', 'OEM Integration'],
        normalized_attributes: {
          'Part Number': form.mpn.trim(),
          'Manufacturer': form.manufacturer.trim(),
        },
        source_evidence: urls.map((u) => ({
          locator: u,
          source_type: 'Supplied URL',
          excerpt: 'Referenced in intake request',
          confidence: 'medium' as const,
        })),
        quality_warnings: err.response
          ? [`Backend error: ${errMsg}`]
          : ['FastAPI backend was unreachable. Displaying fallback structured intake record.'],
      };

      setBackendProduct(demoData);
      setStatus('warning');
      setToast(err.response ? `API Error: ${errMsg}` : 'Resolved using local fallback');
    }
  };

  const downloadJSON = () => {
    const blob = new Blob([jsonOutput], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${activeResult.manufacturer_part_number.toLowerCase()}-product-intelligence.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setToast('JSON payload downloaded');
  };

  const downloadPDF = () => {
    try {
      const doc = new jsPDF();
      doc.setFillColor(20, 35, 45);
      doc.rect(0, 0, 210, 28, 'F');
      doc.setTextColor(255, 255, 255);
      doc.setFontSize(15);
      doc.setFont('helvetica', 'bold');
      doc.text('Industrial Product Intelligence Report', 12, 13);
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.text(`Generated: ${new Date().toLocaleString()} · Cluster AI Agent`, 12, 22);

      doc.setTextColor(30, 41, 59);
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text(activeResult.title || 'Product Report', 12, 38);

      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.text(`MPN: ${activeResult.manufacturer_part_number}   |   Brand: ${activeResult.brand}`, 12, 45);
      doc.text(
        `Category: ${activeResult.category || '-'}   |   Confidence: ${(activeResult.confidence || 'medium').toUpperCase()}`,
        12,
        51
      );

      if (activeResult.commerce_description) {
        doc.setFontSize(8.5);
        const lines = doc.splitTextToSize(activeResult.commerce_description, 185);
        doc.text(lines, 12, 60);
      }

      let yPos = 82;
      if (activeResult.specifications && activeResult.specifications.length > 0) {
        doc.setFontSize(11);
        doc.setFont('helvetica', 'bold');
        doc.text('Technical Specifications', 12, yPos);
        yPos += 5;

        doc.setFillColor(235, 240, 245);
        doc.rect(12, yPos, 185, 6, 'F');
        doc.setFontSize(8.5);
        doc.setFont('helvetica', 'bold');
        doc.text('Name', 14, yPos + 4.5);
        doc.text('Value', 95, yPos + 4.5);
        doc.text('Source', 150, yPos + 4.5);
        yPos += 7;

        doc.setFont('helvetica', 'normal');
        activeResult.specifications.slice(0, 18).forEach((spec, idx) => {
          if (yPos > 270) {
            doc.addPage();
            yPos = 20;
          }
          if (idx % 2 === 0) {
            doc.setFillColor(248, 250, 252);
            doc.rect(12, yPos, 185, 6, 'F');
          }
          doc.text(String(spec.name).substring(0, 40), 14, yPos + 4.2);
          doc.text(`${spec.value} ${spec.unit || ''}`.substring(0, 30), 95, yPos + 4.2);
          doc.text(String(spec.source || '-').substring(0, 25), 150, yPos + 4.2);
          yPos += 6;
        });
      }

      yPos += 6;
      if (activeResult.key_features && activeResult.key_features.length > 0) {
        if (yPos > 260) {
          doc.addPage();
          yPos = 20;
        }
        doc.setFontSize(11);
        doc.setFont('helvetica', 'bold');
        doc.text('Key Features', 12, yPos);
        yPos += 5;
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        activeResult.key_features.slice(0, 6).forEach((feat) => {
          doc.text(`• ${feat}`, 14, yPos + 4);
          yPos += 5;
        });
      }

      doc.save(`${activeResult.manufacturer_part_number.toLowerCase()}-report.pdf`);
      setToast('PDF report generated & downloaded');
    } catch (e: any) {
      console.error(e);
      setToast('Could not generate PDF');
    }
  };

  const copyJSON = () => {
    void navigator.clipboard?.writeText(jsonOutput);
    setToast('Result JSON copied to clipboard');
  };

  return (
    <div className="noise-overlay min-h-[100dvh] bg-[hsl(var(--background))]">
      <div className="flex min-h-[100dvh]">
        <Sidebar
          activeView={activeView}
          onViewChange={setActiveView}
          historyCount={runHistory.length}
          backendConnected={backendConnected}
        />
        {mobileNavOpen && (
          <MobileNav
            activeView={activeView}
            onViewChange={setActiveView}
            onClose={() => setMobileNavOpen(false)}
          />
        )}
        <div className="min-w-0 flex-1">
          <TopBar
            onNewRun={reset}
            onToggleSidebar={() => setMobileNavOpen(true)}
            backendConnected={backendConnected}
            theme={theme}
            onToggleTheme={toggleTheme}
          />
          <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8 lg:px-10">
            {activeView === 'runs' ? (
              <RunHistoryView
                runs={runHistory}
                onSelectRun={(product) => {
                  setBackendProduct(product);
                  setStatus('success');
                  setActiveView('workspace');
                  setToast(`Loaded ${product.manufacturer_part_number}`);
                }}
                onRefresh={fetchProducts}
                loading={historyLoading}
              />
            ) : activeView === 'library' ? (
              <SourceLibraryView runs={runHistory} />
            ) : activeView === 'pdf-preview' ? (
              <PdfPreviewView
                pdfFile={pdfFile}
                pdfExtraction={pdfExtraction}
                onSelectProduct={(prod) => {
                  handleSelectExtractedProduct(prod);
                  setActiveView('workspace');
                }}
                onGoToWorkspace={() => setActiveView('workspace')}
              />
            ) : (
              <>
                <div className="mb-7 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
                  <div className="max-w-[680px]">
                    <div className="eyebrow text-[hsl(var(--accent))]">Industrial Catalog Intelligence</div>
                    <h2 className="font-display mt-2 text-[35px] font-semibold leading-[.97] tracking-[-0.06em] sm:text-[46px]">
                      Make messy part data
                      <br className="hidden sm:block" /> <span className="text-[hsl(var(--accent))]">useful.</span>
                    </h2>
                    <p className="mt-4 max-w-[560px] text-[13px] leading-relaxed text-[hsl(var(--muted-foreground))]">
                      Resolve manufacturer part numbers into confident, structured, commerce-ready intelligence records
                      backed by real web scraping and vision-language extraction.
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-4 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card)/0.52)] px-3.5 py-3">
                    <div className="flex -space-x-1.5">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-[hsl(var(--background))] bg-[hsl(var(--accent))] text-[9px] font-semibold text-[hsl(var(--accent-foreground))]">
                        AI
                      </span>
                      <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-[hsl(var(--background))] bg-[hsl(var(--primary))] text-[9px] font-semibold text-[hsl(var(--primary-foreground))]">
                        VL
                      </span>
                      <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-[hsl(var(--background))] bg-[hsl(var(--foreground))] text-[9px] font-semibold text-[hsl(var(--background))]">
                        DB
                      </span>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold">FastAPI + DeepAgents</div>
                      <div className="mt-0.5 text-[9px] text-[hsl(var(--muted-foreground))]">
                        Qwen VL · Chroma RAG · Supabase
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mb-7 flex items-center gap-3">
                  <div className="h-px flex-1 bg-[hsl(var(--border))]" />
                  <span className="eyebrow text-[hsl(var(--muted-foreground))]">Quick load example</span>
                  <div className="h-px w-10 bg-[hsl(var(--border))]" />
                </div>
                <div className="mb-7 grid grid-cols-1 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                  {presets.map((preset) => (
                    <PresetCard
                      key={preset.id}
                      preset={preset}
                      selected={selectedPreset === preset.id}
                      onClick={() => loadPreset(preset)}
                    />
                  ))}
                </div>
                <div className="grid items-start gap-6 xl:grid-cols-[minmax(340px,0.83fr)_minmax(500px,1.17fr)]">
                  <FormPanel
                    form={form}
                    setForm={setForm}
                    onProcess={processProduct}
                    onClear={reset}
                    status={status}
                    errors={errors}
                    pdfFile={pdfFile}
                    setPdfFile={setPdfFile}
                    pdfExtraction={pdfExtraction}
                    onExtractPdf={handleExtractPdf}
                    onProcessPdfBatch={handleProcessPdfBatch}
                    onSelectExtractedProduct={handleSelectExtractedProduct}
                    pdfLoading={pdfLoading}
                  />
                  {status === 'loading' ? (
                    <LoadingPanel />
                  ) : status === 'success' || status === 'warning' ? (
                    <ResultsPanel
                      data={activeResult}
                      onDownloadJSON={downloadJSON}
                      onDownloadPDF={downloadPDF}
                      onCopy={copyJSON}
                    />
                  ) : (
                    <EmptyResultPanel onPreset={loadPreset} />
                  )}
                </div>
                <div className="mt-7 grid gap-3 border-t border-[hsl(var(--border))] pt-5 sm:grid-cols-3">
                  <div className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))]">
                    <ShieldCheck size={14} className="text-[hsl(var(--accent))]" />
                    <span>
                      <b className="text-[hsl(var(--foreground))]">Evidence first.</b> Sources remain attached.
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))]">
                    <Activity size={14} className="text-[hsl(var(--primary))]" />
                    <span>
                      <b className="text-[hsl(var(--foreground))]">Confidence scored.</b> Quality rubric scored.
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))]">
                    <FileJson size={14} className="text-[hsl(var(--accent))]" />
                    <span>
                      <b className="text-[hsl(var(--foreground))]">JSON & PDF ready.</b> Plug into your workflow.
                    </span>
                  </div>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
      {toast && (
        <div
          className="animate-rise fixed bottom-5 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-2 rounded-sm border border-[hsl(var(--foreground)/0.16)] bg-[hsl(var(--foreground))] px-3.5 py-2.5 text-[11px] font-semibold text-[hsl(var(--background))] shadow-[var(--shadow-md)]"
          role="status"
          data-testid="status-toast"
        >
          <CheckCircle2 size={14} className="text-[hsl(var(--primary))]" />
          {toast}
        </div>
      )}
    </div>
  );
}

function Router() {
  return (
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={Home} />
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;