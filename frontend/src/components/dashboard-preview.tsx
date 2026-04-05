"use client";

import {
  Search,
  Bell,
  ChevronDown,
  Inbox,
  Calendar,
  Users,
  CheckCircle2,
  Clock,
  Shield,
  MessageSquare,
  BarChart3,
  Settings,
  Mail,
  ArrowRight,
  Sparkles,
} from "lucide-react";

/* ─── Sidebar Item ─── */
function SidebarItem({
  icon: Icon,
  label,
  active,
  badge,
}: {
  icon: React.ElementType;
  label: string;
  active?: boolean;
  badge?: string;
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] ${
        active
          ? "bg-secondary font-medium text-foreground"
          : "text-muted-foreground"
      }`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="flex-1">{label}</span>
      {badge && (
        <span className="rounded-full bg-accent px-1.5 py-0.5 text-[9px] font-medium text-accent-foreground">
          {badge}
        </span>
      )}
    </div>
  );
}

/* ─── Coordination Thread Row ─── */
function ThreadRow({
  participants,
  subject,
  status,
  time,
}: {
  participants: string;
  subject: string;
  status: "Active" | "Awaiting Reply" | "Confirmed";
  time: string;
}) {
  const statusColors = {
    Active: "bg-blue-50 text-blue-600",
    "Awaiting Reply": "bg-amber-50 text-amber-600",
    Confirmed: "bg-emerald-50 text-emerald-600",
  };
  return (
    <div className="flex items-center py-2.5 text-[10px] border-b border-border/50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="font-medium text-foreground truncate">{subject}</div>
        <div className="text-muted-foreground mt-0.5">{participants}</div>
      </div>
      <span className="text-muted-foreground text-[9px] mr-3">{time}</span>
      <span
        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-medium whitespace-nowrap ${statusColors[status]}`}
      >
        {status}
      </span>
    </div>
  );
}

