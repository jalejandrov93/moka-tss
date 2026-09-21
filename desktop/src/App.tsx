import React, { useState } from "react";
import {
  HashRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useLocation,
} from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Dashboard } from "@/components/Dashboard";
import { getStatusInfo } from "@/main";
import { cn } from "@/lib/utils";

interface NavItem {
  name: string;
  path: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  {
    name: "Panel",
    path: "/",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <rect width="7" height="9" x="3" y="3" rx="1" />
        <rect width="7" height="5" x="14" y="3" rx="1" />
        <rect width="7" height="9" x="14" y="12" rx="1" />
        <rect width="7" height="5" x="3" y="16" rx="1" />
      </svg>
    ),
  },
  {
    name: "Pantalla",
    path: "/pantalla",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <rect width="20" height="14" x="2" y="3" rx="2" />
        <line x1="8" x2="16" y1="21" y2="21" />
        <line x1="12" x2="12" y1="17" y2="21" />
      </svg>
    ),
  },
  {
    name: "Mascota",
    path: "/mascota",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M8 14s1.5 2 4 2 4-2 4-2" />
        <line x1="9" x2="9.01" y1="9" y2="9" />
        <line x1="15" x2="15.01" y1="9" y2="9" />
      </svg>
    ),
  },
  {
    name: "Reglas",
    path: "/reglas",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <line x1="4" x2="20" y1="6" y2="6" />
        <circle cx="8" cy="6" r="2" />
        <line x1="4" x2="20" y1="12" y2="12" />
        <circle cx="16" cy="12" r="2" />
        <line x1="4" x2="20" y1="18" y2="18" />
        <circle cx="10" cy="18" r="2" />
      </svg>
    ),
  },
  {
    name: "Servicios",
    path: "/servicios",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <rect width="20" height="8" x="2" y="2" rx="2" />
        <rect width="20" height="8" x="2" y="14" rx="2" />
        <line x1="6" x2="6.01" y1="6" y2="6" />
        <line x1="6" x2="6.01" y1="18" y2="18" />
      </svg>
    ),
  },
  {
    name: "Tema",
    path: "/tema",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <circle cx="13.5" cy="6.5" r=".5" fill="currentColor" />
        <circle cx="17.5" cy="10.5" r=".5" fill="currentColor" />
        <circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />
        <circle cx="6.5" cy="12.5" r=".5" fill="currentColor" />
        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.563-2.512 5.563-5.563C22 6.5 17.5 2 12 2Z" />
      </svg>
    ),
  },
  {
    name: "Ajustes",
    path: "/ajustes",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-4 h-4 shrink-0"
      >
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
];

