"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Filter,
  MessageSquare,
  BookOpen,
  Package,
  Kanban,
  Server,
  Play,
  Menu,
  Mic,
} from "lucide-react";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/funnel", label: "Funnel", icon: Filter },
  { href: "/conversations", label: "Conversations", icon: MessageSquare },
  { href: "/kb", label: "Knowledge Base", icon: BookOpen },
  { href: "/products", label: "Products", icon: Package },
  { href: "/pipeline", label: "Sales Pipeline", icon: Kanban },
  { href: "/services", label: "Services", icon: Server },
  { href: "/pipeline-control", label: "Run Pipeline", icon: Play },
  { href: "/voice-settings", label: "Voice Settings", icon: Mic },
];

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-5">
        <h1 className="text-lg font-bold text-orange-500">1ai-reach</h1>
        <p className="text-xs text-neutral-500 mt-0.5">Outreach Automation</p>
      </div>
      <Separator />
      <nav className="flex-1 px-2 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                active
                  ? "bg-orange-500/10 text-orange-500"
                  : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <Separator />
      <div className="px-4 py-3">
        <p className="text-xs text-neutral-600">v2.0.0 — Next.js</p>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden md:flex md:w-56 md:flex-col md:fixed md:inset-y-0 bg-neutral-950 border-r border-neutral-800">
      <NavContent />
    </aside>
  );
}

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Use setTimeout to avoid synchronous setState in effect
    const timer = setTimeout(() => setMounted(true), 0);
    return () => clearTimeout(timer);
  }, []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="md:hidden" disabled>
        <Menu className="h-5 w-5" />
      </Button>
    );
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden"><Menu className="h-5 w-5" /></Button>} />
      <SheetContent side="left" className="p-0 w-56 bg-neutral-950 border-neutral-800">
        <NavContent onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}

export function TopBar() {
  return (
    <header className="sticky top-0 z-40 flex items-center h-14 px-4 border-b border-neutral-800 bg-neutral-950/80 backdrop-blur-sm md:hidden">
      <MobileNav />
      <span className="ml-3 text-sm font-bold text-orange-500">1ai-reach</span>
    </header>
  );
}
