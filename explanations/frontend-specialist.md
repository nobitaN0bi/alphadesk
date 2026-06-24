# Frontend Specialist Persona - Comprehensive Exam Guide

> **Graph Communities**: Frontend Application Layer (Community 1, 51 nodes, 0.06 cohesion) · Frontend Dependencies (Community 6, 27 nodes, 0.07 cohesion) · UI Components & Design (Community 10, 17 nodes, 0.11 cohesion) · TypeScript Configuration (Community 8, 19 nodes, 0.10 cohesion)
>
> **God Node Connections**: compilerOptions (16 edges) · StockDetailsResponse (18 edges, shared with backend)
>
> **Hyperedges**: AlphaDesk Tech Stack (1.00 confidence) — includes alpha_desk_frontend alongside lang_graph, fast_api, chroma_db

---

## 1. Role Definition & Design Philosophy

The **Frontend Specialist** designs and builds user-facing systems with long-term maintainability, performance, and accessibility as foundational requirements. In the AlphaDesk ecosystem, this persona anchors the largest frontend community (51 nodes in Frontend Application Layer) and serves as the visual and interactive interface between human users and AI agent systems. The graph reveals `compilerOptions` as a god node (16 edges), indicating TypeScript configuration and type safety are not peripheral concerns but the **structural foundation** of the entire frontend architecture.

**Core Philosophy**: "Frontend is not just UI — it is system design." Every component decision affects performance budgets, accessibility compliance, and developer experience. The Frontend Specialist thinks in layers: design tokens → component primitives → composition patterns → page orchestration.

**Exam Focus Areas**:
- React & Next.js Architecture (25%)
- TypeScript & Type Safety (20%)
- State Management (15%)
- Performance Optimization (15%)
- Styling & Design Systems (10%)
- Accessibility (A11y) (10%)
- Testing (5%)

---

## 2. React & Next.js Architecture

### 2.1 Server vs. Client Components

The graph's Community 1 (Frontend Application Layer) contains `AgentStepCard`, `ApprovalModal`, `StageStatus` — indicating a mix of static and interactive components. The Frontend Specialist must master the App Router paradigm:

**Server Components (Default)**:
- Render on the server, send minimal HTML to client
- Can be async — fetch data directly in the component
- Zero client-side JavaScript by default
- Cannot use browser APIs, event handlers, or state

**Client Components**:
- Render on both server (for initial HTML) and client (for interactivity)
- Required for: useState, useEffect, event handlers, browser APIs
- Mark with `"use client"` directive

**Decision Framework**:
```
Static content?        → Server Component
User interaction?      → Client Component
Dynamic data fetching? → Server Component (async)
Real-time updates?     → Client Component + Server Actions
```

### 2.2 The AlphaDesk Component Architecture

From graph extraction, the frontend component hierarchy:
```
app/
├── page.tsx           → Home (Server)
├── pipeline/
│   └── page.tsx       → Pipeline visualization (Server + Client)
├── samples/
│   └── page.tsx       → Sample outputs (Server)
└── layout.tsx         → Root layout with providers

components/
├── AgentStepCard.tsx  → Client (interactive status updates)
├── ApprovalModal.tsx  → Client (human-in-the-loop gate)
└── StageStatus.tsx    → Client (real-time progress)
```

**Key Pattern**: The `AgentStepCard` component likely streams updates via WebSockets or Server-Sent Events, showing the progression of agent execution stages. This requires careful separation: the card shell is a Server Component, while the live status indicator is a Client Component embedded within it.

### 2.3 Streaming & Progressive Rendering

The graph shows `StreamingResponse` connecting to `PortfolioState` — the frontend must handle streaming data:

```typescript
// React component consuming SSE stream
"use client";

import { useEffect, useState } from "react";

export function AgentStream({ runId }: { runId: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);

  useEffect(() => {
    const source = new EventSource(`/api/stream/${runId}`);
    
    source.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setEvents((prev) => [...prev, data]);
    };

    return () => source.close();
  }, [runId]);

  return (
    <div className="space-y-2">
      {events.map((event, i) => (
        <AgentStepCard key={i} event={event} />
      ))}
    </div>
  );
}
```

---

## 3. TypeScript & Type Safety

### 3.1 Strict Mode Configuration

The graph's `compilerOptions` god node (16 edges) reveals TypeScript is deeply integrated. The Frontend Specialist must enforce strict typing:

```json
// tsconfig.json (from graph extraction)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "preserve",
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

**Critical Rules**:
- ❌ **Never use `any`**: Use `unknown` for truly unknown types, then narrow with type guards
- ❌ **Never ignore TypeScript errors**: Fix them before committing
- ✅ **Use strict mode**: Catches null/undefined errors at compile time
- ✅ **Explicit return types**: On exported functions for API documentation

### 3.2 Pydantic ↔ TypeScript Bridge

The backend uses Pydantic models (e.g., `StockDetailsResponse`, `ApproveRequest`). The Frontend Specialist should generate TypeScript types from these schemas:

```typescript
// Generated from Pydantic models
interface StockDetailsResponse {
  symbol: string;
  name: string;
  current_price: number;
  change_percent: number;
  recommendation: "BUY" | "HOLD" | "SELL";
  confidence: number;
  rationale: string;
}

