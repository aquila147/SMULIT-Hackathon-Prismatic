# AITHENA Frontend–Backend Integration Guide

## What this is

Complete replacement of `web/` and `app/main.py` to wire your teammate's UI design to the working FastAPI backend. The Next.js app has been converted to a **Vite + React + TypeScript SPA** that calls real API endpoints.

---

## How to deploy on your machine

```powershell
# From aithena-hack directory with venv activated

# 1. Replace app/main.py with the new version
#    (back up your existing one first)
copy app\main.py app\main.py.bak
#    Then paste/copy the new main.py over it

# 2. Replace the web/ directory
#    (back up your existing one first)
rename web web.bak
#    Then copy the new web/ folder in

# 3. Install frontend dependencies
cd web
npm install

# 4. Run in development mode (two terminals)
# Terminal 1:
uvicorn app.main:app --reload --port 8000

# Terminal 2:
cd web
npm run dev
# → opens at http://localhost:5173, proxies /api to :8000

# 5. For the demo (production build)
cd web
npm run build
# Now uvicorn serves everything from port 8000
uvicorn app.main:app --port 8000
# → opens at http://localhost:8000
```

---

## What's connected (UI → Backend)

| UI Feature | API Endpoint | Status |
|---|---|---|
| File upload (drag-drop, browse) | `POST /api/upload` | ✅ Wired — sends real `File` objects via FormData |
| Dashboard stat cards | `GET /api/stats` | ✅ Wired — counts from SQLite |
| Contract list + search/filter | `GET /api/contracts` | ✅ Wired — returns all contracts with fields |
| Contract detail page | `GET /api/contracts/{id}` | ✅ Wired — returns single contract |
| Calendar events (90-day) | `GET /api/calendar` | ✅ Wired — computed from contract dates |
| Conflicts list | `GET /api/conflicts` | ✅ Wired — from `conflicts` table |
| Legal handoff brief | `GET /api/contracts/{id}/handoff` | ✅ Wired — generates from contested/ungrounded fields |
| Scanned page images | `GET /api/pages/{id}/{page}/image` | ✅ Wired — serves PNGs from `page_images/` |
| CSV export (results) | `GET /api/export/results` | ✅ Wired — streams CSV |
| CSV export (coverage) | `GET /api/export/coverage` | ✅ Wired — streams CSV |
| View original PDF | `GET /api/contracts/{id}/pdf` | ✅ Wired — serves uploaded file |
| Source viewer (verbatim quote) | Via contract field data | ✅ Shows `verbatim_quote` from backend |
| Confidence badges | Mapped from backend tiers | ✅ VERIFIED→high, INFERRED→medium, CONTESTED/UNGROUNDED→low |
| Coverage bar (clauses covered) | `clauses_total` / `clauses_covered` | ✅ Shown on contract cards and detail page |

---

## What's NOT connected (and why)

| UI Feature | Reason | Workaround |
|---|---|---|
| Question prompt ("What would you like to know?") | Backend `query.py` (text-to-SQL) is a stretch goal, not implemented | Prompt text is captured but not sent to backend; the upload still works. Add `POST /api/query` later if time permits |
| Suggestion chips ("What contracts renew...") | Same — requires text-to-SQL | Chips populate the prompt field for UX feel; no backend call |
| "Download Report" button on dashboard | No PDF report generator exists | Wired to CSV export instead. Could add `weasyprint` later |
| "Download Analysis" on contract detail | Same | Not wired. Could generate a per-contract CSV |
| Account button (top-right) | No auth system | Decorative only — acceptable for hackathon |
| Dark mode | UI only has light theme defined | Not needed for hackathon |

---

## Data type mapping (Backend → UI)

```
Backend Confidence    →  UI Confidence
─────────────────────────────────────
VERIFIED              →  high     (green badge)
INFERRED              →  medium   (yellow badge, "legal review recommended")
CONTESTED             →  low      (red badge, "legal review recommended")
UNGROUNDED            →  low      (red badge, "Not identified", notFound=true)
```

The mapping logic is in `web/src/lib/api.ts` → `mapConfidence()` and `mapField()`. Contract-level `status` and `confidence` are derived from the field distribution.

---

## Key architectural notes

1. **Branding changed**: "PRISMATIC" → "AITHENA" throughout (header, help page, loading states, meta tags)

2. **react-router-dom replaces Next.js routing**: All `next/link` → `react-router-dom Link`, all `useRouter()` → `useNavigate()`, all `usePathname()` → `useLocation().pathname`

3. **No @base-ui/react dependency**: The Button component was simplified to a plain `<button>` with the same CVA variants — saves a dependency

4. **Tailwind v4**: The UI uses Tailwind v4 with CSS-based theming (`@import 'tailwindcss'`, `@theme inline`). This replaces the old Tailwind v3 `tailwind.config.js` setup. The `@tailwindcss/vite` plugin handles compilation

5. **SPA serving in production**: `app/main.py` mounts `web/dist/` as static files and falls back to `index.html` for client-side routing. One process, one port, no CORS

6. **Fallback logic in main.py**: Every endpoint has a fallback path if Person B's modules aren't fully working — the calendar generates from dates, handoff generates from field confidence, exports generate inline CSVs. Nothing crashes if a module is still stubbed

---

## Files to copy

```
FROM this integration package     →  TO your project
──────────────────────────────────────────────────────
app/main.py                       →  app/main.py (REPLACE)
web/                              →  web/ (REPLACE entire directory)
  ├── package.json
  ├── vite.config.ts
  ├── tsconfig.json
  ├── index.html
  ├── postcss.config.mjs
  └── src/
      ├── main.tsx
      ├── App.tsx
      ├── globals.css
      ├── lib/
      │   ├── api.ts              ← all backend calls + type mapping
      │   ├── types.ts            ← backend + UI type definitions
      │   └── utils.ts
      ├── components/
      │   ├── ui/button.tsx
      │   ├── ui/card.tsx
      │   ├── site-header.tsx
      │   ├── confidence-badge.tsx
      │   ├── contract-library.tsx
      │   ├── contract/
      │   │   ├── contract-detail.tsx
      │   │   ├── analysis-quality.tsx
      │   │   ├── field-card.tsx
      │   │   ├── source-viewer.tsx
      │   │   └── legal-handoff.tsx
      │   ├── report/
      │   │   ├── stat-cards.tsx
      │   │   ├── attention-section.tsx
      │   │   ├── events-timeline.tsx
      │   │   └── conflicts-section.tsx
      │   └── upload-ask/
      │       └── upload-ask-panel.tsx
      └── pages/
          ├── HomePage.tsx
          ├── ReportPage.tsx
          ├── ContractsPage.tsx
          ├── ContractDetailPage.tsx
          ├── CalendarPage.tsx
          ├── RisksPage.tsx
          └── HelpPage.tsx
```