/* ─── Main Dashboard ─── */
export function DashboardPreview() {
  return (
    <div className="w-full select-none pointer-events-none overflow-hidden rounded-xl border border-border bg-background text-[11px]">
      {/* ─── Top Bar ─── */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-foreground text-[10px] font-bold text-background">
            M
          </div>
          <span className="text-xs font-semibold text-foreground">
            MailMind
          </span>
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        </div>

        <div className="hidden md:flex items-center gap-1.5 rounded-lg border border-border bg-secondary/50 px-3 py-1.5">
          <Search className="h-3 w-3 text-muted-foreground" />
          <span className="text-[10px] text-muted-foreground">
            Search threads...
          </span>
          <span className="ml-6 rounded border border-border bg-background px-1 py-0.5 text-[9px] text-muted-foreground">
            ⌘K
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-1 text-[10px] font-medium text-accent">
            <Sparkles className="h-3 w-3" />
            <span>New Coordination</span>
          </div>
          <Bell className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[9px] font-bold text-accent-foreground">
            DG
          </div>
        </div>
      </div>

      {/* ─── Body ─── */}
      <div className="flex">
        {/* ─── Sidebar ─── */}
        <div className="hidden md:flex w-40 shrink-0 flex-col gap-0.5 border-r border-border p-3">
          <SidebarItem icon={MessageSquare} label="Chat" active />
          <SidebarItem icon={Inbox} label="Coordination Inbox" badge="3" />
          <SidebarItem icon={Shield} label="Approval Queue" badge="2" />
          <SidebarItem icon={Calendar} label="Calendar" />
          <SidebarItem icon={Users} label="Participants" />
          <SidebarItem icon={BarChart3} label="Analytics" />

          <div className="mt-4 mb-1 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
            Active Sessions
          </div>
          <SidebarItem icon={Mail} label="Design Review" />
          <SidebarItem icon={Mail} label="Sprint Planning" />
          <SidebarItem icon={Settings} label="Settings" />
        </div>

        {/* ─── Main Content ─── */}
        <div className="flex-1 bg-secondary/30 p-4">
          {/* Chat Header */}
          <div className="mb-4">
            <span className="text-sm font-semibold text-foreground">
              Good morning, Dishant
            </span>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              3 coordinations active · 2 awaiting approval
            </p>
          </div>

          {/* Two cards side by side */}
          <div className="mb-4 flex gap-3">
            {/* Active Coordinations Card */}
            <div className="flex-1 basis-0 rounded-xl border border-border bg-background p-4">
              <div className="mb-1 flex items-center gap-1.5">
                <span className="text-xs font-medium text-foreground">
                  Active Coordinations
                </span>
                <CheckCircle2 className="h-3 w-3 text-accent" />
              </div>

              <div className="mb-3">
                <span className="text-2xl font-semibold tracking-tight text-foreground">
                  12
                </span>
                <span className="text-xs text-muted-foreground ml-1">
                  this week
                </span>
              </div>

              <div className="mb-3 flex items-center gap-4 text-[10px]">
                <span className="text-muted-foreground">Success Rate</span>
                <span className="font-medium text-emerald-600">94%</span>
                <span className="text-muted-foreground">Avg. Time</span>
                <span className="font-medium text-foreground">4.2 hrs</span>
              </div>

              {/* SVG Area Chart */}
              <svg
                viewBox="0 0 300 80"
                className="h-20 w-full"
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient
                    id="chartGrad"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor="hsl(239 84% 67%)"
                      stopOpacity="0.15"
                    />
                    <stop
                      offset="100%"
                      stopColor="hsl(239 84% 67%)"
                      stopOpacity="0"
                    />
                  </linearGradient>
                </defs>
                <path
                  d="M0,60 C30,55 50,45 80,40 C110,35 130,50 160,35 C190,20 210,25 240,15 C260,10 280,18 300,12 L300,80 L0,80 Z"
                  fill="url(#chartGrad)"
                />
                <path
                  d="M0,60 C30,55 50,45 80,40 C110,35 130,50 160,35 C190,20 210,25 240,15 C260,10 280,18 300,12"
                  fill="none"
                  stroke="hsl(239 84% 67%)"
                  strokeWidth="1.5"
                />
              </svg>
            </div>

            {/* Recent Threads Card */}
            <div className="hidden lg:block flex-1 basis-0 rounded-xl border border-border bg-background p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-foreground">
                  Coordination Threads
                </span>
                <span className="text-[9px] text-accent font-medium">
                  View all
                </span>
              </div>

              <ThreadRow
                subject="Q2 Strategy Review"
                participants="Ravi, Chen, Sarah"
                status="Active"
                time="2m ago"
              />
              <ThreadRow
                subject="Client Onboarding Sync"
                participants="Marco, Lisa"
                status="Awaiting Reply"
                time="1h ago"
              />
              <ThreadRow
                subject="Sprint Retro #24"
                participants="Team (6)"
                status="Confirmed"
                time="3h ago"
              />
            </div>
          </div>

          {/* Approval Queue Preview */}
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-foreground">
                  Pending Approvals
                </span>
                <span className="rounded-full bg-amber-50 text-amber-600 px-1.5 py-0.5 text-[9px] font-medium">
                  2 pending
                </span>
              </div>
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-3 rounded-lg border border-border p-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10">
                  <Mail className="h-3.5 w-3.5 text-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-medium text-foreground">
                    Availability Request → Ravi Patel
                  </div>
                  <div className="text-[9px] text-muted-foreground">
                    &quot;Hi Ravi, I&apos;d like to schedule a design review this week...&quot;
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="rounded-md bg-emerald-500 px-2 py-1 text-[9px] font-medium text-white">
                    Approve
                  </span>
                  <span className="rounded-md border border-border px-2 py-1 text-[9px] font-medium text-foreground">
                    Edit
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border p-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10">
                  <CheckCircle2 className="h-3.5 w-3.5 text-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-medium text-foreground">
                    Confirmation Email → All Participants
                  </div>
                  <div className="text-[9px] text-muted-foreground">
                    &quot;Meeting confirmed: Thursday 2:00 PM — 3:00 PM IST&quot;
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="rounded-md bg-emerald-500 px-2 py-1 text-[9px] font-medium text-white">
                    Approve
                  </span>
                  <span className="rounded-md border border-border px-2 py-1 text-[9px] font-medium text-foreground">
                    Edit
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