interface ApproveRequest {
  run_id: string;
  approved_symbols: string[];
  rejection_reason?: string;
}
```

**Tools**: `openapi-typescript` generates types from OpenAPI specs automatically.

### 3.3 Generic Components

```typescript
// Reusable typed component
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  onRowClick?: (row: T) => void;
}

export function DataTable<T extends { id: string }>({
  data,
  columns,
  onRowClick,
}: DataTableProps<T>) {
  return (
    <table>
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col.key}>{col.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row) => (
          <tr key={row.id} onClick={() => onRowClick?.(row)}>
            {columns.map((col) => (
              <td key={col.key}>{col.render(row)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

## 4. State Management

### 4.1 Hierarchy of State

The graph's Community 10 (UI Components & Design) shows `aliases`, `hooks`, `utils` — indicating a well-organized state management layer.

**State Decision Tree**:
1. **Server State** → React Query / TanStack Query (caching, deduping, background refetching)
2. **URL State** → Next.js `useSearchParams` (shareable, bookmarkable)
3. **Global Client State** → Zustand (lightweight, no provider boilerplate)
4. **Shared Component State** → React Context (when prop drilling exceeds 2-3 levels)
5. **Local Component State** → `useState` (default choice)

### 4.2 Server State with TanStack Query

```typescript
import { useQuery, useMutation } from "@tanstack/react-query";

// Fetch pipeline status
function usePipelineStatus(runId: string) {
  return useQuery({
    queryKey: ["pipeline", runId],
    queryFn: async () => {
      const res = await fetch(`/api/pipeline/${runId}`);
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
    refetchInterval: (data) =>
      data?.status === "completed" ? false : 2000,
  });
}

// Submit approval
function useApproveMutation() {
  return useMutation({
    mutationFn: async (request: ApproveRequest) => {
      const res = await fetch("/api/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!res.ok) throw new Error("Approval failed");
      return res.json();
    },
  });
}
```

### 4.3 Form State

For complex forms (e.g., the approval modal), use `react-hook-form` + Zod:

```typescript
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const approvalSchema = z.object({
  run_id: z.string().uuid(),
  approved_symbols: z.array(z.string()).min(1),
  rejection_reason: z.string().optional(),
});

type ApprovalForm = z.infer<typeof approvalSchema>;

export function ApprovalModal({ runId }: { runId: string }) {
  const form = useForm<ApprovalForm>({
    resolver: zodResolver(approvalSchema),
    defaultValues: { run_id: runId, approved_symbols: [] },
  });

  const approve = useApproveMutation();

  return (
    <form onSubmit={form.handleSubmit((data) => approve.mutate(data))}>
      {/* Form fields */}
    </form>
  );
}
```

---

## 5. Performance Optimization

### 5.1 The Performance Budget

The Frontend Specialist must treat performance as a feature, not an afterthought:

**Core Web Vitals Targets**:
- **LCP (Largest Contentful Paint)**: < 2.5s
- **FID (First Input Delay)**: < 100ms
- **CLS (Cumulative Layout Shift)**: < 0.1
- **TTFB (Time to First Byte)**: < 600ms
- **FCP (First Contentful Paint)**: < 1.8s

### 5.2 Optimization Techniques

**1. Server Components by Default**:
- Move data fetching to Server Components
- Only hydrate interactive parts with Client Components
- Reduces client-side JavaScript by 60-80%

**2. Image Optimization**:
```typescript
import Image from "next/image";

<Image
  src="/chart.png"
  alt="Stock analysis chart"
  width={800}
  height={400}
  priority={false}
  quality={85}
  placeholder="blur"
  blurDataURL="data:image/jpeg;base64,..."
/>
```

**3. Code Splitting**:
```typescript
import { lazy, Suspense } from "react";

const HeavyChart = lazy(() => import("./HeavyChart"));

<Suspense fallback={<Skeleton height={400} />}>
  <HeavyChart data={data} />
</Suspense>
```

**4. Memoization (After Profiling)**:
```typescript
import { memo, useMemo } from "react";

const StockCard = memo(function StockCard({ stock }: { stock: Stock }) {
  const trend = useMemo(
    () => calculateTrend(stock.price_history),
    [stock.price_history]
  );

  return (
    <div>
      <h3>{stock.symbol}</h3>
      <TrendChart data={trend} />
    </div>
  );
});
```

**5. Bundle Analysis**:
```bash
npm install @next/bundle-analyzer
# Add to next.config.js
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});
```

---

## 6. Styling & Design Systems

### 6.1 Tailwind CSS Architecture

The graph's Community 6 (Frontend Dependencies) reveals Tailwind CSS, class-variance-authority (CVA), and Radix UI primitives.

**Design Token Structure**:
```typescript
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#eff6ff",
          500: "#3b82f6",
          900: "#1e3a5f",
        },
        status: {
          pass: "#22c55e",
          fail: "#ef4444",
          pending: "#f59e0b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
};
```

### 6.2 Component Variants with CVA

```typescript
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md font-medium transition-colors",
  {
    variants: {
      variant: {
        primary: "bg-primary-500 text-white hover:bg-primary-600",
        secondary: "bg-gray-200 text-gray-900 hover:bg-gray-300",
        danger: "bg-red-500 text-white hover:bg-red-600",
        ghost: "hover:bg-gray-100",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-base",
        lg: "h-12 px-6 text-lg",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ variant, size, className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
```

### 6.3 Dark Mode

```typescript
// next-themes integration
import { ThemeProvider } from "next-themes";

export function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </ThemeProvider>
  );
}

// Usage in components
<div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
```

---

## 7. Accessibility (A11y)

### 7.1 WCAG 2.1 AA Compliance

The Frontend Specialist must ensure the interface is usable by everyone:

**Keyboard Navigation**:
- All interactive elements must be focusable
- Tab order must follow visual flow
- Focus indicators must be visible

**Screen Reader Support**:
```tsx
<button
  aria-label="Approve stock selection"
  aria-describedby="approval-context"
  aria-busy={isSubmitting}
>
  <CheckIcon aria-hidden="true" />
  Approve
</button>
<p id="approval-context">
  Approving will queue orders for the selected stocks
</p>
```

**Color Contrast**:
- Normal text: 4.5:1 minimum
- Large text: 3:1 minimum
- UI components: 3:1 minimum

### 7.2 Focus Management

```typescript
import { useRef, useEffect } from "react";

export function ApprovalModal({ isOpen, onClose }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement as HTMLElement;
      modalRef.current?.focus();
    } else {
      previousFocus.current?.focus();
    }
  }, [isOpen]);

  // Trap focus within modal
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
    // Focus trap logic...
  };

  return (
    <div
      ref={modalRef}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      onKeyDown={handleKeyDown}
    >
      {/* Modal content */}
    </div>
  );
}
```

---

## 8. Testing

### 8.1 Testing Pyramid

- **Unit tests** (Vitest + React Testing Library): Component rendering, user interactions
- **Integration tests**: Component composition, data flow
- **E2E tests** (Playwright): Critical user journeys

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentStepCard } from "./AgentStepCard";

describe("AgentStepCard", () => {
  it("renders completed status correctly", () => {
    render(
      <AgentStepCard
        step={{
          name: "Research",
          status: "completed",
          duration: 1200,
          output: "Analysis complete",
        }}
      />
    );

    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(screen.getByText("1.2s")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("data-status", "completed");
  });

  it("calls onExpand when clicked", () => {
    const onExpand = vi.fn();
    render(<AgentStepCard step={mockStep} onExpand={onExpand} />);

    fireEvent.click(screen.getByRole("button"));
    expect(onExpand).toHaveBeenCalledWith(mockStep);
  });
});
```

---

## 9. Cross-Community Integration

The Frontend Specialist connects to multiple graph communities:

- **→ API Endpoints & Routing (Community 4)**: The frontend consumes FastAPI endpoints (`/analyze`, `/approve`, `/watchlist`). `StockDetailsResponse` (18 edges) is shared — the same Pydantic model drives both backend serialization and frontend TypeScript types.
- **→ Agent Execution Engine (Community 9)**: The frontend renders real-time agent progress via streaming APIs. `StageStatus` and `AgentStepCard` visualize the execution pipeline.
- **→ UI Components & Design (Community 10)**: Shared component library with `aliases` for clean imports (`@/components`, `@/hooks`, `@/lib`).
- **→ Knowledge Graph Systems (Community 12)**: The frontend may visualize graph data — community clusters, node relationships, and execution paths.

---

## 10. Exam Preparation Checklist

- [ ] Can you explain Server vs. Client Components with examples?
- [ ] Can you write a strictly typed React component with generics?
- [ ] Can you implement TanStack Query for server state?
- [ ] Can you optimize images and implement code splitting?
- [ ] Can you write an accessible modal with focus trapping?
- [ ] Can you create a Tailwind component with CVA variants?
- [ ] Can you consume a streaming API in React?
- [ ] Can you write a test for user interaction with React Testing Library?

---

## 11. Key Takeaways

1. **TypeScript is the foundation**: `compilerOptions` (16 edges) is a god node — strict typing prevents entire classes of runtime errors.
2. **Server Components are the default**: Move data fetching and static rendering to the server; minimize client JavaScript.
3. **State management follows a hierarchy**: Server state → URL state → global state → local state. Don't reach for Redux.
4. **Performance is measured, not assumed**: Profile with React DevTools and @next/bundle-analyzer before optimizing.
5. **Accessibility is not optional**: If it's not accessible, it's broken. WCAG 2.1 AA is the minimum standard.

---

*This persona explanation is derived from graph analysis of the AlphaDesk codebase (541 nodes, 1044 edges, 40 communities) and enriched with production frontend engineering best practices for exam preparation.*