function UnderConstruction({ title }: { title: string }) {
  return (
    <div className="flex-1 p-6 flex flex-col items-center justify-center min-h-[50vh]">
      <Card className="w-full max-w-md bg-slate-900 border-slate-800 text-slate-50 shadow-xl">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-xl font-bold tracking-tight text-slate-100">
              {title}
            </CardTitle>
            <Badge variant="secondary">En construcción</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-slate-400">
            Esta sección está en construcción.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function AppLayout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const statusInfo = getStatusInfo();

  const currentItem = NAV_ITEMS.find((item) =>
    item.path === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(item.path)
  );
  const currentTitle = currentItem?.name ?? "Mascota";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col md:flex-row">
      {/* Mobile Top Bar */}
      <header className="flex md:hidden items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800 sticky top-0 z-30">
        <div className="flex items-center gap-2.5">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="text-slate-300 hover:text-slate-100 hover:bg-slate-800 h-8 w-8"
            aria-label="Abrir menú"
          >
            {mobileOpen ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="w-5 h-5"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="w-5 h-5"
              >
                <line x1="4" x2="20" y1="12" y2="12" />
                <line x1="4" x2="20" y1="6" y2="6" />
                <line x1="4" x2="20" y1="18" y2="18" />
              </svg>
            )}
          </Button>
          <span className="font-bold text-base tracking-tight text-slate-100">
            Mascota
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusInfo.variant} className="text-xs">
            {statusInfo.text}
          </Badge>
        </div>
      </header>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile Drawer */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800 flex flex-col transition-transform duration-200 ease-in-out md:hidden shadow-2xl",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <span className="font-bold text-lg tracking-tight text-slate-100">
              Mascota
            </span>
            <Badge variant="outline" className="text-[10px] text-slate-400 border-slate-700">
              TSS
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(false)}
            className="text-slate-400 hover:text-slate-100 h-8 w-8"
            aria-label="Cerrar menú"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-5 h-5"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </Button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.path);
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMobileOpen(false)}
                className="block"
              >
                <Button
                  variant={isActive ? "secondary" : "ghost"}
                  className={cn(
                    "w-full justify-start gap-3 px-3 py-2 text-sm",
                    isActive
                      ? "bg-slate-800 text-slate-50 font-semibold shadow-sm"
                      : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"
                  )}
                >
                  {item.icon}
                  <span>{item.name}</span>
                </Button>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-800 text-xs text-slate-400 font-mono flex items-center justify-between">
          <span className="text-slate-500">Puerto {statusInfo.serverPort}</span>
          <Badge variant={statusInfo.variant} className="text-[10px]">
            {statusInfo.text}
          </Badge>
        </div>
      </aside>

      {/* Desktop Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col bg-slate-900 border-r border-slate-800 shrink-0 sticky top-0 h-screen z-20">
        <div className="flex items-center gap-2.5 px-6 py-5 border-b border-slate-800">
          <span className="font-bold text-xl tracking-tight text-slate-100">
            Mascota
          </span>
          <Badge variant="outline" className="text-[10px] text-slate-400 border-slate-700">
            TSS
          </Badge>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.path);
            return (
              <NavLink key={item.path} to={item.path} className="block">
                <Button
                  variant={isActive ? "secondary" : "ghost"}
                  className={cn(
                    "w-full justify-start gap-3 px-3.5 py-2.5 text-sm",
                    isActive
                      ? "bg-slate-800 text-slate-50 font-semibold shadow-sm"
                      : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"
                  )}
                >
                  {item.icon}
                  <span>{item.name}</span>
                </Button>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-800 text-xs text-slate-400 font-mono space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Servidor</span>
            <span className="text-slate-300">:{statusInfo.serverPort}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Turing</span>
            <Badge variant={statusInfo.variant} className="text-[10px] px-1.5 py-0">
              {statusInfo.text}
            </Badge>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-950">
        {/* Desktop Header */}
        <header className="hidden md:flex items-center justify-between px-8 py-4 border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold tracking-tight text-slate-100">
              {currentTitle}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {statusInfo.mood && (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400 font-mono">Mood:</span>
                <Badge variant="default" className="text-xs uppercase font-mono px-2 py-0.5">
                  {statusInfo.mood}
                </Badge>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-slate-400 font-mono">Turing:</span>
              <Badge variant={statusInfo.variant} className="text-xs px-2.5 py-0.5">
                {statusInfo.text}
              </Badge>
            </div>
          </div>
        </header>

        {/* Routes View */}
        <main className="flex-1 min-w-0 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/panel" element={<Navigate to="/" replace />} />
            <Route path="/pantalla" element={<UnderConstruction title="Pantalla" />} />
            <Route path="/mascota" element={<UnderConstruction title="Mascota" />} />
            <Route path="/reglas" element={<UnderConstruction title="Reglas" />} />
            <Route path="/servicios" element={<UnderConstruction title="Servicios" />} />
            <Route path="/tema" element={<UnderConstruction title="Tema" />} />
            <Route path="/ajustes" element={<UnderConstruction title="Ajustes" />} />
            <Route path="*" element={<UnderConstruction title="Página no encontrada" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <HashRouter>
      <AppLayout />
    </HashRouter>
  );
}

export default App;
